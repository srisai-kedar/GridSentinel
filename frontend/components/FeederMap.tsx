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
import { FeederMapFallback } from "./FeederMapFallback";
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
  forceFallback?: boolean;
  onToggleForceFallback?: () => void;
}

// Center anchor point (e.g., Central Indian Power Grid Node: Nagpur/Hyderabad region)
const ANCHOR_CENTER: [number, number] = [78.4867, 17.385]; // [lng, lat]
const COORDINATE_SCALE = 0.015; // Maps abstract (x,y) to GIS lat/lng offsets
const MAPBOX_LOAD_TIMEOUT_MS = 6000; // 6s timeout before falling back

export const FeederMap: React.FC<FeederMapProps> = ({
  latestState,
  selectedBusId: externalSelectedBus,
  onSelectBus,
  forceFallback = false,
  onToggleForceFallback,
}) => {
  const mapContainerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<mapboxgl.Map | null>(null);
  const markersRef = useRef<{ [busId: number]: mapboxgl.Marker }>({});

  const [topology, setTopology] = useState<TopologyResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [internalSelectedBus, setInternalSelectedBus] = useState<number | null>(null);
  const [showSatellite, setShowSatellite] = useState<boolean>(false);
  const [useFallback, setUseFallback] = useState<boolean>(false);
  const [mapboxError, setMapboxError] = useState<string | null>(null);

  const selectedBus = externalSelectedBus !== undefined ? externalSelectedBus : internalSelectedBus;
  const mapboxToken = process.env.NEXT_PUBLIC_MAPBOX_TOKEN?.trim() || "";

  const isFallbackActive = forceFallback || useFallback || !mapboxToken;

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

  // Fetch topology once on mount
  useEffect(() => {
    let mounted = true;
    async function loadTopologyData() {
      try {
        setLoading(true);
        const data = await getTopology();
        if (mounted) {
          setTopology(data);
        }
      } catch (err) {
        if (mounted) {
          // Fallback topology matching 11kV Feeder specification if backend is offline
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

  // Initialize Mapbox with error detection and timeout fallback
  useEffect(() => {
    if (isFallbackActive || !mapboxToken || !mapContainerRef.current || !topology) return;

    let styleLoaded = false;
    mapboxgl.accessToken = mapboxToken;

    const styleUrl = showSatellite
      ? "mapbox://styles/mapbox/satellite-streets-v12"
      : "mapbox://styles/mapbox/dark-v11";

    let map: mapboxgl.Map;
    try {
      map = new mapboxgl.Map({
        container: mapContainerRef.current,
        style: styleUrl,
        center: ANCHOR_CENTER,
        zoom: 11.2,
        attributionControl: false,
      });
      mapRef.current = map;
    } catch (err) {
      console.warn("[FeederMap] Mapbox GL failed to initialize, switching to fallback:", err);
      setUseFallback(true);
      return;
    }

    // Set a 6s style-load timeout
    const loadTimeout = setTimeout(() => {
      if (!styleLoaded) {
        console.warn("[FeederMap] Mapbox style load timed out, engaging fallback mode.");
        setUseFallback(true);
      }
    }, MAPBOX_LOAD_TIMEOUT_MS);

    map.on("error", (e) => {
      console.warn("[FeederMap] Mapbox GL error encountered:", e.error);
      setMapboxError(e.error?.message || "Mapbox error");
      setUseFallback(true);
    });

    map.on("load", () => {
      styleLoaded = true;
      clearTimeout(loadTimeout);

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

      if (!map.getSource("feeder-lines")) {
        map.addSource("feeder-lines", {
          type: "geojson",
          data: {
            type: "FeatureCollection",
            features: lineFeatures,
          },
        });

        // Line Glow
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
      clearTimeout(loadTimeout);
      Object.values(markersRef.current).forEach((m) => m.remove());
      markersRef.current = {};
      map.remove();
      mapRef.current = null;
    };
  }, [mapboxToken, topology, showSatellite, busCoordinates, isFallbackActive]);

  // Update Mapbox Markers when live state changes
  useEffect(() => {
    if (isFallbackActive || !mapRef.current || !topology) return;
    const map = mapRef.current;

    topology.buses.forEach((bus) => {
      const coord = busCoordinates[bus.bus_index];
      if (!coord) return;

      const color = getBusColor(bus.bus_index);
      const isSelected = selectedBus === bus.bus_index;

      let marker = markersRef.current[bus.bus_index];

      if (!marker) {
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
        const el = marker.getElement();
        el.style.backgroundColor = color;
        el.style.boxShadow = isSelected
          ? `0 0 20px #ffffff, 0 0 30px ${color}`
          : `0 0 12px ${color}`;
        el.style.border = isSelected ? "3px solid #ffffff" : "2px solid rgba(255,255,255,0.8)";
        el.style.transform = isSelected ? "scale(1.3)" : "scale(1)";
      }
    });
  }, [latestState, topology, selectedBus, busCoordinates, isFallbackActive]);

  // If fallback is active, render FeederMapFallback
  if (isFallbackActive) {
    return (
      <FeederMapFallback
        topology={topology}
        latestState={latestState}
        selectedBusId={selectedBus}
        onSelectBus={(bIdx) => {
          setInternalSelectedBus(bIdx);
          if (onSelectBus) onSelectBus(bIdx);
        }}
        onRetryMapbox={
          mapboxToken
            ? () => {
                setUseFallback(false);
                setMapboxError(null);
              }
            : undefined
        }
        isForced={forceFallback}
      />
    );
  }

  // Selected Bus info for Mapbox popup
  const selectedBusInfo = selectedBus !== null && selectedBus !== undefined && topology
    ? {
        bus: topology.buses.find((b) => b.bus_index === selectedBus),
        rtuId: busToRtuMap[selectedBus],
        verdict: getBusVerdict(selectedBus),
        telemetry: latestState?.polled_modbus_telemetry?.[String(busToRtuMap[selectedBus])],
        truePhysical: latestState?.true_physical_state?.bus_voltages?.find((v) => v.bus_index === selectedBus),
      }
    : null;

  return (
    <div className="relative w-full h-full min-h-[420px] bg-[#08090D] rounded-[10px] overflow-hidden border border-white/[0.07] flex flex-col">
      {/* Top Map Header */}
      <div className="absolute top-3 left-3 right-3 z-10 flex flex-wrap items-center justify-between gap-2 pointer-events-none">
        <div className="pointer-events-auto flex items-center space-x-2 bg-[#0E1118]/90 backdrop-blur-md px-3 py-1.5 rounded-[6px] border border-white/[0.08] shadow-lg">
          <Layers className="w-3.5 h-3.5 text-[#A78BFA]" />
          <span className="text-xs font-semibold text-[#EDEDF0] uppercase tracking-wider">
            11kV Radial Feeder Map
          </span>
          <span className="text-[10px] px-2 py-0.5 rounded-full bg-[#131722] text-[#9CA3AF] font-mono border border-white/[0.06]">
            {topology?.feeder_name || "GridSentinel"}
          </span>
        </div>

        <div className="pointer-events-auto flex items-center space-x-3 bg-[#0E1118]/90 backdrop-blur-md px-3 py-1.5 rounded-[6px] border border-white/[0.08] text-[11px] shadow-lg">
          {onToggleForceFallback && (
            <button
              onClick={onToggleForceFallback}
              className="text-[#5A6275] hover:text-[#EDEDF0] pr-2 border-r border-white/[0.08] text-[10px] font-mono"
              title="Force Vector Fallback for testing offline resilience"
            >
              Test Fallback
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

      {/* Mapbox container */}
      <div ref={mapContainerRef} className="w-full h-full flex-1" />

      {/* Floating detail card if bus selected */}
      {selectedBusInfo && selectedBusInfo.bus && (
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
              onClick={() => {
                setInternalSelectedBus(null);
                if (onSelectBus) onSelectBus(null);
              }}
              className="text-[#5A6275] hover:text-[#EDEDF0] text-xs px-1.5 py-0.5 rounded-[4px] bg-[#131722] border border-white/[0.06]"
            >
              ✕
            </button>
          </div>

          <div className="space-y-1.5 font-mono text-[11px]">
            <div className="flex justify-between text-[#5A6275]">
              <span>Nominal Voltage:</span>
              <span className="text-[#EDEDF0]">{selectedBusInfo.bus.vn_kv} kV</span>
            </div>
            {selectedBusInfo.telemetry && (
              <div className="flex justify-between text-[#5A6275]">
                <span>Reported Voltage:</span>
                <span className="text-[#EDEDF0] font-bold">
                  {selectedBusInfo.telemetry.voltage_pu.toFixed(4)} pu
                </span>
              </div>
            )}
            {selectedBusInfo.verdict && (
              <div
                className="p-1.5 rounded-[6px] border mt-1.5"
                style={{
                  backgroundColor: `${getVerdictColor(selectedBusInfo.verdict.verdict)}12`,
                  borderColor: `${getVerdictColor(selectedBusInfo.verdict.verdict)}35`,
                }}
              >
                <div className="flex justify-between font-bold" style={{ color: getVerdictColor(selectedBusInfo.verdict.verdict) }}>
                  <span>{selectedBusInfo.verdict.verdict}</span>
                  <span>{(selectedBusInfo.verdict.confidence * 100).toFixed(0)}% CONF</span>
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Illustrative Layout Caption */}
      <div className="w-full bg-[#0E1118] px-3 py-1.5 border-t border-white/[0.07] text-[10px] text-[#5A6275] flex items-center justify-between">
        <span>
          11kV Radial Distribution Substation Topology (Mapbox GL v3.x)
        </span>
        <span className="font-mono text-[#5A6275]">GIS Map Service</span>
      </div>
    </div>
  );
};
