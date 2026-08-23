import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import React from "react";
import { render, screen, fireEvent, act } from "@testing-library/react";
import { DemoDirector } from "../components/DemoDirector";

describe("DemoDirector Component", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it("renders the 6-beat script with presenter cues", () => {
    render(<DemoDirector />);

    expect(screen.getByText(/Demo Director & Script Pacer/i)).toBeInTheDocument();
    expect(screen.getAllByText(/1. Problem Statement & Threat Landscape/i).length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText(/6. Summary & CEA-2026 Readiness/i)).toBeInTheDocument();
  });

  it("navigates through steps manually with Next and Prev buttons", () => {
    const onStepChange = vi.fn();
    render(<DemoDirector onStepChange={onStepChange} />);

    // Initially at Step 1
    expect(screen.getByText(/CURRENT PRESENTATION CUE \(STEP 1 OF 6\)/i)).toBeInTheDocument();

    // Click Next
    const nextBtn = screen.getByTitle("Next step");
    fireEvent.click(nextBtn);

    expect(screen.getByText(/CURRENT PRESENTATION CUE \(STEP 2 OF 6\)/i)).toBeInTheDocument();
    expect(onStepChange).toHaveBeenCalledWith(1, expect.objectContaining({ id: 2 }));

    // Click Prev
    const prevBtn = screen.getByTitle("Previous step");
    fireEvent.click(prevBtn);

    expect(screen.getByText(/CURRENT PRESENTATION CUE \(STEP 1 OF 6\)/i)).toBeInTheDocument();
  });

  it("executes auto-sequence with timers advancing steps", () => {
    const onStepChange = vi.fn();
    render(
      <DemoDirector
        onStepChange={onStepChange}
        stepDurations={[2, 2, 2, 2, 2, 2]} // 2s per step for fast testing
      />
    );

    const runFullDemoBtn = screen.getByText(/Run Full Demo/i);
    fireEvent.click(runFullDemoBtn);

    expect(screen.getByText(/Pause Sequence/i)).toBeInTheDocument();

    // Fast-forward 2 seconds
    act(() => {
      vi.advanceTimersByTime(2100);
    });

    // Should have advanced to Step 2
    expect(screen.getByText(/CURRENT PRESENTATION CUE \(STEP 2 OF 6\)/i)).toBeInTheDocument();
  });

  it("toggles between Presenter View and Audience View", () => {
    render(<DemoDirector />);

    expect(screen.getByTestId("demo-director-presenter")).toBeInTheDocument();

    // Click Audience View
    const audienceBtn = screen.getByText(/Audience View/i);
    fireEvent.click(audienceBtn);

    expect(screen.getByTestId("demo-director-audience")).toBeInTheDocument();

    // Click Switch back to Presenter
    const switchBackBtn = screen.getByTitle("Switch to Presenter View");
    fireEvent.click(switchBackBtn);

    expect(screen.getByTestId("demo-director-presenter")).toBeInTheDocument();
  });
});
