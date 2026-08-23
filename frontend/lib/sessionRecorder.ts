/**
 * sessionRecorder.ts
 * ------------------
 * Buffers live /ws/live messages for session archival and offline replay.
 */

import { useCallback, useRef, useState } from "react";
import { LiveSocketPayload } from "./types";

export interface RecordedSessionEvent {
  deltaMs: number;
  timestamp: string;
  payload: LiveSocketPayload;
}

export interface RecordedSession {
  version: "1.0";
  createdAt: string;
  totalDurationMs: number;
  eventCount: number;
  events: RecordedSessionEvent[];
}

export class SessionRecorder {
  private events: RecordedSessionEvent[] = [];
  private startTime: number | null = null;
  private isRecording: boolean = false;

  start() {
    this.events = [];
    this.startTime = Date.now();
    this.isRecording = true;
  }

  record(payload: LiveSocketPayload) {
    if (!this.isRecording || this.startTime === null) return;
    const deltaMs = Date.now() - this.startTime;
    this.events.push({
      deltaMs,
      timestamp: new Date().toISOString(),
      payload: JSON.parse(JSON.stringify(payload)), // deep clone
    });
  }

  stop(): RecordedSession {
    this.isRecording = false;
    const totalDurationMs = this.startTime !== null ? Date.now() - this.startTime : 0;
    const session: RecordedSession = {
      version: "1.0",
      createdAt: new Date().toISOString(),
      totalDurationMs,
      eventCount: this.events.length,
      events: [...this.events],
    };
    return session;
  }

  getEventCount(): number {
    return this.events.length;
  }

  isActive(): boolean {
    return this.isRecording;
  }

  exportJson(session?: RecordedSession): string {
    const data = session || this.stop();
    return JSON.stringify(data, null, 2);
  }

  static download(session: RecordedSession, filenamePrefix: string = "GridSentinel_Session") {
    const jsonStr = JSON.stringify(session, null, 2);
    const blob = new Blob([jsonStr], { type: "application/json;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `${filenamePrefix}_${new Date().toISOString().slice(0, 19).replace(/[:T]/g, "-")}.json`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  }
}

export function useSessionRecorder() {
  const recorderRef = useRef<SessionRecorder>(new SessionRecorder());
  const [isRecording, setIsRecording] = useState<boolean>(false);
  const [eventCount, setEventCount] = useState<number>(0);
  const [recordedSession, setRecordedSession] = useState<RecordedSession | null>(null);

  const startRecording = useCallback(() => {
    recorderRef.current.start();
    setIsRecording(true);
    setEventCount(0);
    setRecordedSession(null);
  }, []);

  const recordPayload = useCallback((payload: LiveSocketPayload | null) => {
    if (!payload || !recorderRef.current.isActive()) return;
    recorderRef.current.record(payload);
    setEventCount(recorderRef.current.getEventCount());
  }, []);

  const stopRecording = useCallback(() => {
    const session = recorderRef.current.stop();
    setIsRecording(false);
    setEventCount(session.eventCount);
    setRecordedSession(session);
    return session;
  }, []);

  const downloadRecording = useCallback((sessionToDownload?: RecordedSession) => {
    const target = sessionToDownload || recordedSession || recorderRef.current.stop();
    SessionRecorder.download(target);
  }, [recordedSession]);

  return {
    isRecording,
    eventCount,
    startRecording,
    recordPayload,
    stopRecording,
    downloadRecording,
    recordedSession,
  };
}
