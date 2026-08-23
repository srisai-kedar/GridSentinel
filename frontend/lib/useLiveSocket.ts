/**
 * useLiveSocket.ts
 * ----------------
 * React hook connecting to the backend WebSocket (/ws/live),
 * providing real-time state, honest connection status with exponential backoff,
 * and automatic cleanup on unmount.
 */

import { useEffect, useRef, useState } from "react";
import { ConnectionStatus, LiveSocketPayload, TrafficEvent } from "./types";

const DEFAULT_WS_URL = "ws://localhost:8000/ws/live";

export function useLiveSocket(urlOverride?: string) {
  const [latestState, setLatestState] = useState<LiveSocketPayload | null>(null);
  const [connectionStatus, setConnectionStatus] = useState<ConnectionStatus>("connecting");
  const [recentTrafficEvents, setRecentTrafficEvents] = useState<TrafficEvent[]>([]);
  const [lastError, setLastError] = useState<string | null>(null);

  const socketRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);
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
      setLastError(null);

      try {
        const ws = new WebSocket(wsUrl);
        socketRef.current = ws;

        ws.onopen = () => {
          if (isUnmountedRef.current) {
            ws.close();
            return;
          }
          setConnectionStatus("connected");
          reconnectDelayRef.current = 1000; // Reset backoff on successful connect
        };

        ws.onmessage = (event) => {
          if (isUnmountedRef.current) return;
          try {
            const data: LiveSocketPayload = JSON.parse(event.data);
            setLatestState(data);

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
        };

        ws.onclose = (event) => {
          if (isUnmountedRef.current) return;
          setConnectionStatus("disconnected");
          socketRef.current = null;

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
        setLastError(err instanceof Error ? err.message : "Connection failed");
      }
    }

    connect();

    return () => {
      isUnmountedRef.current = true;
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
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
  };
}
