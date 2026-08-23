/**
 * alertText.ts
 * ------------
 * Plain-language alert formatting and incident intelligence engine for GridSentinel.
 * Implements DISTINCT template strings per verdict and subtype combination.
 */

import { SubtypeType, VerdictType } from "./types";

export const SCADA_COLORS = {
  NORMAL: "#10B981",       // Green
  FAULT: "#F59E0B",        // Amber
  CYBER: "#EF4444",        // Red
  NODATA: "#6B7280",       // Gray
} as const;

export function getVerdictColor(verdict: VerdictType | string): string {
  switch (verdict) {
    case "Normal":
      return SCADA_COLORS.NORMAL;
    case "Natural Fault":
      return SCADA_COLORS.FAULT;
    case "Cyber Intrusion":
      return SCADA_COLORS.CYBER;
    default:
      return SCADA_COLORS.NODATA;
  }
}

export function getRtuAssetLabel(rtuId: number): string {
  const map: Record<number, string> = {
    1: "RTU-1 (Substation-11kV Head)",
    2: "RTU-2 (Bus-1 Feeder A / Industrial)",
    3: "RTU-3 (Bus-2 Feeder B / Residential)",
    4: "RTU-4 (Bus-3 Feeder C / Agriculture)",
    5: "RTU-5 (Bus-4 Feeder A2 / Mixed)",
  };
  return map[rtuId] || `RTU-${rtuId}`;
}

export interface AlertContext {
  voltagePu?: number;
  activePowerMw?: number;
  trippedLine?: number;
  shortCircuitBus?: number;
  details?: string;
}

/**
 * Generates a distinct plain-language incident description based on verdict and subtype.
 */
export function formatAlert(
  verdict: VerdictType | string,
  subtype: SubtypeType | null | undefined,
  rtuId: number,
  confidence: number = 0.95,
  context?: AlertContext
): string {
  const rtuName = `RTU-${rtuId}`;
  const confPct = Math.round(confidence * 100);

  if (verdict === "Cyber Intrusion") {
    switch (subtype) {
      case "data_injection":
      case "silent_data_injection":
        return `${rtuName}'s reading is physically inconsistent with power flow from adjacent buses — pattern matches a silent data-injection signature (${confPct}% conf), not a physical breaker trip.`;

      case "command_injection":
        return `${rtuName} — Unauthorized Modbus TCP write command (FC 06/16) intercepted in SCADA traffic stream (${confPct}% conf) — potential actuator/setpoint tampering detected.`;

      case "replay":
      case "replay_attack":
        return `${rtuName} — Telemetry values remained static across consecutive polling cycles with zero diurnal variance (${confPct}% conf) — historical packet replay attack signature.`;

      default:
        return `${rtuName} — High-confidence cyber anomaly flagged (${confPct}% conf) with conflicting physics residuals and Modbus traffic signatures.`;
    }
  }

  if (verdict === "Natural Fault") {
    switch (subtype) {
      case "line_trip":
      case "physical_fault":
        return `${rtuName} — Physical feeder line outage detected with valid WLS residual convergence (${confPct}% conf) — no cyber indicators present; standard protective relaying action.`;

      case "short_circuit":
      case "short_circuit_stub":
        return `${rtuName} — Severe transient voltage depression and reactive current surge detected (${confPct}% conf) — characteristic of physical short-circuit fault.`;

      default:
        return `${rtuName} — Equipment fault detected with consistent physical power-flow laws (${confPct}% conf) — recommend standard fault-response procedure.`;
    }
  }

  if (verdict === "Normal") {
    return `${rtuName} — Grid operating in normal bounds. Telemetry is physically consistent with WLS state estimation and no anomalous OT traffic.`;
  }

  return `${rtuName} — Telemetry stream offline or uninitialized.`;
}

/**
 * Returns recommended response action for audit reports and incident feed.
 */
export function getRecommendedAction(
  verdict: VerdictType | string,
  subtype: SubtypeType | null | undefined
): string {
  if (verdict === "Cyber Intrusion") {
    switch (subtype) {
      case "command_injection":
        return "Isolate RTU network segment; block unauthorized Modbus master IP; verify physical breaker status.";
      case "data_injection":
      case "silent_data_injection":
        return "Exclude RTU telemetry from automatic dispatch; fallback to WLS state estimation; audit RTU sensor firmware.";
      case "replay":
      case "replay_attack":
        return "Rotate Modbus session sequence keys; verify RTU timestamp counter; restart communication link.";
      default:
        return "Trigger OT Cyber Incident Response Protocol; quarantine RTU subnet and preserve packet logs.";
    }
  }

  if (verdict === "Natural Fault") {
    switch (subtype) {
      case "line_trip":
        return "Dispatch line inspection crew to tripped feeder section; check auto-recloser lockouts.";
      case "short_circuit":
        return "Check feeder circuit breaker trip flags; perform insulation resistance test before re-energizing.";
      default:
        return "Dispatch maintenance crew to substation; inspect transformer and feeder section.";
    }
  }

  return "No action required. Maintain continuous monitoring.";
}

/**
 * Summarizes physics-level evidence.
 */
export function getPhysicsEvidenceSummary(
  verdict: VerdictType | string,
  subtype: SubtypeType | null | undefined
): string {
  if (verdict === "Cyber Intrusion") {
    if (subtype === "data_injection" || subtype === "silent_data_injection") {
      return "WLS Chi-squared test failed; high normalized residual (r_N > 3.0); adjacent bus conservation violated.";
    }
    if (subtype === "replay") {
      return "Zero variance in voltage/power while upstream feeder fluctuates with diurnal curve.";
    }
    return "Physical state estimation mismatch; power flow equations not satisfied at monitored node.";
  }

  if (verdict === "Natural Fault") {
    if (subtype === "line_trip") {
      return "Power flow converged with zero current on isolated branch; downstream bus voltage collapsed.";
    }
    return "Severe bus voltage sag below 0.90 pu; massive reactive power surge across line.";
  }

  return "WLS State estimation converged; chi2 test passed; residuals within 3-sigma band.";
}

/**
 * Summarizes OT network-level evidence.
 */
export function getNetworkEvidenceSummary(
  verdict: VerdictType | string,
  subtype: SubtypeType | null | undefined
): string {
  if (verdict === "Cyber Intrusion") {
    if (subtype === "command_injection") {
      return "Unauthorized source IP executing FC 06/16 Write Register outside scheduled SCADA master window.";
    }
    if (subtype === "replay") {
      return "Modbus frame payload identical to historical traffic window; stale sequence pattern.";
    }
    return "Legitimate Modbus Read traffic observed, but payload values contradict physical grid state.";
  }

  if (verdict === "Natural Fault") {
    return "Modbus polling nominal (FC 03 Read Holding Registers); no unauthorized write transactions logged.";
  }

  return "Standard SCADA Master periodic polling (FC 03); response latency < 25ms; no anomalous writes.";
}
