# IEEE TEMSMET 2026 Expo Hardening Plan

Checkpoint: 0 (inspection only)
Date: 2026-10-27
Branch: `expo-hardening`

## Checkpoint 0 findings

The current checkout has no `AGENTS.md` and no `docs/GridSentinel_doc.txt`. Consequently, the requested project-specific instructions and Appendix B command list are unavailable in this repository state. I did not recreate either document or infer its commands.

The checkout is substantially dirty before this plan. Existing modified files include classifier service/training code, validation reports, and a sensor-drift test. Existing untracked files include corrected datasets, candidate models, many experiment reports/scripts, and Data4Cyber artifacts. Both existing stashes are present and were not changed:

- `stash@{0}` — Preserve local reports and benchmark data
- `stash@{1}` — Preserve validation report changes

The production model exists at `backend/models/fusion_classifier.joblib`; its current SHA-256 is `ee5211510e41eddac32ed1eed405af982a0a550bd0b75e8867253135b812ccae`. No production artifact was modified.

Available corrected datasets include `nbd_fixed_train_seed42.csv`, `nbd_fixed_val_seed999.csv`, and `nbd_fixed_test_seed1337.csv`. The normal dataset trio also exists. The validation report documents a 37-feature production schema, while `backend/reports/metrics.json` contains historical 28-feature-era context; T7 must reconcile this before claims are combined.

## Checks run

### Backend

Command:

```text
backend\.venv\Scripts\python.exe -m pytest backend/tests -q
```

Result: **312 passed, 1 failed**, 472 warnings in 77.69 seconds.

The failure is `backend/tests/test_citation_lint.py::test_all_repo_citations_are_canonical`. It reports six DOI identifiers in the existing untracked `backend/reports/Data4Cyber_V3_Audit.md` that are not listed in `docs/REFERENCES.md`. This is a repository hygiene failure caused by an existing report, not a production-model test failure. Warnings include the unset pytest-asyncio loop-scope configuration, pandapower deprecations, and sklearn feature-name warnings.

### Frontend

Command:

```text
npm test -- --run
```

Result: **11 test files passed, 32 tests passed** in 38.66 seconds. The replay-engine stderr message is expected coverage of malformed-session handling.

### Documentation commands

The README quickstart and test commands were inspected. Appendix B could not be checked because `docs/GridSentinel_doc.txt` is absent. The demo preflight was not run because its authoritative Appendix B invocation and the required running backend/OT state were not available from the missing document; this remains a checkpoint limitation.

## T1–T14 feasibility and acceptance plan

## Checkpoint 0 re-verification (2026-10-27)

`AGENTS.md` and `docs/GridSentinel_doc.txt` are now present and were read. Appendix B was re-verified against the document. The documented commands are usable when run from `backend` with explicit paths:

```text
python -m app.ml.dataset_generator --seed 1337 --ticks 700 --out data/generated/nbd_fixed_test_seed1337.csv
python -m app.ml.train_classifier --train data/generated/nbd_fixed_train_seed42.csv --val data/generated/nbd_fixed_val_seed999.csv --test data/generated/nbd_fixed_test_seed1337.csv --out models/experiments/nbd_fixed_candidate.joblib --report reports/experiments/nbd_fixed_candidate
```

Because the documented test output already existed and must not be overwritten, T1 used the same generator command with a redirected output under `backend/reports/expo/appendix_b_probe/`; the command completed and produced 3,500 rows. The trainer was likewise run with an isolated candidate and report path. The generated probe SHA-256 is `70f6c8b2c33c0b17a2fb84bbc750cd94513aeeaf4eefac498ff2a4e94056a95`, which does not match the document's recorded held-out SHA `9a81c1df00edcef0c99693155cecd6e3494365c327bd8b7182c6f378819f1c96`; this is recorded as a provenance discrepancy, not silently reconciled.

The document's Appendix A still describes a 28-feature schema, while the corrected datasets and T1 candidate use 37 features. This is a documented schema-era mismatch for T7. The current full backend suite was also rechecked: 312 passed and the single known citation-lint failure remains on the existing untracked Data4Cyber report; no new failure was introduced.

| Task | Feasibility here | Estimated runtime | Planned files/areas | Acceptance criterion |
|---|---|---:|---|---|
| T1 Leakage re-evaluation | **Feasible**; corrected train/validation data and corrected test generation inputs are present. | 5–15 min | Isolated experiment report/scripts, candidate output paths, corrected generated data only if the documented procedure requires it. | Fresh corrected test; production inference path; accuracy, class P/R/F1, Cyber FPR, subtype recall, episode recall/delay, importance; NBD-only/PCD-only/fusion AUC and fixed-FPR TPR. Production model untouched. |
| T2 False-alarm suppression | **Feasible** after T1; classifier service has the inference boundary to inspect. | 10–30 min | Isolated post-processing layer in classifier service only if approved, tests, validation-selected parameters, report. | Several validation-selected k-of-n/cooldown settings; held-out false-alarm episodes/hour, episode recall, median/p90 delay, before/after. No test tuning. |
| T3 Base-rate analysis | **Feasible** after T1/T2 metrics. | 5–15 min | Isolated analysis/report. | Precision and false-alarm episodes per shift at 7.5%, 1%, and 0.1% using measured TPR/FPR; tiered alert design only if justified. |
| T4 Sensor-drift evidence | **Conditionally feasible**; drift test/injector code exists, but current held-out test lacks drift rows. | 10–30 min | Injector/test fixtures, isolated seeded drift data, report. | Separate-seed drift evaluation with recall/FPR, FDI/natural-fault confusion, Wilson intervals; no unsupported drift claim. |
| T5 Recall diagnosis | **Feasible**; current reports contain subtype misses and corrected datasets exist. | 15–45 min | Isolated diagnostics/features, selection-seed and confirmation reports/tests. | Evidence for replay/command misses; pre-registered ablation rules applied; promotion only if paired FNR interval, >=3 pp reduction, and <=0.2 pp FPR rise all pass. |
| T6 Natural-fault misses | **Feasible**. | 10–30 min | Label/feature audit scripts and report. | Distinguish timing/label bug, extraction bug, or model weakness with row-level and episode evidence. |
| T7 Schema consistency | **Feasible and should be done early**. | 10–20 min | `metrics.json`, validation report provenance, model metadata, reconciliation report; no compatibility-guard removal. | Exact 28/37 files and causes identified; one minimal documented reconciliation that preserves guards. |
| T8 Statistical rigor | **Feasible**; corrected pipeline and seeds are available. | 20–90 min | Isolated multi-seed runner/results/tests. | >=5 fresh seeds; mean/spread for recall, FPR, false-alarm episodes/hour; block-bootstrap and Wilson intervals. |
| T9 Real baselines | **Mostly feasible**. | 20–60 min | Isolated baseline scripts/results/tests. | Same splits and labels for static, chi-square/LNR, Isolation Forest, NBD-only, PCD-only, fusion; one comparison table and explicit limitations. |
| T10 Robustness | **Conditional**. | 30–120 min | Injector/noise/load-shift fixtures and isolated results. | Only run scenarios supported by existing code/data; report stealth FDI evasion, 0.5x–3x noise, and load-shift degradation. Missing scenario support is reported, not fabricated. |
| T11 Calibration | **Feasible**. | 10–30 min | Validation-only calibration analysis/report/tests. | Reliability diagram and Brier score; Platt/isotonic only if validation improves without test tuning. |
| T12 Scalability | **Feasible but environment-dependent**; pandapower is installed, larger feeder construction needs verification. | 10–30 min | Isolated benchmark script/report. | Measured 33-bus WLS median/p95 on this machine, clearly separate from production claims. |
| T13 MSU/ORNL loader | **Feasible without benchmark**; loader and tests are present, source data need not be downloaded. | 10–25 min | `backend/app/ml/msu_ornl_loader.py`, focused tests/report. | Unknown labels are reported/excluded, never mapped to Normal; tests pass. Do not benchmark absent data. |
| T14 Demo hardening | **Feasible with integration caveats**; preflight, replay, attack/fault endpoints, and runbook exist. | 20–60 min | `scripts/demo-preflight.py`, OT endpoint guard, `docs/DEMO_RUNBOOK.md`, tests. | Offline replay works; exact three-scenario timings and Render warm-up documented; auth/localhost guard does not break approved demo. |

## Additional weaknesses observed

1. The full backend suite is not green because citation lint scans an existing untracked report. This must be resolved or explicitly excluded before expo claims are finalized.
2. The authoritative project document and its Appendix B are missing from this checkout, limiting command verification and requirements traceability.
3. The working tree contains many unrelated untracked datasets, candidate models, and reports. Any later changes must use explicit paths and narrow staging; no broad cleanup or staging is safe.
4. Historical 28-feature metrics and current 37-feature model/report claims coexist. T7 is required before comparing old and corrected results.
5. Current headline validation is heavily tick-level; episode-level and block-level uncertainty must be kept separate because adjacent ticks are autocorrelated.
6. The existing citation lint appears to scan untracked reports, so report-only work can fail the complete suite unless citations are registered or the lint scope is clarified.
7. The available corrected test is only 700 ticks with 22 attack episodes; this is adequate for a fresh estimate but weak for tight episode-level confidence intervals.

## Proposed order after approval

1. T1 leakage re-evaluation.
2. T2 persistence/hysteresis false-alarm suppression.
3. T7 schema reconciliation, so all subsequent tables identify the correct feature era.
4. T3 base-rate analysis and T8 multi-seed statistical rigor.
5. T5 recall diagnosis and T6 natural-fault miss diagnosis.
6. T9 real baselines, then T11 calibration.
7. T4 sensor-drift evidence and T10 robustness, subject to available injector support.
8. T12 scalability and T13 loader hardening.
9. T14 demo hardening and final preflight/runbook verification.

After each approved task: run focused tests plus the relevant broader suite, preserve raw results in an isolated report path, update `reports/expo/PROGRESS.md`, and stop for the requested continuation approval. No T1–T14 implementation was started in Checkpoint 0.
