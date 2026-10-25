/**
 * api.ts
 * ------
 * Typed HTTP client functions for interacting with GridSentinel backend endpoints.
 */

import {
  AuditLogEntry,
  IncidentReplayResponse,
  OTStatusResponse,
  ResetResponse,
  ScenarioActionResponse,
  TopologyResponse,
  TrafficLogResponse,
  VerdictResponse,
} from "./types";
import { getMitreIcsTag } from "./alertText";

const API_BASE =
  process.env.NEXT_PUBLIC_API_URL ||
  process.env.NEXT_PUBLIC_API_BASE_URL ||
  (typeof window !== "undefined" && window.location.hostname !== "localhost"
    ? "https://gridsentinel-72tf.onrender.com"
    : "http://localhost:8000");

export interface PcapAnalysis {
  analysis_type: string; production_inference_run: boolean; labels_assigned: boolean; physical_features_available: boolean;
  packet_summary: { total_packets: number; ipv4_tcp_packets: number; file_size_bytes: number; min_packet_bytes: number | null; max_packet_bytes: number | null; mean_packet_bytes: number | null; };
  modbus_summary: { decoded_messages: number; request_events: number; function_code_distribution: Record<string, number>; source_cardinality: number; request_response_matched: number; matched_response_fraction: number; mean_latency_ms: number | null; min_latency_ms: number | null; max_latency_ms: number | null; error_responses: number; unmatched_requests: number; parser_errors: number; };
  limitations: string[]; processing_seconds: number;
}

export async function analyzePcap(file: File): Promise<PcapAnalysis> {
  const response = await fetch(`${API_BASE}/tools/pcap-analyzer`, { method: "POST", headers: { "Content-Type": "application/octet-stream", "X-PCAP-Filename": file.name }, body: file });
  if (!response.ok) {
    let detail = `HTTP ${response.status} ${response.statusText}`;
    try { const body = await response.json(); if (body?.detail) detail = body.detail; } catch { /* keep HTTP detail */ }
    throw new Error(detail);
  }
  return response.json();
}

async function fetchJson<T>(
  endpoint: string,
  options: RequestInit = {}
): Promise<T> {
  const url = `${API_BASE}${endpoint}`;
  const response = await fetch(url, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
  });

  if (!response.ok) {
    let errorDetail = `HTTP ${response.status} ${response.statusText}`;
    try {
      const errJson = await response.json();
      if (errJson && errJson.detail) {
        errorDetail = errJson.detail;
      }
    } catch {
      // ignore
    }
    throw new Error(`API error [${endpoint}]: ${errorDetail}`);
  }

  return response.json();
}

/** Store the existing frontend audit record for out-of-band report generation. */
export async function registerIncident(entry: AuditLogEntry): Promise<void> {
  await fetchJson("/audit/incidents", {
    method: "POST",
    body: JSON.stringify({
      id: entry.id,
      trigger_tick: entry.tick ?? null,
      timestamp: entry.timestamp || null,
      sim_time: entry.simTime || null,
      rtu_id: entry.rtuId ?? null,
      asset_name: entry.assetName || null,
      verdict: entry.classification || null,
      subtype: entry.subtype || null,
      confidence: typeof entry.confidence === "number" ? entry.confidence : null,
      network_evidence: entry.networkSummary || null,
      physics_evidence: entry.physicsSummary || null,
      conclusion: entry.conclusion || null,
      recommended_action: entry.recommendedAction || null,
      formatted_alert: entry.formattedAlert || null,
      mitre_ics: entry.mitre_ics || (entry.classification === "Cyber Intrusion" ? getMitreIcsTag(entry.classification, entry.subtype) : null),
    }),
  });
}

/** Fetch the static forensic replay window attached to an incident. */
export async function getIncidentReplay(incidentId: string): Promise<IncidentReplayResponse> {
  return fetchJson<IncidentReplayResponse>(`/audit/${encodeURIComponent(incidentId)}/replay`);
}

/** Fetch a generated PDF for an existing incident record. */
export async function downloadIncidentReport(incidentId: string): Promise<Blob> {
  const response = await fetch(`${API_BASE}/audit/${encodeURIComponent(incidentId)}/report.pdf`);
  if (!response.ok) {
    throw new Error(`HTTP ${response.status} ${response.statusText}`);
  }
  const blob = await response.blob();
  if (blob.size === 0) {
    throw new Error("The server returned an empty report.");
  }
  return blob;
}

/** Fetch feeder topology (buses and lines with coordinates) */
export async function getTopology(): Promise<TopologyResponse> {
  return fetchJson<TopologyResponse>("/feeder/topology");
}

/** Reset base feeder network */
export async function resetFeeder(): Promise<ResetResponse> {
  return fetchJson<ResetResponse>("/feeder/reset", {
    method: "POST",
  });
}

/** Start OT SCADA simulation loop and RTUs */
export async function startOtSimulation(): Promise<ScenarioActionResponse> {
  return fetchJson<ScenarioActionResponse>("/ot/start", {
    method: "POST",
  });
}

/** Stop OT SCADA simulation loop and RTUs */
export async function stopOtSimulation(): Promise<ScenarioActionResponse> {
  return fetchJson<ScenarioActionResponse>("/ot/stop", {
    method: "POST",
  });
}

/** Get OT simulation status */
export async function getOtStatus(): Promise<OTStatusResponse> {
  return fetchJson<OTStatusResponse>("/ot/status");
}

/** Get traffic events */
export async function getTrafficLogs(limit: number = 50): Promise<TrafficLogResponse> {
  return fetchJson<TrafficLogResponse>(`/ot/traffic?limit=${limit}`);
}

/** Reset all active cyber overrides and physical faults */
export async function resetOtScenarios(): Promise<ScenarioActionResponse> {
  return fetchJson<ScenarioActionResponse>("/ot/reset", {
    method: "POST",
  });
}

/** Trigger Silent Data Injection attack on target RTU */
export async function injectSilentDataAttack(params: {
  rtu_id: number;
  voltage_pu?: number;
  p_mw?: number;
  q_mvar?: number;
  duration_ticks?: number;
}): Promise<ScenarioActionResponse> {
  return fetchJson<ScenarioActionResponse>("/ot/attack/data-injection", {
    method: "POST",
    body: JSON.stringify(params),
  });
}

/** Trigger Unauthorized Modbus Command Injection */
export async function injectCommandAttack(params: {
  rtu_id: number;
  register_address?: number;
  value: number;
}): Promise<ScenarioActionResponse> {
  return fetchJson<ScenarioActionResponse>("/ot/attack/command-injection", {
    method: "POST",
    body: JSON.stringify(params),
  });
}

/** Trigger Replay attack on target RTU */
export async function injectReplayAttack(params: {
  rtu_id: number;
  duration_ticks?: number;
}): Promise<ScenarioActionResponse> {
  return fetchJson<ScenarioActionResponse>("/ot/attack/replay", {
    method: "POST",
    body: JSON.stringify(params),
  });
}

/** Trigger physical line trip */
export async function triggerLineTrip(params: {
  line_index: number;
}): Promise<ScenarioActionResponse> {
  return fetchJson<ScenarioActionResponse>("/ot/fault/line-trip", {
    method: "POST",
    body: JSON.stringify(params),
  });
}

/** Trigger physical short circuit stub */
export async function triggerShortCircuit(params: {
  bus_index: number;
  fault_load_mw?: number;
  fault_load_mvar?: number;
  duration_ticks?: number;
}): Promise<ScenarioActionResponse> {
  return fetchJson<ScenarioActionResponse>("/ot/fault/short-circuit", {
    method: "POST",
    body: JSON.stringify(params),
  });
}

/** Trigger sensor calibration drift / hardware decalibration */
export async function triggerSensorDrift(params: {
  rtu_id: number;
  drift_percent?: number;
  duration_ticks?: number;
}): Promise<ScenarioActionResponse> {
  return fetchJson<ScenarioActionResponse>("/ot/fault/sensor-drift", {
    method: "POST",
    body: JSON.stringify(params),
  });
}

/** Run ML classifier on current snapshot */
export async function getClassifierVerdict(): Promise<VerdictResponse> {
  return fetchJson<VerdictResponse>("/classifier/verdict", {
    method: "POST",
  });
}
