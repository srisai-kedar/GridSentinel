"use client";

import React, { useMemo } from "react";
import {
  BusTopology,
  LineTopology,
  LiveSocketPayload,
  RTUVerdict,
  TopologyResponse,
} from "@/lib/types";
import { getVerdictColor, SCADA_COLORS } from "@/lib/alertText";
import {
  Activity,
  AlertCircle,
  AlertTriangle,
  Compass,
  Layers,
  MapPin,
  RefreshCw,
  ShieldAlert,
  Zap,
} from "lucide-react";

interface FeederMapFallbackProps {
  topology: TopologyResponse | null;
  latestState: LiveSocketPayload | null;
  selectedBusId?: number | null;
  onSelectBus?: (busIndex: number | null) => void;
  onRetryMapbox?: () => void;
  isForced?: boolean;
}

export const FeederMapFallback: React.FC<FeederMapFallbackProps> = ({
  topology,
  latestState,
  selectedBusId,
  onSelectBus,
  onRetryMapbox,
  isForced = false,
}) => {
  const busToRtuMap = useMemo<Record<number, number>>(
    () => ({
      1: 1,
      2: 2,
      3: 3,
      4: 4,
      5: 5,
    }),
    []
  );

  const getBusVerdict = (busIndex: number): RTUVerdict | null => {
    const rtuId = busToRtuMap[busIndex];
    if (!rtuId || !latestState?.ml_verdicts) return null;
    return latestState.ml_verdicts[String(rtuId)] || latestState.ml_verdicts[rtuId] || null;
  };

  const getBusColor = (busIndex: number): string => {
    if (busIndex === 0) return "#38BDF8"; // 33kV HV Grid Bus (Cyan)
    const verdict = getBusVerdict(busIndex);
    if (!verdict) return SCADA_COLORS.NODATA;
    return getVerdictColor(verdict.verdict);
  };

  const selectedBusInfo = useMemo(() => {
    if (selectedBusId === null || selectedBusId === undefined || !topology) return null;
    const bus = topology.buses.find((b) => b.bus_index === selectedBusId);
    if (!bus) return null;

    const rtuId = busToRtuMap[selectedBusId];
    const verdict = getBusVerdict(selectedBusId);
    const telemetry = latestState?.polled_modbus_telemetry?.[String(rtuId)];
    const truePhysical = latestState?.true_physical_state?.bus_voltages?.find(
      (v) => v.bus_index === selectedBusId
    );
    const estimated = latestState?.state_estimation?.estimated_voltages?.find(
      (ev) => ev.bus_index === selectedBusId
    );

    return {
      bus,
      rtuId,
      verdict,
      telemetry,
      truePhysical,
      estimated,
    };
  }, [selectedBusId, topology, latestState, busToRtuMap]);

  return (
    <div
      data-testid="feeder-map-fallback"
      className="relative w-full h-full min-h-[420px] bg-[#070B14] rounded-lg overflow-hidden border border-gray-800 flex flex-col select-none"
    >
      {/* Top Banner: Fallback Mode Badge */}
      <div className="absolute top-3 left-3 right-3 z-10 flex flex-wrap items-center justify-between gap-2 pointer-events-none">
        {/* Caption & Offline Map Badge */}
        <div className="pointer-events-auto flex items-center space-x-2 bg-[#0F172A]/95 backdrop-blur-md px-3 py-1.5 rounded-md border border-amber-800/80 shadow-lg">
          <Layers className="w-4 h-4 text-amber-400" />
          <span className="text-xs font-bold text-amber-200 uppercase tracking-wider">
            Vector SCADA Schematic
          </span>
          <span className="text-[10px] px-2 py-0.5 rounded-full bg-amber-950 text-amber-300 font-mono border border-amber-700/60 flex items-center space-x-1">
            <span className="w-1.5 h-1.5 rounded-full bg-amber-400 animate-pulse"></span>
            <span>{isForced ? "FORCED FALLBACK" : "OFFLINE MAP MODE"}</span>
          </span>
        </div>

        {/* Action button & Legend */}
        <div className="pointer-events-auto flex items-center space-x-3 bg-[#0F172A]/95 backdrop-blur-md px-3 py-1.5 rounded-md border border-gray-700/80 text-[11px] shadow-lg">
          {onRetryMapbox && (
            <button
              onClick={onRetryMapbox}
              className="text-cyan-400 hover:text-cyan-200 flex items-center space-x-1 pr-2 border-r border-gray-700 font-medium"
              title="Attempt reconnecting to Mapbox GL tile service"
            >
              <RefreshCw className="w-3 h-3" />
              <span>Retry Mapbox</span>
            </button>
          )}

          <div className="flex items-center space-x-2">
            <span className="w-2.5 h-2.5 rounded-full bg-[#10B981]" />
            <span className="text-gray-300">Normal</span>
          </div>
          <div className="flex items-center space-x-2">
            <span className="w-2.5 h-2.5 rounded-full bg-[#F59E0B]" />
            <span className="text-gray-300">Fault</span>
          </div>
          <div className="flex items-center space-x-2">
            <span className="w-2.5 h-2.5 rounded-full bg-[#EF4444] animate-pulse" />
            <span className="text-gray-300">Cyber</span>
          </div>
        </div>
      </div>

      {/* SVG Canvas Schematic */}
      <div className="relative flex-1 w-full h-full flex items-center justify-center p-4 bg-[#080D1A] overflow-hidden">
        {/* Background Grid Pattern */}
        <div
          className="absolute inset-0 opacity-20 pointer-events-none"
          style={{
            backgroundImage:
              "linear-gradient(to right, #1e293b 1px, transparent 1px), linear-gradient(to bottom, #1e293b 1px, transparent 1px)",
            backgroundSize: "32px 32px",
          }}
        />

        <svg
          className="w-full h-full max-h-[580px] max-w-[850px]"
          viewBox="-240 -200 480 380"
        >
          <defs>
            <filter id="fallback-glow-normal" x="-20%" y="-20%" width="140%" height="140%">
              <feGaussianBlur stdDeviation="3" result="blur" />
              <feMerge>
                <feMergeNode in="blur" />
                <feMergeNode in="SourceGraphic" />
              </feMerge>
            </filter>
            <filter id="fallback-glow-cyber" x="-30%" y="-30%" width="160%" height="160%">
              <feGaussianBlur stdDeviation="5" result="blur" />
              <feMerge>
                <feMergeNode in="blur" />
                <feMergeNode in="SourceGraphic" />
              </feMerge>
            </filter>
          </defs>

          {/* Draw Lines */}
          {topology?.lines.map((line) => {
            const fromBus = topology.buses.find((b) => b.bus_index === line.from_bus);
            const toBus = topology.buses.find((b) => b.bus_index === line.to_bus);
            if (!fromBus || !toBus) return null;

            const x1 = fromBus.x * 60;
            const y1 = -fromBus.y * 45 - 60;
            const x2 = toBus.x * 60;
            const y2 = -toBus.y * 45 - 60;

            const isTripped =
              latestState?.active_scenarios?.tripped_lines?.includes(line.line_index);
            const toVerdict = getBusVerdict(line.to_bus);
            const hasAnomaly =
              toVerdict?.verdict === "Cyber Intrusion" ||
              toVerdict?.verdict === "Natural Fault" ||
              isTripped;

            return (
              <g key={`fallback-line-${line.line_index}`} data-testid={`fallback-line-${line.line_index}`}>
                {/* Outer Glow */}
                <line
                  x1={x1}
                  y1={y1}
                  x2={x2}
                  y2={y2}
                  stroke={
                    isTripped
                      ? "#DC2626"
                      : hasAnomaly
                      ? getVerdictColor(toVerdict?.verdict || "Normal")
                      : "#38BDF8"
                  }
                  strokeWidth={hasAnomaly || isTripped ? 8 : 4}
                  strokeOpacity={hasAnomaly || isTripped ? 0.4 : 0.25}
                  strokeLinecap="round"
                />
                {/* Core Line */}
                <line
                  x1={x1}
                  y1={y1}
                  x2={x2}
                  y2={y2}
                  stroke={
                    isTripped
                      ? "#EF4444"
                      : hasAnomaly
                      ? getVerdictColor(toVerdict?.verdict || "Normal")
                      : "#38BDF8"
                  }
                  strokeWidth={hasAnomaly || isTripped ? 3.5 : 2.5}
                  strokeDasharray={isTripped || hasAnomaly ? "6,4" : undefined}
                  className={hasAnomaly || isTripped ? "animate-pulse" : ""}
                />
                {/* Label */}
                <text
                  x={(x1 + x2) / 2 + 8}
                  y={(y1 + y2) / 2 - 6}
                  fill="#64748B"
                  fontSize="9"
                  fontFamily="monospace"
                >
                  {line.name} ({line.length_km}km)
                </text>
              </g>
            );
          })}

          {/* Draw Buses */}
          {topology?.buses.map((bus) => {
            const cx = bus.x * 60;
            const cy = -bus.y * 45 - 60;
            const color = getBusColor(bus.bus_index);
            const verdict = getBusVerdict(bus.bus_index);
            const isSelected = selectedBusId === bus.bus_index;
            const rtuId = busToRtuMap[bus.bus_index];

            return (
              <g
                key={`fallback-bus-${bus.bus_index}`}
                data-testid={`fallback-bus-${bus.bus_index}`}
                onClick={() => onSelectBus && onSelectBus(bus.bus_index)}
                className="cursor-pointer group"
              >
                {/* Ping ring for active anomalies */}
                {verdict && verdict.verdict !== "Normal" && (
                  <circle
                    cx={cx}
                    cy={cy}
                    r={24}
                    fill="none"
                    stroke={color}
                    strokeWidth={2}
                    opacity={0.6}
                    className="animate-ping"
                  />
                )}

                {/* Selection ring */}
                {isSelected && (
                  <circle
                    cx={cx}
                    cy={cy}
                    r={21}
                    fill="none"
                    stroke="#FFFFFF"
                    strokeWidth={2.5}
                    strokeDasharray="4,2"
                  />
                )}

                {/* Circle Marker */}
                <circle
                  cx={cx}
                  cy={cy}
                  r={bus.bus_index === 0 ? 15 : 13}
                  fill={color}
                  stroke="#FFFFFF"
                  strokeWidth={isSelected ? 3 : 2}
                  filter={
                    verdict?.verdict === "Cyber Intrusion"
                      ? "url(#fallback-glow-cyber)"
                      : "url(#fallback-glow-normal)"
                  }
                  className="transition-transform duration-200 group-hover:scale-110"
                />

                {/* Bus Symbol / Text */}
                <text
                  x={cx}
                  y={cy + 4}
                  textAnchor="middle"
                  fill="#FFFFFF"
                  fontSize={bus.bus_index === 0 ? "10" : "11"}
                  fontWeight="bold"
                  fontFamily="monospace"
                  pointerEvents="none"
                >
                  {bus.bus_index === 0 ? "HV" : `B${bus.bus_index}`}
                </text>

                {/* Bus Name */}
                <text
                  x={cx}
                  y={cy + 25}
                  textAnchor="middle"
                  fill={isSelected ? "#FFFFFF" : "#CBD5E1"}
                  fontSize="10"
                  fontWeight={isSelected ? "bold" : "normal"}
                  fontFamily="sans-serif"
                >
                  {bus.name}
                </text>

                {/* RTU tag */}
                {rtuId && (
                  <text
                    x={cx}
                    y={cy + 37}
                    textAnchor="middle"
                    fill={color}
                    fontSize="9"
                    fontFamily="monospace"
                  >
                    [RTU-{rtuId}]
                  </text>
                )}
              </g>
            );
          })}
        </svg>
      </div>

      {/* Selected Bus Floating Detail Card */}
      {selectedBusInfo && (
        <div className="absolute bottom-10 right-3 z-20 w-80 bg-[#0F172A]/95 backdrop-blur-md rounded-lg border border-gray-700 shadow-2xl p-3.5 text-xs select-none">
          <div className="flex items-center justify-between border-b border-gray-700 pb-2 mb-2.5">
            <div className="flex items-center space-x-2">
              <div
                className="w-3 h-3 rounded-full"
                style={{ backgroundColor: getBusColor(selectedBusInfo.bus.bus_index) }}
              />
              <span className="font-bold text-gray-100 text-sm">
                {selectedBusInfo.bus.name}
              </span>
            </div>
            <button
              onClick={() => onSelectBus && onSelectBus(null)}
              className="text-gray-400 hover:text-white text-xs px-1.5 py-0.5 rounded bg-gray-800"
            >
              ✕
            </button>
          </div>

          <div className="space-y-2 font-mono text-[11px]">
            {/* Specs */}
            <div className="grid grid-cols-2 gap-2 bg-slate-900/80 p-2 rounded border border-gray-800">
              <div>
                <span className="text-gray-500 block text-[10px]">NOMINAL KV</span>
                <span className="text-gray-200 font-semibold">{selectedBusInfo.bus.vn_kv} kV</span>
              </div>
              <div>
                <span className="text-gray-500 block text-[10px]">ASSET MAPPING</span>
                <span className="text-cyan-400 font-semibold">
                  {selectedBusInfo.rtuId ? `RTU-${selectedBusInfo.rtuId}` : "Substation Tx"}
                </span>
              </div>
            </div>

            {/* Telemetry */}
            {selectedBusInfo.telemetry && (
              <div className="bg-slate-900/80 p-2 rounded border border-gray-800 space-y-1">
                <div className="flex justify-between">
                  <span className="text-gray-400">Reported Voltage:</span>
                  <span className="text-yellow-300 font-bold">
                    {selectedBusInfo.telemetry.voltage_pu.toFixed(4)} pu
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-400">Active Power:</span>
                  <span className="text-emerald-400 font-semibold">
                    {selectedBusInfo.telemetry.p_mw.toFixed(3)} MW
                  </span>
                </div>
              </div>
            )}

            {/* Verdict */}
            {selectedBusInfo.verdict ? (
              <div
                className="p-2 rounded border"
                style={{
                  backgroundColor: `${getVerdictColor(selectedBusInfo.verdict.verdict)}15`,
                  borderColor: `${getVerdictColor(selectedBusInfo.verdict.verdict)}66`,
                }}
              >
                <div className="flex items-center justify-between mb-1">
                  <span className="text-gray-400">Verdict:</span>
                  <span
                    className="font-bold uppercase tracking-wider"
                    style={{ color: getVerdictColor(selectedBusInfo.verdict.verdict) }}
                  >
                    {selectedBusInfo.verdict.verdict}
                  </span>
                </div>
                <div className="flex items-center justify-between text-[10px] text-gray-400">
                  <span>Subtype: {selectedBusInfo.verdict.subtype || "none"}</span>
                  <span className="font-semibold text-gray-300">
                    Conf: {(selectedBusInfo.verdict.confidence * 100).toFixed(1)}%
                  </span>
                </div>
              </div>
            ) : (
              <div className="text-gray-500 text-center py-1">No RTU verdict</div>
            )}
          </div>
        </div>
      )}

      {/* Footer Caption */}
      <div className="w-full bg-[#0B0F19] px-3 py-1.5 border-t border-gray-800 text-[10px] text-gray-400 flex items-center justify-between">
        <span>
          Illustrative SCADA Feeder Topology (Anchor: 11kV Radial Distribution Substation). Vector SCADA Engine.
        </span>
        <span className="font-mono text-gray-500">Autonomous Offline Resilient</span>
      </div>
    </div>
  );
};
