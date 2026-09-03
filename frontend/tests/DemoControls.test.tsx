import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { DemoControls } from "../components/DemoControls";

const { triggerShortCircuit } = vi.hoisted(() => ({ triggerShortCircuit: vi.fn() }));

vi.mock("@/lib/api", () => ({
  injectCommandAttack: vi.fn(() => Promise.resolve({ message: "ok" })),
  injectReplayAttack: vi.fn(() => Promise.resolve({ message: "ok" })),
  injectSilentDataAttack: vi.fn(() => Promise.resolve({ message: "ok" })),
  resetOtScenarios: vi.fn(() => Promise.resolve({ message: "ok" })),
  startOtSimulation: vi.fn(() => Promise.resolve({ message: "ok" })),
  stopOtSimulation: vi.fn(() => Promise.resolve({ message: "ok" })),
  triggerLineTrip: vi.fn(() => Promise.resolve({ message: "ok" })),
  triggerShortCircuit,
}));

describe("DemoControls", () => {
  beforeEach(() => {
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
});
