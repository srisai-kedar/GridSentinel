"use client";

import React, { useCallback, useEffect, useRef, useState } from "react";
import {
  injectCommandAttack,
  injectReplayAttack,
  injectSilentDataAttack,
  resetOtScenarios,
  startOtSimulation,
  triggerLineTrip,
  triggerShortCircuit,
} from "@/lib/api";
import {
  AlertTriangle,
  Award,
  ChevronLeft,
  ChevronRight,
  Clock,
  Eye,
  EyeOff,
  Flame,
  Layers,
  Maximize2,
  Minimize2,
  Pause,
  Play,
  RotateCcw,
  Shield,
  ShieldAlert,
  Sparkles,
  Zap,
} from "lucide-react";

export interface DemoStep {
  id: number;
  title: string;
  defaultDurationSec: number;
  cueNote: string;
  actionSummary: string;
  execute?: () => Promise<string>;
}

interface DemoDirectorProps {
  onStepChange?: (stepIndex: number, step: DemoStep) => void;
  onNavigateTab?: (tabName: "FEED" | "AUDIT" | "CONTROLS" | "COMPLIANCE") => void;
  isReplayMode?: boolean;
  stepDurations?: number[]; // [15, 30, 30, 30, 30, 15]
}

export const DEFAULT_STEP_DURATIONS = [15, 30, 30, 30, 30, 15]; // 150s total

export const DemoDirector: React.FC<DemoDirectorProps> = ({
  onStepChange,
  onNavigateTab,
  isReplayMode = false,
  stepDurations = DEFAULT_STEP_DURATIONS,
}) => {
  const [currentStepIdx, setCurrentStepIdx] = useState<number>(0);
  const [isAutoRunning, setIsAutoRunning] = useState<boolean>(false);
  const [remainingTimeSec, setRemainingTimeSec] = useState<number>(
    stepDurations[0] || 15
  );
  const [isAudienceView, setIsAudienceView] = useState<boolean>(false);
  const [actionFeedback, setActionFeedback] = useState<string | null>(null);
  const [isExecutingAction, setIsExecutingAction] = useState<boolean>(false);

  const timerRef = useRef<NodeJS.Timeout | null>(null);

  // Build the 6-beat demo script
  const demoScript: DemoStep[] = [
    {
      id: 1,
      title: "1. Problem Statement & Threat Landscape",
      defaultDurationSec: stepDurations[0] || 15,
      cueNote:
        "Explain the distribution SCADA challenge: legacy unauthenticated Modbus TCP protocols, increasing IT-OT integration, and why physics-aware cross-validation is essential for Indian utilities under CEA-2026.",
      actionSummary: "Presenter Cue (No live action)",
      execute: async () => {
        if (!isReplayMode) {
          await startOtSimulation();
        }
        return "Baseline initialised.";
      },
    },
    {
      id: 2,
      title: "2. Live SCADA Baseline & State Estimation",
      defaultDurationSec: stepDurations[1] || 30,
      cueNote:
        "Showcase nominal feeder operations: 5 Modbus RTUs, continuous diurnal load curves, and pandapower WLS state estimation converging with Chi-squared test passed and zero bad-data residuals.",
      actionSummary: "Reset Scenarios & Run Nominal Grid",
      execute: async () => {
        if (!isReplayMode) {
          await resetOtScenarios();
        }
        return "All RTUs operating in nominal state.";
      },
    },
    {
      id: 3,
      title: "3. Genuine Physical Fault (Line Outage)",
      defaultDurationSec: stepDurations[2] || 30,
      cueNote:
        "Trip Feeder Line 0. Pandapower physics cuts branch current to zero and drops downstream Bus 2 voltage. WLS residuals converge cleanly with no anomalous network writes. Classifier correctly flags Natural Fault (line_trip).",
      actionSummary: "Trip Line 0 (Substation → Feeder A)",
      execute: async () => {
        if (!isReplayMode) {
          await triggerLineTrip({ line_index: 0 });
        }
        return "Physical Line 0 outage triggered.";
      },
    },
    {
      id: 4,
      title: "4. Cyber Intrusion (Silent Sensor Tampering)",
      defaultDurationSec: stepDurations[3] || 30,
      cueNote:
        "Clear fault and inject silent overvoltage (+15%) on RTU-2. Physical power flow is unchanged and Modbus packets appear standard, but WLS Chi2 test fails (r_N > 3.0). Classifier detects Cyber Intrusion (data_injection).",
      actionSummary: "Inject Silent Data Injection on RTU-2",
      execute: async () => {
        if (!isReplayMode) {
          await resetOtScenarios();
          await injectSilentDataAttack({
            rtu_id: 2,
            voltage_pu: 1.15,
            duration_ticks: 20,
          });
        }
        return "Silent Data Injection active on RTU-2.";
      },
    },
    {
      id: 5,
      title: "5. Real-Time Forensic Triage & Audit Trail",
      defaultDurationSec: stepDurations[4] || 30,
      cueNote:
        "Review the plain-language triage alert explaining physics contradictions. Switch to the CEA-2026 Audit Trail to showcase timestamped incident evidence and single-click CSV/JSON export.",
      actionSummary: "Navigate to Alert Feed & Audit Log",
      execute: async () => {
        if (onNavigateTab) {
          onNavigateTab("AUDIT");
        }
        return "Audit log and forensic reports focused.";
      },
    },
    {
      id: 6,
      title: "6. Summary & CEA-2026 Readiness",
      defaultDurationSec: stepDurations[5] || 15,
      cueNote:
        "Wrap up by highlighting GridSentinel's passive, non-intrusive architecture, 24x7 dual-channel monitoring, and domestic open-source foundation ready for CSIRT-Power compliance.",
      actionSummary: "Restore Clean Grid State & Conclude",
      execute: async () => {
        if (!isReplayMode) {
          await resetOtScenarios();
        }
        if (onNavigateTab) {
          onNavigateTab("COMPLIANCE");
        }
        return "Demo concluded. Clean state restored.";
      },
    },
  ];

  const currentStep = demoScript[currentStepIdx] || demoScript[0];

  // Execute step action
  const runStepAction = useCallback(
    async (step: DemoStep) => {
      if (!step.execute) return;
      try {
        setIsExecutingAction(true);
        const msg = await step.execute();
        setActionFeedback(msg);
        setTimeout(() => setActionFeedback(null), 3500);
      } catch (err: any) {
        setActionFeedback(`Action error: ${err.message || "Failed"}`);
        setTimeout(() => setActionFeedback(null), 3500);
      } finally {
        setIsExecutingAction(false);
      }
    },
    []
  );

  // Jump to specific step
  const goToStep = useCallback(
    (index: number, autoTrigger: boolean = true) => {
      const targetIdx = Math.max(0, Math.min(index, demoScript.length - 1));
      setCurrentStepIdx(targetIdx);
      const targetStep = demoScript[targetIdx];
      setRemainingTimeSec(targetStep.defaultDurationSec);

      if (onStepChange) {
        onStepChange(targetIdx, targetStep);
      }

      if (autoTrigger) {
        runStepAction(targetStep);
      }
    },
    [demoScript, onStepChange, runStepAction]
  );

  // Next / Back handlers
  const handleNextStep = useCallback(() => {
    if (currentStepIdx < demoScript.length - 1) {
      goToStep(currentStepIdx + 1, true);
    } else {
      setIsAutoRunning(false);
    }
  }, [currentStepIdx, demoScript.length, goToStep]);

  const handlePrevStep = useCallback(() => {
    if (currentStepIdx > 0) {
      goToStep(currentStepIdx - 1, true);
    }
  }, [currentStepIdx, goToStep]);

  // Start / Stop Auto-Sequence
  const startAutoDemo = useCallback(() => {
    setIsAutoRunning(true);
    goToStep(0, true);
  }, [goToStep]);

  const stopAutoDemo = useCallback(() => {
    setIsAutoRunning(false);
  }, []);

  // Timer Tick
  useEffect(() => {
    if (!isAutoRunning) {
      if (timerRef.current) clearInterval(timerRef.current);
      return;
    }

    timerRef.current = setInterval(() => {
      setRemainingTimeSec((prev) => {
        if (prev <= 1) {
          // Advance to next step
          if (currentStepIdx < demoScript.length - 1) {
            goToStep(currentStepIdx + 1, true);
            return demoScript[currentStepIdx + 1]?.defaultDurationSec || 15;
          } else {
            setIsAutoRunning(false);
            return 0;
          }
        }
        return prev - 1;
      });
    }, 1000);

    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, [isAutoRunning, currentStepIdx, demoScript, goToStep]);

  const totalDemoSeconds = demoScript.reduce(
    (acc, step) => acc + step.defaultDurationSec,
    0
  );

  const stepDuration = currentStep.defaultDurationSec;
  const stepElapsed = stepDuration - remainingTimeSec;
  const stepProgressPct =
    stepDuration > 0 ? (stepElapsed / stepDuration) * 100 : 0;

  // Render Audience View (Minimized unobtrusive bottom cue bar)
  if (isAudienceView) {
    return (
      <div
        data-testid="demo-director-audience"
        className="fixed bottom-3 left-1/2 -translate-x-1/2 z-50 bg-[#0F172A]/95 backdrop-blur-md border border-cyan-700/60 rounded-full px-5 py-2 flex items-center space-x-4 shadow-2xl select-none"
      >
        <div className="flex items-center space-x-2">
          <span className="w-2 h-2 rounded-full bg-cyan-400 animate-pulse" />
          <span className="text-xs font-bold text-gray-200">
            {currentStep.title}
          </span>
        </div>

        {isAutoRunning && (
          <div className="flex items-center space-x-2 border-l border-gray-700 pl-3">
            <Clock className="w-3.5 h-3.5 text-cyan-400" />
            <span className="font-mono text-xs text-cyan-300 font-semibold">
              {remainingTimeSec}s
            </span>
          </div>
        )}

        <button
          onClick={() => setIsAudienceView(false)}
          className="text-gray-400 hover:text-white p-1 rounded hover:bg-gray-800 transition"
          title="Switch to Presenter View"
        >
          <Eye className="w-4 h-4" />
        </button>
      </div>
    );
  }

  // Presenter View
  return (
    <div
      data-testid="demo-director-presenter"
      className="flex flex-col h-full bg-[#0F172A] rounded-lg border border-cyan-800/60 overflow-hidden text-xs select-none shadow-xl"
    >
      {/* Header */}
      <div className="p-3 bg-[#0B0F19] border-b border-gray-800 flex items-center justify-between">
        <div className="flex items-center space-x-2">
          <Sparkles className="w-4 h-4 text-cyan-400" />
          <h2 className="font-bold text-gray-100 uppercase tracking-wider text-xs">
            Demo Director & Script Pacer
          </h2>
          <span className="text-[10px] px-2 py-0.5 rounded bg-cyan-950 text-cyan-300 font-mono border border-cyan-800">
            {totalDemoSeconds}s Script
          </span>
        </div>

        {/* View Toggle */}
        <div className="flex items-center space-x-2">
          <button
            onClick={() => setIsAudienceView(true)}
            className="flex items-center space-x-1 text-gray-400 hover:text-cyan-300 px-2 py-1 rounded hover:bg-gray-800 transition text-[11px]"
            title="Switch to clean audience presentation mode"
          >
            <EyeOff className="w-3.5 h-3.5" />
            <span className="hidden sm:inline">Audience View</span>
          </button>
        </div>
      </div>

      {/* Auto-Sequence Controls & Timer Bar */}
      <div className="p-3 bg-[#111A2E] border-b border-gray-800 flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center space-x-2">
          {!isAutoRunning ? (
            <button
              onClick={startAutoDemo}
              className="flex items-center space-x-1.5 bg-gradient-to-r from-cyan-600 to-blue-600 hover:from-cyan-500 hover:to-blue-500 text-white font-bold px-3.5 py-1.5 rounded-md shadow transition"
            >
              <Play className="w-3.5 h-3.5 fill-white" />
              <span>Run Full Demo (150s)</span>
            </button>
          ) : (
            <button
              onClick={stopAutoDemo}
              className="flex items-center space-x-1.5 bg-amber-600 hover:bg-amber-500 text-white font-bold px-3.5 py-1.5 rounded-md shadow transition"
            >
              <Pause className="w-3.5 h-3.5" />
              <span>Pause Sequence</span>
            </button>
          )}

          <button
            onClick={() => goToStep(0, true)}
            className="p-1.5 text-gray-400 hover:text-gray-200 hover:bg-gray-800 rounded transition"
            title="Restart script from Beat 1"
          >
            <RotateCcw className="w-3.5 h-3.5" />
          </button>
        </div>

        {/* Big Countdown Timer */}
        <div className="flex items-center space-x-3">
          <div className="flex items-center space-x-1.5 px-3 py-1 bg-slate-900 rounded border border-gray-700">
            <Clock className="w-4 h-4 text-cyan-400" />
            <span className="font-mono text-base font-bold text-cyan-300">
              {remainingTimeSec}s
            </span>
            <span className="text-gray-500 text-[10px]">
              / {stepDuration}s
            </span>
          </div>

          {/* Manual Step Prev / Next */}
          <div className="flex items-center space-x-1">
            <button
              onClick={handlePrevStep}
              disabled={currentStepIdx === 0}
              className="p-1.5 rounded bg-gray-800 hover:bg-gray-700 text-gray-300 disabled:opacity-30 disabled:cursor-not-allowed transition"
              title="Previous step"
            >
              <ChevronLeft className="w-4 h-4" />
            </button>
            <button
              onClick={handleNextStep}
              disabled={currentStepIdx === demoScript.length - 1}
              className="p-1.5 rounded bg-gray-800 hover:bg-gray-700 text-gray-300 disabled:opacity-30 disabled:cursor-not-allowed transition"
              title="Next step"
            >
              <ChevronRight className="w-4 h-4" />
            </button>
          </div>
        </div>
      </div>

      {/* Progress Bar for Current Step */}
      <div className="w-full h-1.5 bg-gray-800">
        <div
          className="h-full bg-cyan-400 transition-all duration-300 ease-linear"
          style={{ width: `${stepProgressPct}%` }}
        />
      </div>

      {/* Action Notification Toast */}
      {actionFeedback && (
        <div className="px-3 py-1.5 bg-cyan-950 text-cyan-200 border-b border-cyan-800 text-[11px] font-mono flex items-center justify-between">
          <span>{actionFeedback}</span>
        </div>
      )}

      {/* Active Step Highlight Card */}
      <div className="p-3.5 bg-[#0B0F19] border-b border-gray-800 space-y-2">
        <div className="flex items-center justify-between">
          <span className="text-[10px] font-mono uppercase tracking-wider text-cyan-400 font-bold">
            CURRENT PRESENTATION CUE (STEP {currentStep.id} OF 6)
          </span>
          <span className="text-[11px] font-mono text-gray-400">
            Action: {currentStep.actionSummary}
          </span>
        </div>

        <h3 className="text-sm font-bold text-gray-100">{currentStep.title}</h3>

        {/* Presenter Spoken Cue */}
        <div className="bg-slate-900/90 p-3 rounded-md border border-cyan-900/60 text-gray-200 text-xs leading-relaxed font-sans shadow-inner">
          <p className="font-medium text-cyan-200 mb-1">
            Presenter Talking Point:
          </p>
          <p className="text-gray-300">{currentStep.cueNote}</p>
        </div>

        <button
          onClick={() => runStepAction(currentStep)}
          disabled={isExecutingAction}
          className="flex items-center space-x-1.5 text-xs text-cyan-400 hover:text-cyan-200 font-semibold transition"
        >
          <Zap className="w-3.5 h-3.5" />
          <span>Re-trigger Step Action ({currentStep.actionSummary})</span>
        </button>
      </div>

      {/* 6-Beat Step List */}
      <div className="flex-1 overflow-y-auto p-2 space-y-1.5">
        {demoScript.map((step, idx) => {
          const isCurrent = idx === currentStepIdx;
          const isPassed = idx < currentStepIdx;

          return (
            <div
              key={step.id}
              onClick={() => goToStep(idx, true)}
              className={`p-2.5 rounded-md border transition cursor-pointer flex items-center justify-between ${
                isCurrent
                  ? "bg-cyan-950/70 border-cyan-500 text-cyan-100 shadow-md"
                  : isPassed
                  ? "bg-slate-900/50 border-gray-800 text-gray-400 hover:border-gray-700"
                  : "bg-slate-900/30 border-gray-800/80 text-gray-400 hover:border-gray-700"
              }`}
            >
              <div className="flex items-center space-x-2.5">
                <span
                  className={`w-5 h-5 rounded-full flex items-center justify-center font-mono font-bold text-[10px] ${
                    isCurrent
                      ? "bg-cyan-500 text-black shadow-[0_0_8px_#06B6D4]"
                      : isPassed
                      ? "bg-emerald-900 text-emerald-300"
                      : "bg-gray-800 text-gray-400"
                  }`}
                >
                  {step.id}
                </span>
                <div>
                  <span className="font-semibold text-[11px] block text-gray-200">
                    {step.title}
                  </span>
                  <span className="text-[10px] text-gray-500 font-mono">
                    {step.actionSummary}
                  </span>
                </div>
              </div>

              <div className="text-right font-mono text-[10px] text-gray-400">
                {step.defaultDurationSec}s
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};
