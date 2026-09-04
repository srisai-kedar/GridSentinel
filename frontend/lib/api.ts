/**
 * api.ts
 * ------
 * Typed HTTP client functions for interacting with GridSentinel backend endpoints.
 */

import {
  OTStatusResponse,
  ResetResponse,
  ScenarioActionResponse,
  TopologyResponse,
  TrafficLogResponse,
  VerdictResponse,
} from "./types";

const API_BASE =
  process.env.NEXT_PUBLIC_API_URL ||
  process.env.NEXT_PUBLIC_API_BASE_URL ||
  (typeof window !== "undefined" && window.location.hostname !== "localhost"
    ? "https://gridsentinel-72tf.onrender.com"
    : "http://localhost:8000");

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

/** Run ML classifier on current snapshot */
export async function getClassifierVerdict(): Promise<VerdictResponse> {
  return fetchJson<VerdictResponse>("/classifier/verdict", {
    method: "POST",
  });
}
