import React from "react";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { StatusBar } from "../components/StatusBar";
import { LiveSocketPayload } from "../lib/types";

describe("StatusBar inference performance HUD", () => {
  it("renders live latency percentiles and tick rate from the existing payload", () => {
    const payload = {
      inference_p50_ms: 1.2345,
      inference_p95_ms: 2.3456,
      ticks_per_second: 0.98,
    } as LiveSocketPayload;

    render(<StatusBar connectionStatus="connected" streamStatus="streaming" latestState={payload} />);

    const hud = screen.getByLabelText("Live inference performance");
    expect(hud).toHaveTextContent("p50 1.23 ms");
    expect(hud).toHaveTextContent("p95 2.35 ms");
    expect(hud).toHaveTextContent("0.98 ticks/s");
  });
});
