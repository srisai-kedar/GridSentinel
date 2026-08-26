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
    icon: <CheckCircle2 className="w-3.5 h-3.5 text-[#10B981]" />,
  };

  if (!latestState) {
    overallHealth = {
      label: "NO TELEMETRY STREAM",
      verdict: "No Data",
      color: SCADA_COLORS.NODATA,
      icon: <Radio className="w-3.5 h-3.5 text-[#5A6275]" />,
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
        icon: <ShieldAlert className="w-3.5 h-3.5 text-[#EF4444] animate-pulse" />,
      };
    } else if (hasFault) {
      overallHealth = {
        label: "WARNING: PHYSICAL FAULT DETECTED",
        verdict: "Natural Fault",
        color: SCADA_COLORS.FAULT,
        icon: <AlertTriangle className="w-3.5 h-3.5 text-[#F59E0B] animate-pulse" />,
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
    <header className="w-full bg-[#0E1118] border-b border-white/[0.07] px-4 py-2 flex flex-wrap items-center justify-between text-xs select-none shadow-sm z-30">
      {/* Brand & Subtitle */}
      <div className="flex items-center space-x-3">
        <div className="flex items-center space-x-2">
          <div className="w-2 h-2 rounded-full bg-[#10B981]" />
          <span className="font-bold tracking-wider text-sm text-[#EDEDF0] uppercase">
            GridSentinel
          </span>
          <span className="text-[10px] px-1.5 py-0.5 rounded-[4px] bg-[#131722] text-[#9CA3AF] font-mono border border-white/[0.08]">
            SCADA L2/L3
          </span>
        </div>
        <div className="hidden md:block h-3.5 w-px bg-white/[0.08]" />
        <span className="hidden md:inline text-[#5A6275] text-[11px] font-sans">
          Physics-Aware Cyber-Physical Anomaly Detection
        </span>
      </div>

      {/* Center SCADA Telemetry Badges */}
      <div className="flex items-center space-x-2 md:space-x-3 my-1 md:my-0">
        {/* Sim Time */}
        <div className="flex items-center space-x-1.5 px-2.5 py-1 rounded-[6px] bg-[#131722] border border-white/[0.06]">
          <Clock className="w-3.5 h-3.5 text-[#9CA3AF]" />
          <span className="text-[#5A6275] text-[10px] uppercase font-mono tracking-wider">SIM CLOCK</span>
          <span className="text-[#EDEDF0] font-mono font-medium">{simTime}</span>
          <span className="text-[#5A6275] font-mono text-[10px]">({diurnal})</span>
        </div>

        {/* Total Load */}
        <div className="hidden lg:flex items-center space-x-1.5 px-2.5 py-1 rounded-[6px] bg-[#131722] border border-white/[0.06]">
          <Zap className="w-3.5 h-3.5 text-[#9CA3AF]" />
          <span className="text-[#5A6275] text-[10px] uppercase font-mono tracking-wider">FEEDER LOAD</span>
          <span className="text-[#EDEDF0] font-mono font-medium">{totalLoad}</span>
        </div>

        {/* State Estimation Status */}
        <div className="hidden xl:flex items-center space-x-1.5 px-2.5 py-1 rounded-[6px] bg-[#131722] border border-white/[0.06]">
          <Activity className="w-3.5 h-3.5 text-[#9CA3AF]" />
          <span className="text-[#EDEDF0] font-mono">{seStatus}</span>
        </div>

        {/* Overall Health Indicator */}
        <div
          className="flex items-center space-x-1.5 px-2.5 py-1 rounded-[6px] border font-medium font-mono text-[11px] tracking-wide"
          style={{
            borderColor: `${overallHealth.color}40`,
            backgroundColor: `${overallHealth.color}12`,
            color: overallHealth.color,
          }}
        >
          {overallHealth.icon}
          <span>{overallHealth.label}</span>
        </div>
      </div>

      {/* Right: Connection Status */}
      <div className="flex items-center space-x-3">
        <div className="flex items-center space-x-2 px-2.5 py-1 rounded-[6px] bg-[#131722] border border-white/[0.06]">
          {connectionStatus === "connected" && (
            <>
              <span className="relative flex h-2 w-2">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-[#10B981] opacity-75"></span>
                <span className="relative inline-flex rounded-full h-2 w-2 bg-[#10B981]"></span>
              </span>
              <Wifi className="w-3.5 h-3.5 text-[#10B981]" />
              <span className="text-[#10B981] font-mono text-[11px] font-medium">LIVE /ws/live</span>
            </>
          )}
          {connectionStatus === "connecting" && (
            <>
              <Radio className="w-3.5 h-3.5 text-[#F59E0B] animate-pulse" />
              <span className="text-[#F59E0B] font-mono text-[11px]">RECONNECTING...</span>
            </>
          )}
          {connectionStatus === "disconnected" && (
            <>
              <WifiOff className="w-3.5 h-3.5 text-[#EF4444]" />
              <span className="text-[#EF4444] font-mono text-[11px]">DISCONNECTED</span>
            </>
          )}
        </div>
      </div>
    </header>
  );
};

