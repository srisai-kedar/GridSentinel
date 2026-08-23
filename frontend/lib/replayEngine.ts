/**
 * replayEngine.ts
 * ---------------
 * Replays a pre-recorded session into the GridSentinel frontend state
 * without requiring any connection to a live backend.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { LiveSocketPayload } from "./types";
import { RecordedSession } from "./sessionRecorder";

export interface ReplayState {
  isLoaded: boolean;
  isPlaying: boolean;
  currentIndex: number;
  totalEvents: number;
  progressPercent: number;
  playbackSpeed: number;
  currentPayload: LiveSocketPayload | null;
  sessionInfo: {
    createdAt: string;
    totalDurationMs: number;
  } | null;
}

export function useReplayEngine(
  initialSession?: RecordedSession | null,
  onPayloadUpdate?: (payload: LiveSocketPayload) => void
) {
  const [session, setSession] = useState<RecordedSession | null>(initialSession || null);
  const [isPlaying, setIsPlaying] = useState<boolean>(false);
  const [currentIndex, setCurrentIndex] = useState<number>(0);
  const [playbackSpeed, setPlaybackSpeed] = useState<number>(1.0);
  const [currentPayload, setCurrentPayload] = useState<LiveSocketPayload | null>(null);

  const timeoutRef = useRef<NodeJS.Timeout | null>(null);
  const isPlayingRef = useRef<boolean>(false);
  const currentIndexRef = useRef<number>(0);
  const sessionRef = useRef<RecordedSession | null>(session);
  const playbackSpeedRef = useRef<number>(playbackSpeed);
  const onPayloadUpdateRef = useRef(onPayloadUpdate);

  useEffect(() => {
    onPayloadUpdateRef.current = onPayloadUpdate;
  }, [onPayloadUpdate]);

  useEffect(() => {
    sessionRef.current = session;
  }, [session]);

  useEffect(() => {
    playbackSpeedRef.current = playbackSpeed;
  }, [playbackSpeed]);

  const emitPayloadAtIndex = useCallback((index: number, sess?: RecordedSession) => {
    const s = sess || sessionRef.current;
    if (!s || index < 0 || index >= s.events.length) return;

    const ev = s.events[index];
    if (ev && ev.payload) {
      setCurrentPayload(ev.payload);
      if (onPayloadUpdateRef.current) {
        onPayloadUpdateRef.current(ev.payload);
      }
    }
  }, []);

  const clearTimer = () => {
    if (timeoutRef.current) {
      clearTimeout(timeoutRef.current);
      timeoutRef.current = null;
    }
  };

  const scheduleNextStep = useCallback(() => {
    if (!isPlayingRef.current || !sessionRef.current) return;
    const sess = sessionRef.current;
    const currIdx = currentIndexRef.current;

    if (currIdx >= sess.events.length - 1) {
      // Loop or pause at end
      isPlayingRef.current = false;
      setIsPlaying(false);
      return;
    }

    const currentDelta = sess.events[currIdx].deltaMs;
    const nextDelta = sess.events[currIdx + 1].deltaMs;
    const rawDelay = Math.max(10, nextDelta - currentDelta);
    const scaledDelay = Math.max(5, rawDelay / playbackSpeedRef.current);

    clearTimer();
    timeoutRef.current = setTimeout(() => {
      if (!isPlayingRef.current) return;
      const nextIdx = currentIndexRef.current + 1;
      currentIndexRef.current = nextIdx;
      setCurrentIndex(nextIdx);
      emitPayloadAtIndex(nextIdx);
      scheduleNextStep();
    }, scaledDelay);
  }, [emitPayloadAtIndex]);

  const play = useCallback(() => {
    if (!sessionRef.current || sessionRef.current.events.length === 0) return;
    isPlayingRef.current = true;
    setIsPlaying(true);

    if (currentIndexRef.current >= sessionRef.current.events.length - 1) {
      currentIndexRef.current = 0;
      setCurrentIndex(0);
      emitPayloadAtIndex(0);
    }
    scheduleNextStep();
  }, [emitPayloadAtIndex, scheduleNextStep]);

  const pause = useCallback(() => {
    isPlayingRef.current = false;
    setIsPlaying(false);
    clearTimer();
  }, []);

  const stop = useCallback(() => {
    isPlayingRef.current = false;
    setIsPlaying(false);
    clearTimer();
    currentIndexRef.current = 0;
    setCurrentIndex(0);
    emitPayloadAtIndex(0);
  }, [emitPayloadAtIndex]);

  const seekToIndex = useCallback(
    (index: number) => {
      if (!sessionRef.current) return;
      const validIndex = Math.max(0, Math.min(index, sessionRef.current.events.length - 1));
      currentIndexRef.current = validIndex;
      setCurrentIndex(validIndex);
      emitPayloadAtIndex(validIndex);
    },
    [emitPayloadAtIndex]
  );

  const seekToPercent = useCallback(
    (pct: number) => {
      if (!sessionRef.current || sessionRef.current.events.length === 0) return;
      const clampedPct = Math.max(0, Math.min(100, pct));
      const targetIndex = Math.round(((sessionRef.current.events.length - 1) * clampedPct) / 100);
      seekToIndex(targetIndex);
    },
    [seekToIndex]
  );

  const loadSession = useCallback(
    (newSession: RecordedSession) => {
      pause();
      setSession(newSession);
      sessionRef.current = newSession;
      currentIndexRef.current = 0;
      setCurrentIndex(0);
      if (newSession.events.length > 0) {
        emitPayloadAtIndex(0, newSession);
      }
    },
    [emitPayloadAtIndex, pause]
  );

  const loadSessionFromJson = useCallback(
    (jsonString: string) => {
      try {
        const parsed = JSON.parse(jsonString) as RecordedSession;
        if (!parsed.events || !Array.isArray(parsed.events)) {
          throw new Error("Invalid session format: missing events array");
        }
        loadSession(parsed);
        return true;
      } catch (err) {
        console.error("[replayEngine] Failed to parse session JSON:", err);
        return false;
      }
    },
    [loadSession]
  );

  useEffect(() => {
    if (initialSession) {
      loadSession(initialSession);
    }
    return () => {
      clearTimer();
    };
  }, [initialSession, loadSession]);

  const totalEvents = session?.events.length || 0;
  const progressPercent = totalEvents > 1 ? (currentIndex / (totalEvents - 1)) * 100 : 0;

  return {
    isLoaded: Boolean(session && session.events.length > 0),
    isPlaying,
    currentIndex,
    totalEvents,
    progressPercent,
    playbackSpeed,
    currentPayload,
    session,
    play,
    pause,
    stop,
    seekToIndex,
    seekToPercent,
    setPlaybackSpeed,
    loadSession,
    loadSessionFromJson,
  };
}
