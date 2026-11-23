# GridSentinel P0–P12 Master Tracker

This tracker is based on the committed task findings and the current repository audit. It does not convert a pilot or an implementation into a completed research acceptance.

| Task | Status | Evidence / completed work | Acceptance gap or human action | Commit |
|---|---|---|---|---|
| P0 | COMPLETED AND VERIFIED | 5,000-tick clean run, reproducibility comparison, and four-process concurrency evidence | Container image digest remains unavailable because Docker daemon was unavailable | `e2404a4` |
| P1 | VALIDATION PASSED | Shared topology map, ownership tests, and diagnostic before/after attribution run | Diagnostic is not independent production evidence; WLS residual distribution limitation remains | prior P1 research commit |
| P2 | EXPERIMENT RUN | Static provenance, blind re-extraction, canary, and lock tests rerun/revalidated on current code | Historical pre-PR16 scratch code/data are not present in refs or unreachable objects; expanded scenario impact rerun is not independently reproduced | `c076ede` |
| P3 | EXPERIMENT RUN | All configured train/validation/OOD/clean seed bands generated and hashed; labels and provenance fields checked | Runs are short exploratory seed-band data, not sufficient exposure for P8 or final statistical claims | `75ea7fd` |
| P4 | EXPERIMENT RUN | Registry and focused scenario-effect tests exist | Full parameter-grid execution across every scenario/profile is not complete | existing P4 commit |
| P5 | IMPLEMENTED | Protocol, clustered metrics, bootstrap, Holm adjustment, and test-set guard implemented | No definitive authorized final evaluation has been completed | existing P5 commit |
| P6 | EXPERIMENT RUN | Feature/model arms, grouped CV, validation thresholding, calibration, and isolated candidate freeze executed | Threshold 1.0/perfect episode result is based on short validation exposure; no independent final evaluation | `e4d30b8` |
| P7 | EXPERIMENT RUN | Eight-method pilot comparison and complementarity tables exist | Independent episode exposure and statistical power are insufficient for a reliable fusion claim | existing P7-complete commit |
| P8 | BLOCKED — HUMAN ACTION REQUIRED | Alert-layer candidates and validation operating curves exist | Generate at least 24 real-clock clean validation hours, an independent clean held-out set, and benign-event runs | existing P8 commit |
| P9 | BLOCKED — HUMAN ACTION REQUIRED | Drift-rule audit and readiness checks exist | Generate all FDI magnitudes, drift profiles, natural faults, benign events, and independent runs | existing P9 commit |
| P10 | EXPERIMENT RUN | Jacobian-based single/coordinated diagnostic frontier and theory check exist | Resolve the actual 13-versus-15 RTU-reported measurement contract before acceptance | existing P10 commit |
| P11 | BLOCKED — HUMAN ACTION REQUIRED | Redundancy/observability and per-cycle latency diagnostic exists | Approve a second feeder/topology and authorize OOD final evaluation using independent runs | existing P11 commit |
| P12 | BLOCKED — HUMAN ACTION REQUIRED | Passive parser/harness and comparison tests exist | Run elevated Windows packet capture against the simulator and return ETL/PCAP plus aligned tap logs | existing P12 commit |

## Human actions required

1. P8: run the exact clean-run commands documented in `backend/reports/research/P8/FINDINGS.md`, using distinct ports and enough runs to reach 24 real-clock hours; provide the generated manifests and clean files for the authorized final evaluator.
2. P9: approve and run the missing magnitude/profile scenario matrix with independent validation and held-out runs.
3. P10: approve whether the actual attackable measurement set is 13 or 15, with an explicit topology-map reference.
4. P11: provide or approve the second feeder topology, RTU placement, operating-condition family, and independent run schedule.
5. P12: run elevated capture commands using the exact packet-capture procedure in the P12 findings, then return the capture and tap logs without modifying them.

## Repository safety

- Production model SHA-256 remains `EE5211510E41EDDAC32ED1EED405AF982A0A550BD0B75E8867253135B812CCAE`.
- `backend/reports/metrics.json` remains unchanged.
- Existing uncommitted work and both stashes were preserved.
- No production model, deployment, or paper text was modified by this tracker update.
