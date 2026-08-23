import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { SessionRecorder } from "../lib/sessionRecorder";
import { LiveSocketPayload } from "../lib/types";

describe("SessionRecorder", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("records payloads with relative timestamps and exports valid JSON", () => {
    const recorder = new SessionRecorder();
    expect(recorder.isActive()).toBe(false);
    expect(recorder.getEventCount()).toBe(0);

    recorder.start();
    expect(recorder.isActive()).toBe(true);

    const mockPayload1: Partial<LiveSocketPayload> = {
      tick: 1,
      sim_time: "08:00:00",
      power_flow_converged: true,
    };

    recorder.record(mockPayload1 as LiveSocketPayload);
    expect(recorder.getEventCount()).toBe(1);

    // Advance 500ms
    vi.advanceTimersByTime(500);

    const mockPayload2: Partial<LiveSocketPayload> = {
      tick: 2,
      sim_time: "08:15:00",
      power_flow_converged: true,
    };

    recorder.record(mockPayload2 as LiveSocketPayload);
    expect(recorder.getEventCount()).toBe(2);

    // Stop recording
    const session = recorder.stop();
    expect(recorder.isActive()).toBe(false);
    expect(session.version).toBe("1.0");
    expect(session.eventCount).toBe(2);
    expect(session.events.length).toBe(2);
    expect(session.events[0].payload.tick).toBe(1);
    expect(session.events[1].payload.tick).toBe(2);
    expect(session.events[1].deltaMs).toBeGreaterThanOrEqual(500);

    // JSON export
    const json = recorder.exportJson(session);
    const parsed = JSON.parse(json);
    expect(parsed.eventCount).toBe(2);
  });
});
