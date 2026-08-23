import { describe, it, expect, vi } from "vitest";
import React from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import { FeederMapFallback } from "../components/FeederMapFallback";
import { TopologyResponse, LiveSocketPayload } from "../lib/types";

describe("FeederMapFallback Component", () => {
  const mockTopology: TopologyResponse = {
    feeder_name: "GridSentinel-Test-Feeder",
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
  };

  const mockState: LiveSocketPayload = {
    tick: 1,
    sim_time: "08:15:00",
    diurnal_multiplier: 1.0,
    power_flow_converged: true,
    true_physical_state: { bus_voltages: [], line_loadings: [], total_load_mw: 1.0, total_loss_mw: 0.01 },
    polled_modbus_telemetry: {
      "2": { voltage_pu: 0.985, p_mw: 0.28, q_mvar: 0.175, status: 1 },
    },
    state_estimation: { success: true, estimated_voltages: [], chi2_test_passed: true, chi2_statistic: 1.0, chi2_threshold: 12.0, bad_data_detected: false, flagged_measurements: [] },
    active_scenarios: { summary: "NORMAL", silent_overrides: {}, replay_attacks: [], tripped_lines: [], short_circuit_active: false },
    recent_traffic_log: [],
    ml_verdicts: {
      "2": { rtu_id: 2, verdict: "Normal", subtype: "normal", confidence: 0.98, probabilities: {}, model_status: "loaded" },
    },
  };

  it("renders all feeder buses and lines in SVG canvas", () => {
    render(
      <FeederMapFallback
        topology={mockTopology}
        latestState={mockState}
      />
    );

    expect(screen.getByTestId("feeder-map-fallback")).toBeInTheDocument();
    expect(screen.getByText(/OFFLINE MAP MODE/i)).toBeInTheDocument();

    // Check all buses are rendered
    mockTopology.buses.forEach((b) => {
      expect(screen.getByTestId(`fallback-bus-${b.bus_index}`)).toBeInTheDocument();
      expect(screen.getByText(b.name)).toBeInTheDocument();
    });

    // Check all lines are rendered
    mockTopology.lines.forEach((l) => {
      expect(screen.getByTestId(`fallback-line-${l.line_index}`)).toBeInTheDocument();
    });
  });

  it("handles bus selection and renders detail card", () => {
    const onSelectBus = vi.fn();
    const { rerender } = render(
      <FeederMapFallback
        topology={mockTopology}
        latestState={mockState}
        selectedBusId={null}
        onSelectBus={onSelectBus}
      />
    );

    const bus2Element = screen.getByTestId("fallback-bus-2");
    fireEvent.click(bus2Element);

    expect(onSelectBus).toHaveBeenCalledWith(2);

    // Re-render with selectedBusId=2
    rerender(
      <FeederMapFallback
        topology={mockTopology}
        latestState={mockState}
        selectedBusId={2}
        onSelectBus={onSelectBus}
      />
    );

    expect(screen.getByText(/Reported Voltage:/i)).toBeInTheDocument();
    expect(screen.getByText(/0.9850 pu/i)).toBeInTheDocument();
  });
});
