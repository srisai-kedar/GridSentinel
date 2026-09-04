"use client";

import React, { useMemo } from "react";
import { Layers, RefreshCw } from "lucide-react";
import { BusTopology, LiveSocketPayload, RTUVerdict, TopologyResponse } from "@/lib/types";
import { getVerdictColor, SCADA_COLORS } from "@/lib/alertText";

interface FeederMapFallbackProps {
  topology: TopologyResponse | null;
  latestState: LiveSocketPayload | null;
  selectedBusId?: number | null;
  onSelectBus?: (busIndex: number | null) => void;
  onRetryMapbox?: () => void;
  isForced?: boolean;
}

const busToRtu: Record<number, number> = { 1: 1, 2: 2, 3: 3, 4: 4, 5: 5 };

export const FeederMapFallback: React.FC<FeederMapFallbackProps> = ({
  topology,
  latestState,
  selectedBusId,
  onSelectBus,
  onRetryMapbox,
  isForced = false,
}) => {
  const getVerdict = (busIndex: number): RTUVerdict | null => {
    const rtuId = busToRtu[busIndex];
    if (!rtuId || !latestState?.ml_verdicts) return null;
    return latestState.ml_verdicts[String(rtuId)] || latestState.ml_verdicts[rtuId] || null;
  };

  const selectedBusInfo = useMemo(() => {
    if (selectedBusId === null || selectedBusId === undefined || !topology) return null;
    const bus = topology.buses.find((item) => item.bus_index === selectedBusId);
    if (!bus) return null;
    const rtuId = busToRtu[selectedBusId];
    return {
      bus,
      rtuId,
      verdict: getVerdict(selectedBusId),
      telemetry: latestState?.polled_modbus_telemetry?.[String(rtuId)],
      estimated: latestState?.state_estimation?.estimated_voltages?.find((item) => item.bus_index === selectedBusId),
    };
  }, [selectedBusId, topology, latestState]);

  const point = (bus: BusTopology) => ({ x: bus.x * 60, y: -bus.y * 45 - 60 });
  const labelFor = (bus: BusTopology) => {
    const p = point(bus);
    if (bus.bus_index === 0 || bus.bus_index === 1) return { x: p.x, y: p.y - 21, anchor: "middle" as const, rtuY: p.y - 33 };
    if (bus.bus_index === 3) return { x: p.x - 20, y: p.y - 2, anchor: "end" as const, rtuY: p.y + 10 };
    return { x: p.x, y: p.y + 24, anchor: "middle" as const, rtuY: p.y + 36 };
  };

  return (
    <div data-testid="feeder-map-fallback" className="scada-vector-map">
      <div className="scada-map-toolbar">
        <div className="scada-map-title"><Layers size={14} /><span>Vector SCADA schematic</span><em><span className={`map-stream-dot ${latestState ? "is-live" : ""}`} />OFFLINE MAP MODE</em></div>
        <div className="scada-map-legend">
          {onRetryMapbox && <button onClick={onRetryMapbox}><RefreshCw size={12} /> Retry Mapbox</button>}
          <span><i className="legend-dot normal" />Normal</span><span><i className="legend-dot fault" />Fault</span><span><i className="legend-dot cyber" />Cyber</span>
        </div>
      </div>

      <div className="scada-vector-canvas">
        <svg viewBox="-240 -200 480 380" role="img" aria-label="11 kilovolt radial feeder topology">
          <defs>
            <pattern id="engineering-grid" width="24" height="24" patternUnits="userSpaceOnUse">
              <path d="M 24 0 L 0 0 0 24" fill="none" stroke="#223047" strokeWidth="0.6" opacity="0.45" />
            </pattern>
          </defs>
          <rect x="-240" y="-200" width="480" height="380" fill="url(#engineering-grid)" />

          {topology?.lines.map((line) => {
            const from = topology.buses.find((bus) => bus.bus_index === line.from_bus);
            const to = topology.buses.find((bus) => bus.bus_index === line.to_bus);
            if (!from || !to) return null;
            const start = point(from);
            const end = point(to);
            const verdict = getVerdict(line.to_bus);
            const tripped = latestState?.active_scenarios?.tripped_lines?.includes(line.line_index);
            const anomaly = tripped || verdict?.verdict === "Natural Fault" || verdict?.verdict === "Cyber Intrusion";
            const color = tripped ? SCADA_COLORS.CYBER : verdict ? getVerdictColor(verdict.verdict) : "#53627A";
            const dx = end.x - start.x;
            const dy = end.y - start.y;
            const length = Math.hypot(dx, dy) || 1;
            const midpoint = { x: (start.x + end.x) / 2, y: (start.y + end.y) / 2 };
            const label = Math.abs(dx) < 1
              ? { x: midpoint.x + 11, y: midpoint.y, anchor: "start" as const }
              : { x: midpoint.x, y: midpoint.y - 10, anchor: "middle" as const };
            return (
              <g key={`fallback-line-${line.line_index}`} data-testid={`fallback-line-${line.line_index}`}>
                <line x1={start.x} y1={start.y} x2={end.x} y2={end.y} stroke={color} strokeWidth={anomaly ? 4 : 2} strokeOpacity={anomaly ? 0.82 : 0.7} strokeDasharray={tripped ? "7 5" : undefined} />
                <text x={label.x} y={label.y} textAnchor={label.anchor} fill="#8D9AB0" fontSize="8.5" fontFamily="monospace" stroke="#0B111B" strokeWidth="4" paintOrder="stroke fill">{line.name} · {line.length_km} km</text>
              </g>
            );
          })}

          {topology?.buses.map((bus) => {
            const p = point(bus);
            const label = labelFor(bus);
            const verdict = getVerdict(bus.bus_index);
            const selected = selectedBusId === bus.bus_index;
            const color = bus.bus_index === 0 ? "#A8B4C7" : verdict ? getVerdictColor(verdict.verdict) : "#6D7B91";
            const anomaly = verdict?.verdict === "Natural Fault" || verdict?.verdict === "Cyber Intrusion";
            return (
              <g key={`fallback-bus-${bus.bus_index}`} data-testid={`fallback-bus-${bus.bus_index}`} onClick={() => onSelectBus?.(bus.bus_index)} className="scada-bus-node" role="button" tabIndex={0} aria-label={`Inspect ${bus.name}`}>
                {selected && <circle cx={p.x} cy={p.y} r={18} fill="none" stroke="#E8EEF7" strokeWidth="1.2" strokeDasharray="4 3" />}
                <circle cx={p.x} cy={p.y} r={bus.bus_index === 0 ? 15 : 13} fill={anomaly ? color : "#111A28"} stroke={selected || anomaly ? "#F5F7FA" : color} strokeWidth={selected || anomaly ? 2 : 1.2} />
                <text x={p.x} y={p.y + 3.5} textAnchor="middle" fill={anomaly ? "#08101C" : "#E8EEF7"} fontSize={bus.bus_index === 0 ? 9 : 10} fontWeight="700" fontFamily="monospace" pointerEvents="none">{bus.bus_index === 0 ? "HV" : `B${bus.bus_index}`}</text>
                <text x={label.x} y={label.y} textAnchor={label.anchor} fill={selected ? "#F5F7FA" : "#AAB6C8"} fontSize="9.5" fontWeight={selected ? "700" : "500"} fontFamily="sans-serif" stroke="#0B111B" strokeWidth="4" paintOrder="stroke fill" pointerEvents="none">{bus.name}</text>
                {busToRtu[bus.bus_index] && <text x={label.x} y={label.rtuY} textAnchor={label.anchor} fill={anomaly ? color : "#718098"} fontSize="8.5" fontFamily="monospace" fontWeight="600" stroke="#0B111B" strokeWidth="3" paintOrder="stroke fill" pointerEvents="none">RTU-{busToRtu[bus.bus_index]}</text>}
              </g>
            );
          })}
        </svg>
        {!topology && <div className="scada-empty-state">Loading topology…</div>}
      </div>

      {selectedBusInfo && (
        <div className="scada-bus-detail">
          <div className="scada-bus-detail-head"><div><span className="scada-kicker">Selected asset</span><strong>{selectedBusInfo.bus.name}</strong></div><button onClick={() => onSelectBus?.(null)} aria-label="Close bus detail">×</button></div>
          <div className="scada-bus-detail-grid"><div><span>Nominal</span><strong>{selectedBusInfo.bus.vn_kv} kV</strong></div><div><span>Asset</span><strong>{selectedBusInfo.rtuId ? `RTU-${selectedBusInfo.rtuId}` : "Substation"}</strong></div></div>
          {selectedBusInfo.telemetry && <div className="scada-bus-telemetry"><div><span>Reported Voltage:</span><strong>{selectedBusInfo.telemetry.voltage_pu.toFixed(4)} pu</strong></div><div><span>Active Power</span><strong>{selectedBusInfo.telemetry.p_mw.toFixed(3)} MW</strong></div></div>}
          {selectedBusInfo.verdict && <div className="scada-bus-verdict" style={{ color: getVerdictColor(selectedBusInfo.verdict.verdict) }}><span>Verdict</span><strong>{selectedBusInfo.verdict.verdict}</strong><small>{(selectedBusInfo.verdict.confidence * 100).toFixed(0)}% confidence</small></div>}
        </div>
      )}

      <div className="scada-map-footer"><span>{topology?.total_buses || 0} buses · {topology?.total_lines || 0} line segments · schematic coordinates preserved</span><span>{isForced ? "Manual fallback" : "Mapbox unavailable"}</span></div>
    </div>
  );
};
