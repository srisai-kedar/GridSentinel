# T1 — Corrected Leakage Re-evaluation

Date: 2026-10-27  
Status: complete; no production artifact changed

## Decision scope

This is an isolated re-evaluation of the corrected synthetic NBD/PCD dataset. It is not a production-model evaluation and does not establish deployment readiness. The production model `backend/models/fusion_classifier.joblib` was not loaded for scoring or overwritten.

## Commands and evidence

The generator and trainer commands are the Appendix B commands documented in `docs/GridSentinel_doc.txt`, with safe redirected output paths because the documented test file already existed:

```text
cd backend
.\.venv\Scripts\python.exe -m app.ml.dataset_generator --seed 1337 --ticks 700 --out reports/expo/appendix_b_probe/nbd_fixed_test_seed1337.csv
.\.venv\Scripts\python.exe -m app.ml.train_classifier --train data/generated/nbd_fixed_train_seed42.csv --val data/generated/nbd_fixed_val_seed999.csv --test reports/expo/appendix_b_probe/nbd_fixed_test_seed1337.csv --out models/experiments/expo_t1_corrected_candidate.joblib --report reports/expo/t1_corrected_candidate
```

The actual command was run from the repository root with equivalent explicit Windows paths. The generator completed with 3,500 rows. The safe probe SHA-256 is `70f6c8b2c33c0b17a2fb84bbc750cd94513aeeaf4eefac498ff2a4e94056a95`; the project document records a different held-out SHA (`9a81c1df...f1c96`). The difference is unresolved provenance and is not treated as an equivalence claim.

Raw machine-readable evidence:

- Test probe: `backend/reports/expo/appendix_b_probe/nbd_fixed_test_seed1337.csv`
- Candidate metrics: `backend/reports/expo/t1_corrected_candidate/metrics.json`
- Confusion matrix image: `backend/reports/expo/t1_corrected_candidate/confusion_matrix.png`
- Lens/episode analysis: `backend/reports/expo/t1_corrected_candidate/lens_ablation_and_episode_results.json`
- Re-runnable analysis: `backend/scripts/expo/t1_leakage_re_evaluation.py`
- Candidate artifact: `backend/models/experiments/expo_t1_corrected_candidate.joblib`

Figures below are labelled **Measured** when emitted by a command, **Computed** when derived directly from measured counts, and **Planned** when they are a future acceptance criterion.

## Data and selection

**Measured:** train has 7,500 rows, validation 3,500 rows, and the fresh safe test probe 3,500 rows. The trainer used 37 features and partitioned Sensor Malfunction rows from the primary three-class evaluation. The safe test probe contains Normal 2,610, Natural Fault 495, Cyber Intrusion 204, and Sensor Malfunction 191 rows.

**Measured:** Random Forest was selected using validation-only Cyber F2 under the existing 50 ms latency gate. Validation threshold was 0.25; validation Cyber F2 was 0.5828, recall 0.5391, precision 0.8625, FPR 0.0034. LightGBM and XGBoost were not selected by that rule (validation F2 0.5707 and 0.5746 respectively).

## Held-out corrected-probe result

The selected threshold was frozen before test scoring.

**Measured:** overall accuracy 0.9495; Cyber Intrusion precision 0.9912, recall 0.5490, F1 0.7066, F2 0.6028, and FPR 0.0003 (112 TP, 92 FN, 1 FP, 3,104 non-cyber negatives in the primary evaluation). The primary confusion matrix, in class order `Cyber Intrusion`, `Natural Fault`, `Normal`, is:

```text
[[112, 2, 90],
 [  0,429, 66],
 [  1,  8,2601]]
```

**Measured:** class metrics were Cyber Intrusion P/R/F1 = 0.9912/0.5490/0.7066; Natural Fault = 0.9772/0.8667/0.9186; Normal = 0.9434/0.9966/0.9693. Candidate latency was median 32.696 ms, p95 43.283 ms, mean 34.232 ms; it was within the 50 ms gate.

**Measured:** cyber subtype recall was command_injection 0.3778 (90), data_injection 0.8723 (47), and replay 0.9403 (67). Sensor-drift rows were handled by the separate pathway in the trainer: 191 rows, dedicated-pathway recall 0.623. The primary model marked 129 of those rows as Cyber Intrusion; this is a taxonomy/confusion observation, not a cyber false-positive rate.

## Network-lens ablation and episode analysis

The analysis script fits each lens on training rows, selects a threshold on validation at a target FPR of 1%, then scores the test probe once. These are **Measured** ablation results, not production performance:

| Lens | Validation threshold | Test ROC-AUC | Test PR-AUC | Precision | Recall | F1 | Test FPR | Confusion matrix (truth 0/1, pred 0/1) |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| NBD-only (10) | 0.505 | 0.6013 | 0.2334 | 0.0898 | 0.3627 | 0.1440 | 0.2415 | `[[2355,750],[130,74]]` |
| PCD-only (27) | 0.195 | 0.7727 | 0.4957 | 0.8710 | 0.3971 | 0.5455 | 0.0039 | `[[3093,12],[123,81]]` |
| Fusion-all-37 | 0.150 | 0.8376 | 0.6426 | 0.8014 | 0.5735 | 0.6686 | 0.0093 | `[[3076,29],[87,117]]` |

**Computed:** the fusion lens improved test recall over NBD-only by 0.2108 absolute and reduced FPR by 0.2322 absolute at their independently validation-selected thresholds. This does not prove that PCD or fusion improves the deployed detector because the ablation models are separate experimental Random Forests and the data are synthetic/correlated.

**Measured:** the candidate’s tick-grouped test trace contained 17 cyber episodes; all 17 were detected. Delays were 0–1 seconds, median 0 seconds and p90 1 second. This episode result is descriptive and optimistic because adjacent ticks are autocorrelated and the test probe is generated from the same documented synthetic procedure; it is not independent-capture evidence.

## Limitations and unresolved blockers

1. The fresh probe checksum differs from the checksum recorded in the project document; the exact historical test artifact is not reconstructed by this task.
2. The ablation and candidate results are not a fair independent-site or independent-capture estimate. The available splits do not establish site/campaign independence.
3. The 37-feature corrected schema conflicts with the document’s older 28-feature Appendix A; schema reconciliation remains T7.
4. T1 did not replace or score `fusion_classifier.joblib`, and it did not invoke a live production service endpoint. Production integration compatibility remains unproven.
5. Command-injection recall remains low, and Sensor Malfunction is a separate taxonomy path with substantial primary-model confusion.
6. Maximum F2 and the 1% ablation target are analysis choices, not approved operational policy.

## T1 outcome

**Measured conclusion:** the corrected isolated candidate is reproducible and meets the measured latency gate on the safe probe, but its Cyber recall is 54.90% and the NBD-only lens is weak. **Decision:** T1 does not justify production integration or a claim of improved GridSentinel detection. The next approved task may investigate false alarms/recall diagnosis after schema reconciliation; no T2 work was started here.
