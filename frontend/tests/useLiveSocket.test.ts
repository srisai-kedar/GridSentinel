import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { useLiveSocket } from "../lib/useLiveSocket";

// Mock WebSocket implementation
class MockWebSocket {
  url: string;
  onopen: (() => void) | null = null;
  onclose: (() => void) | null = null;
  onerror: ((err: any) => void) | null = null;
  onmessage: ((ev: { data: string }) => void) | null = null;
  readyState: number = 0;

  static instances: MockWebSocket[] = [];

  constructor(url: string) {
    this.url = url;
    MockWebSocket.instances.push(this);
    setTimeout(() => {
      this.readyState = 1;
      if (this.onopen) this.onopen();
    }, 10);
  }

  send(data: any) {}
  close() {
    this.readyState = 3;
    if (this.onclose) this.onclose();
  }
}

describe("useLiveSocket", () => {
  beforeEach(() => {
    MockWebSocket.instances = [];
    (global as any).WebSocket = MockWebSocket;
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it("transitions connectionStatus from connecting to connected and handles messages", async () => {
    const { result } = renderHook(() => useLiveSocket("ws://localhost:8000/ws/live"));

    expect(result.current.connectionStatus).toBe("connecting");

    // Advance timer to trigger onopen
    act(() => {
      vi.advanceTimersByTime(20);
    });

    expect(result.current.connectionStatus).toBe("connected");

    // Deliver a message
    const ws = MockWebSocket.instances[0];
    const testPayload = {
      tick: 42,
      sim_time: "09:30:00",
      diurnal_multiplier: 1.05,
      power_flow_converged: true,
      true_physical_state: {
        bus_voltages: [],
        line_loadings: [],
        total_load_mw: 1.25,
        total_loss_mw: 0.04,
      },
      polled_modbus_telemetry: {},
      state_estimation: {
        success: true,
        estimated_voltages: [],
        chi2_test_passed: true,
        chi2_statistic: 1.2,
        chi2_threshold: 12.5,
        bad_data_detected: false,
        flagged_measurements: [],
      },
      active_scenarios: {
        summary: "NORMAL_OPERATION",
        silent_overrides: {},
        replay_attacks: [],
        tripped_lines: [],
        short_circuit_active: false,
      },
      recent_traffic_log: [],
    };

    act(() => {
      if (ws.onmessage) {
        ws.onmessage({ data: JSON.stringify(testPayload) });
      }
    });

    expect(result.current.latestState?.tick).toBe(42);
    expect(result.current.latestState?.sim_time).toBe("09:30:00");
  });

  it("handles disconnect and reconnect backoff correctly", () => {
    const { result } = renderHook(() => useLiveSocket("ws://localhost:8000/ws/live"));

    act(() => {
      vi.advanceTimersByTime(20);
    });
    expect(result.current.connectionStatus).toBe("connected");

    // Trigger unexpected close
    const ws = MockWebSocket.instances[0];
    act(() => {
      ws.close();
    });

    expect(result.current.connectionStatus).toBe("disconnected");

    // Advance backoff time to trigger reconnect (at 1000ms new socket is created in 'connecting')
    act(() => {
      vi.advanceTimersByTime(1001);
    });

    expect(MockWebSocket.instances.length).toBe(2);

    // After new socket opens, status returns to connected
    act(() => {
      vi.advanceTimersByTime(20);
    });

    expect(result.current.connectionStatus).toBe("connected");
  });
});
