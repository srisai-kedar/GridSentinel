"""
simulation_loop.py
------------------
Asynchronous background simulation loop for GridSentinel OT layer.
Runs the real-time simulation tick:
  1. Advances simulated clock (default: 15 simulated mins per 1s tick).
  2. Applies realistic diurnal load curve to pandapower feeder loads.
  3. Executes Newton-Raphson power flow to obtain "True" physical state.
  4. Computes telemetry for 5 RTUs (with RTU noise) and applies any active
     cyber overrides (silent data injection / replay).
  5. Writes telemetry into simulated Modbus TCP RTUs.
  6. SCADA Master polls RTUs over Modbus TCP and logs traffic.
  7. Feeds polled telemetry into WLS State Estimation + Bad Data Detection.
  8. Broadcasts live telemetry snapshot to WebSocket clients.
"""

from __future__ import annotations

import asyncio
import datetime
import logging
import math
import time
from typing import Any, Callable, Dict, List, Optional, Set
import numpy as np
import pandapower as pp

from app.core.feeder import build_feeder, run_power_flow
from app.core.state_estimation import (
    add_measurements,
    detect_bad_data,
    run_state_estimation,
)
from app.ot.rtu_server import RTU_CONFIGS, rtu_pool
from app.ot.scada_master import scada_master
from app.ot.scenario_injector import scenario_injector
from app.ot.traffic_logger import traffic_logger

logger = logging.getLogger("GridSentinel.SimulationLoop")


def calculate_diurnal_multiplier(sim_hour_float: float) -> float:
    """
    Calculate smooth diurnal load multiplier for hour t in [0, 24).
    Produces:
      - Trough around 03:00-05:00 (~0.68x)
      - Daytime plateau around 10:00-16:00 (~1.05x)
      - Evening peak around 19:00-21:00 (~1.32x)
    """
    t = sim_hour_float % 24.0
    base = 1.0
    evening_wave = 0.24 * math.sin(2.0 * math.pi * (t - 14.0) / 24.0)
    day_wave = 0.08 * math.sin(4.0 * math.pi * (t - 6.0) / 24.0)
    multiplier = base + evening_wave + day_wave
    return max(0.5, round(multiplier, 4))


def _safe_float_val(val_in: Any, default: float = 0.0, noise_std: float = 0.0) -> float:
    """Safely extract finite float from dataframe cell, applying optional Gaussian noise."""
    try:
        f = float(val_in)
        if np.isnan(f) or np.isinf(f):
            return default
        if noise_std > 0.0:
            f += float(np.random.normal(0.0, noise_std))
        return f
    except Exception:
        return default


class SimulationLoop:
    """
    Controls the background simulation task and WebSocket broadcast subscribers.
    """

    def __init__(
        self,
        tick_interval_seconds: float = 1.0,
        sim_minutes_per_tick: float = 15.0,
        initial_sim_time_hour: float = 8.0,  # starts at 08:00 AM
    ):
        self.tick_interval: float = tick_interval_seconds
        self.sim_minutes_per_tick: float = sim_minutes_per_tick
        self.sim_time_total_minutes: float = initial_sim_time_hour * 60.0

        self.is_running: bool = False
        self._task: Optional[asyncio.Task] = None

        self.net: Optional[pp.pandapowerNet] = None
        self._base_load_p: Dict[int, float] = {}
        self._base_load_q: Dict[int, float] = {}

        self.tick_count: int = 0
        self.latest_state: Dict[str, Any] = {}

        # WebSocket broadcast subscribers
        self._ws_subscribers: Set[asyncio.Queue] = set()

    def get_sim_time_string(self) -> str:
        """Format total simulated minutes as HH:MM:SS."""
        total_secs = int((self.sim_time_total_minutes % (24 * 60)) * 60)
        hours = (total_secs // 3600) % 24
        mins = (total_secs % 3600) // 60
        secs = total_secs % 60
        return f"{hours:02d}:{mins:02d}:{secs:02d}"

    def get_sim_hour_float(self) -> float:
        """Return fractional hour (e.g. 19.5 for 19:30)."""
        return (self.sim_time_total_minutes % (24 * 60)) / 60.0

    async def start(self, net: Optional[pp.pandapowerNet] = None) -> None:
        """Start the background simulation loop and RTUs."""
        if self.is_running:
            return

        # Initialize network
        if net is None:
            self.net = build_feeder()
        else:
            self.net = net

        # Cache baseline load values for diurnal scaling
        self._base_load_p = {idx: float(row["p_mw"]) for idx, row in self.net.load.iterrows()}
        self._base_load_q = {idx: float(row["q_mvar"]) for idx, row in self.net.load.iterrows()}

        # Start all 5 RTU servers
        await rtu_pool.start_all()

        self.is_running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info("SimulationLoop started.")

    async def stop(self) -> None:
        """Stop the background simulation loop and RTUs."""
        if not self.is_running:
            return

        self.is_running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass
            self._task = None

        await rtu_pool.stop_all()
        logger.info("SimulationLoop stopped.")

    async def _run_loop(self) -> None:
        """Main periodic tick execution."""
        while self.is_running:
            start_tick = time.perf_counter()
            try:
                await self.tick()
            except Exception as exc:
                logger.error(f"Error during simulation tick: {exc}", exc_info=True)

            elapsed = time.perf_counter() - start_tick
            sleep_time = max(0.05, self.tick_interval - elapsed)
            await asyncio.sleep(sleep_time)

    async def tick(self) -> Dict[str, Any]:
        """
        Execute one full simulation step.
        """
        self.tick_count += 1
        self.sim_time_total_minutes += self.sim_minutes_per_tick

        sim_time_str = self.get_sim_time_string()
        sim_hour = self.get_sim_hour_float()
        diurnal_mult = calculate_diurnal_multiplier(sim_hour)

        # 1. Apply diurnal curve to loads
        for idx, base_p in self._base_load_p.items():
            if idx in self.net.load.index:
                self.net.load.at[idx, "p_mw"] = base_p * diurnal_mult
                self.net.load.at[idx, "q_mvar"] = self._base_load_q[idx] * diurnal_mult

        # 2. Advance scenario injector lifecycle
        scenario_injector.on_simulation_tick(self.net)

        # 3. Run power flow to obtain "True" physical grid state
        pf_res = run_power_flow(self.net)
        converged = pf_res.get("converged", False)

        # 4. Generate telemetry for all 5 RTUs
        # Monitored mappings:
        # RTU 1 -> Bus 1 V, Trafo 0 LV P/Q
        # RTU 2 -> Bus 2 V, Line 0 from P/Q
        # RTU 3 -> Bus 3 V, Line 1 from P/Q
        # RTU 4 -> Bus 4 V, Line 2 from P/Q
        # RTU 5 -> Bus 5 V, Line 3 from P/Q
        rtu_telemetry_to_write: Dict[int, Dict[str, Any]] = {}

        if converged:
            # RTU 1 (Substation)
            v1 = _safe_float_val(self.net.res_bus.at[1, "vm_pu"] if 1 in self.net.res_bus.index else None, 1.0, 0.002)
            p1 = _safe_float_val(self.net.res_trafo.at[0, "p_lv_mw"] if 0 in self.net.res_trafo.index else None, 0.0, 0.004)
            q1 = _safe_float_val(self.net.res_trafo.at[0, "q_lv_mvar"] if 0 in self.net.res_trafo.index else None, 0.0, 0.004)
            rtu_telemetry_to_write[1] = {"voltage_pu": v1, "p_mw": p1, "q_mvar": q1}

            # RTU 2 (Feeder A)
            v2 = _safe_float_val(self.net.res_bus.at[2, "vm_pu"] if 2 in self.net.res_bus.index else None, 0.0, 0.002)
            p2 = _safe_float_val(self.net.res_line.at[0, "p_from_mw"] if 0 in self.net.res_line.index else None, 0.0, 0.004)
            q2 = _safe_float_val(self.net.res_line.at[0, "q_from_mvar"] if 0 in self.net.res_line.index else None, 0.0, 0.004)
            rtu_telemetry_to_write[2] = {"voltage_pu": v2, "p_mw": p2, "q_mvar": q2}

            # RTU 3 (Feeder B)
            v3 = _safe_float_val(self.net.res_bus.at[3, "vm_pu"] if 3 in self.net.res_bus.index else None, 0.0, 0.002)
            p3 = _safe_float_val(self.net.res_line.at[1, "p_from_mw"] if 1 in self.net.res_line.index else None, 0.0, 0.004)
            q3 = _safe_float_val(self.net.res_line.at[1, "q_from_mvar"] if 1 in self.net.res_line.index else None, 0.0, 0.004)
            rtu_telemetry_to_write[3] = {"voltage_pu": v3, "p_mw": p3, "q_mvar": q3}

            # RTU 4 (Feeder C)
            v4 = _safe_float_val(self.net.res_bus.at[4, "vm_pu"] if 4 in self.net.res_bus.index else None, 0.0, 0.002)
            p4 = _safe_float_val(self.net.res_line.at[2, "p_from_mw"] if 2 in self.net.res_line.index else None, 0.0, 0.004)
            q4 = _safe_float_val(self.net.res_line.at[2, "q_from_mvar"] if 2 in self.net.res_line.index else None, 0.0, 0.004)
            rtu_telemetry_to_write[4] = {"voltage_pu": v4, "p_mw": p4, "q_mvar": q4}

            # RTU 5 (Feeder A2)
            v5 = _safe_float_val(self.net.res_bus.at[5, "vm_pu"] if 5 in self.net.res_bus.index else None, 0.0, 0.002)
            p5 = _safe_float_val(self.net.res_line.at[3, "p_from_mw"] if 3 in self.net.res_line.index else None, 0.0, 0.004)
            q5 = _safe_float_val(self.net.res_line.at[3, "q_from_mvar"] if 3 in self.net.res_line.index else None, 0.0, 0.004)
            rtu_telemetry_to_write[5] = {"voltage_pu": v5, "p_mw": p5, "q_mvar": q5}
        else:
            for rtu_id in range(1, 6):
                rtu_telemetry_to_write[rtu_id] = {"voltage_pu": 0.0, "p_mw": 0.0, "q_mvar": 0.0}

        # 5. Apply cyber overrides (Silent Data Injection or Replay)
        # Note: Attacks take priority over fresh simulated writes
        for rtu_id in range(1, 6):
            if rtu_id not in rtu_telemetry_to_write:
                continue

            # Check Replay attack
            if rtu_id in scenario_injector.replay_attacks:
                frozen = scenario_injector.replay_attacks[rtu_id]["frozen_values"]
                rtu_telemetry_to_write[rtu_id] = dict(frozen)

            # Check Silent Data Injection attack
            if rtu_id in scenario_injector.silent_overrides:
                overrides = scenario_injector.silent_overrides[rtu_id]["overrides"]
                for k, v in overrides.items():
                    rtu_telemetry_to_write[rtu_id][k] = v

            # Write to RTU server registers
            rtu = rtu_pool.get_rtu(rtu_id)
            if rtu and rtu.is_running:
                t_val = rtu_telemetry_to_write[rtu_id]
                status_code = 3 if t_val["voltage_pu"] == 0.0 else 1
                await rtu.write_values(
                    voltage_pu=t_val["voltage_pu"],
                    p_mw=t_val["p_mw"],
                    q_mvar=t_val["q_mvar"],
                    status=status_code,
                )

        # 6. SCADA Master polls all RTUs over Modbus TCP
        polled_telemetry = await scada_master.poll_all_rtus()

        # 7. Feed polled telemetry into State Estimation
        add_measurements(self.net, telemetry=polled_telemetry)
        se_result = run_state_estimation(self.net)
        detection_result = detect_bad_data(self.net)

        # 8. Assemble full state snapshot (True vs Reported vs Estimated)
        active_scenarios = scenario_injector.get_active_scenarios()
        recent_traffic = traffic_logger.get_recent_events(limit=5)

        snapshot = {
            "tick": self.tick_count,
            "sim_time": sim_time_str,
            "diurnal_multiplier": diurnal_mult,
            "power_flow_converged": converged,
            "true_physical_state": {
                "bus_voltages": pf_res.get("bus_voltages", []),
                "line_loadings": pf_res.get("line_loadings", []),
                "total_load_mw": pf_res.get("total_load_mw", 0.0),
                "total_loss_mw": pf_res.get("total_loss_mw", 0.0),
            },
            "polled_modbus_telemetry": polled_telemetry,
            "state_estimation": {
                "success": se_result.get("success", False),
                "estimated_voltages": se_result.get("estimated_voltages", []),
                "chi2_test_passed": se_result.get("chi2_test_passed", True),
                "chi2_statistic": se_result.get("chi2_statistic", 0.0),
                "chi2_threshold": se_result.get("chi2_threshold", 0.0),
                "bad_data_detected": detection_result.get("bad_data_detected", False),
                "flagged_measurements": detection_result.get("flagged_measurements", []),
            },
            "active_scenarios": active_scenarios,
            "recent_traffic_log": recent_traffic,
        }

        self.latest_state = snapshot

        # 9. Broadcast to all active WebSocket subscribers
        await self._broadcast_ws(snapshot)

        return snapshot

    # -----------------------------------------------------------------------
    # WebSocket Subscription Management
    # -----------------------------------------------------------------------
    def subscribe_ws(self) -> asyncio.Queue:
        """Register a new WebSocket client queue."""
        q: asyncio.Queue = asyncio.Queue(maxsize=10)
        self._ws_subscribers.add(q)
        return q

    def unsubscribe_ws(self, q: asyncio.Queue) -> None:
        """Unregister a WebSocket client queue."""
        self._ws_subscribers.discard(q)

    async def _broadcast_ws(self, payload: Dict[str, Any]) -> None:
        """Push snapshot to all subscribed WebSocket queues non-blockingly."""
        for q in list(self._ws_subscribers):
            try:
                if q.full():
                    q.get_nowait()
                q.put_nowait(payload)
            except Exception:
                pass


# Global singleton instance
sim_loop = SimulationLoop()
