"use client";

import React, { useEffect, useRef, useState, useMemo } from "react";
import mapboxgl from "mapbox-gl";
import "mapbox-gl/dist/mapbox-gl.css";
import {
  BusTopology,
  LineTopology,
  LiveSocketPayload,
  RTUVerdict,
  TopologyResponse,
} from "@/lib/types";
import { getTopology } from "@/lib/api";
import { getVerdictColor, SCADA_COLORS } from "@/lib/alertText";
import {
  Activity,
  AlertCircle,
  Eye,
  Info,
  Layers,
  MapPin,
  RefreshCw,
  ShieldAlert,
  Zap,
} from "lucide-react";

interface FeederMapProps {
  latestState: LiveSocketPayload | null;
  selectedBusId?: number | null;
  onSelectBus?: (busIndex: number | null) => void;
}

// Center anchor point (e.g., Central Indian Power Grid Node: Nagpur/Hyderabad region)
const ANCHOR_CENTER: [number, number] = [78.4867, 17.385]; // [lng, lat]
const COORDINATE_SCALE = 0.015; // Maps abstract (x,y) to GIS lat/lng offsets

export const FeederMap: React.FC<FeederMapProps> = ({
  latestState,
  selectedBusId: externalSelectedBus,
  onSelectBus,
}) => {
  const mapContainerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<mapboxgl.Map | null>(null);
  const markersRef = useRef<{ [busId: number]: mapboxgl.Marker }>({});

  const [topology, setTopology] = useState<TopologyResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [internalSelectedBus, setInternalSelectedBus] = useState<number | null>(null);
  const [showSatellite, setShowSatellite] = useState<boolean>(false);

  const selectedBus = externalSelectedBus !== undefined ? externalSelectedBus : internalSelectedBus;

  const mapboxToken = process.env.NEXT_PUBLIC_MAPBOX_TOKEN?.trim() || "";

  // Bus ID to RTU ID mapping (from rtu_server.py)
  // Substation Bus 1 -> RTU 1
  // Bus 2 (Feeder A) -> RTU 2
  // Bus 3 (Feeder B) -> RTU 3
  // Bus 4 (Feeder C) -> RTU 4
  // Bus 5 (Feeder A2) -> RTU 5
  const busToRtuMap = useMemo<Record<number, number>>(() => ({
    1: 1,
    2: 2,
    3: 3,
    4: 4,
    5: 5,
  }), []);

  // Fetch topology once on mount
  useEffect(() => {
    let mounted = true;
    async function loadTopologyData() {
      try {
        setLoading(true);
        const data = await getTopology();
        if (mounted) {
          setTopology(data);
          setLoadError(null);
        }
      } catch (err) {
        if (mounted) {
          // Fallback topology matching 11kV Feeder specification if backend is starting
          console.warn("[FeederMap] Could not fetch topology from backend, using default radial topology:", err);
          setTopology({
            feeder_name: "GridSentinel-Feeder",
            total_buses: 7,
            total_lines: 5,
            buses: [
              { bus_index: 0, name: "HV-Grid-33kV", vn_kv: 33.0, x: 0.0, y: 2.0, in_service: true },
              { bus_index: 1, name: "Substation-11kV", vn_kv: 11.0, x: 0.0, y: 0.0, in_service: true },
              { bus_index: 2, name: "Bus-1-FeederA", vn_kv: 11.0, x: -3.0, y: -2.0, in_service: true },
              { bus_index: 3, name: "Bus-2-FeederB", vn_kv: 11.0, x: 0.0, y: -2.0, in_service: true },
              { bus_index: 4, name: "Bus-3-FeederC", vn_kv: 11.0, x: 3.0, y: -2.0, in_service: true },
              { bus_index: 5, name: "Bus-4-FeederA2", vn_kv: 11.0, x: -3.0, y: -4.0, in_service: true },
              { bus_index: 6, name: "Bus-5-FeederB2", vn_kv: 11.0, x: 0.0, y: -4.0, in_service: true },
            ],
            lines: [
              { line_index: 0, name: "L0-Sub-A", from_bus: 1, to_bus: 2, length_km: 2.5 },
              { line_index: 1, name: "L1-Sub-B", from_bus: 1, to_bus: 3, length_km: 1.8 },
              { line_index: 2, name: "L2-Sub-C", from_bus: 1, to_bus: 4, length_km: 3.2 },
              { line_index: 3, name: "L3-A-A2", from_bus: 2, to_bus: 5, length_km: 2.0 },
              { line_index: 4, name: "L4-B-B2", from_bus: 3, to_bus: 6, length_km: 1.5 },
            ],
          });
        }
      } finally {
        if (mounted) setLoading(false);
      }
    }

    loadTopologyData();
    return () => {
      mounted = false;
    };
  }, []);

  // Compute bus coordinate dictionary
  const busCoordinates = useMemo(() => {
    const coords: Record<number, [number, number]> = {};
    if (!topology) return coords;

    for (const b of topology.buses) {
      coords[b.bus_index] = [
        ANCHOR_CENTER[0] + b.x * COORDINATE_SCALE,
        ANCHOR_CENTER[1] + b.y * COORDINATE_SCALE,
      ];
    }
    return coords;
  }, [topology]);

  // Helper to extract verdict for a bus
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

  // Initialize Mapbox if token is present
  useEffect(() => {
    if (!mapboxToken || !mapContainerRef.current || !topology) return;

    mapboxgl.accessToken = mapboxToken;

    const styleUrl = showSatellite
      ? "mapbox://styles/mapbox/satellite-streets-v12"
      : "mapbox://styles/mapbox/dark-v11";

    const map = new mapboxgl.Map({
      container: mapContainerRef.current,
      style: styleUrl,
      center: ANCHOR_CENTER,
      zoom: 11.2,
      attributionControl: false,
    });

    mapRef.current = map;

    map.on("load", () => {
      // Add Line GeoJSON Layer
      const lineFeatures = topology.lines.map((line) => {
        const fromCoord = busCoordinates[line.from_bus] || ANCHOR_CENTER;
        const toCoord = busCoordinates[line.to_bus] || ANCHOR_CENTER;
        return {
          type: "Feature" as const,
          properties: {
            line_index: line.line_index,
            name: line.name,
            length_km: line.length_km,
            from_bus: line.from_bus,
            to_bus: line.to_bus,
          },
          geometry: {
            type: "LineString" as const,
            coordinates: [fromCoord, toCoord],
          },
        };
      });

      // Add source
      if (!map.getSource("feeder-lines")) {
        map.addSource("feeder-lines", {
          type: "geojson",
          data: {
            type: "FeatureCollection",
            features: lineFeatures,
          },
        });

        // Background Line Glow
        map.addLayer({
          id: "feeder-lines-glow",
          type: "line",
          source: "feeder-lines",
          layout: { "line-join": "round", "line-cap": "round" },
          paint: {
            "line-color": "#38BDF8",
            "line-width": 8,
            "line-opacity": 0.25,
            "line-blur": 3,
          },
        });

        // Main Line
        map.addLayer({
          id: "feeder-lines-main",
          type: "line",
          source: "feeder-lines",
          layout: { "line-join": "round", "line-cap": "round" },
          paint: {
            "line-color": "#38BDF8",
            "line-width": 3.5,
          },
        });
      }
    });

    return () => {
      // Clean up markers
      Object.values(markersRef.current).forEach((m) => m.remove());
      markersRef.current = {};
      map.remove();
      mapRef.current = null;
    };
  }, [mapboxToken, topology, showSatellite, busCoordinates]);

  // Update Mapbox Markers when live state changes
  useEffect(() => {
    if (!mapRef.current || !topology) return;
    const map = mapRef.current;

    topology.buses.forEach((bus) => {
      const coord = busCoordinates[bus.bus_index];
      if (!coord) return;

      const color = getBusColor(bus.bus_index);
      const verdict = getBusVerdict(bus.bus_index);
      const isSelected = selectedBus === bus.bus_index;

      let marker = markersRef.current[bus.bus_index];

      if (!marker) {
        // Create custom HTML element for marker
        const el = document.createElement("div");
        el.className = "scada-bus-marker cursor-pointer transition-all duration-300 transform hover:scale-125";
        el.style.width = "22px";
        el.style.height = "22px";
        el.style.borderRadius = "50%";
        el.style.border = "2px solid #ffffff";
        el.style.boxShadow = `0 0 14px ${color}`;
        el.style.backgroundColor = color;
        el.style.display = "flex";
        el.style.alignItems = "center";
        el.style.justifyContent = "center";
        el.style.color = "#ffffff";
        el.style.fontSize = "10px";
        el.style.fontWeight = "bold";
        el.innerText = `${bus.bus_index}`;

        el.addEventListener("click", () => {
          setInternalSelectedBus(bus.bus_index);
          if (onSelectBus) onSelectBus(bus.bus_index);
        });

        marker = new mapboxgl.Marker({ element: el })
          .setLngLat(coord)
          .addTo(map);

        markersRef.current[bus.bus_index] = marker;
      } else {
        // Update existing element styles
        const el = marker.getElement();
        el.style.backgroundColor = color;
        el.style.boxShadow = isSelected
          ? `0 0 20px #ffffff, 0 0 30px ${color}`
          : `0 0 12px ${color}`;
        el.style.border = isSelected ? "3px solid #ffffff" : "2px solid rgba(255,255,255,0.8)";
        el.style.transform = isSelected ? "scale(1.3)" : "scale(1)";
      }
    });
  }, [latestState, topology, selectedBus, busCoordinates]);

  // Information details for the currently selected bus
  const selectedBusInfo = useMemo(() => {
    if (selectedBus === null || selectedBus === undefined || !topology) return null;
    const bus = topology.buses.find((b) => b.bus_index === selectedBus);
    if (!bus) return null;

    const rtuId = busToRtuMap[selectedBus];
    const verdict = getBusVerdict(selectedBus);
    const telemetry = latestState?.polled_modbus_telemetry?.[String(rtuId)];
    const truePhysical = latestState?.true_physical_state?.bus_voltages?.find(
      (v) => v.bus_index === selectedBus
    );
    const estimated = latestState?.state_estimation?.estimated_voltages?.find(
      (ev) => ev.bus_index === selectedBus
    );

    return {
      bus,
      rtuId,
      verdict,
      telemetry,
      truePhysical,
      estimated,
    };
  }, [selectedBus, topology, latestState, busToRtuMap]);

  return (
    <div className="relative w-full h-full min-h-[420px] bg-[#090D16] rounded-lg overflow-hidden border border-gray-800 flex flex-col">
      {/* Top Map Header & Controls */}
      <div className="absolute top-3 left-3 right-3 z-10 flex flex-wrap items-center justify-between gap-2 pointer-events-none">
        {/* Caption Badge */}
        <div className="pointer-events-auto flex items-center space-x-2 bg-[#0F172A]/90 backdrop-blur-md px-3 py-1.5 rounded-md border border-gray-700/80 shadow-lg">
          <Layers className="w-4 h-4 text-cyan-400" />
          <span className="text-xs font-semibold text-gray-200 uppercase tracking-wider">
            11kV Radial Feeder Topology
          </span>
          <span className="text-[10px] px-1.5 py-0.5 rounded bg-blue-900/60 text-blue-300 font-mono border border-blue-700/50">
            {topology?.feeder_name || "GridSentinel"}
          </span>
        </div>

        {/* Map Legend */}
        <div className="pointer-events-auto flex items-center space-x-3 bg-[#0F172A]/90 backdrop-blur-md px-3 py-1.5 rounded-md border border-gray-700/80 text-[11px] shadow-lg">
          <div className="flex items-center space-x-1.5">
            <span className="w-2.5 h-2.5 rounded-full bg-[#10B981] shadow-[0_0_6px_#10B981]" />
            <span className="text-gray-300">Normal</span>
          </div>
          <div className="flex items-center space-x-1.5">
            <span className="w-2.5 h-2.5 rounded-full bg-[#F59E0B] shadow-[0_0_6px_#F59E0B]" />
            <span className="text-gray-300">Natural Fault</span>
          </div>
          <div className="flex items-center space-x-1.5">
            <span className="w-2.5 h-2.5 rounded-full bg-[#EF4444] shadow-[0_0_6px_#EF4444] animate-pulse" />
            <span className="text-gray-300 font-medium">Cyber Intrusion</span>
          </div>
        </div>
      </div>

      {/* Main Map Canvas or Vector SCADA Schematic */}
      <div className="relative flex-1 w-full h-full">
        {mapboxToken ? (
          <div ref={mapContainerRef} className="w-full h-full" />
        ) : (
          /* High-Fidelity Vector SCADA Schematic Canvas (fallback if token is not yet configured) */
          <div className="w-full h-full flex flex-col items-center justify-center p-4 relative bg-[#0a0f1d] overflow-hidden select-none">
            {/* Grid Lines Pattern */}
            <div
              className="absolute inset-0 opacity-15 pointer-events-none"
              style={{
                backgroundImage:
                  "linear-gradient(to right, #1e293b 1px, transparent 1px), linear-gradient(to bottom, #1e293b 1px, transparent 1px)",
                backgroundSize: "32px 32px",
              }}
            />

            {/* Notice for Mapbox Token */}
            <div className="absolute top-12 left-4 right-4 z-10 flex items-center justify-between bg-amber-950/70 border border-amber-800/80 px-3 py-1.5 rounded text-[11px] text-amber-200 backdrop-blur-sm shadow-md">
              <div className="flex items-center space-x-2">
                <Info className="w-4 h-4 text-amber-400 shrink-0" />
                <span>
                  Mapbox token not supplied in <code className="font-mono bg-amber-900/60 px-1 py-0.5 rounded text-amber-100">.env.local</code>.
                  Displaying live interactive vector SCADA schematic.
                </span>
              </div>
            </div>

            {/* SVG Schematic Canvas */}
            <svg
              className="w-full h-full max-h-[560px] max-w-[800px]"
              viewBox="-240 -200 480 380"
            >
              <defs>
                <filter id="glow-normal" x="-20%" y="-20%" width="140%" height="140%">
                  <feGaussianBlur stdDeviation="3" result="blur" />
                  <feMerge>
                    <feMergeNode in="blur" />
                    <feMergeNode in="SourceGraphic" />
                  </feMerge>
                </filter>
                <filter id="glow-cyber" x="-30%" y="-30%" width="160%" height="160%">
                  <feGaussianBlur stdDeviation="5" result="blur" />
                  <feMerge>
                    <feMergeNode in="blur" />
                    <feMergeNode in="SourceGraphic" />
                  </feMerge>
                </filter>
                <linearGradient id="line-normal" x1="0%" y1="0%" x2="100%" y2="100%">
                  <stop offset="0%" stopColor="#38BDF8" stopOpacity="0.8" />
                  <stop offset="100%" stopColor="#0284C7" stopOpacity="0.8" />
                </linearGradient>
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
                  <g key={line.line_index} className="transition-all duration-300">
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
                      strokeOpacity={hasAnomaly || isTripped ? 0.4 : 0.2}
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
                      strokeWidth={hasAnomaly || isTripped ? 3 : 2}
                      strokeDasharray={isTripped || hasAnomaly ? "6,4" : undefined}
                      className={hasAnomaly || isTripped ? "animate-pulse" : ""}
                    />
                    {/* Line Label */}
                    <text
                      x={(x1 + x2) / 2 + 10}
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
                const isSelected = selectedBus === bus.bus_index;
                const rtuId = busToRtuMap[bus.bus_index];

                return (
                  <g
                    key={bus.bus_index}
                    onClick={() => {
                      setInternalSelectedBus(bus.bus_index);
                      if (onSelectBus) onSelectBus(bus.bus_index);
                    }}
                    className="cursor-pointer group"
                  >
                    {/* Pulsing ring for anomalies */}
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

                    {/* Outer selection ring */}
                    {isSelected && (
                      <circle
                        cx={cx}
                        cy={cy}
                        r={20}
                        fill="none"
                        stroke="#FFFFFF"
                        strokeWidth={2}
                        strokeDasharray="4,2"
                      />
                    )}

                    {/* Bus Circle Marker */}
                    <circle
                      cx={cx}
                      cy={cy}
                      r={bus.bus_index === 0 ? 15 : 13}
                      fill={color}
                      stroke="#FFFFFF"
                      strokeWidth={isSelected ? 3 : 2}
                      filter={
                        verdict?.verdict === "Cyber Intrusion"
                          ? "url(#glow-cyber)"
                          : "url(#glow-normal)"
                      }
                      className="transition-transform duration-200 group-hover:scale-110"
                    />

                    {/* Bus Index / Symbol */}
                    <text
                      cx={cx}
                      cy={cy}
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

                    {/* Bus Name Label */}
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

                    {/* Subtitle / RTU tag */}
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
        )}
      </div>

      {/* Selected Bus Floating SCADA Card / Popup */}
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
              onClick={() => {
                setInternalSelectedBus(null);
                if (onSelectBus) onSelectBus(null);
              }}
              className="text-gray-400 hover:text-white text-xs px-1.5 py-0.5 rounded bg-gray-800"
            >
              ✕
            </button>
          </div>

          <div className="space-y-2 font-mono">
            {/* Bus Specs */}
            <div className="grid grid-cols-2 gap-2 text-[11px] bg-slate-900/80 p-2 rounded border border-gray-800">
              <div>
                <span className="text-gray-500 block">NOMINAL KV</span>
                <span className="text-gray-200 font-semibold">{selectedBusInfo.bus.vn_kv} kV</span>
              </div>
              <div>
                <span className="text-gray-500 block">ASSET MAPPING</span>
                <span className="text-cyan-400 font-semibold">
                  {selectedBusInfo.rtuId ? `RTU-${selectedBusInfo.rtuId}` : "Substation Tx"}
                </span>
              </div>
            </div>

            {/* Telemetry Snapshot */}
            {selectedBusInfo.telemetry && (
              <div className="bg-slate-900/80 p-2 rounded border border-gray-800 space-y-1 text-[11px]">
                <div className="flex justify-between">
                  <span className="text-gray-400">Reported Voltage:</span>
                  <span className="text-yellow-300 font-bold">
                    {selectedBusInfo.telemetry.voltage_pu.toFixed(4)} pu (
                    {(selectedBusInfo.telemetry.voltage_pu * selectedBusInfo.bus.vn_kv).toFixed(2)} kV)
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-400">Active Power (P):</span>
                  <span className="text-emerald-400 font-semibold">
                    {selectedBusInfo.telemetry.p_mw.toFixed(3)} MW
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-400">Reactive Power (Q):</span>
                  <span className="text-blue-400 font-semibold">
                    {selectedBusInfo.telemetry.q_mvar.toFixed(3)} MVAR
                  </span>
                </div>
              </div>
            )}

            {/* True vs Estimated Physics */}
            {selectedBusInfo.truePhysical && (
              <div className="bg-slate-900/80 p-2 rounded border border-gray-800 space-y-1 text-[11px]">
                <div className="flex justify-between">
                  <span className="text-gray-400">Physics True V:</span>
                  <span className="text-gray-200 font-semibold">
                    {selectedBusInfo.truePhysical.vm_pu !== null
                      ? `${selectedBusInfo.truePhysical.vm_pu.toFixed(4)} pu`
                      : "N/A"}
                  </span>
                </div>
                {selectedBusInfo.estimated && (
                  <div className="flex justify-between">
                    <span className="text-gray-400">WLS Estimated V:</span>
                    <span className="text-indigo-300 font-semibold">
                      {selectedBusInfo.estimated.vm_pu_est !== null
                        ? `${selectedBusInfo.estimated.vm_pu_est.toFixed(4)} pu`
                        : "N/A"}
                    </span>
                  </div>
                )}
              </div>
            )}

            {/* ML Classification Verdict */}
            {selectedBusInfo.verdict ? (
              <div
                className="p-2 rounded border text-[11px]"
                style={{
                  backgroundColor: `${getVerdictColor(selectedBusInfo.verdict.verdict)}15`,
                  borderColor: `${getVerdictColor(selectedBusInfo.verdict.verdict)}66`,
                }}
              >
                <div className="flex items-center justify-between mb-1">
                  <span className="text-gray-400">ML Fusion Verdict:</span>
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
                    Confidence: {(selectedBusInfo.verdict.confidence * 100).toFixed(1)}%
                  </span>
                </div>
              </div>
            ) : (
              <div className="text-gray-500 text-center py-1">No active RTU ML classifier verdict</div>
            )}
          </div>
        </div>
      )}

      {/* Illustrative Layout Caption */}
      <div className="w-full bg-[#0d121f] px-3 py-1.5 border-t border-gray-800 text-[10px] text-gray-400 flex items-center justify-between">
        <span>
          Illustrative SCADA Feeder Topology (Anchor: 11kV Radial Distribution Substation). Layout coordinates mapped to GIS canvas for operational situational awareness.
        </span>
        <span className="font-mono text-gray-500 hidden sm:inline">
          Pandapower v3.x Engine
        </span>
      </div>
    </div>
  );
};
