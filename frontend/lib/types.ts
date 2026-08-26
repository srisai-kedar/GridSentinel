/**
 * types.ts
 * --------
 * TypeScript types and interfaces mirroring FastAPI Pydantic schemas for GridSentinel.
 */

export interface BusTopology {
  bus_index: number;
  name: string;
  vn_kv: number;
  x: number;
  y: number;
  in_service: boolean;
}

export interface LineTopology {
  line_index: number;
  name: string;
  from_bus: number;
  to_bus: number;
  length_km: number;
}

export interface TopologyResponse {
  feeder_name: string;
  buses: BusTopology[];
  lines: LineTopology[];
  total_buses: number;
  total_lines: number;
}

export interface BusVoltage {
  bus_index: number;
  name: string;
  vm_pu: number | null;
  va_degree: number | null;
}

export interface LineLoading {
  line_index: number;
  name: string;
  loading_percent: number | null;
  i_ka: number | null;
}

export interface EstimatedVoltage {
  bus_index: number;
  name: string;
  vm_pu_est: number | null;
  va_degree_est: number | null;
}

export interface FlaggedMeasurement {
  measurement_index: number;
  name: string;
  meas_type: string;
  element_type: string;
  element: number;
  value: number;
  std_dev: number;
  normalised_residual: number;
}

export interface TrafficEvent {
  event_id: number;
  timestamp: string;
  source: string;
  target_rtu: string;
  function_code: number;
  function_name: string;
  response_time_ms: number;
  is_unexpected_write: boolean;
  success: boolean;
  details: string;
}

export interface TrafficLogResponse {
  total_events_captured: number;
  returned_events_count: number;
  events: TrafficEvent[];
}

export interface RTUInfo {
  rtu_id: number;
  name: string;
  port: number;
  host: string;
  is_running: boolean;
  monitored_bus: number;
  telemetry: Record<string, any>;
}

export interface RTUListResponse {
  total_rtus: number;
  rtus: RTUInfo[];
}

export interface OTStatusResponse {
  is_simulation_running: boolean;
  sim_time: string;
  sim_hour: number;
  diurnal_multiplier: number;
  tick_count: number;
  active_scenarios: {
    summary: string;
    silent_overrides: Record<string, Record<string, number>>;
    replay_attacks: number[];
    tripped_lines: number[];
    short_circuit_active: boolean;
  };
  total_traffic_events: number;
}

export interface ResetResponse {
  status: string;
  message: string;
}

export interface ScenarioActionResponse {
  status: string;
  message: string;
  details: Record<string, any>;
}

export type VerdictType = "Normal" | "Natural Fault" | "Cyber Intrusion" | "No Data";

export type SubtypeType =
  | "normal"
  | "physical_fault"
  | "data_injection"
  | "command_injection"
  | "replay"
  | "line_trip"
  | "short_circuit"
  | string;

export interface RTUVerdict {
  rtu_id: number;
  verdict: VerdictType;
  subtype: SubtypeType | null;
  confidence: number;
  probabilities: Record<string, number>;
  decision_threshold?: number;
  // Step 7: 3-line explainable evidence panel
  network_evidence?: string;
  physics_evidence?: string;
  conclusion?: string;
  model_status: string;
}

export interface VerdictResponse {
  tick_timestamp: string;
  model_loaded: boolean;
  overall_status: string;
  rtu_verdicts: RTUVerdict[];
  evaluation_latency_ms: number;
}

export interface PolledTelemetryData {
  voltage_pu: number;
  p_mw: number;
  q_mvar: number;
  status: number;
}

export interface LiveSocketPayload {
  tick: number;
  sim_time: string;
  diurnal_multiplier: number;
  power_flow_converged: boolean;
  true_physical_state: {
    bus_voltages: BusVoltage[];
    line_loadings: LineLoading[];
    total_load_mw: number;
    total_loss_mw: number;
  };
  polled_modbus_telemetry: Record<string, PolledTelemetryData>;
  state_estimation: {
    success: boolean;
    estimated_voltages: EstimatedVoltage[];
    chi2_test_passed: boolean;
    chi2_statistic: number;
    chi2_threshold: number;
    bad_data_detected: boolean;
    flagged_measurements: FlaggedMeasurement[];
  };
  active_scenarios: {
    summary: string;
    silent_overrides: Record<string, { voltage_pu?: number; p_mw?: number; q_mvar?: number }>;
    replay_attacks: number[];
    tripped_lines: number[];
    short_circuit_active: boolean;
  };
  recent_traffic_log: TrafficEvent[];
  ml_verdicts?: Record<string, RTUVerdict>;
}

export interface AuditLogEntry {
  id: string;
  timestamp: string;
  simTime: string;
  rtuId: number;
  assetName: string;
  classification: VerdictType;
  subtype: string;
  confidence: number;
  networkSummary: string;
  physicsSummary: string;
  recommendedAction: string;
  formattedAlert: string;
}

export type ConnectionStatus = "connecting" | "connected" | "disconnected";
