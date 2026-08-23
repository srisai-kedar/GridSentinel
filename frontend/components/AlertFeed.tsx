"use client";

import React, { useEffect, useRef, useState } from "react";
import {
  AlertCircle,
  AlertTriangle,
  Bell,
  CheckCircle2,
  Filter,
  Radio,
  ShieldAlert,
  Trash2,
} from "lucide-react";
import { LiveSocketPayload, RTUVerdict, VerdictType } from "@/lib/types";
import { formatAlert, getRtuAssetLabel, getVerdictColor, SCADA_COLORS } from "@/lib/alertText";

export interface AlertFeedItem {
  id: string;
  rtuId: number;
  simTime: string;
  wallTimestamp: string;
  verdict: VerdictType;
  subtype: string | null;
  confidence: number;
  message: string;
  previousVerdict?: VerdictType;
}

interface AlertFeedProps {
  latestState: LiveSocketPayload | null;
  onAlertClick?: (rtuId: number) => void;
  onNewVerdictChange?: (item: AlertFeedItem) => void;
}

export const AlertFeed: React.FC<AlertFeedProps> = ({
  latestState,
  onAlertClick,
  onNewVerdictChange,
}) => {
  const [alerts, setAlerts] = useState<AlertFeedItem[]>([]);
  const [filter, setFilter] = useState<"ALL" | "CYBER" | "FAULT" | "NORMAL">("ALL");

  // Track previous verdicts per RTU to only log transitions / changes
  const prevVerdictsRef = useRef<Record<number, { verdict: VerdictType; subtype: string | null }>>({});

  useEffect(() => {
    if (!latestState || !latestState.ml_verdicts) return;

    const mlVerdicts = latestState.ml_verdicts;
    const simTime = latestState.sim_time || new Date().toLocaleTimeString();
    const wallTimestamp = new Date().toISOString();

    const newAlertItems: AlertFeedItem[] = [];

    // Check each RTU for verdict state changes
    Object.entries(mlVerdicts).forEach(([rtuIdStr, vData]) => {
      const rtuId = parseInt(rtuIdStr, 10);
      const verdict = vData.verdict as VerdictType;
      const subtype = vData.subtype;
      const confidence = vData.confidence;

      const prev = prevVerdictsRef.current[rtuId];

      // Detect transition or first initialization if non-normal
      const isInitial = !prev;
      const hasChanged = prev && (prev.verdict !== verdict || prev.subtype !== subtype);

      if (hasChanged || (isInitial && verdict !== "Normal")) {
        const message = formatAlert(verdict, subtype, rtuId, confidence);
        const item: AlertFeedItem = {
          id: `alert-${Date.now()}-${rtuId}-${Math.random().toString(36).substr(2, 4)}`,
          rtuId,
          simTime,
          wallTimestamp,
          verdict,
          subtype,
          confidence,
          message,
          previousVerdict: prev ? prev.verdict : undefined,
        };

        newAlertItems.push(item);

        if (onNewVerdictChange) {
          onNewVerdictChange(item);
        }
      }

      // Update ref
      prevVerdictsRef.current[rtuId] = { verdict, subtype };
    });

    if (newAlertItems.length > 0) {
      setAlerts((prev) => [...newAlertItems, ...prev].slice(0, 100)); // Keep newest 100
    }
  }, [latestState, onNewVerdictChange]);

  const filteredAlerts = alerts.filter((a) => {
    if (filter === "CYBER") return a.verdict === "Cyber Intrusion";
    if (filter === "FAULT") return a.verdict === "Natural Fault";
    if (filter === "NORMAL") return a.verdict === "Normal";
    return true;
  });

  const clearAlerts = () => {
    setAlerts([]);
  };

  const getAlertIcon = (verdict: VerdictType) => {
    switch (verdict) {
      case "Cyber Intrusion":
        return <ShieldAlert className="w-4 h-4 text-rose-500 shrink-0 mt-0.5" />;
      case "Natural Fault":
        return <AlertTriangle className="w-4 h-4 text-amber-500 shrink-0 mt-0.5" />;
      case "Normal":
        return <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0 mt-0.5" />;
      default:
        return <AlertCircle className="w-4 h-4 text-gray-400 shrink-0 mt-0.5" />;
    }
  };

  return (
    <div className="flex flex-col h-full bg-[#111827] rounded-lg border border-gray-800 overflow-hidden select-none">
      {/* Feed Header */}
      <div className="p-3 border-b border-gray-800 bg-[#0F172A] flex items-center justify-between">
        <div className="flex items-center space-x-2">
          <Bell className="w-4 h-4 text-cyan-400" />
          <h2 className="text-xs font-bold text-gray-200 uppercase tracking-wider">
            Real-Time Alert Feed
          </h2>
          <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-gray-800 text-gray-400 font-mono border border-gray-700">
            {filteredAlerts.length}
          </span>
        </div>

        <div className="flex items-center space-x-1.5">
          {/* Clear Button */}
          {alerts.length > 0 && (
            <button
              onClick={clearAlerts}
              title="Clear feed"
              className="text-gray-400 hover:text-gray-200 p-1 rounded hover:bg-gray-800 transition"
            >
              <Trash2 className="w-3.5 h-3.5" />
            </button>
          )}
        </div>
      </div>

      {/* Filter Tabs */}
      <div className="flex items-center space-x-1 p-2 bg-[#0B0F19] border-b border-gray-800 text-[11px]">
        <button
          onClick={() => setFilter("ALL")}
          className={`px-2 py-1 rounded transition font-medium ${
            filter === "ALL"
              ? "bg-slate-700 text-white font-semibold"
              : "text-gray-400 hover:text-gray-200"
          }`}
        >
          All
        </button>
        <button
          onClick={() => setFilter("CYBER")}
          className={`px-2 py-1 rounded transition font-medium ${
            filter === "CYBER"
              ? "bg-rose-950/80 text-rose-300 border border-rose-800"
              : "text-gray-400 hover:text-rose-300"
          }`}
        >
          Cyber ({alerts.filter((a) => a.verdict === "Cyber Intrusion").length})
        </button>
        <button
          onClick={() => setFilter("FAULT")}
          className={`px-2 py-1 rounded transition font-medium ${
            filter === "FAULT"
              ? "bg-amber-950/80 text-amber-300 border border-amber-800"
              : "text-gray-400 hover:text-amber-300"
          }`}
        >
          Fault ({alerts.filter((a) => a.verdict === "Natural Fault").length})
        </button>
        <button
          onClick={() => setFilter("NORMAL")}
          className={`px-2 py-1 rounded transition font-medium ${
            filter === "NORMAL"
              ? "bg-emerald-950/80 text-emerald-300 border border-emerald-800"
              : "text-gray-400 hover:text-emerald-300"
          }`}
        >
          Normal
        </button>
      </div>

      {/* Scrolling Alert Cards */}
      <div className="flex-1 overflow-y-auto p-2 space-y-2 max-h-[480px]">
        {filteredAlerts.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-48 text-center p-4">
            <Radio className="w-8 h-8 text-gray-600 mb-2 animate-pulse" />
            <p className="text-xs text-gray-400 font-medium">No state transitions detected</p>
            <p className="text-[10px] text-gray-500 mt-1 max-w-[200px]">
              Trigger an attack or physical fault scenario to observe plain-language triage alerts.
            </p>
          </div>
        ) : (
          filteredAlerts.map((alert) => {
            const color = getVerdictColor(alert.verdict);
            const assetName = getRtuAssetLabel(alert.rtuId);

            return (
              <div
                key={alert.id}
                onClick={() => onAlertClick && onAlertClick(alert.rtuId)}
                className="group relative p-2.5 rounded-md border transition-all duration-200 cursor-pointer bg-[#0D1322] hover:bg-[#131B30]"
                style={{
                  borderColor: `${color}40`,
                  boxShadow: alert.verdict !== "Normal" ? `0 0 10px ${color}15` : undefined,
                }}
              >
                {/* Left color bar */}
                <div
                  className="absolute left-0 top-0 bottom-0 w-1 rounded-l-md"
                  style={{ backgroundColor: color }}
                />

                <div className="flex items-start space-x-2 pl-1.5">
                  {getAlertIcon(alert.verdict)}

                  <div className="flex-1 min-w-0">
                    <div className="flex items-center justify-between gap-1 mb-1">
                      <span className="font-mono text-[11px] font-bold text-gray-200 truncate">
                        {assetName}
                      </span>
                      <span className="font-mono text-[10px] text-cyan-400 shrink-0">
                        {alert.simTime}
                      </span>
                    </div>

                    <p className="text-xs text-gray-300 leading-snug font-sans break-words mb-1.5">
                      {alert.message}
                    </p>

                    <div className="flex flex-wrap items-center justify-between text-[10px] text-gray-400 gap-1 pt-1 border-t border-gray-800">
                      <span
                        className="font-mono font-semibold px-1.5 py-0.2 rounded"
                        style={{
                          backgroundColor: `${color}20`,
                          color: color,
                        }}
                      >
                        {alert.verdict} {alert.subtype ? `• ${alert.subtype}` : ""}
                      </span>

                      <span className="font-mono text-gray-400">
                        Conf: {(alert.confidence * 100).toFixed(0)}%
                      </span>
                    </div>
                  </div>
                </div>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
};
