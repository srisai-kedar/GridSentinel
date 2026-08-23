"""
main.py
-------
GridSentinel API — Physics Engine, OT SCADA Simulation & ML Fusion Classifier.

Endpoints
---------
Phase 1 (Physics API):
  GET  /health                  — Liveness probe
  GET  /feeder/topology         — Feeder layout with coordinates
  POST /feeder/tick             — Single static power flow + SE step
  POST /feeder/inject-bad-data  — Static bad-data injection test
  POST /feeder/reset            — Reset static feeder state

Phase 2 (OT SCADA Simulation & Scenario Engine):
  POST /ot/start                — Start background simulation loop & 5 RTUs
  POST /ot/stop                 — Stop background simulation loop & RTUs
  GET  /ot/status               — Simulation loop & scenario status
  GET  /ot/rtus                 — Telemetry & state for all 5 Modbus RTUs
  GET  /ot/traffic              — Rolling Modbus traffic log buffer
  POST /ot/attack/data-injection   — Silent Data Injection (telemetry-only override)
  POST /ot/attack/command-injection — Unauthorized Modbus command write (logged as anomalous)
  POST /ot/attack/replay        — Replay / freeze telemetry
  POST /ot/fault/line-trip      — Physical line trip in pandapower
  POST /ot/fault/short-circuit  — Physical short-circuit fault stub
  POST /ot/reset                — Reset all scenarios & clear overrides
  WebSocket /ws/live            — Live real-time telemetry stream

Phase 3 (ML Fusion Classifier):
  POST /classifier/verdict      — Run ML inference on current or provided snapshot
  POST /classifier/reload       — Hot-reload the trained model bundle from disk
  GET  /classifier/status       — Model load status & class labels
"""

from __future__ import annotations

import asyncio
import copy
from contextlib import asynccontextmanager
import json
from typing import Any, Dict, List, Optional

import numpy as np
from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from app.core.feeder import build_feeder, run_power_flow
from app.core.state_estimation import (
    add_measurements,
    detect_bad_data,
    inject_bad_data,
    run_state_estimation,
)
from app.models.schemas import (
    BadDataResponse,
    BusTopology,
    BusVoltage,
    ClassifierReloadResponse,
    ClassifierStatusResponse,
    CommandInjectionRequest,
    EstimatedVoltage,
    FlaggedMeasurement,
    HealthResponse,
    InjectBadDataRequest,
    LineLoading,
    LineTopology,
    LineTripRequest,
    OTStatusResponse,
    ReplayAttackRequest,
    ResetResponse,
    RTUInfo,
    RTUListResponse,
    RTUVerdict,
    ScenarioActionResponse,
    ShortCircuitRequest,
    SilentDataInjectionRequest,
    TickResponse,
    TopologyResponse,
    TrafficEvent,
    TrafficLogResponse,
    VerdictRequest,
    VerdictResponse,
)
from app.ml.classifier_service import classifier_service
from app.ot.rtu_server import rtu_pool
from app.ot.scada_master import scada_master
from app.ot.scenario_injector import scenario_injector
from app.ot.simulation_loop import sim_loop
from app.ot.traffic_logger import traffic_logger


# ---------------------------------------------------------------------------
# Shared application state
# ---------------------------------------------------------------------------
app_state: Dict[str, Any] = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for the application."""
    net = build_feeder()
    import pandapower as pp
    pp.runpp(net, algorithm="nr", calculate_voltage_angles=True, numba=False)
    app_state["net"] = net
    app_state["clean_net"] = copy.deepcopy(net)

    print(f"[GridSentinel] Feeder initialized. Buses: {len(net.bus)}, Lines: {len(net.line)}")
    yield
    # Shutdown simulation loop and RTUs on exit
    if sim_loop.is_running:
        await sim_loop.stop()
    app_state.clear()
    print("[GridSentinel] Shutdown — state cleared.")


# ---------------------------------------------------------------------------
# FastAPI app setup
# ---------------------------------------------------------------------------
app = FastAPI(
    title="GridSentinel API",
    description=(
        "Physics-aware cyber-physical anomaly detection for Indian power distribution SCADA. "
        "Phase 1: Feeder physics & WLS state estimation. "
        "Phase 2: Live Modbus TCP OT layer, background diurnal simulation, and attack/fault scenarios. "
        "Phase 3: ML Fusion Classifier (Random Forest) combining physics residuals and network behaviour."
    ),
    version="3.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ===========================================================================
# Phase 1 Endpoints (Physics Engine)
# ===========================================================================

@app.get("/health", response_model=HealthResponse, tags=["System"])
def health_check():
    """Liveness probe."""
    return HealthResponse(status="ok")


@app.get("/feeder/topology", response_model=TopologyResponse, tags=["Feeder Physics"])
def get_topology():
    """Return feeder bus & line topology with layout coordinates."""
    net = app_state.get("net")
    if net is None:
        raise HTTPException(status_code=503, detail="Feeder not initialised")

    buses = []
    for idx, row in net.bus.iterrows():
        x, y = 0.0, 0.0
        # Check GeoJSON format in pandapower 3.x
        if "geo" in row and row["geo"]:
            geo = row["geo"]
            if isinstance(geo, str):
                try:
                    data = json.loads(geo)
                    coords = data.get("coordinates", [0.0, 0.0])
                    x, y = float(coords[0]), float(coords[1])
                except Exception:
                    pass
            elif isinstance(geo, dict):
                coords = geo.get("coordinates", [0.0, 0.0])
                x, y = float(coords[0]), float(coords[1])
        elif "bus_geodata" in net and idx in net["bus_geodata"].index:
            geo_row = net["bus_geodata"].loc[idx]
            x = float(geo_row["x"]) if not np.isnan(geo_row["x"]) else 0.0
            y = float(geo_row["y"]) if not np.isnan(geo_row["y"]) else 0.0

        buses.append(
            BusTopology(
                bus_index=int(idx),
                name=str(row["name"]),
                vn_kv=float(row["vn_kv"]),
                x=x,
                y=y,
                in_service=bool(row["in_service"]),
            )
        )

    lines = []
    for idx, row in net.line.iterrows():
        lines.append(
            LineTopology(
                line_index=int(idx),
                name=str(row["name"]),
                from_bus=int(row["from_bus"]),
                to_bus=int(row["to_bus"]),
                length_km=float(row["length_km"]),
            )
        )

    return TopologyResponse(
        feeder_name=str(net.name),
        buses=buses,
        lines=lines,
        total_buses=len(buses),
        total_lines=len(lines),
    )


@app.post("/feeder/tick", response_model=TickResponse, tags=["Feeder Physics"])
def feeder_tick():
    """Run one synchronous power flow + state estimation cycle on the base feeder."""
    net = app_state.get("net")
    if net is None:
        raise HTTPException(status_code=503, detail="Feeder not initialised")

    pf_result = run_power_flow(net)
    if not pf_result.get("converged", False):
        raise HTTPException(
            status_code=500,
            detail=f"Power flow did not converge: {pf_result.get('error', 'unknown')}",
        )

    add_measurements(net)
    se_result = run_state_estimation(net)

    bus_voltages = [BusVoltage(**bv) for bv in pf_result["bus_voltages"]]
    line_loadings = [LineLoading(**ll) for ll in pf_result["line_loadings"]]
    estimated_voltages = [
        EstimatedVoltage(**ev) for ev in se_result.get("estimated_voltages", [])
    ]

    return TickResponse(
        power_flow_converged=pf_result["converged"],
        bus_voltages=bus_voltages,
        line_loadings=line_loadings,
        total_load_mw=pf_result["total_load_mw"],
        total_loss_mw=pf_result["total_loss_mw"],
        state_estimation_success=se_result.get("success", False),
        estimated_voltages=estimated_voltages,
        chi2_test_passed=se_result.get("chi2_test_passed", True),
        chi2_statistic=se_result.get("chi2_statistic", 0.0),
        chi2_threshold=se_result.get("chi2_threshold", 0.0),
        error=se_result.get("error"),
    )


@app.post("/feeder/inject-bad-data", response_model=BadDataResponse, tags=["Feeder Physics"])
def inject_bad_data_endpoint(request: InjectBadDataRequest):
    """Corrupt a specific measurement and run bad-data detection."""
    net = app_state.get("net")
    if net is None:
        raise HTTPException(status_code=503, detail="Feeder not initialised")

    if net.res_bus.empty:
        run_power_flow(net)
    if net.measurement.empty:
        add_measurements(net)

    if request.measurement_index not in net.measurement.index:
        valid = list(net.measurement.index)
        raise HTTPException(
            status_code=422,
            detail=f"measurement_index {request.measurement_index} not found. Valid indices: {valid}",
        )

    inject_bad_data(net, request.measurement_index, request.magnitude_multiplier)
    detection = detect_bad_data(net)

    if detection.get("error"):
        raise HTTPException(status_code=500, detail=detection["error"])

    flagged = [FlaggedMeasurement(**fm) for fm in detection.get("flagged_measurements", [])]
    bad_detected = detection.get("bad_data_detected", False)
    verdict = "ANOMALY_DETECTED" if bad_detected else "CLEAN"

    return BadDataResponse(
        injected_measurement_index=request.measurement_index,
        magnitude_multiplier=request.magnitude_multiplier,
        bad_data_detected=bad_detected,
        flagged_measurements=flagged,
        chi2_test_passed=detection.get("chi2_test_passed", True),
        chi2_statistic=detection.get("chi2_statistic", 0.0),
        chi2_threshold=detection.get("chi2_threshold", 0.0),
        lnr_threshold=detection.get("lnr_threshold", 3.0),
        verdict=verdict,
        error=detection.get("error"),
    )


@app.post("/feeder/reset", response_model=ResetResponse, tags=["Feeder Physics"])
def reset_feeder():
    """Reset base feeder network back to clean initial state."""
    clean = app_state.get("clean_net")
    if clean is None:
        raise HTTPException(status_code=503, detail="No clean snapshot available")

    import pandapower as pp
    restored = copy.deepcopy(clean)
    pp.runpp(restored, algorithm="nr", calculate_voltage_angles=True, numba=False)
    app_state["net"] = restored

    return ResetResponse(
        status="ok",
        message="Feeder reset to clean initial state. Injected bad data cleared.",
    )


# ===========================================================================
# Phase 2 Endpoints (OT Simulation & Modbus SCADA Layer)
# ===========================================================================

@app.post("/ot/start", response_model=ScenarioActionResponse, tags=["OT SCADA Simulation"])
async def start_ot_simulation():
    """Start the background Modbus RTU servers and continuous simulation loop."""
    net = app_state.get("net")
    if sim_loop.is_running:
        return ScenarioActionResponse(
            status="already_running",
            message="OT simulation is already running.",
            details={"tick_count": sim_loop.tick_count, "sim_time": sim_loop.get_sim_time_string()},
        )

    await sim_loop.start(net=net)
    return ScenarioActionResponse(
        status="started",
        message="OT simulation loop and 5 Modbus TCP RTUs started successfully.",
        details={"tick_interval_s": sim_loop.tick_interval, "sim_time": sim_loop.get_sim_time_string()},
    )


@app.post("/ot/stop", response_model=ScenarioActionResponse, tags=["OT SCADA Simulation"])
async def stop_ot_simulation():
    """Stop the background simulation loop and shut down Modbus RTU servers."""
    if not sim_loop.is_running:
        return ScenarioActionResponse(
            status="already_stopped",
            message="OT simulation is not running.",
            details={},
        )

    await sim_loop.stop()
    return ScenarioActionResponse(
        status="stopped",
        message="OT simulation loop and all RTU servers stopped.",
        details={"total_ticks_run": sim_loop.tick_count},
    )


@app.get("/ot/status", response_model=OTStatusResponse, tags=["OT SCADA Simulation"])
def get_ot_status():
    """Get current status of OT simulation, clock, diurnal scaling, and active scenarios."""
    return OTStatusResponse(
        is_simulation_running=sim_loop.is_running,
        sim_time=sim_loop.get_sim_time_string(),
        sim_hour=round(sim_loop.get_sim_hour_float(), 2),
        diurnal_multiplier=calculate_diurnal_multiplier(sim_loop.get_sim_hour_float()) if sim_loop.is_running else 1.0,
        tick_count=sim_loop.tick_count,
        active_scenarios=scenario_injector.get_active_scenarios(),
        total_traffic_events=traffic_logger.get_total_count(),
    )


def calculate_diurnal_multiplier(hour: float) -> float:
    from app.ot.simulation_loop import calculate_diurnal_multiplier as cdm
    return cdm(hour)


@app.get("/ot/rtus", response_model=RTUListResponse, tags=["OT SCADA Simulation"])
def get_rtus():
    """Return all 5 simulated Modbus RTUs and their current telemetry registers."""
    rtu_statuses = rtu_pool.get_all_status()
    rtus = [RTUInfo(**item) for item in rtu_statuses]
    return RTUListResponse(total_rtus=len(rtus), rtus=rtus)


@app.get("/ot/traffic", response_model=TrafficLogResponse, tags=["OT SCADA Simulation"])
def get_traffic_logs(limit: int = Query(50, ge=1, le=500)):
    """Retrieve rolling Modbus TCP traffic transaction logs."""
    events_raw = traffic_logger.get_recent_events(limit=limit)
    events = [TrafficEvent(**e) for e in events_raw]
    return TrafficLogResponse(
        total_events_captured=traffic_logger.get_total_count(),
        returned_events_count=len(events),
        events=events,
    )


# ---------------------------------------------------------------------------
# Cyber Attack Endpoints
# ---------------------------------------------------------------------------

@app.post("/ot/attack/data-injection", response_model=ScenarioActionResponse, tags=["Scenario Injector"])
def inject_data_attack(req: SilentDataInjectionRequest):
    """
    Trigger Silent Data Injection attack on target RTU.
    Overrides served telemetry without changing pandapower physical state or Modbus network traffic.
    """
    res = scenario_injector.inject_silent_data_injection(
        rtu_id=req.rtu_id,
        voltage_pu=req.voltage_pu,
        p_mw=req.p_mw,
        q_mvar=req.q_mvar,
        duration_ticks=req.duration_ticks,
    )
    return ScenarioActionResponse(
        status="injected",
        message=f"Silent data injection active on RTU-{req.rtu_id}.",
        details=res,
    )


@app.post("/ot/attack/command-injection", response_model=ScenarioActionResponse, tags=["Scenario Injector"])
async def inject_command_attack(req: CommandInjectionRequest):
    """
    Simulate an unauthorized cyber-attacker sending an unauthorized Modbus TCP Write command.
    Logged in the traffic logger as an unexpected write anomaly.
    """
    res = await scenario_injector.inject_command_write(
        rtu_id=req.rtu_id,
        register_address=req.register_address,
        value=req.value,
    )
    return ScenarioActionResponse(
        status=res.get("status", "injected"),
        message=f"Command injection executed on RTU-{req.rtu_id} register {req.register_address}.",
        details=res,
    )


@app.post("/ot/attack/replay", response_model=ScenarioActionResponse, tags=["Scenario Injector"])
def inject_replay_attack(req: ReplayAttackRequest):
    """Freeze telemetry on target RTU and replay historical values."""
    res = scenario_injector.inject_replay(
        rtu_id=req.rtu_id,
        duration_ticks=req.duration_ticks,
    )
    return ScenarioActionResponse(
        status="injected",
        message=f"Replay attack active on RTU-{req.rtu_id} for {req.duration_ticks} ticks.",
        details=res,
    )


# ---------------------------------------------------------------------------
# Physical Fault Endpoints
# ---------------------------------------------------------------------------

@app.post("/ot/fault/line-trip", response_model=ScenarioActionResponse, tags=["Scenario Injector"])
def trigger_line_trip_endpoint(req: LineTripRequest):
    """
    Trigger a physical line outage in the feeder.
    Takes line out of service in pandapower and propagates physically to all downstream RTUs.
    """
    net = sim_loop.net or app_state.get("net")
    if net is None:
        raise HTTPException(status_code=503, detail="Grid network not initialized")

    res = scenario_injector.trigger_line_trip(net=net, line_index=req.line_index)
    return ScenarioActionResponse(
        status="triggered",
        message=f"Physical Line Trip triggered on Line {req.line_index}.",
        details=res,
    )


@app.post("/ot/fault/short-circuit", response_model=ScenarioActionResponse, tags=["Scenario Injector"])
def trigger_short_circuit_endpoint(req: ShortCircuitRequest):
    """Trigger a temporary short-circuit fault stub producing voltage sag."""
    net = sim_loop.net or app_state.get("net")
    if net is None:
        raise HTTPException(status_code=503, detail="Grid network not initialized")

    res = scenario_injector.trigger_short_circuit_stub(
        net=net,
        bus_index=req.bus_index,
        fault_load_mw=req.fault_load_mw,
        fault_load_mvar=req.fault_load_mvar,
        duration_ticks=req.duration_ticks,
    )
    return ScenarioActionResponse(
        status="triggered",
        message=f"Short circuit stub triggered on Bus {req.bus_index} for {req.duration_ticks} ticks.",
        details=res,
    )


@app.post("/ot/reset", response_model=ScenarioActionResponse, tags=["Scenario Injector"])
def reset_ot_scenarios():
    """Clear all active cyber overrides and physical faults, restoring normal grid operation."""
    net = sim_loop.net or app_state.get("net")
    scenario_injector.clear_all_scenarios(net=net)
    traffic_logger.clear()
    return ScenarioActionResponse(
        status="ok",
        message="All cyber attacks and physical faults cleared. Normal operation restored.",
        details={"active_scenarios": scenario_injector.get_active_scenarios()},
    )


# ===========================================================================
# Phase 3 — ML Fusion Classifier Endpoints
# ===========================================================================

import time as _time
from datetime import datetime, timezone


@app.post("/classifier/verdict", response_model=VerdictResponse, tags=["ML Classifier"])
def get_classifier_verdict(req: Optional[VerdictRequest] = None):
    """
    Run the ML Fusion Classifier on the current or provided simulation snapshot.

    - If called with no body (or null fields), the endpoint samples the live
      traffic logger, the latest simulation tick state, and the live RTU pool.
    - To evaluate an offline snapshot, POST the relevant dicts in the request body.

    Returns per-RTU verdicts: Normal / Natural Fault / Cyber Intrusion (subtyped).
    """
    t0 = _time.perf_counter()

    # ── Resolve traffic events ────────────────────────────────────────────────
    if req and req.traffic_window is not None:
        traffic_events = req.traffic_window
    else:
        traffic_events = traffic_logger.get_recent_events(limit=200)

    # ── Resolve state estimation result ──────────────────────────────────────
    if req and req.state_estimation_result is not None:
        se_result = req.state_estimation_result
    else:
        latest = sim_loop.latest_state or {}
        se_result = latest.get("state_estimation", {})

    # ── Resolve RTU telemetry ─────────────────────────────────────────────────
    if req and req.polled_telemetry is not None:
        # Keys come as strings from JSON; normalise to int
        polled = {int(k): v for k, v in req.polled_telemetry.items()}
    else:
        polled = {
            rtu.rtu_id: rtu.get_current_values()
            for rtu in rtu_pool.rtus.values()
        }

    # ── Run inference for all RTUs ────────────────────────────────────────────
    verdicts = classifier_service.evaluate_all_rtus(
        traffic_events=traffic_events,
        state_estimation_result=se_result,
        polled_telemetry=polled,
    )

    elapsed_ms = round((_time.perf_counter() - t0) * 1000, 2)

    # ── Aggregate overall status ─────────────────────────────────────────────
    any_anomaly = any(
        v.get("verdict") in ("Natural Fault", "Cyber Intrusion")
        for v in verdicts.values()
    )
    overall_status = "ANOMALY_DETECTED" if any_anomaly else "NORMAL"

    rtu_verdict_list = [
        RTUVerdict(
            rtu_id=rtu_id,
            verdict=v["verdict"],
            subtype=v.get("subtype"),
            confidence=v["confidence"],
            probabilities=v["probabilities"],
            model_status=v.get("model_status", "loaded"),
        )
        for rtu_id, v in sorted(verdicts.items())
    ]

    return VerdictResponse(
        tick_timestamp=datetime.now(timezone.utc).isoformat(),
        model_loaded=classifier_service.is_loaded,
        overall_status=overall_status,
        rtu_verdicts=rtu_verdict_list,
        evaluation_latency_ms=elapsed_ms,
    )


@app.post("/classifier/reload", response_model=ClassifierReloadResponse, tags=["ML Classifier"])
def reload_classifier_model():
    """
    Hot-reload the trained model bundle from disk without restarting the server.
    Use this after running `python -m app.ml.train_classifier ...` to pick up a
    freshly trained model in the running process.
    """
    success = classifier_service.load_model()
    return ClassifierReloadResponse(
        success=success,
        message=(
            "Model successfully reloaded from disk."
            if success
            else f"Model file '{classifier_service.model_path}' not found or failed to load. "
                 "Server is running in heuristic baseline mode."
        ),
        model_path=str(classifier_service.model_path),
    )


@app.get("/classifier/status", response_model=ClassifierStatusResponse, tags=["ML Classifier"])
def get_classifier_status():
    """Return model load status, class labels, and number of cached RTU verdicts."""
    return ClassifierStatusResponse(
        is_loaded=classifier_service.is_loaded,
        model_path=str(classifier_service.model_path),
        classes=classifier_service.classes,
        subtype_classes=classifier_service.subtype_classes,
        cached_rtu_count=len(classifier_service.latest_verdicts),
    )


# ===========================================================================
# WebSocket Live Telemetry Feed (includes Phase 3 ML verdicts)
# ===========================================================================

@app.websocket("/ws/live")
async def websocket_live_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint for real-time live telemetry streaming.
    Broadcasts simulation ticks with true state, reported Modbus telemetry,
    state estimation verdicts, active scenarios, recent traffic logs,
    AND Phase 3 per-RTU ML fusion verdicts.
    """
    await websocket.accept()
    queue = sim_loop.subscribe_ws()

    try:
        # Send current latest state immediately upon connection if available
        if sim_loop.latest_state:
            initial = dict(sim_loop.latest_state)
            initial["ml_verdicts"] = classifier_service.latest_verdicts
            await websocket.send_text(json.dumps(initial))

        while True:
            # Wait for next simulation tick broadcast
            payload = await queue.get()
            # Attach the most recent cached ML verdicts to every tick
            payload["ml_verdicts"] = classifier_service.latest_verdicts
            await websocket.send_text(json.dumps(payload))

    except (WebSocketDisconnect, asyncio.CancelledError):
        pass
    finally:
        sim_loop.unsubscribe_ws(queue)
