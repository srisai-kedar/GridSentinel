"use client";

import React, { useState } from "react";
import {
  injectCommandAttack,
  injectReplayAttack,
  injectSilentDataAttack,
  resetOtScenarios,
  startOtSimulation,
  stopOtSimulation,
  triggerLineTrip,
  triggerShortCircuit,
} from "@/lib/api";
import { LiveSocketPayload } from "@/lib/types";
import {
  AlertTriangle,
  Flame,
  Pause,
  Play,
  Radio,
  RefreshCw,
  RotateCcw,
  ShieldAlert,
  Sliders,
  Terminal,
  Zap,
} from "lucide-react";

interface DemoControlsProps {
  latestState: LiveSocketPayload | null;
  onActionComplete?: (message: string) => void;
}

export const DemoControls: React.FC<DemoControlsProps> = ({
  latestState,
  onActionComplete,
}) => {
  const [loadingAction, setLoadingAction] = useState<string | null>(null);
  const [actionFeedback, setActionFeedback] = useState<{ message: string; isError?: boolean } | null>(null);

  // Target selectors
  const [selectedRtu, setSelectedRtu] = useState<number>(2);
  const [selectedLine, setSelectedLine] = useState<number>(0);
  const [selectedBus, setSelectedBus] = useState<number>(2);

  // Active Scenarios from backend
  const activeScenarios = latestState?.active_scenarios;
  const isSilentActive = Boolean(
    activeScenarios?.silent_overrides &&
      Object.keys(activeScenarios.silent_overrides).length > 0
  );
  const isReplayActive = Boolean(
    activeScenarios?.replay_attacks && activeScenarios.replay_attacks.length > 0
  );
  const isLineTripActive = Boolean(
    activeScenarios?.tripped_lines && activeScenarios.tripped_lines.length > 0
  );
  const isShortCircuitActive = Boolean(activeScenarios?.short_circuit_active);

  const isAnyScenarioActive =
    isSilentActive || isReplayActive || isLineTripActive || isShortCircuitActive;

  const showFeedback = (msg: string, isError: boolean = false) => {
    setActionFeedback({ message: msg, isError });
    if (onActionComplete) onActionComplete(msg);
    setTimeout(() => {
      setActionFeedback(null);
    }, 4000);
  };

  // Handlers
  const handleStartSim = async () => {
    try {
      setLoadingAction("start_sim");
      const res = await startOtSimulation();
      showFeedback(res.message || "OT Simulation started.");
    } catch (err: any) {
      showFeedback(err.message || "Failed to start simulation.", true);
    } finally {
      setLoadingAction(null);
    }
  };

  const handleStopSim = async () => {
    try {
      setLoadingAction("stop_sim");
      const res = await stopOtSimulation();
      showFeedback(res.message || "OT Simulation stopped.");
    } catch (err: any) {
      showFeedback(err.message || "Failed to stop simulation.", true);
    } finally {
      setLoadingAction(null);
    }
  };

  const handleResetNormal = async () => {
    try {
      setLoadingAction("reset_all");
      const res = await resetOtScenarios();
      showFeedback(res.message || "Grid reset to clean normal state.");
    } catch (err: any) {
      showFeedback(err.message || "Failed to reset scenarios.", true);
    } finally {
      setLoadingAction(null);
    }
  };

  const handleSilentDataInjection = async () => {
    try {
      setLoadingAction("silent_data");
      const res = await injectSilentDataAttack({
        rtu_id: selectedRtu,
        voltage_pu: 1.15, // Noticeable falsified overvoltage
        duration_ticks: 20,
      });
      showFeedback(res.message || `Silent Data Injection active on RTU-${selectedRtu}.`);
    } catch (err: any) {
      showFeedback(err.message || "Failed to inject silent data attack.", true);
    } finally {
      setLoadingAction(null);
    }
  };

  const handleCommandInjection = async () => {
    try {
      setLoadingAction("command_injection");
      const res = await injectCommandAttack({
        rtu_id: selectedRtu,
        register_address: 1, // Active power register
        value: 5000,         // Unauthorized high value
      });
      showFeedback(res.message || `Unauthorized Modbus Write sent to RTU-${selectedRtu}.`);
    } catch (err: any) {
      showFeedback(err.message || "Failed to inject command write.", true);
    } finally {
      setLoadingAction(null);
    }
  };

  const handleReplayAttack = async () => {
    try {
      setLoadingAction("replay");
      const res = await injectReplayAttack({
        rtu_id: selectedRtu,
        duration_ticks: 20,
      });
      showFeedback(res.message || `Replay attack active on RTU-${selectedRtu}.`);
    } catch (err: any) {
      showFeedback(err.message || "Failed to inject replay attack.", true);
    } finally {
      setLoadingAction(null);
    }
  };

  const handleLineTrip = async () => {
    try {
      setLoadingAction("line_trip");
      const res = await triggerLineTrip({
        line_index: selectedLine,
      });
      showFeedback(res.message || `Physical line ${selectedLine} tripped.`);
    } catch (err: any) {
      showFeedback(err.message || "Failed to trigger line trip.", true);
    } finally {
      setLoadingAction(null);
    }
  };

  const handleShortCircuit = async () => {
    try {
      setLoadingAction("short_circuit");
      const res = await triggerShortCircuit({
        bus_index: selectedBus,
        fault_load_mw: 6.0,
        fault_load_mvar: 4.0,
        duration_ticks: 6,
      });
      showFeedback(res.message || `Short circuit fault triggered on Bus ${selectedBus}.`);
    } catch (err: any) {
      showFeedback(err.message || "Failed to trigger short circuit.", true);
    } finally {
      setLoadingAction(null);
    }
  };

  return (
    <div className="flex flex-col h-full bg-[#111827] rounded-lg border border-gray-800 overflow-hidden text-xs select-none shadow-md">
      {/* Header */}
      <div className="p-3 bg-[#0F172A] border-b border-gray-800 flex items-center justify-between">
        <div className="flex items-center space-x-2">
          <Terminal className="w-4 h-4 text-cyan-400" />
          <h2 className="font-bold text-gray-200 uppercase tracking-wider text-xs">
            Scenario & Attack Injection Engine
          </h2>
        </div>

        {/* Global Simulation Toggle */}
        <div className="flex items-center space-x-1">
          <button
            onClick={handleStartSim}
            disabled={loadingAction !== null}
            className="flex items-center space-x-1 bg-emerald-950/80 hover:bg-emerald-900 text-emerald-300 border border-emerald-700 px-2 py-1 rounded transition disabled:opacity-50 font-medium text-[11px]"
            title="Start background simulation loop"
          >
            <Play className="w-3 h-3 fill-emerald-300" />
            <span>Start OT</span>
          </button>
          <button
            onClick={handleStopSim}
            disabled={loadingAction !== null}
            className="flex items-center space-x-1 bg-slate-800 hover:bg-slate-700 text-gray-300 border border-gray-700 px-2 py-1 rounded transition disabled:opacity-50 font-medium text-[11px]"
            title="Stop simulation loop"
          >
            <Pause className="w-3 h-3" />
            <span>Stop</span>
          </button>
        </div>
      </div>

      {/* Action Notification Toast */}
      {actionFeedback && (
        <div
          className={`px-3 py-1.5 text-[11px] font-mono border-b flex items-center justify-between ${
            actionFeedback.isError
              ? "bg-rose-950/90 text-rose-200 border-rose-800"
              : "bg-emerald-950/90 text-emerald-200 border-emerald-800"
          }`}
        >
          <span>{actionFeedback.message}</span>
        </div>
      )}

      {/* Target Selector Toolbar */}
      <div className="p-2.5 bg-[#0B0F19] border-b border-gray-800 flex flex-wrap items-center gap-3 text-[11px]">
        <div className="flex items-center space-x-1.5">
          <span className="text-gray-400 font-mono">Target RTU:</span>
          <select
            value={selectedRtu}
            onChange={(e) => setSelectedRtu(parseInt(e.target.value, 10))}
            className="bg-[#1E293B] text-gray-200 px-2 py-0.5 rounded border border-gray-700 focus:outline-none"
          >
            <option value={1}>RTU-1 (Substation-11kV)</option>
            <option value={2}>RTU-2 (Feeder A Industrial)</option>
            <option value={3}>RTU-3 (Feeder B Residential)</option>
            <option value={4}>RTU-4 (Feeder C Agriculture)</option>
            <option value={5}>RTU-5 (Feeder A2 Mixed)</option>
          </select>
        </div>

        <div className="flex items-center space-x-1.5">
          <span className="text-gray-400 font-mono">Target Line:</span>
          <select
            value={selectedLine}
            onChange={(e) => setSelectedLine(parseInt(e.target.value, 10))}
            className="bg-[#1E293B] text-gray-200 px-2 py-0.5 rounded border border-gray-700 focus:outline-none"
          >
            <option value={0}>Line 0 (Substation → Feeder A)</option>
            <option value={1}>Line 1 (Substation → Feeder B)</option>
            <option value={2}>Line 2 (Substation → Feeder C)</option>
            <option value={3}>Line 3 (Feeder A → Feeder A2)</option>
            <option value={4}>Line 4 (Feeder B → Feeder B2)</option>
          </select>
        </div>
      </div>

      {/* Action Buttons Grid */}
      <div className="p-3 space-y-3 flex-1 overflow-y-auto">
        {/* Reset to Normal Button (Prominent) */}
        <button
          onClick={handleResetNormal}
          disabled={loadingAction !== null}
          className="w-full flex items-center justify-center space-x-2 bg-gradient-to-r from-emerald-600 to-teal-600 hover:from-emerald-500 hover:to-teal-500 text-white font-bold py-2.5 px-4 rounded-md shadow-lg shadow-emerald-950/40 transition disabled:opacity-50 text-xs tracking-wider uppercase border border-emerald-400/40"
        >
          <RotateCcw className={`w-4 h-4 ${loadingAction === "reset_all" ? "animate-spin" : ""}`} />
          <span>Reset Grid to Clean State</span>
        </button>

        {/* Section 1: Cyber Attack Scenarios */}
        <div>
          <div className="flex items-center space-x-1.5 text-rose-400 font-bold uppercase tracking-wider text-[11px] mb-2">
            <ShieldAlert className="w-3.5 h-3.5" />
            <span>Cyber Attack Scenarios</span>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-2">
            {/* Silent Data Injection */}
            <button
              onClick={handleSilentDataInjection}
              disabled={isSilentActive || loadingAction !== null}
              className={`p-2.5 rounded-md border text-left flex flex-col justify-between transition ${
                isSilentActive
                  ? "bg-rose-950/60 border-rose-700 text-rose-300 cursor-not-allowed"
                  : "bg-[#1E293B] hover:bg-[#283548] border-gray-700 text-gray-200 hover:border-rose-500/60"
              }`}
            >
              <div className="flex items-center justify-between mb-1">
                <span className="font-semibold text-[11px]">Silent Data Injection</span>
                {isSilentActive && (
                  <span className="text-[9px] px-1.5 py-0.5 rounded bg-rose-900 text-rose-200 font-mono animate-pulse">
                    ACTIVE
                  </span>
                )}
              </div>
              <p className="text-[10px] text-gray-400 leading-tight">
                Overrides telemetry (1.15 pu V) without touching physics or Modbus packets.
              </p>
              <div className="mt-2 text-[9px] font-mono text-rose-400">
                {loadingAction === "silent_data" ? "Triggering..." : "Target: RTU-" + selectedRtu}
              </div>
            </button>

            {/* Unauthorized Command Injection */}
            <button
              onClick={handleCommandInjection}
              disabled={loadingAction !== null}
              className="p-2.5 rounded-md border bg-[#1E293B] hover:bg-[#283548] border-gray-700 text-gray-200 hover:border-rose-500/60 transition text-left flex flex-col justify-between"
            >
              <div className="flex items-center justify-between mb-1">
                <span className="font-semibold text-[11px]">Command Injection</span>
              </div>
              <p className="text-[10px] text-gray-400 leading-tight">
                Sends unauthorized FC 06 Modbus Write; logged in SCADA traffic as anomaly.
              </p>
              <div className="mt-2 text-[9px] font-mono text-rose-400">
                {loadingAction === "command_injection" ? "Injecting..." : "Write Reg 1 = 5000"}
              </div>
            </button>

            {/* Replay Attack */}
            <button
              onClick={handleReplayAttack}
              disabled={isReplayActive || loadingAction !== null}
              className={`p-2.5 rounded-md border text-left flex flex-col justify-between transition ${
                isReplayActive
                  ? "bg-rose-950/60 border-rose-700 text-rose-300 cursor-not-allowed"
                  : "bg-[#1E293B] hover:bg-[#283548] border-gray-700 text-gray-200 hover:border-rose-500/60"
              }`}
            >
              <div className="flex items-center justify-between mb-1">
                <span className="font-semibold text-[11px]">Replay Attack</span>
                {isReplayActive && (
                  <span className="text-[9px] px-1.5 py-0.5 rounded bg-rose-900 text-rose-200 font-mono animate-pulse">
                    ACTIVE
                  </span>
                )}
              </div>
              <p className="text-[10px] text-gray-400 leading-tight">
                Freezes and loops stale telemetry packets with 0 diurnal load variance.
              </p>
              <div className="mt-2 text-[9px] font-mono text-rose-400">
                {loadingAction === "replay" ? "Freezing..." : "Duration: 20 ticks"}
              </div>
            </button>
          </div>
        </div>

        {/* Section 2: Physical Grid Faults */}
        <div>
          <div className="flex items-center space-x-1.5 text-amber-400 font-bold uppercase tracking-wider text-[11px] mb-2">
            <AlertTriangle className="w-3.5 h-3.5" />
            <span>Physical Grid Faults</span>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
            {/* Line Trip Outage */}
            <button
              onClick={handleLineTrip}
              disabled={isLineTripActive || loadingAction !== null}
              className={`p-2.5 rounded-md border text-left flex flex-col justify-between transition ${
                isLineTripActive
                  ? "bg-amber-950/60 border-amber-700 text-amber-300 cursor-not-allowed"
                  : "bg-[#1E293B] hover:bg-[#283548] border-gray-700 text-gray-200 hover:border-amber-500/60"
              }`}
            >
              <div className="flex items-center justify-between mb-1">
                <span className="font-semibold text-[11px]">Physical Line Trip</span>
                {isLineTripActive && (
                  <span className="text-[9px] px-1.5 py-0.5 rounded bg-amber-900 text-amber-200 font-mono animate-pulse">
                    TRIPPED
                  </span>
                )}
              </div>
              <p className="text-[10px] text-gray-400 leading-tight">
                Takes line out of service in pandapower; real physical current drops to zero.
              </p>
              <div className="mt-2 text-[9px] font-mono text-amber-400">
                {loadingAction === "line_trip" ? "Tripping..." : "Trip Line " + selectedLine}
              </div>
            </button>

            {/* Short Circuit Fault */}
            <button
              onClick={handleShortCircuit}
              disabled={isShortCircuitActive || loadingAction !== null}
              className={`p-2.5 rounded-md border text-left flex flex-col justify-between transition ${
                isShortCircuitActive
                  ? "bg-amber-950/60 border-amber-700 text-amber-300 cursor-not-allowed"
                  : "bg-[#1E293B] hover:bg-[#283548] border-gray-700 text-gray-200 hover:border-amber-500/60"
              }`}
            >
              <div className="flex items-center justify-between mb-1">
                <span className="font-semibold text-[11px]">Short-Circuit Surge</span>
                {isShortCircuitActive && (
                  <span className="text-[9px] px-1.5 py-0.5 rounded bg-amber-900 text-amber-200 font-mono animate-pulse">
                    FAULT ACTIVE
                  </span>
                )}
              </div>
              <p className="text-[10px] text-gray-400 leading-tight">
                Applies 6 MW fault load to trigger severe voltage sag across feeder nodes.
              </p>
              <div className="mt-2 text-[9px] font-mono text-amber-400">
                {loadingAction === "short_circuit" ? "Applying fault..." : "Duration: 6 ticks"}
              </div>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
