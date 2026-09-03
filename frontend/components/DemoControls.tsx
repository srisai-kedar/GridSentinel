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
  Lock,
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
  isReplayMode?: boolean;
}

export const DemoControls: React.FC<DemoControlsProps> = ({
  latestState,
  onActionComplete,
  isReplayMode = false,
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

  const showFeedback = (msg: string, isError: boolean = false) => {
    setActionFeedback({ message: msg, isError });
    if (onActionComplete) onActionComplete(msg);
    setTimeout(() => {
      setActionFeedback(null);
    }, 4000);
  };

  // Handlers
  const handleStartSim = async () => {
    if (isReplayMode) return;
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
    if (isReplayMode) return;
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
    if (isReplayMode) return;
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
    if (isReplayMode) return;
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
    if (isReplayMode) return;
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
    if (isReplayMode) return;
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
    if (isReplayMode) return;
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
    if (isReplayMode) return;
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
    <div className="flex flex-col h-full bg-[#0E1118] rounded-[10px] border border-white/[0.07] overflow-hidden text-xs select-none shadow-sm">
      {/* Header */}
      <div className="p-3 bg-[#0E1118] border-b border-white/[0.07] flex items-center justify-between">
        <div className="flex items-center space-x-2">
          <Terminal className="w-3.5 h-3.5 text-[#A78BFA]" />
          <h2 className="font-bold text-[#EDEDF0] uppercase tracking-wider text-xs">
            Scenario & Attack Injection Engine
          </h2>
        </div>

        {/* Global Simulation Toggle */}
        <div className="flex items-center space-x-1">
          <button
            onClick={handleStartSim}
            disabled={isReplayMode || loadingAction !== null}
            className="flex items-center space-x-1 bg-[#131722] hover:bg-[#181E2C] text-[#10B981] border border-[#10B981]/30 px-2.5 py-1 rounded-[4px] transition disabled:opacity-40 disabled:cursor-not-allowed font-medium text-[11px]"
            title={isReplayMode ? "Disabled in Replay Mode" : "Start background simulation loop"}
          >
            <Play className="w-3 h-3 fill-[#10B981]" />
            <span>Start OT</span>
          </button>
          <button
            onClick={handleStopSim}
            disabled={isReplayMode || loadingAction !== null}
            className="flex items-center space-x-1 bg-[#131722] hover:bg-[#181E2C] text-[#5A6275] hover:text-[#EDEDF0] border border-white/[0.08] px-2.5 py-1 rounded-[4px] transition disabled:opacity-40 disabled:cursor-not-allowed font-medium text-[11px]"
            title={isReplayMode ? "Disabled in Replay Mode" : "Stop simulation loop"}
          >
            <Pause className="w-3 h-3" />
            <span>Stop</span>
          </button>
        </div>
      </div>

      {/* Replay Mode Notice if active */}
      {isReplayMode && (
        <div className="p-2.5 bg-[#131722] border-b border-[#F59E0B]/30 text-[#F59E0B] flex items-center space-x-2 font-mono text-[11px]">
          <Lock className="w-3.5 h-3.5 text-[#F59E0B] shrink-0" />
          <span>Demo triggers are disabled during recorded session replay.</span>
        </div>
      )}

      {/* Action Notification Toast */}
      {actionFeedback && (
        <div
          className={`px-3 py-1.5 text-[11px] font-mono border-b flex items-center justify-between ${
            actionFeedback.isError
              ? "bg-[#131722] text-[#EF4444] border-[#EF4444]/30"
              : "bg-[#131722] text-[#10B981] border-[#10B981]/30"
          }`}
        >
          <span>{actionFeedback.message}</span>
        </div>
      )}

      {/* Target Selector Toolbar */}
      <div className="p-2 bg-[#131722] border-b border-white/[0.07] flex flex-wrap items-center gap-3 text-[11px]">
        <div className="flex items-center space-x-1.5">
          <span className="text-[#5A6275] font-mono text-[10px] uppercase">Target RTU:</span>
          <select
            value={selectedRtu}
            onChange={(e) => setSelectedRtu(parseInt(e.target.value, 10))}
            disabled={isReplayMode}
            className="bg-[#0E1118] text-[#EDEDF0] px-2 py-0.5 rounded-[4px] border border-white/[0.08] focus:outline-none disabled:opacity-50"
          >
            <option value={1}>RTU-1 (Substation-11kV)</option>
            <option value={2}>RTU-2 (Feeder A Industrial)</option>
            <option value={3}>RTU-3 (Feeder B Residential)</option>
            <option value={4}>RTU-4 (Feeder C Agriculture)</option>
            <option value={5}>RTU-5 (Feeder A2 Mixed)</option>
          </select>
        </div>

        <div className="flex items-center space-x-1.5">
          <span className="text-[#5A6275] font-mono text-[10px] uppercase">Target Line:</span>
          <select
            value={selectedLine}
            onChange={(e) => setSelectedLine(parseInt(e.target.value, 10))}
            disabled={isReplayMode}
            className="bg-[#0E1118] text-[#EDEDF0] px-2 py-0.5 rounded-[4px] border border-white/[0.08] focus:outline-none disabled:opacity-50"
          >
            <option value={0}>Line 0 (Substation → Feeder A)</option>
            <option value={1}>Line 1 (Substation → Feeder B)</option>
            <option value={2}>Line 2 (Substation → Feeder C)</option>
            <option value={3}>Line 3 (Feeder A → Feeder A2)</option>
            <option value={4}>Line 4 (Feeder B → Feeder B2)</option>
          </select>
        </div>

        <div className="flex items-center space-x-1.5">
          <span className="text-[#5A6275] font-mono text-[10px] uppercase">Target Bus:</span>
          <select
            aria-label="Target Bus"
            value={selectedBus}
            onChange={(e) => setSelectedBus(parseInt(e.target.value, 10))}
            disabled={isReplayMode}
            className="bg-[#0E1118] text-[#EDEDF0] px-2 py-0.5 rounded-[4px] border border-white/[0.08] focus:outline-none disabled:opacity-50"
          >
            <option value={1}>Bus 1 (Substation)</option>
            <option value={2}>Bus 2 (Feeder A)</option>
            <option value={3}>Bus 3 (Feeder B)</option>
            <option value={4}>Bus 4 (Feeder C)</option>
            <option value={5}>Bus 5 (Feeder A2)</option>
          </select>
        </div>
      </div>

      {/* Action Buttons Grid */}
      <div className="p-3 space-y-3 flex-1 min-h-0 overflow-y-auto">
        {/* Reset to Normal Button (Prominent) */}
        <button
          onClick={handleResetNormal}
          disabled={isReplayMode || loadingAction !== null}
          className="w-full flex items-center justify-center space-x-2 bg-[#131722] hover:bg-[#181E2C] text-[#EDEDF0] hover:text-[#10B981] font-semibold py-2 px-4 rounded-[6px] border border-white/[0.08] hover:border-[#10B981]/40 shadow-sm transition disabled:opacity-40 disabled:cursor-not-allowed text-xs tracking-wider uppercase"
        >
          <RotateCcw className={`w-3.5 h-3.5 ${loadingAction === "reset_all" ? "animate-spin" : ""}`} />
          <span>Reset Grid to Clean State</span>
        </button>

        {/* Section 1: Cyber Attack Scenarios */}
        <div>
          <div className="flex items-center space-x-1.5 text-[#EF4444] font-semibold uppercase tracking-wider text-[10px] mb-2">
            <ShieldAlert className="w-3.5 h-3.5" />
            <span>Cyber Attack Scenarios</span>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-2">
            {/* Silent Data Injection */}
            <button
              onClick={handleSilentDataInjection}
              disabled={isReplayMode || isSilentActive || loadingAction !== null}
              className={`p-2.5 rounded-[6px] border text-left flex flex-col justify-between transition ${
                isSilentActive
                  ? "bg-[#131722] border-[#EF4444]/60 text-[#EF4444] cursor-not-allowed"
                  : "bg-[#131722] hover:bg-[#181E2C] border-white/[0.06] text-[#EDEDF0] hover:border-[#EF4444]/40 disabled:opacity-40 disabled:cursor-not-allowed"
              }`}
            >
              <div className="flex items-center justify-between mb-1">
                <span className="font-semibold text-[11px]">Silent Data Injection</span>
                {isSilentActive && (
                  <span className="text-[9px] px-1.5 py-0.5 rounded-[4px] bg-[#EF4444]/20 text-[#EF4444] font-mono animate-pulse">
                    ACTIVE
                  </span>
                )}
              </div>
              <p className="text-[10px] text-[#5A6275] leading-tight">
                Overrides telemetry (1.15 pu V) without touching physics or Modbus packets.
              </p>
              <div className="mt-2 text-[9px] font-mono text-[#EF4444]">
                {loadingAction === "silent_data" ? "Triggering..." : "Target: RTU-" + selectedRtu}
              </div>
            </button>

            {/* Unauthorized Command Injection */}
            <button
              onClick={handleCommandInjection}
              disabled={isReplayMode || loadingAction !== null}
              className="p-2.5 rounded-[6px] border bg-[#131722] hover:bg-[#181E2C] border-white/[0.06] text-[#EDEDF0] hover:border-[#EF4444]/40 transition text-left flex flex-col justify-between disabled:opacity-40 disabled:cursor-not-allowed"
            >
              <div className="flex items-center justify-between mb-1">
                <span className="font-semibold text-[11px]">Command Injection</span>
              </div>
              <p className="text-[10px] text-[#5A6275] leading-tight">
                Sends unauthorized FC 06 Modbus Write; logged in SCADA traffic as anomaly.
              </p>
              <div className="mt-2 text-[9px] font-mono text-[#EF4444]">
                {loadingAction === "command_injection" ? "Injecting..." : "Write Reg 1 = 5000"}
              </div>
            </button>

            {/* Replay Attack */}
            <button
              onClick={handleReplayAttack}
              disabled={isReplayMode || isReplayActive || loadingAction !== null}
              className={`p-2.5 rounded-[6px] border text-left flex flex-col justify-between transition ${
                isReplayActive
                  ? "bg-[#131722] border-[#EF4444]/60 text-[#EF4444] cursor-not-allowed"
                  : "bg-[#131722] hover:bg-[#181E2C] border-white/[0.06] text-[#EDEDF0] hover:border-[#EF4444]/40 disabled:opacity-40 disabled:cursor-not-allowed"
              }`}
            >
              <div className="flex items-center justify-between mb-1">
                <span className="font-semibold text-[11px]">Replay Attack</span>
                {isReplayActive && (
                  <span className="text-[9px] px-1.5 py-0.5 rounded-[4px] bg-[#EF4444]/20 text-[#EF4444] font-mono animate-pulse">
                    ACTIVE
                  </span>
                )}
              </div>
              <p className="text-[10px] text-[#5A6275] leading-tight">
                Freezes and loops stale telemetry packets with 0 diurnal load variance.
              </p>
              <div className="mt-2 text-[9px] font-mono text-[#EF4444]">
                {loadingAction === "replay" ? "Freezing..." : "Duration: 20 ticks"}
              </div>
            </button>
          </div>
        </div>

        {/* Section 2: Physical Grid Faults */}
        <div>
          <div className="flex items-center space-x-1.5 text-[#F59E0B] font-semibold uppercase tracking-wider text-[10px] mb-2">
            <AlertTriangle className="w-3.5 h-3.5" />
            <span>Physical Grid Faults</span>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
            {/* Line Trip Outage */}
            <button
              onClick={handleLineTrip}
              disabled={isReplayMode || isLineTripActive || loadingAction !== null}
              className={`p-2.5 rounded-[6px] border text-left flex flex-col justify-between transition ${
                isLineTripActive
                  ? "bg-[#131722] border-[#F59E0B]/60 text-[#F59E0B] cursor-not-allowed"
                  : "bg-[#131722] hover:bg-[#181E2C] border-white/[0.06] text-[#EDEDF0] hover:border-[#F59E0B]/40 disabled:opacity-40 disabled:cursor-not-allowed"
              }`}
            >
              <div className="flex items-center justify-between mb-1">
                <span className="font-semibold text-[11px]">Physical Line Trip</span>
                {isLineTripActive && (
                  <span className="text-[9px] px-1.5 py-0.5 rounded-[4px] bg-[#F59E0B]/20 text-[#F59E0B] font-mono animate-pulse">
                    TRIPPED
                  </span>
                )}
              </div>
              <p className="text-[10px] text-[#5A6275] leading-tight">
                Takes line out of service in pandapower; real physical current drops to zero.
              </p>
              <div className="mt-2 text-[9px] font-mono text-[#F59E0B]">
                {loadingAction === "line_trip" ? "Tripping..." : "Trip Line " + selectedLine}
              </div>
            </button>

            {/* Short Circuit Fault */}
            <button
              onClick={handleShortCircuit}
              disabled={isReplayMode || isShortCircuitActive || loadingAction !== null}
              className={`p-2.5 rounded-[6px] border text-left flex flex-col justify-between transition ${
                isShortCircuitActive
                  ? "bg-[#131722] border-[#F59E0B]/60 text-[#F59E0B] cursor-not-allowed"
                  : "bg-[#131722] hover:bg-[#181E2C] border-white/[0.06] text-[#EDEDF0] hover:border-[#F59E0B]/40 disabled:opacity-40 disabled:cursor-not-allowed"
              }`}
            >
              <div className="flex items-center justify-between mb-1">
                <span className="font-semibold text-[11px]">Short-Circuit Surge</span>
                {isShortCircuitActive && (
                  <span className="text-[9px] px-1.5 py-0.5 rounded-[4px] bg-[#F59E0B]/20 text-[#F59E0B] font-mono animate-pulse">
                    FAULT ACTIVE
                  </span>
                )}
              </div>
              <p className="text-[10px] text-[#5A6275] leading-tight">
                Applies 6 MW fault load to trigger severe voltage sag across feeder nodes.
              </p>
              <div className="mt-2 text-[9px] font-mono text-[#F59E0B]">
                {loadingAction === "short_circuit" ? "Applying fault..." : "Duration: 6 ticks"}
              </div>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
