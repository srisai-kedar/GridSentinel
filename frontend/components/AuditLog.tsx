"use client";

import React, { useState } from "react";
import {
  AuditLogEntry,
  IncidentReplayResponse,
  ReplayWindowPoint,
  VerdictType,
} from "@/lib/types";
import {
  formatAlert,
  getNetworkEvidenceSummary,
  getPhysicsEvidenceSummary,
  getRecommendedAction,
  getRtuAssetLabel,
  getVerdictColor,
  SCADA_COLORS,
} from "@/lib/alertText";
import {
  AlertTriangle,
  CheckCircle2,
  Download,
  FileSpreadsheet,
  FileText,
  LoaderCircle,
  Search,
  Shield,
  ShieldAlert,
  History,
  Trash2,
} from "lucide-react";
import { downloadIncidentReport, getIncidentReplay } from "@/lib/api";

interface AuditLogProps {
  entries: AuditLogEntry[];
  onClearLogs?: () => void;
}

export function generateCsvData(entries: AuditLogEntry[]): string {
  const headers = [
    "Detection Time (Sim)",
    "Detection Time (UTC)",
    "RTU ID",
    "Affected Asset",
    "Classification",
    "Subtype",
    "Confidence (%)",
    "Network Evidence Summary",
    "Physics Evidence Summary",
    "Recommended Action",
    "Plain-Language Incident Triage",
  ];

  const escapeCsv = (str: string | number) => {
    const val = String(str).replace(/"/g, '""');
    return `"${val}"`;
  };

  const rows = entries.map((e) => [
    escapeCsv(e.simTime),
    escapeCsv(e.timestamp),
    escapeCsv(e.rtuId),
    escapeCsv(e.assetName),
    escapeCsv(e.classification),
    escapeCsv(e.subtype || "N/A"),
    escapeCsv(`${(e.confidence * 100).toFixed(1)}%`),
    escapeCsv(e.networkSummary),
    escapeCsv(e.physicsSummary),
    escapeCsv(e.recommendedAction),
    escapeCsv(e.formattedAlert),
  ]);

  return [headers.join(","), ...rows.map((r) => r.join(","))].join("\n");
}

export const AuditLog: React.FC<AuditLogProps> = ({
  entries,
  onClearLogs,
}) => {
  const [searchTerm, setSearchTerm] = useState<string>("");
  const [selectedFilter, setSelectedFilter] = useState<string>("ALL");
  const [reportLoadingId, setReportLoadingId] = useState<string | null>(null);
  const [reportError, setReportError] = useState<string | null>(null);
  const [replayLoadingId, setReplayLoadingId] = useState<string | null>(null);
  const [replayError, setReplayError] = useState<string | null>(null);
  const [selectedReplay, setSelectedReplay] = useState<{
    entry: AuditLogEntry;
    data: IncidentReplayResponse;
  } | null>(null);
  const [replayIndex, setReplayIndex] = useState(0);

  const filteredEntries = entries.filter((entry) => {
    const matchesSearch =
      entry.assetName.toLowerCase().includes(searchTerm.toLowerCase()) ||
      entry.classification.toLowerCase().includes(searchTerm.toLowerCase()) ||
      (entry.subtype && entry.subtype.toLowerCase().includes(searchTerm.toLowerCase())) ||
      entry.formattedAlert.toLowerCase().includes(searchTerm.toLowerCase());

    if (selectedFilter === "CYBER") {
      return matchesSearch && entry.classification === "Cyber Intrusion";
    }
    if (selectedFilter === "FAULT") {
      return matchesSearch && entry.classification === "Natural Fault";
    }
    if (selectedFilter === "NORMAL") {
      return matchesSearch && entry.classification === "Normal";
    }
    return matchesSearch;
  });

  const exportCsv = () => {
    const csvContent = generateCsvData(entries);
    const blob = new Blob([csvContent], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.setAttribute("href", url);
    link.setAttribute(
      "download",
      `GridSentinel_AuditLog_CEA2026_${new Date().toISOString().slice(0, 19).replace(/[:T]/g, "-")}.csv`
    );
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  const exportJson = () => {
    const jsonContent = JSON.stringify(entries, null, 2);
    const blob = new Blob([jsonContent], { type: "application/json;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.setAttribute("href", url);
    link.setAttribute(
      "download",
      `GridSentinel_AuditLog_${new Date().toISOString().slice(0, 19).replace(/[:T]/g, "-")}.json`
    );
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  const handleDownloadReport = async (entry: AuditLogEntry) => {
    setReportLoadingId(entry.id);
    setReportError(null);
    try {
      const blob = await downloadIncidentReport(entry.id);
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `GridSentinel-incident-${entry.id}.pdf`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(url);
    } catch (error) {
      setReportError(error instanceof Error ? error.message : "Report unavailable");
    } finally {
      setReportLoadingId(null);
    }
  };

  const handleOpenReplay = async (entry: AuditLogEntry) => {
    setReplayLoadingId(entry.id);
    setReplayError(null);
    try {
      const data = await getIncidentReplay(entry.id);
      if (data.replay_window.length === 0) {
        throw new Error("Replay window is not available for this incident yet.");
      }
      setSelectedReplay({ entry, data });
      setReplayIndex(Math.max(0, data.replay_window.findIndex((point) => point.tick_offset === 0)));
    } catch (error) {
      setReplayError(error instanceof Error ? error.message : "Replay unavailable");
    } finally {
      setReplayLoadingId(null);
    }
  };

  const activeReplayPoint: ReplayWindowPoint | null = selectedReplay?.data.replay_window[replayIndex] || null;
  const replayResidual = activeReplayPoint?.pcd.pcd_max_lnr;
  const replayAnomaly = activeReplayPoint
    ? activeReplayPoint.nbd.nbd_unexpected_write_count > 0 || activeReplayPoint.nbd.nbd_modbus_anomaly_rate > 0
    : false;

  const formatReplayNumber = (value: number | null | undefined, digits = 4) =>
    typeof value === "number" ? value.toFixed(digits) : "Not recorded";

  return (
    <div data-testid="audit-log" className="scada-audit-panel flex flex-col h-full overflow-hidden text-xs select-none">
      {/* Header */}
      <div className="scada-audit-toolbar p-3 bg-[#0E1118] border-b border-white/[0.07] flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center space-x-2">
          <Shield className="w-3.5 h-3.5 text-[#10B981]" />
          <h2 className="font-bold text-[#EDEDF0] uppercase tracking-wider text-xs">
            CEA-2026 Incident Audit Trail Log
          </h2>
          <span className="text-[10px] px-2 py-0.5 rounded-[2px] bg-[#131722] text-[#10B981] font-mono border border-white/[0.06]">
            {filteredEntries.length} Events Logged
          </span>
        </div>

        {/* Action Controls: Search, Export, Clear */}
        <div className="scada-audit-actions flex items-center space-x-2">
          {(reportError || replayError) && <span role="status" className="text-[10px] text-[#EF4444]">{reportError || replayError}</span>}
          {/* Search bar */}
          <div className="relative">
            <Search className="w-3.5 h-3.5 text-[#5A6275] absolute left-2.5 top-1/2 -translate-y-1/2" />
            <input
              type="text"
              placeholder="Search audit trail..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="bg-[#131722] text-[#EDEDF0] placeholder-[#5A6275] text-[11px] pl-8 pr-2.5 py-1 rounded-[3px] border border-white/[0.08] focus:outline-none focus:border-[#7D8FB0] w-36 md:w-48 transition"
            />
          </div>

          {/* Filter dropdown */}
          <select
            value={selectedFilter}
            onChange={(e) => setSelectedFilter(e.target.value)}
            className="bg-[#131722] text-[#9CA3AF] text-[11px] px-2 py-1 rounded-[3px] border border-white/[0.08] focus:outline-none"
          >
            <option value="ALL">All Categories</option>
            <option value="CYBER">Cyber Intrusion</option>
            <option value="FAULT">Natural Fault</option>
            <option value="NORMAL">Normal Operation</option>
          </select>

          {/* Export CSV */}
          <button
            onClick={exportCsv}
            disabled={entries.length === 0}
            className="flex items-center space-x-1 bg-[#131722] hover:bg-[#181E2C] text-[#EDEDF0] border border-white/[0.08] px-2.5 py-1 rounded-[3px] transition disabled:opacity-40 disabled:cursor-not-allowed font-medium text-[11px]"
            title="Download CSV report"
          >
            <FileSpreadsheet className="w-3.5 h-3.5 text-[#10B981]" />
            <span className="hidden sm:inline">Export CSV</span>
          </button>

          {/* Export JSON */}
          <button
            onClick={exportJson}
            disabled={entries.length === 0}
            className="flex items-center space-x-1 bg-[#131722] hover:bg-[#181E2C] text-[#EDEDF0] border border-white/[0.08] px-2.5 py-1 rounded-[3px] transition disabled:opacity-40 disabled:cursor-not-allowed font-medium text-[11px]"
            title="Download JSON telemetry"
          >
            <FileText className="w-3.5 h-3.5 text-[#AAB8CE]" />
            <span className="hidden sm:inline">Export JSON</span>
          </button>

          {/* Clear Logs */}
          {onClearLogs && (
            <button
              onClick={onClearLogs}
              disabled={entries.length === 0}
              className="text-[#5A6275] hover:text-[#EF4444] p-1.5 rounded-[3px] hover:bg-[#181E2C] transition disabled:opacity-30"
              title="Clear session audit log"
            >
              <Trash2 className="w-3.5 h-3.5" />
            </button>
          )}
        </div>
      </div>

      {/* Table Container */}
      <div className="flex-1 min-h-0 overflow-auto max-h-[500px]">
        {filteredEntries.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-48 text-center p-6 text-[#5A6275]">
            <Shield className="w-6 h-6 text-[#5A6275] mb-2 opacity-50" />
            <p className="text-xs text-[#9CA3AF]">No audit events matching criteria</p>
            <p className="text-[10px] text-[#5A6275] mt-1">
              Events are automatically captured when telemetry verdict state changes occur.
            </p>
          </div>
        ) : (
          <table className="w-full text-left border-collapse font-mono text-[11px]">
            <thead className="bg-[#131722] text-[#5A6275] sticky top-0 border-b border-white/[0.07] z-10 uppercase text-[10px] tracking-wider">
              <tr>
                <th className="p-2.5 font-medium text-[#9CA3AF]">Time (Sim / UTC)</th>
                <th className="p-2.5 font-medium text-[#9CA3AF]">Affected Asset</th>
                <th className="p-2.5 font-medium text-[#9CA3AF]">Classification</th>
                <th className="p-2.5 font-medium text-[#9CA3AF]">Subtype</th>
                <th className="p-2.5 font-medium text-[#9CA3AF]">Conf</th>
                <th className="p-2.5 font-medium text-[#9CA3AF] min-w-[180px]">Network Signal</th>
                <th className="p-2.5 font-medium text-[#9CA3AF] min-w-[180px]">Physics Signal</th>
                <th className="p-2.5 font-medium text-[#9CA3AF] min-w-[200px]">Recommended Action</th>
                <th className="p-2.5 font-medium text-[#9CA3AF]">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/[0.04] bg-[#0E1118]">
              {filteredEntries.map((entry) => {
                const color = getVerdictColor(entry.classification);

                return (
                  <tr
                    key={entry.id}
                    className="hover:bg-[#181E2C] transition-colors duration-150"
                  >
                    {/* Time */}
                    <td className="p-2.5 whitespace-nowrap text-[#9CA3AF]">
                      <div className="font-medium text-[#EDEDF0]">{entry.simTime}</div>
                      <div className="text-[9px] text-[#5A6275]">{entry.timestamp.slice(11, 19)} UTC</div>
                    </td>

                    {/* Asset */}
                    <td className="p-2.5 whitespace-nowrap font-medium text-[#EDEDF0]">
                      {entry.assetName}
                    </td>

                    {/* Classification */}
                    <td className="p-2.5 whitespace-nowrap">
                      <span
                        className="inline-flex items-center space-x-1 px-2 py-0.5 rounded-[2px] font-medium uppercase tracking-wider text-[10px]"
                        style={{
                          backgroundColor: `${color}15`,
                          color: color,
                          border: `1px solid ${color}35`,
                        }}
                      >
                        {entry.classification === "Cyber Intrusion" && (
                          <ShieldAlert className="w-3 h-3 text-[#EF4444] mr-1" />
                        )}
                        {entry.classification === "Natural Fault" && (
                          <AlertTriangle className="w-3 h-3 text-[#F59E0B] mr-1" />
                        )}
                        {entry.classification === "Normal" && (
                          <CheckCircle2 className="w-3 h-3 text-[#10B981] mr-1" />
                        )}
                        <span>{entry.classification}</span>
                      </span>
                    </td>

                    {/* Subtype */}
                    <td className="p-2.5 whitespace-nowrap text-[#5A6275]">
                      {entry.subtype || "none"}
                    </td>

                    {/* Confidence */}
                    <td className="p-2.5 whitespace-nowrap font-bold text-[#EDEDF0]">
                      {(entry.confidence * 100).toFixed(0)}%
                    </td>

                    {/* Network Signal */}
                    <td className="p-2.5 text-[#9CA3AF] text-[10px] leading-relaxed font-sans">
                      {entry.networkSummary}
                    </td>

                    {/* Physics Signal */}
                    <td className="p-2.5 text-[#9CA3AF] text-[10px] leading-relaxed font-sans">
                      {entry.physicsSummary}
                    </td>

                    {/* Recommended Action */}
                    <td className="p-2.5 text-[#F59E0B] text-[10px] leading-relaxed font-sans">
                      {entry.recommendedAction}
                    </td>

                    <td className="p-2.5 whitespace-nowrap">
                      <button
                        type="button"
                        onClick={() => void handleOpenReplay(entry)}
                        disabled={replayLoadingId !== null}
                        className="mr-1 inline-flex items-center gap-1 rounded-[2px] border border-white/[0.08] bg-[#131722] px-2 py-1 text-[10px] font-medium text-[#AAB8CE] hover:border-[#7D8FB0] hover:text-[#EDEDF0] disabled:cursor-not-allowed disabled:opacity-40"
                        title="Open forensic replay"
                        aria-label={`Replay incident for ${entry.assetName}`}
                      >
                        {replayLoadingId === entry.id ? <LoaderCircle className="h-3 w-3 animate-spin" /> : <History className="h-3 w-3" />}
                        <span className="hidden sm:inline">Replay</span>
                      </button>
                      <button
                        type="button"
                        onClick={() => void handleDownloadReport(entry)}
                        disabled={reportLoadingId !== null}
                        className="inline-flex items-center gap-1 rounded-[2px] border border-white/[0.08] bg-[#131722] px-2 py-1 text-[10px] font-medium text-[#AAB8CE] hover:border-[#7D8FB0] hover:text-[#EDEDF0] disabled:cursor-not-allowed disabled:opacity-40"
                        title="Download incident report PDF"
                        aria-label={`Download report for ${entry.assetName}`}
                      >
                        {reportLoadingId === entry.id ? <LoaderCircle className="h-3 w-3 animate-spin" /> : <Download className="h-3 w-3" />}
                        <span className="hidden sm:inline">Download</span>
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>

      {selectedReplay && activeReplayPoint && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4" role="presentation" onMouseDown={(event) => {
          if (event.target === event.currentTarget) setSelectedReplay(null);
        }}>
          <section
            role="dialog"
            aria-modal="true"
            aria-labelledby="incident-replay-title"
            className="w-full max-w-lg rounded-[4px] border border-[#29394e] bg-[#0E1118] p-4 text-[#EDEDF0] shadow-2xl"
          >
            <div className="flex items-start justify-between gap-4 border-b border-white/[0.07] pb-3">
              <div>
                <span className="scada-kicker">Forensic replay · static captured window</span>
                <h2 id="incident-replay-title" className="mt-1 text-sm font-semibold">{selectedReplay.entry.assetName}</h2>
              </div>
              <button type="button" onClick={() => setSelectedReplay(null)} className="text-xs text-[#9CA3AF] hover:text-[#EDEDF0]" aria-label="Close replay">Close</button>
            </div>

            <div className="mt-4 space-y-3">
              <label className="block text-[10px] uppercase tracking-wider text-[#9CA3AF]" htmlFor="incident-replay-scrubber">
                Tick {activeReplayPoint.tick_offset > 0 ? `+${activeReplayPoint.tick_offset}` : activeReplayPoint.tick_offset} · {activeReplayPoint.sim_time || "Not recorded"}
              </label>
              <input
                id="incident-replay-scrubber"
                type="range"
                min={0}
                max={selectedReplay.data.replay_window.length - 1}
                value={replayIndex}
                onChange={(event) => setReplayIndex(Number(event.target.value))}
                className="w-full accent-[#AAB8CE]"
              />
              <div className="flex justify-between text-[9px] font-mono text-[#5A6275]">
                <span>{selectedReplay.data.replay_window[0].tick_offset}</span>
                <span>{selectedReplay.data.replay_window[selectedReplay.data.replay_window.length - 1].tick_offset}</span>
              </div>

              <div className="grid grid-cols-2 gap-2 text-[10px]">
                <div className="rounded-[3px] border border-white/[0.07] bg-[#131722] p-3">
                  <span className="text-[#5A6275]">Affected RTU</span>
                  <strong className="mt-1 block text-[#EDEDF0]">RTU-{selectedReplay.data.rtu_id ?? "Not recorded"}</strong>
                  <span className="mt-2 block text-[#5A6275]">Verdict</span>
                  <strong className="mt-1 block" style={{ color: activeReplayPoint.verdict === "Cyber Intrusion" ? "#EF4444" : activeReplayPoint.verdict === "Natural Fault" ? "#F59E0B" : "#10B981" }}>
                    {activeReplayPoint.verdict || "Not recorded"}
                  </strong>
                </div>
                <div className="rounded-[3px] border border-white/[0.07] bg-[#131722] p-3">
                  <span className="text-[#5A6275]">Feeder state</span>
                  <strong className={`mt-1 block ${replayAnomaly ? "text-[#EF4444]" : "text-[#10B981]"}`}>{replayAnomaly ? "ANOMALOUS" : "NOMINAL"}</strong>
                  <span className="mt-2 block text-[#5A6275]">Max normalized residual</span>
                  <strong className="mt-1 block font-mono text-[#EDEDF0]">{formatReplayNumber(replayResidual, 2)}</strong>
                </div>
              </div>

              <div className="grid grid-cols-3 gap-2 border-t border-white/[0.07] pt-3 text-[10px] font-mono text-[#AAB8CE]">
                <span>V {formatReplayNumber(activeReplayPoint.voltage_pu, 5)} pu</span>
                <span>P {formatReplayNumber(activeReplayPoint.p_mw, 5)} MW</span>
                <span>Q {formatReplayNumber(activeReplayPoint.q_mvar, 5)} Mvar</span>
              </div>
              <div className="text-[9px] text-[#5A6275]">Network anomaly: {replayAnomaly ? "detected in captured NBD fields" : "not detected in captured NBD fields"}. Values are the recorded classifier inputs for this tick.</div>
            </div>
          </section>
        </div>
      )}
    </div>
  );
};
