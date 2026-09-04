/**
 * useLiveSocket.ts
 * ----------------
 * React hook connecting to the backend WebSocket (/ws/live),
 * providing real-time state, honest connection status with exponential backoff,
 * and automatic cleanup on unmount.
 */

import { useEffect, useRef, useState } from "react";
import { ConnectionStatus, LiveSocketPayload, StreamStatus, TrafficEvent } from "./types";

const DEFAULT_WS_URL =
  typeof window !== "undefined" && window.location.hostname !== "localhost"
    ? "wss://gridsentinel-72tf.onrender.com/ws/live"
    : "ws://localhost:8000/ws/live";

export function useLiveSocket(urlOverride?: string) {
  const [latestState, setLatestState] = useState<LiveSocketPayload | null>(null);
  const [connectionStatus, setConnectionStatus] = useState<ConnectionStatus>("connecting");
  const [recentTrafficEvents, setRecentTrafficEvents] = useState<TrafficEvent[]>([]);
  const [lastError, setLastError] = useState<string | null>(null);
  const [streamStatus, setStreamStatus] = useState<StreamStatus>("connecting");
  const [lastMessageAt, setLastMessageAt] = useState<string | null>(null);

  const socketRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const staleTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const reconnectDelayRef = useRef<number>(1000); // 1s start
  const isUnmountedRef = useRef<boolean>(false);

  useEffect(() => {
    isUnmountedRef.current = false;
    const wsUrl =
      urlOverride ||
      process.env.NEXT_PUBLIC_WS_URL ||
      DEFAULT_WS_URL;

    function connect() {
      if (isUnmountedRef.current) return;

      setConnectionStatus("connecting");
      setStreamStatus("connecting");
      setLastError(null);

      const clearStaleTimer = () => {
        if (staleTimeoutRef.current) clearTimeout(staleTimeoutRef.current);
        staleTimeoutRef.current = null;
      };

      const armStaleTimer = () => {
        clearStaleTimer();
        staleTimeoutRef.current = setTimeout(() => {
          if (!isUnmountedRef.current && socketRef.current?.readyState === WebSocket.OPEN) {
            setStreamStatus("stale");
            setLastError("No live telemetry received within the expected interval");
          }
        }, 5000);
      };

      try {
        const ws = new WebSocket(wsUrl);
        socketRef.current = ws;

        ws.onopen = () => {
          if (isUnmountedRef.current) {
            ws.close();
            return;
          }
          setConnectionStatus("connected");
          setStreamStatus("waiting");
          reconnectDelayRef.current = 1000; // Reset backoff on successful connect
          armStaleTimer();
        };

        ws.onmessage = (event) => {
          if (isUnmountedRef.current) return;
          try {
            const data: Partial<LiveSocketPayload> = JSON.parse(event.data);
            const hasTelemetry = Boolean(
              data.true_physical_state &&
                Array.isArray(data.true_physical_state.bus_voltages) &&
                Array.isArray(data.true_physical_state.line_loadings) &&
                typeof data.true_physical_state.total_load_mw === "number" &&
                typeof data.true_physical_state.total_loss_mw === "number" &&
                data.state_estimation &&
                Array.isArray(data.state_estimation.estimated_voltages)
            );
            if (hasTelemetry) setLatestState(data as LiveSocketPayload);

            if (data.stream_status === "stopped" || data.simulation_running === false) {
              setStreamStatus("stopped");
              clearStaleTimer();
            } else if (data.stream_status === "error") {
              setStreamStatus("error");
              armStaleTimer();
            } else if (hasTelemetry) {
              setStreamStatus(data.stale ? "stale" : "streaming");
              armStaleTimer();
            }

            setLastMessageAt(new Date().toISOString());
            if (Object.prototype.hasOwnProperty.call(data, "last_error")) {
              setLastError(data.last_error ?? null);
            }

            if (data.recent_traffic_log && Array.isArray(data.recent_traffic_log)) {
              setRecentTrafficEvents(data.recent_traffic_log);
            }
          } catch (err) {
            console.error("[useLiveSocket] Error parsing WebSocket message:", err);
          }
        };

        ws.onerror = (event) => {
          if (isUnmountedRef.current) return;
          setLastError("WebSocket transport error");
          setStreamStatus("error");
        };

        ws.onclose = (event) => {
          if (isUnmountedRef.current) return;
          setConnectionStatus("disconnected");
          setStreamStatus("error");
          socketRef.current = null;
          clearStaleTimer();

          // Schedule reconnection with exponential backoff (1s -> 2s -> 4s -> ... -> max 10s)
          const delay = reconnectDelayRef.current;
          reconnectDelayRef.current = Math.min(delay * 1.5, 10000);

          reconnectTimeoutRef.current = setTimeout(() => {
            if (!isUnmountedRef.current) {
              connect();
            }
          }, delay);
        };
      } catch (err) {
        setConnectionStatus("disconnected");
        setStreamStatus("error");
        setLastError(err instanceof Error ? err.message : "Connection failed");
      }
    }

    connect();

    return () => {
      isUnmountedRef.current = true;
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
      if (staleTimeoutRef.current) clearTimeout(staleTimeoutRef.current);
      if (socketRef.current) {
        socketRef.current.close();
        socketRef.current = null;
      }
    };
  }, [urlOverride]);

  return {
    latestState,
    connectionStatus,
    recentTrafficEvents,
    lastError,
    streamStatus,
    lastMessageAt,
  };
}
