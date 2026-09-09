import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, it, expect, vi } from "vitest";
import { getIncidentReplay } from "../lib/api";
import { AuditLog, generateCsvData } from "../components/AuditLog";
import { AuditLogEntry } from "../lib/types";

vi.mock("../lib/api", () => ({
  downloadIncidentReport: vi.fn(),
  getIncidentReplay: vi.fn(),
}));

const mockedGetIncidentReplay = vi.mocked(getIncidentReplay);

const makeAuditEntry = (id: string): AuditLogEntry => ({
  id,
  timestamp: "2026-09-04T10:00:00.000Z",
  simTime: "08:00:00",
  rtuId: 2,
  assetName: "RTU-2-FeederA",
  classification: "Cyber Intrusion",
  subtype: "data_injection",
  confidence: 0.95,
  networkSummary: "Network evidence",
  physicsSummary: "Physics evidence",
  recommendedAction: "Inspect RTU",
  formattedAlert: "Silent data injection detected",
});

describe("AuditLog CSV Export", () => {
  beforeEach(() => {
    mockedGetIncidentReplay.mockReset();
  });

  it("produces correctly formatted CSV data with proper headers and escaping", () => {
    const sampleEntries: AuditLogEntry[] = [
      {
        id: "audit-1",
        timestamp: "2026-08-23T15:30:00.000Z",
        simTime: "08:15:00",
        rtuId: 2,
        assetName: "RTU-2 (Bus-1 Feeder A / Industrial)",
        classification: "Cyber Intrusion",
        subtype: "data_injection",
        confidence: 0.92,
        networkSummary: "Legitimate Modbus Read traffic observed, but payload values contradict physical grid state.",
        physicsSummary: "WLS Chi-squared test failed; high normalized residual (r_N > 3.0); adjacent bus conservation violated.",
        recommendedAction: "Exclude RTU telemetry from automatic dispatch; fallback to WLS state estimation; audit RTU sensor firmware.",
        formattedAlert: "RTU-2's reading is physically inconsistent with power flow from adjacent buses — pattern matches a silent data-injection signature (92% conf), not a physical breaker trip.",
      },
      {
        id: "audit-2",
        timestamp: "2026-08-23T15:35:00.000Z",
        simTime: "08:30:00",
        rtuId: 3,
        assetName: "RTU-3 (Bus-2 Feeder B / Residential)",
        classification: "Natural Fault",
        subtype: "line_trip",
        confidence: 0.85,
        networkSummary: "Modbus polling nominal (FC 03 Read Holding Registers); no unauthorized write transactions logged.",
        physicsSummary: "Power flow converged with zero current on isolated branch; downstream bus voltage collapsed.",
        recommendedAction: "Dispatch line inspection crew to tripped feeder section; check auto-recloser lockouts.",
        formattedAlert: "RTU-3 — Physical feeder line outage detected with valid WLS residual convergence (85% conf) — no cyber indicators present; standard protective relaying action.",
      },
    ];

    const csv = generateCsvData(sampleEntries);
    const lines = csv.split("\n");

    // Check Header line
    expect(lines[0]).toContain("Detection Time (Sim)");
    expect(lines[0]).toContain("Affected Asset");
    expect(lines[0]).toContain("Classification");
    expect(lines[0]).toContain("Recommended Action");

    // Check Row 1
    expect(lines[1]).toContain('"08:15:00"');
    expect(lines[1]).toContain('"RTU-2 (Bus-1 Feeder A / Industrial)"');
    expect(lines[1]).toContain('"Cyber Intrusion"');
    expect(lines[1]).toContain('"data_injection"');
    expect(lines[1]).toContain('"92.0%"');
    expect(lines[1]).toContain('"Exclude RTU telemetry');

    // Check Row 2
    expect(lines[2]).toContain('"08:30:00"');
    expect(lines[2]).toContain('"Natural Fault"');
    expect(lines[2]).toContain('"line_trip"');
    expect(lines[2]).toContain('"85.0%"');
  });

  it("renders every supplied row when the header reports the event count", () => {
    const entries = Array.from({ length: 7 }, (_, index) => makeAuditEntry(`audit-${index}`));

    render(React.createElement(AuditLog, { entries }));

    expect(screen.getByText("7 Events Logged")).toBeInTheDocument();
    expect(screen.getAllByRole("row")).toHaveLength(8); // header row + seven event rows
    expect(screen.getAllByText("RTU-2-FeederA")).toHaveLength(7);

    fireEvent.change(screen.getByPlaceholderText("Search audit trail..."), {
      target: { value: "does-not-match" },
    });
    expect(screen.getByText("0 Events Logged")).toBeInTheDocument();
    expect(screen.queryAllByRole("row")).toHaveLength(0);
  });

  it("opens the captured replay and moves the static scrubber without another fetch", async () => {
    mockedGetIncidentReplay.mockResolvedValue({
      id: "audit-replay",
      rtu_id: 2,
      trigger_tick: 6,
      replay_window: [-1, 0, 1].map((tickOffset) => ({
        tick: 6 + tickOffset,
        tick_offset: tickOffset,
        sim_time: `08:0${tickOffset + 5}:00`,
        timestamp: "2026-09-04T10:00:00.000Z",
        voltage_pu: 0.98 + tickOffset * 0.001,
        p_mw: 0.2,
        q_mvar: 0.05,
        nbd: { nbd_unexpected_write_count: tickOffset === 1 ? 1 : 0, nbd_modbus_anomaly_rate: tickOffset === 1 ? 0.5 : 0 },
        pcd: { pcd_max_lnr: tickOffset === 1 ? 4.2 : 0.4 },
        verdict: tickOffset === 1 ? "Cyber Intrusion" : "Normal",
        subtype: tickOffset === 1 ? "data_injection" : "normal",
        confidence: 0.95,
      })),
    });

    render(React.createElement(AuditLog, { entries: [makeAuditEntry("audit-replay")] }));
    fireEvent.click(screen.getByRole("button", { name: "Replay incident for RTU-2-FeederA" }));

    await waitFor(() => expect(screen.getByRole("dialog")).toBeInTheDocument());
    expect(screen.getByText("Tick 0 · 08:05:00")).toBeInTheDocument();
    expect(screen.getByText("NOMINAL")).toBeInTheDocument();

    fireEvent.change(screen.getByRole("slider"), { target: { value: "2" } });
    expect(screen.getByText("Tick +1 · 08:06:00")).toBeInTheDocument();
    expect(screen.getByText("ANOMALOUS")).toBeInTheDocument();
    expect(screen.getByText("4.20")).toBeInTheDocument();
    expect(mockedGetIncidentReplay).toHaveBeenCalledTimes(1);
  });
});
