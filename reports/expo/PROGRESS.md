# Expo hardening progress

## 2026-10-27 — T1 leakage re-evaluation

- **Command:** Appendix B dataset generation and isolated training commands from `docs/GridSentinel_doc.txt`, redirected to `backend/reports/expo/appendix_b_probe/` and `backend/models/experiments/expo_t1_corrected_candidate.joblib`; then `backend/scripts/expo/t1_leakage_re_evaluation.py`.
- **Result:** fresh safe probe generated (3,500 rows); isolated candidate trained; lens ablation and episode analysis completed. Candidate test Cyber recall 0.5490, precision 0.9912, F1 0.7066, FPR 0.0003, median/p95 latency 32.696/43.283 ms. Episode analysis detected 17/17 grouped cyber episodes with median/p90 delay 0/1 seconds.
- **Caveat:** safe probe SHA differs from the document’s recorded held-out SHA; production model was not modified or scored. Full backend suite remains 312 passed, 1 known citation-lint baseline failure, with no new failure.
- **Next step:** stop after T1; await approval for a later task. T2 was not started.
