import { describe, it, expect } from "vitest";
import React from "react";
import { render, screen } from "@testing-library/react";
import { ComplianceMap } from "../components/ComplianceMap";
import { CEA_2026_FACTS, COMPLIANCE_MAPPING } from "../data/compliance-mapping";

describe("ComplianceMap Component", () => {
  it("renders CEA-2026 facts and statutory details accurately", () => {
    render(<ComplianceMap />);

    expect(
      screen.getByText(/CEA-2026 Cyber Security Regulations Compliance Matrix/i)
    ).toBeInTheDocument();
    expect(screen.getByText(CEA_2026_FACTS.name)).toBeInTheDocument();
    expect(screen.getByText(CEA_2026_FACTS.gazetteDate)).toBeInTheDocument();
    expect(screen.getByText(CEA_2026_FACTS.effectiveDate)).toBeInTheDocument();
    expect(screen.getByText(CEA_2026_FACTS.nodalAgency)).toBeInTheDocument();
  });

  it("renders all 5 compliance mapping rows without omission", () => {
    render(<ComplianceMap />);

    COMPLIANCE_MAPPING.forEach((item) => {
      expect(screen.getByText(item.obligation)).toBeInTheDocument();
      expect(screen.getByText(item.gridSentinelFeature)).toBeInTheDocument();
    });
  });

  it("renders official disclaimer text", () => {
    render(<ComplianceMap />);

    expect(
      screen.getByText(/illustrative capability mapping developed for a technical demonstration/i)
    ).toBeInTheDocument();
  });
});
