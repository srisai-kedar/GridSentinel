"use client";

import React, { useState } from "react";
import {
  AuditLogEntry,
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
  Search,
  Shield,
  ShieldAlert,
  Trash2,
} from "lucide-react";

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

  return (
    <div data-testid="audit-log" className="flex flex-col h-full bg-[#0E1118] rounded-[10px] border border-white/[0.07] overflow-hidden text-xs select-none">
      {/* Header */}
      <div className="scada-audit-toolbar p-3 bg-[#0E1118] border-b border-white/[0.07] flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center space-x-2">
          <Shield className="w-3.5 h-3.5 text-[#10B981]" />
          <h2 className="font-bold text-[#EDEDF0] uppercase tracking-wider text-xs">
            CEA-2026 Incident Audit Trail Log
          </h2>
          <span className="text-[10px] px-2 py-0.5 rounded-[4px] bg-[#131722] text-[#10B981] font-mono border border-white/[0.06]">
            {filteredEntries.length} Events Logged
          </span>
        </div>

        {/* Action Controls: Search, Export, Clear */}
        <div className="scada-audit-actions flex items-center space-x-2">
          {/* Search bar */}
          <div className="relative">
            <Search className="w-3.5 h-3.5 text-[#5A6275] absolute left-2.5 top-1/2 -translate-y-1/2" />
            <input
              type="text"
              placeholder="Search audit trail..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="bg-[#131722] text-[#EDEDF0] placeholder-[#5A6275] text-[11px] pl-8 pr-2.5 py-1 rounded-[6px] border border-white/[0.08] focus:outline-none focus:border-[#8B5CF6] w-36 md:w-48 transition"
            />
          </div>

          {/* Filter dropdown */}
          <select
            value={selectedFilter}
            onChange={(e) => setSelectedFilter(e.target.value)}
            className="bg-[#131722] text-[#9CA3AF] text-[11px] px-2 py-1 rounded-[6px] border border-white/[0.08] focus:outline-none"
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
            className="flex items-center space-x-1 bg-[#131722] hover:bg-[#181E2C] text-[#EDEDF0] border border-white/[0.08] px-2.5 py-1 rounded-[6px] transition disabled:opacity-40 disabled:cursor-not-allowed font-medium text-[11px]"
            title="Download CSV report"
          >
            <FileSpreadsheet className="w-3.5 h-3.5 text-[#10B981]" />
            <span className="hidden sm:inline">Export CSV</span>
          </button>

          {/* Export JSON */}
          <button
            onClick={exportJson}
            disabled={entries.length === 0}
            className="flex items-center space-x-1 bg-[#131722] hover:bg-[#181E2C] text-[#EDEDF0] border border-white/[0.08] px-2.5 py-1 rounded-[6px] transition disabled:opacity-40 disabled:cursor-not-allowed font-medium text-[11px]"
            title="Download JSON telemetry"
          >
            <FileText className="w-3.5 h-3.5 text-[#A78BFA]" />
            <span className="hidden sm:inline">Export JSON</span>
          </button>

          {/* Clear Logs */}
          {onClearLogs && (
            <button
              onClick={onClearLogs}
              disabled={entries.length === 0}
              className="text-[#5A6275] hover:text-[#EF4444] p-1.5 rounded-[6px] hover:bg-[#181E2C] transition disabled:opacity-30"
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
                        className="inline-flex items-center space-x-1 px-2 py-0.5 rounded-[4px] font-medium uppercase tracking-wider text-[10px]"
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
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
};
