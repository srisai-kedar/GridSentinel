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
    <div className="flex flex-col h-full bg-[#0F172A] rounded-lg border border-gray-800 overflow-hidden text-xs select-none">
      {/* Header */}
      <div className="p-3 bg-[#0B0F19] border-b border-gray-800 flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center space-x-2">
          <Shield className="w-4 h-4 text-emerald-400" />
          <h2 className="font-bold text-gray-200 uppercase tracking-wider text-xs">
            CEA-2026 Cyber-Physical Incident Audit Trail
          </h2>
          <span className="text-[10px] px-2 py-0.5 rounded bg-emerald-950/80 text-emerald-300 font-mono border border-emerald-800">
            {entries.length} Events Logged
          </span>
        </div>

        {/* Action Controls: Search, Export, Clear */}
        <div className="flex items-center space-x-2">
          {/* Search bar */}
          <div className="relative">
            <Search className="w-3.5 h-3.5 text-gray-500 absolute left-2.5 top-1/2 -translate-y-1/2" />
            <input
              type="text"
              placeholder="Search audit trail..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="bg-[#1E293B] text-gray-200 placeholder-gray-500 text-[11px] pl-8 pr-2.5 py-1 rounded border border-gray-700 focus:outline-none focus:border-cyan-500 w-40 md:w-52"
            />
          </div>

          {/* Filter dropdown */}
          <select
            value={selectedFilter}
            onChange={(e) => setSelectedFilter(e.target.value)}
            className="bg-[#1E293B] text-gray-300 text-[11px] px-2 py-1 rounded border border-gray-700 focus:outline-none"
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
            className="flex items-center space-x-1 bg-blue-900/60 hover:bg-blue-800 text-blue-200 border border-blue-700 px-2.5 py-1 rounded transition disabled:opacity-40 disabled:cursor-not-allowed font-medium text-[11px]"
            title="Download CSV report"
          >
            <FileSpreadsheet className="w-3.5 h-3.5" />
            <span className="hidden sm:inline">Export CSV</span>
          </button>

          {/* Export JSON */}
          <button
            onClick={exportJson}
            disabled={entries.length === 0}
            className="flex items-center space-x-1 bg-purple-900/60 hover:bg-purple-800 text-purple-200 border border-purple-700 px-2.5 py-1 rounded transition disabled:opacity-40 disabled:cursor-not-allowed font-medium text-[11px]"
            title="Download JSON telemetry"
          >
            <FileText className="w-3.5 h-3.5" />
            <span className="hidden sm:inline">Export JSON</span>
          </button>

          {/* Clear Logs */}
          {onClearLogs && (
            <button
              onClick={onClearLogs}
              disabled={entries.length === 0}
              className="text-gray-400 hover:text-red-400 p-1.5 rounded hover:bg-gray-800 transition disabled:opacity-30"
              title="Clear session audit log"
            >
              <Trash2 className="w-3.5 h-3.5" />
            </button>
          )}
        </div>
      </div>

      {/* Table Container */}
      <div className="flex-1 overflow-auto max-h-[500px]">
        {filteredEntries.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-48 text-center p-6 text-gray-500">
            <Shield className="w-8 h-8 text-gray-600 mb-2 opacity-50" />
            <p className="text-xs">No audit events matching criteria</p>
            <p className="text-[10px] text-gray-600 mt-1">
              Events are automatically captured when telemetry verdict state changes occur.
            </p>
          </div>
        ) : (
          <table className="w-full text-left border-collapse font-mono text-[11px]">
            <thead className="bg-[#0B0F19] text-gray-400 sticky top-0 border-b border-gray-800 z-10">
              <tr>
                <th className="p-2.5 font-semibold text-gray-300">Time (Sim / UTC)</th>
                <th className="p-2.5 font-semibold text-gray-300">Affected Asset</th>
                <th className="p-2.5 font-semibold text-gray-300">Classification</th>
                <th className="p-2.5 font-semibold text-gray-300">Subtype</th>
                <th className="p-2.5 font-semibold text-gray-300">Conf</th>
                <th className="p-2.5 font-semibold text-gray-300 min-w-[200px]">Network Signal</th>
                <th className="p-2.5 font-semibold text-gray-300 min-w-[200px]">Physics Signal</th>
                <th className="p-2.5 font-semibold text-gray-300 min-w-[220px]">Recommended Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-800/60 bg-[#0F172A]">
              {filteredEntries.map((entry) => {
                const color = getVerdictColor(entry.classification);

                return (
                  <tr
                    key={entry.id}
                    className="hover:bg-[#1E293B]/70 transition-colors duration-150"
                  >
                    {/* Time */}
                    <td className="p-2.5 whitespace-nowrap text-gray-300">
                      <div className="font-bold text-cyan-400">{entry.simTime}</div>
                      <div className="text-[9px] text-gray-500">{entry.timestamp.slice(11, 19)} UTC</div>
                    </td>

                    {/* Asset */}
                    <td className="p-2.5 whitespace-nowrap font-medium text-gray-200">
                      {entry.assetName}
                    </td>

                    {/* Classification */}
                    <td className="p-2.5 whitespace-nowrap">
                      <span
                        className="inline-flex items-center space-x-1 px-2 py-0.5 rounded font-bold uppercase tracking-wider text-[10px]"
                        style={{
                          backgroundColor: `${color}20`,
                          color: color,
                          border: `1px solid ${color}40`,
                        }}
                      >
                        {entry.classification === "Cyber Intrusion" && (
                          <ShieldAlert className="w-3 h-3 text-rose-500 mr-1" />
                        )}
                        {entry.classification === "Natural Fault" && (
                          <AlertTriangle className="w-3 h-3 text-amber-500 mr-1" />
                        )}
                        {entry.classification === "Normal" && (
                          <CheckCircle2 className="w-3 h-3 text-emerald-400 mr-1" />
                        )}
                        <span>{entry.classification}</span>
                      </span>
                    </td>

                    {/* Subtype */}
                    <td className="p-2.5 whitespace-nowrap text-gray-400">
                      {entry.subtype || "none"}
                    </td>

                    {/* Confidence */}
                    <td className="p-2.5 whitespace-nowrap font-bold text-gray-300">
                      {(entry.confidence * 100).toFixed(0)}%
                    </td>

                    {/* Network Signal */}
                    <td className="p-2.5 text-gray-300 text-[10px] leading-relaxed font-sans">
                      {entry.networkSummary}
                    </td>

                    {/* Physics Signal */}
                    <td className="p-2.5 text-gray-300 text-[10px] leading-relaxed font-sans">
                      {entry.physicsSummary}
                    </td>

                    {/* Recommended Action */}
                    <td className="p-2.5 text-yellow-300 text-[10px] leading-relaxed font-sans">
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
