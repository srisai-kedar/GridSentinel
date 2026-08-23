import { describe, it, expect } from "vitest";
import {
  formatAlert,
  getNetworkEvidenceSummary,
  getPhysicsEvidenceSummary,
  getRecommendedAction,
  getVerdictColor,
  SCADA_COLORS,
} from "../lib/alertText";

describe("alertText formatAlert", () => {
  it("produces distinct templates for Cyber Intrusion subtypes", () => {
    const dataInjection = formatAlert("Cyber Intrusion", "data_injection", 2, 0.92);
    const commandInjection = formatAlert("Cyber Intrusion", "command_injection", 4, 0.95);
    const replay = formatAlert("Cyber Intrusion", "replay", 3, 0.88);

    expect(dataInjection).toContain("RTU-2");
    expect(dataInjection).toContain("inconsistent with power flow");
    expect(dataInjection).toContain("silent data-injection");

    expect(commandInjection).toContain("RTU-4");
    expect(commandInjection).toContain("Unauthorized Modbus TCP write");

    expect(replay).toContain("RTU-3");
    expect(replay).toContain("static across consecutive polling cycles");

    // All strings must be distinct
    expect(dataInjection).not.toEqual(commandInjection);
    expect(dataInjection).not.toEqual(replay);
    expect(commandInjection).not.toEqual(replay);
  });

  it("produces distinct templates for Natural Fault subtypes", () => {
    const lineTrip = formatAlert("Natural Fault", "line_trip", 2, 0.85);
    const shortCircuit = formatAlert("Natural Fault", "short_circuit", 3, 0.91);

    expect(lineTrip).toContain("RTU-2");
    expect(lineTrip).toContain("line outage");
    expect(lineTrip).toContain("protective relaying");

    expect(shortCircuit).toContain("RTU-3");
    expect(shortCircuit).toContain("voltage depression");
    expect(shortCircuit).toContain("short-circuit");

    expect(lineTrip).not.toEqual(shortCircuit);
  });

  it("produces appropriate template for Normal operation", () => {
    const normal = formatAlert("Normal", "normal", 1, 0.99);
    expect(normal).toContain("RTU-1");
    expect(normal).toContain("normal bounds");
    expect(normal).toContain("WLS state estimation");
  });

  it("assigns consistent colors to SCADA verdicts", () => {
    expect(getVerdictColor("Normal")).toBe(SCADA_COLORS.NORMAL);
    expect(getVerdictColor("Natural Fault")).toBe(SCADA_COLORS.FAULT);
    expect(getVerdictColor("Cyber Intrusion")).toBe(SCADA_COLORS.CYBER);
    expect(getVerdictColor("No Data")).toBe(SCADA_COLORS.NODATA);
  });

  it("returns distinct recommended actions", () => {
    const cyberCmdAction = getRecommendedAction("Cyber Intrusion", "command_injection");
    const cyberDataAction = getRecommendedAction("Cyber Intrusion", "data_injection");
    const faultLineAction = getRecommendedAction("Natural Fault", "line_trip");
    const normalAction = getRecommendedAction("Normal", "normal");

    expect(cyberCmdAction).toContain("Isolate RTU");
    expect(cyberDataAction).toContain("Exclude RTU telemetry");
    expect(faultLineAction).toContain("Dispatch line inspection crew");
    expect(normalAction).toContain("No action required");
  });

  it("returns distinct physics and network summaries", () => {
    const netCyber = getNetworkEvidenceSummary("Cyber Intrusion", "command_injection");
    const physCyber = getPhysicsEvidenceSummary("Cyber Intrusion", "data_injection");

    expect(netCyber).toContain("FC 06/16 Write");
    expect(physCyber).toContain("Chi-squared test failed");
  });
});
