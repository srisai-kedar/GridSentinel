"""
Regression tests for the NBD data-leakage fix.

Invariant under test
--------------------
Every NBD feature is a function of what was OBSERVED on the wire (function
codes, addresses, TCP connects) plus the master's own poll latency/success.
No scenario label, attack type, ground truth, caller-declared flag or free-text
source name may influence a model input.
"""

from __future__ import annotations

import ast
import asyncio
import inspect
import socket
from pathlib import Path
from typing import Any, Dict, List

import joblib
import pandas as pd
import pytest

from app.ml import feature_engineering as fe
from app.ml.classifier_service import ClassifierService
from app.ml.dataset_generator import split_sensor_ticks
from app.ml.feature_engineering import (
    EXTRACTED_FEATURE_KEYS,
    FEATURE_SCHEMA,
    NBD_WINDOW_TICKS,
    extract_features,
)
from app.ot import nbd_policy
from app.ot.rtu_server import RTUPool, SimulatedRTU, RTU_CONFIGS, rtu_pool
from app.ot.scada_master import scada_master
from app.ot.scenario_injector import scenario_injector
from app.ot.traffic_logger import ModbusTrafficLogger, traffic_logger

@pytest.fixture(autouse=True)
def _isolated_traffic_log():
    """ModbusTrafficLogger is a process-wide singleton: start/end each test clean."""
    traffic_logger.clear()
    yield
    traffic_logger.clear()


APP_DIR = Path(__file__).resolve().parents[1] / "app"
NBD_FEATURES = [f for f in FEATURE_SCHEMA if f.startswith("nbd_")]


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _se_ok() -> Dict[str, Any]:
    return {
        "success": True, "chi2_test_passed": True, "chi2_statistic": 4.0,
        "chi2_threshold": 15.5, "flagged_measurements": [], "bad_data_detected": False,
        "normalized_residuals": {},
    }


def _telemetry() -> Dict[int, Dict[str, Any]]:
    return {i: {"voltage_pu": 1.0, "p_mw": 0.2, "q_mvar": 0.1, "status_flag": 1} for i in range(1, 6)}


def _nbd(events: List[Dict[str, Any]], rtu_id: int = 1) -> Dict[str, float]:
    feats = extract_features(
        target_rtu_id=rtu_id,
        traffic_events=events,
        state_estimation_result=_se_ok(),
        polled_telemetry=_telemetry(),
    )
    return {k: feats[k] for k in NBD_FEATURES}


def _wire(fc: int, **extra: Any) -> Dict[str, Any]:
    ev = {
        "event_id": 1, "timestamp": "t", "source": "RTU_TAP", "target_rtu": "RTU-1 (Port 5021)",
        "function_code": fc, "function_name": "x", "response_time_ms": 0.0,
        "is_unexpected_write": False, "success": True, "details": "",
        "observer": "rtu_tap", "rtu_id": 1, "address": 0,
    }
    ev.update(extra)
    return ev


# ---------------------------------------------------------------------------
# 1. The flag cannot be declared by the traffic's author
# ---------------------------------------------------------------------------
def test_logger_has_no_caller_declared_flag():
    assert "is_unexpected_write" not in inspect.signature(ModbusTrafficLogger.log_transaction).parameters
    with pytest.raises(TypeError):
        ModbusTrafficLogger().log_transaction(  # type: ignore[call-arg]
            source="X", target_rtu="RTU-1", function_code=3, response_time_ms=1.0,
            is_unexpected_write=True,
        )


@pytest.mark.parametrize("fc,expected", [(1, False), (2, False), (3, False), (4, False),
                                          (5, True), (6, True), (15, True), (16, True),
                                          (21, True), (22, True), (23, True)])
def test_policy_depends_only_on_function_code(fc, expected):
    assert nbd_policy.is_unexpected_write(fc) is expected


def test_policy_allow_list_hook(monkeypatch):
    monkeypatch.setattr(nbd_policy, "AUTHORIZED_WRITES", {(6, 7)})
    assert nbd_policy.is_unexpected_write(6, 7) is False
    assert nbd_policy.is_unexpected_write(6, 0) is True


def test_logger_derives_flag_from_function_code_not_names():
    lg = traffic_logger
    read = lg.log_transaction("ATTACKER_COMMAND_INJECTION", "RTU-1", 3, 1.0, details="UNAUTHORIZED WRITE")
    write = lg.log_transaction("SCADA_MASTER", "RTU-1", 6, 1.0, details="routine poll")
    assert read["is_unexpected_write"] is False   # an attacker-named FC03 is not a write
    assert write["is_unexpected_write"] is True   # a master-named FC06 still is


# ---------------------------------------------------------------------------
# 2. Features ignore declared flags, source strings and scenario metadata
# ---------------------------------------------------------------------------
def test_features_ignore_declared_flag():
    reads_flagged = [_wire(3, event_id=i, is_unexpected_write=True) for i in range(6)]
    writes_unflagged = [_wire(6, event_id=10 + i, is_unexpected_write=False) for i in range(2)]
    assert _nbd(reads_flagged)["nbd_unexpected_write_count"] == 0.0
    assert _nbd(writes_unflagged)["nbd_unexpected_write_count"] == 2.0


def test_features_ignore_source_string():
    base = [_wire(3, event_id=i) for i in range(5)] + [_wire(6, event_id=9)]
    a = _nbd([dict(e, source="SCADA_MASTER") for e in base])
    b = _nbd([dict(e, source="ATTACKER_COMMAND_INJECTION") for e in base])
    c = _nbd([dict(e, source="10.9.8.7") for e in base])
    assert a == b == c


def test_features_ignore_scenario_metadata():
    base = [_wire(3, event_id=i) for i in range(5)] + [_wire(6, event_id=9)]
    tagged = [dict(e, scenario="command_injection", attack_type="COMMAND_INJECTION",
                   ground_truth="Cyber Intrusion", top_level_label="Cyber Intrusion") for e in base]
    assert _nbd(base) == _nbd(tagged)


def test_extract_features_accepts_no_label_parameters():
    params = set(inspect.signature(extract_features).parameters)
    forbidden = {"scenario", "scenario_type", "label", "labels", "attack", "attack_type",
                 "ground_truth", "truth", "active_scenarios", "is_attack"}
    assert not (params & forbidden), params & forbidden


def test_connection_count_comes_only_from_observed_connections():
    conn = lambda i: {**_wire(0, event_id=i), "observer": "rtu_tap_conn", "function_name": "TCP_CONNECT"}
    only_pdus = [_wire(3, event_id=i) for i in range(6)]
    assert _nbd(only_pdus)["nbd_connection_count"] == 0.0
    with_conns = only_pdus + [conn(100 + i) for i in range(7)]
    assert _nbd(with_conns)["nbd_connection_count"] == 7.0
    # other RTUs' connections are not counted
    other = dict(conn(200), rtu_id=2, target_rtu="RTU-2 (Port 5022)")
    assert _nbd(with_conns + [other])["nbd_connection_count"] == 7.0


# ---------------------------------------------------------------------------
# 3. Static guards (cannot regress without a failing test)
# ---------------------------------------------------------------------------
def test_no_module_passes_a_declared_flag_into_the_logger():
    offenders = []
    for path in APP_DIR.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                for kw in node.keywords:
                    if kw.arg == "is_unexpected_write":
                        offenders.append(f"{path.relative_to(APP_DIR)}:{node.lineno}")
    # only the logger's own construction of the stored event may set the key
    assert all(o.startswith("ot/traffic_logger.py") or o.startswith("ot\\traffic_logger.py") for o in offenders), offenders


def test_feature_extractor_never_reads_declared_fields():
    src = inspect.getsource(fe.extract_features)
    # reads of the declared flag / source label would reintroduce the leak
    assert '"is_unexpected_write"' not in src.replace("nbd_policy.is_unexpected_write", "")
    assert 'get("source"' not in src and "['source']" not in src and '["source"]' not in src


def test_injector_does_not_write_to_traffic_log_directly():
    src = inspect.getsource(scenario_injector.inject_command_write)
    assert "log_transaction" not in src and "log_tap" not in src


def test_all_feature_windows_use_the_shared_window_constant():
    """Generator, live loop and API must use the SAME accessor and constant."""
    for rel in ("ml/dataset_generator.py", "ot/simulation_loop.py", "main.py"):
        text = (APP_DIR / rel).read_text(encoding="utf-8")
        assert "get_window_events(NBD_WINDOW_TICKS)" in text, rel
        assert "get_recent_events(limit=30)" not in text and "get_recent_events(limit=200)" not in text, rel


def test_window_matches_training_semantics():
    # committed v2.0.0 data: 30-event window / 5 RTUs = 6 polls per RTU = 6 ticks
    assert NBD_WINDOW_TICKS == 6


# ---------------------------------------------------------------------------
# 4. Tick window semantics (pure logger, no network)
# ---------------------------------------------------------------------------
def test_window_covers_exactly_n_ticks_and_ages_out():
    lg = traffic_logger
    # a write logged BETWEEN ticks belongs to the upcoming tick
    lg.log_transaction("x", "RTU-1", 6, 0.0, observer="rtu_tap", rtu_id=1)
    for t in range(1, 12):
        lg.begin_tick()
        lg.log_transaction("m", "RTU-1", 3, 1.0, observer="scada_master", rtu_id=1)
        window = lg.get_window_events(NBD_WINDOW_TICKS)
        writes_visible = [e for e in window if e["function_code"] == 6]
        polls_visible = [e for e in window if e["function_code"] == 3]
        assert len(polls_visible) == min(t, NBD_WINDOW_TICKS)
        # the write is visible for exactly NBD_WINDOW_TICKS evaluated ticks (1..6)
        assert bool(writes_visible) == (t <= NBD_WINDOW_TICKS), t
        lg.end_tick()


def test_clear_resets_tick_clock():
    lg = traffic_logger
    lg.begin_tick(); lg.end_tick(); lg.clear()
    assert lg.current_tick == 0


# ---------------------------------------------------------------------------
# 5. Model-schema guard and 3-class data handling
# ---------------------------------------------------------------------------
def _bundle_with_version(tmp_path, version: str) -> str:
    shipped = Path(__file__).resolve().parents[1] / "models" / "fusion_classifier.joblib"
    bundle = joblib.load(shipped)
    bundle["feature_schema_version"] = version
    out = tmp_path / f"bundle_{version}.joblib"
    joblib.dump(bundle, out)
    return str(out)


def test_schema_guard_refuses_legacy_model_by_default(tmp_path, monkeypatch):
    monkeypatch.delenv("GRIDSENTINEL_ALLOW_LEGACY_SCHEMA", raising=False)
    svc = ClassifierService(model_path=_bundle_with_version(tmp_path, "2.0.0"))
    assert svc.load_model() is False and svc.is_loaded is False


def test_schema_guard_legacy_opt_in_is_explicit(tmp_path, monkeypatch):
    monkeypatch.setenv("GRIDSENTINEL_ALLOW_LEGACY_SCHEMA", "1")
    svc = ClassifierService(model_path=_bundle_with_version(tmp_path, "2.0.0"))
    assert svc.load_model() is True and svc.schema_compat == "legacy"


def test_schema_guard_accepts_matching_major(tmp_path, monkeypatch):
    monkeypatch.delenv("GRIDSENTINEL_ALLOW_LEGACY_SCHEMA", raising=False)
    svc = ClassifierService(model_path=_bundle_with_version(tmp_path, fe.FEATURE_SCHEMA_VERSION))
    assert svc.load_model() is True and svc.schema_compat == "exact"


def test_model_schema_is_28_unique_features_and_extractor_covers_it():
    assert len(FEATURE_SCHEMA) == 28 and len(set(FEATURE_SCHEMA)) == 28
    assert "nbd_distinct_sources_count" not in FEATURE_SCHEMA and "nbd_connection_count" in FEATURE_SCHEMA
    feats = extract_features(target_rtu_id=1, traffic_events=[], state_estimation_result=_se_ok(), polled_telemetry=_telemetry())
    assert set(feats) == set(EXTRACTED_FEATURE_KEYS)


def test_split_sensor_ticks_moves_whole_ticks():
    rows = []
    for tick in range(1, 5):
        for rtu in range(1, 6):
            label = "Sensor Malfunction" if (tick == 2 and rtu == 3) else "Normal"
            rows.append({"tick": tick, "rtu_id": rtu, "top_level_label": label, "x": 0})
    primary, sensor = split_sensor_ticks(pd.DataFrame(rows))
    assert set(sensor["tick"]) == {2} and len(sensor) == 5
    assert 2 not in set(primary["tick"]) and "Sensor Malfunction" not in set(primary["top_level_label"])


def test_trainer_rejects_non_three_class_csv(tmp_path):
    from app.ml.train_classifier import load_dataset
    row = {k: 0.0 for k in FEATURE_SCHEMA}
    df = pd.DataFrame([dict(row, top_level_label="Sensor Malfunction", subtype_label="sensor_drift")])
    p = tmp_path / "d.csv"; df.to_csv(p, index=False)
    with pytest.raises(ValueError, match="3-class"):
        load_dataset(str(p))


# ---------------------------------------------------------------------------
# 6. Integration: real Modbus servers, real wire observations
# ---------------------------------------------------------------------------
async def _poll_tick() -> None:
    """One simulated tick: begin -> master polls -> end (as sim_loop.tick does)."""
    traffic_logger.begin_tick()
    try:
        await scada_master.poll_all_rtus()
    finally:
        traffic_logger.end_tick()


def _features_for(rtu_id: int) -> Dict[str, float]:
    events = traffic_logger.get_window_events(NBD_WINDOW_TICKS)
    return _nbd(events, rtu_id)


@pytest.mark.asyncio
async def test_rtu_start_is_deterministic_no_sleep():
    """Servers must accept connections the instant start_all() returns."""
    for _ in range(3):
        await rtu_pool.start_all()
        try:
            for cfg in RTU_CONFIGS:
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection("127.0.0.1", cfg["port"]), timeout=1.0
                )
                writer.close()
                await writer.wait_closed()
        finally:
            await rtu_pool.stop_all()


@pytest.mark.asyncio
async def test_rtu_bind_failure_propagates_and_pool_rolls_back():
    port = RTU_CONFIGS[2]["port"]
    blocker = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    blocker.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 0)
    blocker.bind(("127.0.0.1", port)); blocker.listen(1)
    pool = RTUPool()
    try:
        with pytest.raises(Exception):
            await pool.start_all()
        # all-or-nothing: no RTU is left running after a failed start
        assert not any(r.is_running for r in pool.rtus.values())
    finally:
        blocker.close()
        await pool.stop_all()


@pytest.mark.asyncio
async def test_normal_polling_has_no_writes_and_one_connection_per_poll():
    traffic_logger.clear()
    await rtu_pool.start_all()
    try:
        for _ in range(3):
            await _poll_tick()
        for rtu_id in range(1, 6):
            f = _features_for(rtu_id)
            assert f["nbd_unexpected_write_count"] == 0.0
            assert f["nbd_fc6_write_count"] == 0.0 and f["nbd_fc16_write_count"] == 0.0
            assert f["nbd_fc3_read_count"] == 3.0 == f["nbd_traffic_volume"]
            assert f["nbd_connection_count"] == 3.0  # 1 TCP connect per poll, no probe noise
    finally:
        await rtu_pool.stop_all()


@pytest.mark.asyncio
async def test_injected_write_is_counted_from_the_wire_only():
    traffic_logger.clear()
    await rtu_pool.start_all()
    try:
        await _poll_tick()
        res = await scenario_injector.inject_command_write(rtu_id=3, register_address=0, value=12000)
        assert res["status"] == "success" and res["flagged_in_traffic_log"] is True
        await _poll_tick()

        target = _features_for(3)
        assert target["nbd_unexpected_write_count"] == 1.0
        assert target["nbd_fc6_write_count"] == 1.0
        assert target["nbd_connection_count"] == 3.0       # 2 polls + 1 attacker connection
        assert target["nbd_traffic_volume"] == 3.0
        for other in (1, 2, 4, 5):
            assert _features_for(other)["nbd_unexpected_write_count"] == 0.0
    finally:
        await rtu_pool.stop_all()


@pytest.mark.asyncio
async def test_attacker_adds_nothing_to_the_log_by_itself(monkeypatch):
    """Spy on every log call: only the RTU tap may record the attacker's write."""
    traffic_logger.clear()
    calls: List[str] = []
    real = traffic_logger.log_transaction

    def spy(*args, **kwargs):
        calls.append(kwargs.get("observer", "scada_master"))
        return real(*args, **kwargs)

    monkeypatch.setattr(traffic_logger, "log_transaction", spy)
    await rtu_pool.start_all()
    try:
        await scenario_injector.inject_command_write(rtu_id=2, register_address=0, value=9000)
        assert calls == ["rtu_tap"], calls   # exactly one record, made by the tap
    finally:
        await rtu_pool.stop_all()


@pytest.mark.asyncio
async def test_failed_write_attempt_is_not_counted():
    """No RTU listening -> nothing reaches the wire -> nothing is observed."""
    traffic_logger.clear()
    res = await scenario_injector.inject_command_write(rtu_id=4, register_address=0, value=1)
    assert res["status"] == "error"
    assert traffic_logger.get_window_events(NBD_WINDOW_TICKS) == []
    assert _nbd([], 4)["nbd_unexpected_write_count"] == 0.0


@pytest.mark.asyncio
async def test_internal_telemetry_updates_are_not_network_observations():
    traffic_logger.clear()
    await rtu_pool.start_all()
    try:
        await rtu_pool.get_rtu(1).write_values(1.0, 0.3, 0.1)
        assert traffic_logger.get_window_events(NBD_WINDOW_TICKS) == []
    finally:
        await rtu_pool.stop_all()
