/**
 * compliance-mapping.ts
 * ---------------------
 * Hardcoded, verified CEA-2026 regulation facts and feature mappings for GridSentinel.
 * Content derived strictly from official Gazette text.
 */

export interface CeaFacts {
  name: string;
  gazetteDate: string;
  legalBasis: string;
  effectiveDate: string;
  nodalAgency: string;
  note: string;
}

export interface ComplianceMappingItem {
  obligation: string;
  gridSentinelFeature: string;
}

export const CEA_2026_FACTS: CeaFacts = {
  name: "Central Electricity Authority (Cyber Security in Power Sector) Regulations, 2026",
  gazetteDate: "31 July 2026",
  legalBasis: "Section 177 read with Section 73(c), Electricity Act 2003 (with MeitY concurrence)",
  effectiveDate: "1 April 2027 (general provisions)",
  nodalAgency: "CSIRT-Power",
  note: "Six specific provisions (24x7 Information Security Division, mandatory ISO/IEC 27001 certification, mandatory training, trusted-source IT procurement, OT perimeter hardware security, and one other) take effect on later dates set separately by CEA.",
};

export const COMPLIANCE_MAPPING: ComplianceMappingItem[] = [
  {
    obligation: "Report cyber incidents to CSIRT-Power within 6 hours",
    gridSentinelFeature: "Audit log captures timestamped detection events with verdict, confidence, and evidence summary — structured to be quickly transcribed into a CSIRT-Power incident report within the 6-hour window",
  },
  {
    obligation: "Maintain a cyber asset register and Cyber Risk Assessment and Mitigation Plan",
    gridSentinelFeature: "Feeder topology + RTU register map (from the OT simulation layer) doubles as a live inventory of monitored cyber-physical assets",
  },
  {
    obligation: "Physically or logically isolate OT networks from IT/internet-facing systems",
    gridSentinelFeature: "GridSentinel sits passively alongside SCADA as a read-only observer — it has no write path into OT and issues no control commands, by design",
  },
  {
    obligation: "Move toward continuous (24x7) security monitoring capability",
    gridSentinelFeature: "The dual-detection tick loop (physics + network layers) runs continuously, not on a scheduled-audit basis",
  },
  {
    obligation: "Trusted-source procurement, reducing reliance on foreign platforms",
    gridSentinelFeature: "Built entirely on open-source tooling (pandapower, FastAPI, Next.js) — a domestically deployable alternative to foreign enterprise OT-security platforms",
  },
];

export const COMPLIANCE_DISCLAIMER =
  "Note: This is an illustrative capability mapping developed for a technical demonstration and prototype evaluation. It does not constitute a certified compliance claim. Authoritative interpretation rests strictly with the officially notified Gazette text.";
