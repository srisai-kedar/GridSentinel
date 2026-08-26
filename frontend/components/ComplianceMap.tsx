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
      className="flex flex-col h-full bg-[#0E1118] rounded-[10px] border border-white/[0.07] overflow-hidden text-xs select-none shadow-sm print:bg-white print:text-black print:border-none print:shadow-none"
    >
      {/* Header */}
      <div className="p-3 bg-[#0E1118] border-b border-white/[0.07] flex flex-wrap items-center justify-between gap-2 print:border-b-2 print:border-black">
        <div className="flex items-center space-x-2">
          <Scale className="w-3.5 h-3.5 text-[#10B981] print:text-black" />
          <h2 className="font-bold text-[#EDEDF0] uppercase tracking-wider text-xs print:text-black print:text-sm">
            CEA-2026 Cyber Security Regulations Compliance Matrix
          </h2>
          <span className="text-[10px] px-2 py-0.5 rounded-[4px] bg-[#131722] text-[#10B981] font-mono border border-white/[0.06] print:bg-gray-200 print:text-black">
            Verified Statutory Mapping
          </span>
        </div>

        <button
          onClick={handlePrint}
          className="flex items-center space-x-1.5 bg-[#131722] hover:bg-[#181E2C] text-[#EDEDF0] border border-white/[0.08] px-2.5 py-1 rounded-[6px] transition text-[11px] font-medium print:hidden"
          title="Print or export compliance report as PDF"
        >
          <Printer className="w-3.5 h-3.5" />
          <span>Print Matrix</span>
        </button>
      </div>

      {/* Main Container */}
      <div className="flex-1 overflow-y-auto p-3.5 space-y-3 print:overflow-visible print:p-0">
        {/* Statutory Facts Card */}
        <div className="bg-[#131722] p-3 rounded-[8px] border border-white/[0.07] space-y-2 text-[11px] print:bg-gray-50 print:border print:border-gray-400">
          <div className="flex items-center space-x-2 text-[#10B981] font-medium print:text-black">
            <BookOpen className="w-3.5 h-3.5" />
            <span className="text-xs">{CEA_2026_FACTS.name}</span>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-2 pt-1 font-mono text-[10px]">
            <div className="bg-[#0E1118] p-2 rounded-[6px] border border-white/[0.05] print:bg-white print:border-gray-300">
              <span className="text-[#5A6275] block text-[9px] uppercase tracking-wider">GAZETTE NOTIFICATION</span>
              <span className="text-[#EDEDF0] font-semibold print:text-black">
                {CEA_2026_FACTS.gazetteDate}
              </span>
            </div>
            <div className="bg-[#0E1118] p-2 rounded-[6px] border border-white/[0.05] print:bg-white print:border-gray-300">
              <span className="text-[#5A6275] block text-[9px] uppercase tracking-wider">EFFECTIVE DATE</span>
              <span className="text-[#EDEDF0] font-semibold print:text-black">
                {CEA_2026_FACTS.effectiveDate}
              </span>
            </div>
            <div className="bg-[#0E1118] p-2 rounded-[6px] border border-white/[0.05] print:bg-white print:border-gray-300">
              <span className="text-[#5A6275] block text-[9px] uppercase tracking-wider">NODAL SECTOR AGENCY</span>
              <span className="text-[#10B981] font-semibold print:text-black">
                {CEA_2026_FACTS.nodalAgency}
              </span>
            </div>
            <div className="bg-[#0E1118] p-2 rounded-[6px] border border-white/[0.05] print:bg-white print:border-gray-300">
              <span className="text-[#5A6275] block text-[9px] uppercase tracking-wider">STATUTORY BASIS</span>
              <span className="text-[#A78BFA] font-semibold print:text-black">
                Electricity Act 2003
              </span>
            </div>
          </div>

          <p className="text-[10px] text-[#5A6275] italic pt-1 print:text-gray-700">
            {CEA_2026_FACTS.note}
          </p>
        </div>

        {/* 5-Row Compliance Mapping Table */}
        <div className="bg-[#0E1118] rounded-[8px] border border-white/[0.07] overflow-hidden print:border print:border-gray-400">
          <table className="w-full text-left border-collapse text-[11px]">
            <thead className="bg-[#131722] text-[#9CA3AF] border-b border-white/[0.07] print:bg-gray-100 print:text-black">
              <tr>
                <th className="p-2.5 font-medium w-1/3 border-r border-white/[0.06] print:border-gray-300">
                  CEA-2026 Statutory Obligation / Mandate
                </th>
                <th className="p-2.5 font-medium w-2/3">
                  GridSentinel Cyber-Physical Operational Alignment
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/[0.04] print:divide-gray-300">
              {COMPLIANCE_MAPPING.map((item, idx) => (
                <tr
                  key={idx}
                  className="hover:bg-[#181E2C] transition-colors print:hover:bg-transparent"
                >
                  <td className="p-2.5 font-medium text-[#EDEDF0] border-r border-white/[0.06] align-top print:text-black print:border-gray-300">
                    <div className="flex items-start space-x-2">
                      <ShieldCheck className="w-3.5 h-3.5 text-[#10B981] shrink-0 mt-0.5 print:text-black" />
                      <span>{item.obligation}</span>
                    </div>
                  </td>
                  <td className="p-2.5 text-[#9CA3AF] leading-relaxed align-top font-sans print:text-black">
                    <div className="flex items-start space-x-2">
                      <CheckCircle2 className="w-3.5 h-3.5 text-[#A78BFA] shrink-0 mt-0.5 print:text-black" />
                      <span>{item.gridSentinelFeature}</span>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* Official Gazette Disclaimer */}
        <div className="bg-[#131722] p-2.5 rounded-[6px] border border-white/[0.06] flex items-start space-x-2 text-[10px] text-[#5A6275] print:bg-transparent print:border print:border-gray-300 print:text-gray-700">
          <Info className="w-3.5 h-3.5 text-[#A78BFA] shrink-0 mt-0.5 print:text-black" />
          <p className="leading-normal">{COMPLIANCE_DISCLAIMER}</p>
        </div>
      </div>
    </div>
  );
};

