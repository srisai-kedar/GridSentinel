import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { FeederMap } from "../components/FeederMap";

const getTopology = vi.hoisted(() => vi.fn());

vi.mock("@/lib/api", () => ({ getTopology }));

describe("FeederMap resilience", () => {
  beforeEach(() => {
    getTopology.mockResolvedValue({
      feeder_name: "GridSentinel-Test-Feeder",
      total_buses: 1,
      total_lines: 0,
      buses: [{ bus_index: 0, name: "HV-Grid-33kV", vn_kv: 33, x: 0, y: 2, in_service: true }],
      lines: [],
    });
  });

  it("uses the vector schematic when no Mapbox token is configured", async () => {
    render(<FeederMap latestState={null} />);

    await waitFor(() => {
      expect(screen.getByTestId("feeder-map-fallback")).toBeInTheDocument();
    });
    expect(screen.getByText(/OFFLINE MAP MODE/i)).toBeInTheDocument();
    expect(screen.getByText(/Mapbox unavailable/i)).toBeInTheDocument();
  });
});
