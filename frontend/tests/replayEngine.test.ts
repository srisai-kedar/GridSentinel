import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { useReplayEngine } from "../lib/replayEngine";
import { RecordedSession } from "../lib/sessionRecorder";

describe("useReplayEngine", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  const mockSession: RecordedSession = {
    version: "1.0",
    createdAt: "2026-08-24T00:00:00.000Z",
    totalDurationMs: 2000,
    eventCount: 3,
    events: [
      {
        deltaMs: 0,
        timestamp: "2026-08-24T00:00:00.000Z",
        payload: {
          tick: 1,
          sim_time: "08:00:00",
          diurnal_multiplier: 1.0,
          power_flow_converged: true,
          true_physical_state: { bus_voltages: [], line_loadings: [], total_load_mw: 1.0, total_loss_mw: 0.01 },
          polled_modbus_telemetry: {},
          state_estimation: { success: true, estimated_voltages: [], chi2_test_passed: true, chi2_statistic: 1.0, chi2_threshold: 12.0, bad_data_detected: false, flagged_measurements: [] },
          active_scenarios: { summary: "NORMAL", silent_overrides: {}, replay_attacks: [], tripped_lines: [], short_circuit_active: false },
          recent_traffic_log: [],
          ml_verdicts: {
            "2": { rtu_id: 2, verdict: "Normal", subtype: "normal", confidence: 0.98, probabilities: {}, model_status: "loaded" },
          },
        },
      },
      {
        deltaMs: 1000,
        timestamp: "2026-08-24T00:00:01.000Z",
        payload: {
          tick: 2,
          sim_time: "08:15:00",
          diurnal_multiplier: 1.02,
          power_flow_converged: true,
          true_physical_state: { bus_voltages: [], line_loadings: [], total_load_mw: 1.2, total_loss_mw: 0.02 },
          polled_modbus_telemetry: {},
          state_estimation: { success: true, estimated_voltages: [], chi2_test_passed: false, chi2_statistic: 40.0, chi2_threshold: 12.0, bad_data_detected: true, flagged_measurements: [] },
          active_scenarios: { summary: "ATTACK: Silent Data Injection", silent_overrides: { "2": { "voltage_pu": 1.15 } }, replay_attacks: [], tripped_lines: [], short_circuit_active: false },
          recent_traffic_log: [],
          ml_verdicts: {
            "2": { rtu_id: 2, verdict: "Cyber Intrusion", subtype: "data_injection", confidence: 0.96, probabilities: {}, model_status: "loaded" },
          },
        },
      },
      {
        deltaMs: 2000,
        timestamp: "2026-08-24T00:00:02.000Z",
        payload: {
          tick: 3,
          sim_time: "08:30:00",
          diurnal_multiplier: 1.02,
          power_flow_converged: true,
          true_physical_state: { bus_voltages: [], line_loadings: [], total_load_mw: 1.2, total_loss_mw: 0.02 },
          polled_modbus_telemetry: {},
          state_estimation: { success: true, estimated_voltages: [], chi2_test_passed: true, chi2_statistic: 1.0, chi2_threshold: 12.0, bad_data_detected: false, flagged_measurements: [] },
          active_scenarios: { summary: "NORMAL", silent_overrides: {}, replay_attacks: [], tripped_lines: [], short_circuit_active: false },
          recent_traffic_log: [],
          ml_verdicts: {
            "2": { rtu_id: 2, verdict: "Normal", subtype: "normal", confidence: 0.98, probabilities: {}, model_status: "loaded" },
          },
        },
      },
    ],
  };

  it("loads and plays back recorded payloads in timed sequence", () => {
    const onPayload = vi.fn();
    const { result } = renderHook(() => useReplayEngine(mockSession, onPayload));

    expect(result.current.isLoaded).toBe(true);
    expect(result.current.totalEvents).toBe(3);
    expect(result.current.currentIndex).toBe(0);
    expect(result.current.currentPayload?.tick).toBe(1);

    // Start playback
    act(() => {
      result.current.play();
    });

    expect(result.current.isPlaying).toBe(true);

    // Advance 1050ms
    act(() => {
      vi.advanceTimersByTime(1050);
    });

    expect(result.current.currentIndex).toBe(1);
    expect(result.current.currentPayload?.tick).toBe(2);
    expect(result.current.currentPayload?.ml_verdicts?.["2"].verdict).toBe("Cyber Intrusion");

    // Advance another 1050ms
    act(() => {
      vi.advanceTimersByTime(1050);
    });

    expect(result.current.currentIndex).toBe(2);
    expect(result.current.currentPayload?.tick).toBe(3);
  });

  it("allows seeking and speed multiplication", () => {
    const { result } = renderHook(() => useReplayEngine(mockSession));

    act(() => {
      result.current.seekToIndex(1);
    });

    expect(result.current.currentIndex).toBe(1);
    expect(result.current.currentPayload?.tick).toBe(2);

    act(() => {
      result.current.setPlaybackSpeed(2.0);
    });

    expect(result.current.playbackSpeed).toBe(2.0);
  });

  it("rejects malformed or non-chronological replay sessions", () => {
    const { result } = renderHook(() => useReplayEngine(mockSession));
    const invalidSession = {
      ...mockSession,
      events: [mockSession.events[1], mockSession.events[0]],
    };

    let loaded = true;
    act(() => {
      loaded = result.current.loadSessionFromJson(JSON.stringify(invalidSession));
    });

    expect(loaded).toBe(false);
    expect(result.current.currentPayload?.tick).toBe(1);
  });
});
