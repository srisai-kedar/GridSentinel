import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { DemoControls } from "../components/DemoControls";

const {
  injectCommandAttack,
  injectReplayAttack,
  injectSilentDataAttack,
  resetOtScenarios,
  startOtSimulation,
  stopOtSimulation,
  triggerLineTrip,
  triggerShortCircuit,
} = vi.hoisted(() => ({
  injectCommandAttack: vi.fn(),
  injectReplayAttack: vi.fn(),
  injectSilentDataAttack: vi.fn(),
  resetOtScenarios: vi.fn(),
  startOtSimulation: vi.fn(),
  stopOtSimulation: vi.fn(),
  triggerLineTrip: vi.fn(),
  triggerShortCircuit: vi.fn(),
}));

vi.mock("@/lib/api", () => ({
  injectCommandAttack,
  injectReplayAttack,
  injectSilentDataAttack,
  resetOtScenarios,
  startOtSimulation,
  stopOtSimulation,
  triggerLineTrip,
  triggerShortCircuit,
}));

describe("DemoControls", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    for (const mock of [
      injectCommandAttack,
      injectReplayAttack,
      injectSilentDataAttack,
      resetOtScenarios,
      startOtSimulation,
      stopOtSimulation,
      triggerLineTrip,
    ]) {
      mock.mockResolvedValue({ message: "ok" });
    }
    triggerShortCircuit.mockResolvedValue({ message: "short circuit triggered" });
  });

  it("sends the visible target bus to the short-circuit endpoint", async () => {
    render(<DemoControls latestState={null} />);

    fireEvent.change(screen.getByLabelText("Target Bus"), { target: { value: "4" } });
    fireEvent.click(screen.getByRole("button", { name: /Short-Circuit Surge/i }));

    await waitFor(() => {
      expect(triggerShortCircuit).toHaveBeenCalledWith({
        bus_index: 4,
        fault_load_mw: 6,
        fault_load_mvar: 4,
        duration_ticks: 6,
      });
    });
  });

  it("renders every operator-facing Phase 3 scenario action", () => {
    render(<DemoControls latestState={null} />);

    expect(screen.getByRole("button", { name: /Silent Data Injection/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Command Injection/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Replay Attack/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Physical Line Trip/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Short-Circuit Surge/i })).toBeInTheDocument();
  });

  it("wires each visible attack and fault control to its existing endpoint payload", async () => {
    const cases = [
      { button: /Silent Data Injection/i, mock: injectSilentDataAttack, payload: { rtu_id: 2, voltage_pu: 1.15, duration_ticks: 20 } },
      { button: /Command Injection/i, mock: injectCommandAttack, payload: { rtu_id: 2, register_address: 1, value: 5000 } },
      { button: /Replay Attack/i, mock: injectReplayAttack, payload: { rtu_id: 2, duration_ticks: 20 } },
      { button: /Physical Line Trip/i, mock: triggerLineTrip, payload: { line_index: 0 } },
      { button: /Short-Circuit Surge/i, mock: triggerShortCircuit, payload: { bus_index: 2, fault_load_mw: 6, fault_load_mvar: 4, duration_ticks: 6 } },
    ] as const;

    for (const scenario of cases) {
      render(<DemoControls latestState={null} />);
      fireEvent.click(screen.getByRole("button", { name: scenario.button }));
      await waitFor(() => expect(scenario.mock).toHaveBeenCalledWith(scenario.payload));
      cleanup();
    }
  });
});
