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
  const isStreaming = latestState !== null;

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
    if (busIndex === 0) return "#9CA3AF"; // Subdued neutral for 33kV at rest
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
      className="relative w-full h-full min-h-[420px] bg-[#08090D] rounded-[10px] overflow-hidden border border-white/[0.07] flex flex-col select-none"
    >
      {/* Top Banner: Fallback Mode Badge & Legend */}
      <div className="absolute top-3 left-3 right-3 z-10 flex flex-wrap items-center justify-between gap-2 pointer-events-none">
        {/* Caption & Offline Map Badge */}
        <div className="pointer-events-auto flex items-center space-x-2 bg-[#0E1118]/90 backdrop-blur-md px-3 py-1.5 rounded-[6px] border border-white/[0.08] shadow-lg">
          <Layers className="w-3.5 h-3.5 text-[#A78BFA]" />
          <span className="text-xs font-semibold text-[#EDEDF0] uppercase tracking-wider">
            Vector SCADA Schematic
          </span>
          <span className="text-[10px] px-2 py-0.5 rounded-full bg-[#131722] text-[#9CA3AF] font-mono border border-white/[0.06] flex items-center space-x-1.5">
            <span className={`w-1.5 h-1.5 rounded-full ${isStreaming ? "bg-[#10B981]" : "bg-[#5A6275]"}`}></span>
            <span>OFFLINE MAP MODE</span>
          </span>
        </div>

        {/* Action button & Legend */}
        <div className="pointer-events-auto flex items-center space-x-3 bg-[#0E1118]/90 backdrop-blur-md px-3 py-1.5 rounded-[6px] border border-white/[0.08] text-[11px] shadow-lg">
          {onRetryMapbox && (
            <button
              onClick={onRetryMapbox}
              className="text-[#9CA3AF] hover:text-[#EDEDF0] flex items-center space-x-1 pr-2 border-r border-white/[0.08] font-medium"
              title="Attempt reconnecting to Mapbox GL tile service"
            >
              <RefreshCw className="w-3 h-3" />
              <span>Retry Mapbox</span>
            </button>
          )}

          <div className="flex items-center space-x-1.5">
            <span className="w-2 h-2 rounded-full bg-[#10B981]" />
            <span className="text-[#9CA3AF]">Normal</span>
          </div>
          <div className="flex items-center space-x-1.5">
            <span className="w-2 h-2 rounded-full bg-[#F59E0B]" />
            <span className="text-[#9CA3AF]">Fault</span>
          </div>
          <div className="flex items-center space-x-1.5">
            <span className="w-2 h-2 rounded-full bg-[#EF4444]" />
            <span className="text-[#9CA3AF]">Cyber</span>
          </div>
        </div>
      </div>

      {/* SVG Canvas Schematic */}
      <div className="relative flex-1 w-full h-full flex items-center justify-center p-4 bg-[#08090D] overflow-hidden">
        {/* Background Subtle Grid Pattern */}
        <div
          className="absolute inset-0 opacity-10 pointer-events-none"
          style={{
            backgroundImage:
              "linear-gradient(to right, #1E2433 1px, transparent 1px), linear-gradient(to bottom, #1E2433 1px, transparent 1px)",
            backgroundSize: "28px 28px",
          }}
        />

        <svg
          className="w-full h-full max-h-[580px] max-w-[850px]"
          viewBox="-240 -200 480 380"
        >
          <defs>
            <filter id="fallback-glow-fault" x="-30%" y="-30%" width="160%" height="160%">
              <feGaussianBlur stdDeviation="4" result="blur" />
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
            const isCyber = toVerdict?.verdict === "Cyber Intrusion";
            const isFault = toVerdict?.verdict === "Natural Fault";
            const hasAnomaly = isCyber || isFault || isTripped;

            // Geometry calculations for collision-free line distance labels
            const dx = x2 - x1;
            const dy = y2 - y1;
            const len = Math.hypot(dx, dy) || 1;
            const mx = (x1 + x2) / 2;
            const my = (y1 + y2) / 2;

            let labelX = mx;
            let labelY = my;
            let textAnchor: "start" | "middle" | "end" = "middle";
            let dominantBaseline: "auto" | "central" | "middle" = "auto";

            if (Math.abs(dx) < 1) {
              // Strictly vertical line (e.g., L1, L3, L4): offset cleanly to the right
              labelX = mx + 10;
              labelY = my;
              textAnchor = "start";
              dominantBaseline = "central";
            } else if (Math.abs(dy) < 1) {
              // Strictly horizontal line: offset above
              labelX = mx;
              labelY = my - 10;
              textAnchor = "middle";
            } else {
              // Diagonal line (e.g., L0, L2): offset along perpendicular vector pointing upward
              let nx = -dy / len;
              let ny = dx / len;
              if (ny > 0) {
                nx = -nx;
                ny = -ny;
              }
              labelX = mx + nx * 12;
              labelY = my + ny * 12;
              textAnchor = "middle";
            }

            return (
              <g key={`fallback-line-${line.line_index}`} data-testid={`fallback-line-${line.line_index}`}>
                {/* Outer Base Line (Hairline quiet track) */}
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
                      : "#1E2433"
                  }
                  strokeWidth={hasAnomaly || isTripped ? 6 : 2}
                  strokeOpacity={hasAnomaly || isTripped ? 0.3 : 1}
                  strokeLinecap="round"
                />

                {/* Telemetry Stream Animated Pulse Line (Active ONLY when streaming) */}
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
                      : isStreaming
                      ? "#3A4660"
                      : "#1E2433"
                  }
                  strokeWidth={hasAnomaly || isTripped ? 2.5 : 1.5}
                  strokeDasharray={isTripped ? "6,4" : isStreaming ? "4,6" : undefined}
                  className={
                    isTripped || hasAnomaly
                      ? "animate-pulse"
                      : isStreaming
                      ? "animate-telemetry-flow"
                      : ""
                  }
                />

                {/* Line Distance Micro-Label with crisp halo for high legibility */}
                <text
                  x={labelX}
                  y={labelY}
                  textAnchor={textAnchor}
                  dominantBaseline={dominantBaseline}
                  fill="#5A6275"
                  fontSize="8.5"
                  fontFamily="monospace"
                  stroke="#08090D"
                  strokeWidth="3"
                  strokeLinejoin="round"
                  paintOrder="stroke fill"
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
            const verdict = getBusVerdict(bus.bus_index);
            const isSelected = selectedBusId === bus.bus_index;
            const rtuId = busToRtuMap[bus.bus_index];
            const isCyber = verdict?.verdict === "Cyber Intrusion";
            const isFault = verdict?.verdict === "Natural Fault";
            const hasAnomaly = isCyber || isFault;

            // Rest state colors: quiet near-black fill with crisp hairline border
            const nodeFill = hasAnomaly ? (isCyber ? "#EF4444" : "#F59E0B") : "#0E1118";
            const nodeBorder = hasAnomaly ? "#FFFFFF" : isSelected ? "#FFFFFF" : "#2A3245";
            const nodeTextFill = hasAnomaly ? "#FFFFFF" : "#EDEDF0";

            // Optimal text layout per bus position to avoid collision with outgoing feeder branches
            let nameX = cx;
            let nameY = cy + 22;
            let rtuX = cx;
            let rtuY = cy + 33;
            let textAnchor: "start" | "middle" | "end" = "middle";

            if (bus.bus_index === 1) {
              // Substation (Bus 1): Place labels ABOVE node so downward branches (L0, L1, L2) stay clear
              nameX = cx;
              nameY = cy - 15;
              rtuX = cx;
              rtuY = cy - 27;
              textAnchor = "middle";
            } else if (bus.bus_index === 3) {
              // Bus 3: Has top incoming line (L1) and bottom outgoing line (L4) -> Place labels to the LEFT
              nameX = cx - 18;
              nameY = cy - 2;
              rtuX = cx - 18;
              rtuY = cy + 10;
              textAnchor = "end";
            }

            return (
              <g
                key={`fallback-bus-${bus.bus_index}`}
                data-testid={`fallback-bus-${bus.bus_index}`}
                onClick={() => onSelectBus && onSelectBus(bus.bus_index)}
                className="cursor-pointer group"
              >
                {/* Ping ring for active anomalies only */}
                {hasAnomaly && (
                  <circle
                    cx={cx}
                    cy={cy}
                    r={22}
                    fill="none"
                    stroke={isCyber ? "#EF4444" : "#F59E0B"}
                    strokeWidth={1.5}
                    opacity={0.6}
                    className="animate-ping"
                  />
                )}

                {/* Selection ring */}
                {isSelected && (
                  <circle
                    cx={cx}
                    cy={cy}
                    r={bus.bus_index === 0 ? 18 : 16}
                    fill="none"
                    stroke="#FFFFFF"
                    strokeWidth={1.5}
                    strokeDasharray="3,2"
                  />
                )}

                {/* Circle Marker */}
                <circle
                  cx={cx}
                  cy={cy}
                  r={bus.bus_index === 0 ? 14 : 12}
                  fill={nodeFill}
                  stroke={nodeBorder}
                  strokeWidth={isSelected || hasAnomaly ? 2 : 1.25}
                  filter={
                    isCyber
                      ? "url(#fallback-glow-cyber)"
                      : isFault
                      ? "url(#fallback-glow-fault)"
                      : undefined
                  }
                  className="transition-all duration-200 group-hover:stroke-[#EDEDF0]"
                />

                {/* Bus Symbol / Identifier */}
                <text
                  x={cx}
                  y={cy + 3.5}
                  textAnchor="middle"
                  fill={nodeTextFill}
                  fontSize={bus.bus_index === 0 ? "9" : "10"}
                  fontWeight="bold"
                  fontFamily="monospace"
                  pointerEvents="none"
                >
                  {bus.bus_index === 0 ? "HV" : `B${bus.bus_index}`}
                </text>

                {/* Bus Name with protective dark halo */}
                <text
                  x={nameX}
                  y={nameY}
                  textAnchor={textAnchor}
                  fill={isSelected ? "#EDEDF0" : "#9CA3AF"}
                  fontSize="9.5"
                  fontWeight={isSelected ? "bold" : "500"}
                  fontFamily="sans-serif"
                  stroke="#08090D"
                  strokeWidth="3"
                  strokeLinejoin="round"
                  paintOrder="stroke fill"
                >
                  {bus.name}
                </text>

                {/* RTU tag in Monospace with protective dark halo */}
                {rtuId && (
                  <text
                    x={rtuX}
                    y={rtuY}
                    textAnchor={textAnchor}
                    fill={hasAnomaly ? (isCyber ? "#EF4444" : "#F59E0B") : "#5A6275"}
                    fontSize="8.5"
                    fontFamily="monospace"
                    fontWeight="600"
                    stroke="#08090D"
                    strokeWidth="2.5"
                    strokeLinejoin="round"
                    paintOrder="stroke fill"
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
        <div className="absolute bottom-10 right-3 z-20 w-72 bg-[#0E1118]/95 backdrop-blur-md rounded-[10px] border border-white/[0.08] shadow-2xl p-3 text-xs select-none">
          <div className="flex items-center justify-between border-b border-white/[0.07] pb-2 mb-2">
            <div className="flex items-center space-x-2">
              <div
                className="w-2.5 h-2.5 rounded-full"
                style={{ backgroundColor: getBusColor(selectedBusInfo.bus.bus_index) }}
              />
              <span className="font-bold text-[#EDEDF0] text-xs">
                {selectedBusInfo.bus.name}
              </span>
            </div>
            <button
              onClick={() => onSelectBus && onSelectBus(null)}
              className="text-[#5A6275] hover:text-[#EDEDF0] text-xs px-1.5 py-0.5 rounded-[4px] bg-[#131722] border border-white/[0.06]"
            >
              ✕
            </button>
          </div>

          <div className="space-y-1.5 font-mono text-[11px]">
            {/* Specs */}
            <div className="grid grid-cols-2 gap-1.5 bg-[#131722] p-2 rounded-[6px] border border-white/[0.05]">
              <div>
                <span className="text-[#5A6275] block text-[9px] uppercase tracking-wider">NOMINAL KV</span>
                <span className="text-[#EDEDF0] font-semibold">{selectedBusInfo.bus.vn_kv} kV</span>
              </div>
              <div>
                <span className="text-[#5A6275] block text-[9px] uppercase tracking-wider">ASSET</span>
                <span className="text-[#A78BFA] font-semibold">
                  {selectedBusInfo.rtuId ? `RTU-${selectedBusInfo.rtuId}` : "Substation Tx"}
                </span>
              </div>
            </div>

            {/* Telemetry */}
            {selectedBusInfo.telemetry && (
              <div className="bg-[#131722] p-2 rounded-[6px] border border-white/[0.05] space-y-1">
                <div className="flex justify-between">
                  <span className="text-[#5A6275]">Reported Voltage:</span>
                  <span className="text-[#EDEDF0] font-bold">
                    {selectedBusInfo.telemetry.voltage_pu.toFixed(4)} pu
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-[#5A6275]">Active Power:</span>
                  <span className="text-[#10B981] font-semibold">
                    {selectedBusInfo.telemetry.p_mw.toFixed(3)} MW
                  </span>
                </div>
              </div>
            )}

            {/* Verdict */}
            {selectedBusInfo.verdict ? (
              <div
                className="p-2 rounded-[6px] border"
                style={{
                  backgroundColor: `${getVerdictColor(selectedBusInfo.verdict.verdict)}12`,
                  borderColor: `${getVerdictColor(selectedBusInfo.verdict.verdict)}35`,
                }}
              >
                <div className="flex items-center justify-between mb-0.5">
                  <span className="text-[#5A6275] text-[10px]">Verdict:</span>
                  <span
                    className="font-bold uppercase tracking-wider text-[10px]"
                    style={{ color: getVerdictColor(selectedBusInfo.verdict.verdict) }}
                  >
                    {selectedBusInfo.verdict.verdict}
                  </span>
                </div>
                <div className="flex items-center justify-between text-[10px] text-[#5A6275]">
                  <span>Subtype: {selectedBusInfo.verdict.subtype || "none"}</span>
                  <span className="font-semibold text-[#9CA3AF]">
                    CONF: {(selectedBusInfo.verdict.confidence * 100).toFixed(0)}%
                  </span>
                </div>
              </div>
            ) : (
              <div className="text-[#5A6275] text-center py-1 text-[10px]">No RTU verdict</div>
            )}
          </div>
        </div>
      )}

      {/* Footer Caption */}
      <div className="w-full bg-[#0E1118] px-3 py-1.5 border-t border-white/[0.07] text-[10px] text-[#5A6275] flex items-center justify-between">
        <span>
          11kV Radial Distribution Substation Topology · Vector SCADA Engine
        </span>
        <span className="font-mono text-[#5A6275]">Autonomous Offline Resilient</span>
      </div>
    </div>
  );
};

