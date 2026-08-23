"use client";

import React from "react";
import {
  CEA_2026_FACTS,
  COMPLIANCE_DISCLAIMER,
  COMPLIANCE_MAPPING,
} from "@/data/compliance-mapping";
import {
  AlertCircle,
  Award,
  BookOpen,
  CheckCircle2,
  ExternalLink,
  FileCheck,
  Info,
  Printer,
  Scale,
  Shield,
  ShieldCheck,
} from "lucide-react";

export const ComplianceMap: React.FC = () => {
  const handlePrint = () => {
    if (typeof window !== "undefined") {
      window.print();
    }
  };

  return (
    <div
      data-testid="compliance-map-panel"
      className="flex flex-col h-full bg-[#0F172A] rounded-lg border border-gray-800 overflow-hidden text-xs select-none shadow-xl print:bg-white print:text-black print:border-none print:shadow-none"
    >
      {/* Header */}
      <div className="p-3 bg-[#0B0F19] border-b border-gray-800 flex flex-wrap items-center justify-between gap-2 print:border-b-2 print:border-black">
        <div className="flex items-center space-x-2">
          <Scale className="w-4 h-4 text-emerald-400 print:text-black" />
          <h2 className="font-bold text-gray-100 uppercase tracking-wider text-xs print:text-black print:text-sm">
            CEA-2026 Cyber Security Regulations Compliance Matrix
          </h2>
          <span className="text-[10px] px-2 py-0.5 rounded bg-emerald-950/80 text-emerald-300 font-mono border border-emerald-800 print:bg-gray-200 print:text-black">
            Verified Statutory Mapping
          </span>
        </div>

        <button
          onClick={handlePrint}
          className="flex items-center space-x-1.5 bg-slate-800 hover:bg-slate-700 text-gray-200 border border-gray-700 px-2.5 py-1 rounded transition text-[11px] font-medium print:hidden"
          title="Print or export compliance report as PDF"
        >
          <Printer className="w-3.5 h-3.5" />
          <span>Print Matrix</span>
        </button>
      </div>

      {/* Main Container */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4 print:overflow-visible print:p-0">
        {/* Statutory Facts Card */}
        <div className="bg-[#111A2E] p-3.5 rounded-lg border border-gray-800 space-y-2 text-[11px] print:bg-gray-50 print:border print:border-gray-400">
          <div className="flex items-center space-x-2 text-emerald-400 font-semibold print:text-black">
            <BookOpen className="w-4 h-4" />
            <span className="text-xs">{CEA_2026_FACTS.name}</span>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-2 pt-1 font-mono text-[10px]">
            <div className="bg-slate-900/80 p-2 rounded border border-gray-800 print:bg-white print:border-gray-300">
              <span className="text-gray-500 block">GAZETTE NOTIFICATION</span>
              <span className="text-gray-200 font-semibold print:text-black">
                {CEA_2026_FACTS.gazetteDate}
              </span>
            </div>
            <div className="bg-slate-900/80 p-2 rounded border border-gray-800 print:bg-white print:border-gray-300">
              <span className="text-gray-500 block">EFFECTIVE DATE</span>
              <span className="text-cyan-300 font-semibold print:text-black">
                {CEA_2026_FACTS.effectiveDate}
              </span>
            </div>
            <div className="bg-slate-900/80 p-2 rounded border border-gray-800 print:bg-white print:border-gray-300">
              <span className="text-gray-500 block">NODAL SECTOR AGENCY</span>
              <span className="text-emerald-300 font-semibold print:text-black">
                {CEA_2026_FACTS.nodalAgency}
              </span>
            </div>
            <div className="bg-slate-900/80 p-2 rounded border border-gray-800 print:bg-white print:border-gray-300">
              <span className="text-gray-500 block">STATUTORY BASIS</span>
              <span className="text-purple-300 font-semibold print:text-black">
                Electricity Act 2003
              </span>
            </div>
          </div>

          <p className="text-[10px] text-gray-400 italic pt-1 print:text-gray-700">
            {CEA_2026_FACTS.note}
          </p>
        </div>

        {/* 5-Row Compliance Mapping Table */}
        <div className="bg-[#0B0F19] rounded-lg border border-gray-800 overflow-hidden print:border print:border-gray-400">
          <table className="w-full text-left border-collapse text-[11px]">
            <thead className="bg-[#111827] text-gray-300 border-b border-gray-800 print:bg-gray-100 print:text-black">
              <tr>
                <th className="p-3 font-semibold w-1/3 border-r border-gray-800 print:border-gray-300">
                  CEA-2026 Statutory Obligation / Mandate
                </th>
                <th className="p-3 font-semibold w-2/3">
                  GridSentinel Cyber-Physical Operational Alignment
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-800/70 print:divide-gray-300">
              {COMPLIANCE_MAPPING.map((item, idx) => (
                <tr
                  key={idx}
                  className="hover:bg-[#131D33] transition-colors print:hover:bg-transparent"
                >
                  <td className="p-3 font-medium text-gray-200 border-r border-gray-800/70 align-top print:text-black print:border-gray-300">
                    <div className="flex items-start space-x-2">
                      <ShieldCheck className="w-4 h-4 text-emerald-400 shrink-0 mt-0.5 print:text-black" />
                      <span>{item.obligation}</span>
                    </div>
                  </td>
                  <td className="p-3 text-gray-300 leading-relaxed align-top font-sans print:text-black">
                    <div className="flex items-start space-x-2">
                      <CheckCircle2 className="w-4 h-4 text-cyan-400 shrink-0 mt-0.5 print:text-black" />
                      <span>{item.gridSentinelFeature}</span>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* Official Gazette Disclaimer */}
        <div className="bg-slate-900/60 p-3 rounded-lg border border-gray-800 flex items-start space-x-2.5 text-[10px] text-gray-400 print:bg-transparent print:border print:border-gray-300 print:text-gray-700">
          <Info className="w-4 h-4 text-cyan-400 shrink-0 mt-0.5 print:text-black" />
          <p className="leading-normal">{COMPLIANCE_DISCLAIMER}</p>
        </div>
      </div>
    </div>
  );
};
