"use client";

import React from "react";
import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  Clock,
  Radio,
  ShieldAlert,
  Wifi,
  WifiOff,
  Zap,
} from "lucide-react";
import { ConnectionStatus, LiveSocketPayload, VerdictType } from "@/lib/types";
import { SCADA_COLORS } from "@/lib/alertText";

interface StatusBarProps {
  connectionStatus: ConnectionStatus;
  latestState: LiveSocketPayload | null;
}

export const StatusBar: React.FC<StatusBarProps> = ({
  connectionStatus,
  latestState,
}) => {
  // Determine overall feeder health
  let overallHealth: {
    label: string;
    verdict: VerdictType;
    color: string;
    icon: React.ReactNode;
  } = {
    label: "ALL SYSTEMS NOMINAL",
    verdict: "Normal",
    color: SCADA_COLORS.NORMAL,
    icon: <CheckCircle2 className="w-4 h-4 text-emerald-400" />,
  };

  if (!latestState) {
    overallHealth = {
      label: "NO TELEMETRY STREAM",
      verdict: "No Data",
      color: SCADA_COLORS.NODATA,
      icon: <Radio className="w-4 h-4 text-gray-400 animate-pulse" />,
    };
  } else if (latestState.ml_verdicts) {
    const verdicts = Object.values(latestState.ml_verdicts);
    const hasCyber = verdicts.some((v) => v.verdict === "Cyber Intrusion");
    const hasFault = verdicts.some((v) => v.verdict === "Natural Fault");

    if (hasCyber) {
      overallHealth = {
        label: "CRITICAL: CYBER INTRUSION DETECTED",
        verdict: "Cyber Intrusion",
        color: SCADA_COLORS.CYBER,
        icon: <ShieldAlert className="w-4 h-4 text-red-500 animate-pulse" />,
      };
    } else if (hasFault) {
      overallHealth = {
        label: "WARNING: PHYSICAL FAULT DETECTED",
        verdict: "Natural Fault",
        color: SCADA_COLORS.FAULT,
        icon: <AlertTriangle className="w-4 h-4 text-amber-500 animate-pulse" />,
      };
    }
  }

  const simTime = latestState?.sim_time || "--:--:--";
  const diurnal = latestState?.diurnal_multiplier
    ? `${latestState.diurnal_multiplier.toFixed(2)}x`
    : "1.00x";
  const totalLoad = latestState?.true_physical_state?.total_load_mw
    ? `${latestState.true_physical_state.total_load_mw.toFixed(2)} MW`
    : "-- MW";
  const seStatus = latestState?.state_estimation?.success
    ? latestState.state_estimation.bad_data_detected
      ? "SE: Bad Data Detected"
      : "SE: Converged (Chi2 OK)"
    : "SE: Standby";

  return (
    <header className="w-full bg-[#0d121f] border-b border-gray-800 px-4 py-2.5 flex flex-wrap items-center justify-between text-xs select-none shadow-md z-30">
      {/* Brand & Subtitle */}
      <div className="flex items-center space-x-3">
        <div className="flex items-center space-x-2">
          <div className="w-2.5 h-2.5 rounded-full bg-emerald-500 shadow-[0_0_8px_#10B981]" />
          <span className="font-bold tracking-wider text-sm text-gray-100 uppercase">
            GridSentinel
          </span>
          <span className="text-[10px] px-1.5 py-0.5 rounded bg-gray-800 text-gray-300 font-mono border border-gray-700">
            SCADA L2/L3
          </span>
        </div>
        <div className="hidden md:block h-4 w-px bg-gray-700" />
        <span className="hidden md:inline text-gray-400 text-[11px]">
          Physics-Aware Cyber-Physical Anomaly Detection
        </span>
      </div>

      {/* Center SCADA Telemetry Badges */}
      <div className="flex items-center space-x-2 md:space-x-4 my-1 md:my-0">
        {/* Sim Time */}
        <div className="flex items-center space-x-1.5 px-2.5 py-1 rounded bg-[#131b2e] border border-gray-800">
          <Clock className="w-3.5 h-3.5 text-cyan-400" />
          <span className="text-gray-400 font-mono">SIM CLOCK:</span>
          <span className="text-cyan-300 font-mono font-semibold">{simTime}</span>
          <span className="text-gray-500 font-mono text-[10px]">({diurnal})</span>
        </div>

        {/* Total Load */}
        <div className="hidden lg:flex items-center space-x-1.5 px-2.5 py-1 rounded bg-[#131b2e] border border-gray-800">
          <Zap className="w-3.5 h-3.5 text-yellow-400" />
          <span className="text-gray-400">FEEDER LOAD:</span>
          <span className="text-yellow-300 font-mono font-semibold">{totalLoad}</span>
        </div>

        {/* State Estimation Status */}
        <div className="hidden xl:flex items-center space-x-1.5 px-2.5 py-1 rounded bg-[#131b2e] border border-gray-800">
          <Activity className="w-3.5 h-3.5 text-indigo-400" />
          <span className="text-gray-300 font-mono">{seStatus}</span>
        </div>

        {/* Overall Health Indicator */}
        <div
          className="flex items-center space-x-1.5 px-3 py-1 rounded border font-semibold font-mono tracking-wide"
          style={{
            borderColor: `${overallHealth.color}66`,
            backgroundColor: `${overallHealth.color}15`,
            color: overallHealth.color,
          }}
        >
          {overallHealth.icon}
          <span>{overallHealth.label}</span>
        </div>
      </div>

      {/* Right: Connection Status */}
      <div className="flex items-center space-x-3">
        <div className="flex items-center space-x-2 px-2.5 py-1 rounded bg-[#131b2e] border border-gray-800">
          {connectionStatus === "connected" && (
            <>
              <span className="relative flex h-2 w-2">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span>
              </span>
              <Wifi className="w-3.5 h-3.5 text-emerald-400" />
              <span className="text-emerald-400 font-mono font-medium">LIVE /ws/live</span>
            </>
          )}
          {connectionStatus === "connecting" && (
            <>
              <Radio className="w-3.5 h-3.5 text-amber-400 animate-pulse" />
              <span className="text-amber-400 font-mono">RECONNECTING...</span>
            </>
          )}
          {connectionStatus === "disconnected" && (
            <>
              <WifiOff className="w-3.5 h-3.5 text-rose-500" />
              <span className="text-rose-400 font-mono">DISCONNECTED</span>
            </>
          )}
        </div>
      </div>
    </header>
  );
};
