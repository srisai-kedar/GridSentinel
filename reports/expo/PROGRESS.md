# Expo hardening progress

## 2026-10-27 — T1 leakage re-evaluation

- **Command:** Appendix B dataset generation and isolated training commands from `docs/GridSentinel_doc.txt`, redirected to `backend/reports/expo/appendix_b_probe/` and `backend/models/experiments/expo_t1_corrected_candidate.joblib`; then `backend/scripts/expo/t1_leakage_re_evaluation.py`.
- **Result:** fresh safe probe generated (3,500 rows); isolated candidate trained; lens ablation and episode analysis completed. Candidate test Cyber recall 0.5490, precision 0.9912, F1 0.7066, FPR 0.0003, median/p95 latency 32.696/43.283 ms. Episode analysis detected 17/17 grouped cyber episodes with median/p90 delay 0/1 seconds.
- **Caveat:** safe probe SHA differs from the document’s recorded held-out SHA; production model was not modified or scored. Full backend suite remains 312 passed, 1 known citation-lint baseline failure, with no new failure.
- **Next step:** stop after T1; await approval for a later task. T2 was not started.

## 2026-10-27 — T1 follow-up counts and like-for-like production read

Command: `backend\\.venv\\Scripts\\python.exe backend\\scripts\\expo\\t1_followup_counts.py --train backend\\data\\generated\\nbd_fixed_train_seed42.csv --val backend\\data\\generated\\nbd_fixed_val_seed999.csv --test backend\\reports\\expo\\appendix_b_probe\\nbd_fixed_test_seed1337.csv --candidate backend\\models\\experiments\\expo_t1_corrected_candidate.joblib --production backend\\models\\fusion_classifier.joblib --out backend\\reports\\expo\\t1_corrected_candidate\\followup_counts.json`.

All intervals below are **Computed** with the two-sided 95% Wilson interval from command output; no test-set threshold was selected for them.

### Corrected test and candidate counts

| Quantity | Value |
|---|---:|
| Test rows | 3,500 |
| Cyber attack readings | 204 |
| Overall prevalence | 5.8286% |
| Candidate cyber TP / FP / FN / TN | 112 / 1 / 92 / 3,104 |

| Truth \\ Predicted | Cyber Intrusion | Natural Fault | Normal |
|---|---:|---:|---:|
| Cyber Intrusion | 112 | 2 | 90 |
| Natural Fault | 0 | 429 | 66 |
| Normal | 1 | 8 | 2,601 |

| Metric | Count / denominator | Estimate | 95% Wilson interval |
|---|---:|---:|---:|
| Cyber recall | 112 / 204 | 54.90% | 48.05%–61.58% |
| Cyber precision | 112 / 113 | 99.12% | 95.16%–99.84% |
| Cyber FPR | 1 / 3,105 | 0.0322% | 0.0057%–0.1822% |

### Read-only old production model

The production artifact loaded successfully, unchanged, with its 28-feature schema. Every required production feature name was present in the corrected test columns, so a read-only like-for-like score was possible. Production threshold: 0.58.

| Model | Cyber TP | FP | FN | TN | Recall | Precision | FPR |
|---|---:|---:|---:|---:|---:|---:|---:|
| Corrected candidate | 112 | 1 | 92 | 3,104 | 54.90% | 99.12% | 0.0322% |
| Old production model | 108 | 3 | 96 | 3,102 | 52.94% | 97.30% | 0.0966% |

| Model | 3-class confusion matrix, labels = Cyber / Natural / Normal |
|---|---|
| Corrected candidate | `[[112, 2, 90], [0, 429, 66], [1, 8, 2601]]` |
| Old production model | `[[108, 3, 93], [1, 427, 67], [2, 46, 2562]]` |

### Candidate per-subtype cyber recall

| Subtype | Correct / total | Recall | 95% Wilson interval |
|---|---:|---:|---:|
| Command injection | 34 / 90 | 37.78% | 28.46%–48.10% |
| Data injection (FDI) | 41 / 47 | 87.23% | 74.83%–94.02% |
| Replay | 63 / 67 | 94.03% | 85.63%–97.65% |

### NBD-only versus PCD-only versus fusion

Each lens was trained on corrected train rows. For each target, the threshold was selected on validation to maximize validation TPR subject to the target FPR, then applied once to corrected test rows. Reported test FPR/TPR are **Measured** at those validation-selected thresholds; they are not test-tuned thresholds.

| Lens | ROC-AUC | Target | Validation threshold | Test TPR | Test FPR |
|---|---:|---:|---:|---:|---:|
| NBD-only | 0.6013 | 0.5% | 0.415 | 36.76% | 24.32% |
| NBD-only | 0.6013 | 1.0% | 0.360 | 37.75% | 26.15% |
| PCD-only | 0.7727 | 0.5% | 0.245 | 39.22% | 0.16% |
| PCD-only | 0.7727 | 1.0% | 0.160 | 40.69% | 0.68% |
| Fusion-all-37 | 0.8376 | 0.5% | 0.215 | 55.88% | 0.16% |
| Fusion-all-37 | 0.8376 | 1.0% | 0.150 | 57.35% | 0.93% |

### Feature importance and threshold provenance

| Feature | Importance rank | Importance share |
|---|---:|---:|
| `nbd_unexpected_write_count` | 25 / 37 | 0.5099% |

The candidate cyber threshold is **0.25**, selected on validation only by the existing trainer’s validation Cyber-F2 rule; the held-out corrected test was evaluated with that frozen threshold.

### Episode-level result

| Quantity | Value |
|---|---:|
| Cyber episodes | 17 |
| Episodes detected | 17 / 17 (100%) |
| Median delay | 0 seconds |
| P90 delay | 1 second |
| False-alarm episodes on non-attack ticks | 18 |
| Test duration | 0.1944 hours (700 ticks) |
| False-alarm episodes/hour | 92.57 |

### Why the episode count differs from the older 22

| Dataset | Seed / ticks | Class counts | Cyber episodes |
|---|---|---|---:|
| Older `backend/data/generated/test_dataset_seed1337.csv` | 1337 / 700 | Normal 2,531; Natural Fault 705; Cyber 264 | 22 |
| Corrected `nbd_fixed_test_seed1337.csv` used here | 1337 / 700 | Normal 2,610; Natural Fault 495; Sensor Malfunction 191; Cyber 204 | 17 |

The corrected generator uses the current scenario schedule: 25% each Normal, Natural Fault, Sensor Malfunction, and Cyber Intrusion, with seeded random episode durations and targets. The older file has no Sensor Malfunction class and different class/subtype counts, so the two files are not like-for-like despite sharing seed and tick count. The corrected safe probe also differs from the historical checksum recorded in the project document.

## 2026-10-27 — T1 reconciliation and T2 persistence

Command: `backend\\.venv\\Scripts\\python.exe backend\\scripts\\expo\\t1_reconcile_t2_persistence.py --train backend\\data\\generated\\nbd_fixed_train_seed42.csv --val backend\\data\\generated\\nbd_fixed_val_seed999.csv --test backend\\reports\\expo\\appendix_b_probe\\nbd_fixed_test_seed1337.csv --candidate backend\\models\\experiments\\expo_t1_corrected_candidate.joblib --production backend\\models\\fusion_classifier.joblib --out backend\\reports\\expo\\t1_corrected_candidate\\reconciliation_t2.json`.

All numbers below are **Measured** or directly **Computed** from that command. Wilson intervals are two-sided 95% intervals. The production model was read-only.

### Reconciliation A.1 — excluded Sensor Malfunction rows

The three-class confusion matrix intentionally uses the primary triage set: all `Sensor Malfunction` rows are excluded before confusion-matrix construction. The test has 3,500 rows; 191 sensor rows are excluded, leaving 3,309 primary rows.

| Model prediction on the 191 excluded sensor rows | Cyber | Natural Fault | Normal | Total |
|---|---:|---:|---:|---:|
| Corrected candidate | 129 | 25 | 37 | 191 |
| Old production model | 118 | 36 | 37 | 191 |

### Reconciliation A.2 — detection versus subtype classification

The earlier `34 + 41 + 63 = 138` table meant subtype-classifier correctness among all cyber rows: the secondary subtype model predicted the true subtype for 34/90 command-injection, 41/47 data-injection, and 63/67 replay rows. It did not mean that 138 rows were flagged as Cyber by the top-level detector.

| Subtype | Candidate flagged Cyber / total | Candidate detection Wilson interval | Old flagged Cyber / total | Old detection Wilson interval |
|---|---:|---:|---:|---:|
| Command injection | 33 / 90 | 27.45%–46.98% | 34 / 90 | 28.46%–48.10% |
| Data injection / FDI | 40 / 47 | 72.31%–92.59% | 36 / 47 | 62.78%–86.40% |
| Replay | 39 / 67 | 46.27%–69.26% | 38 / 67 | 44.81%–67.90% |

Among readings that were detected as Cyber, the subtype classifier was 100% correct for each listed subtype for both candidate and old model. This conditional result is separate from detection recall and is affected by the small detected subsets.

### Reconciliation A.3 — false-alarm episode definitions

An episode is one contiguous run of tick seconds with at least one alert in the selected row subset; the test contains 700 unique tick seconds. The primary subset has 3,105 non-attack rows (`Cyber Intrusion` and `Sensor Malfunction` excluded from the negative denominator). The inclusive subset has 3,296 non-attack rows (only `Cyber Intrusion` excluded). Both subsets touch all 700 seconds because other RTUs remain present during attack ticks.

| Candidate definition | False-alarm episodes | Non-attack seconds | Episodes/hour |
|---|---:|---:|---:|
| Primary 3,105-row subset | 1 | 700 | 5.14 |
| Including 191 sensor rows | 19 | 700 | 97.71 |

The earlier 18 figure used a different alert grouping implementation and was not reconciled with the one-reading confusion-matrix count. It should not be used; this command's explicit row-subset calculation supersedes it.

### Reconciliation A.4 — write visibility

`nbd_unexpected_write_count > 0` is the available observer-verified write-count field in this corrected feature table. It was positive in 34/90 command-injection rows (37.78%; Wilson 28.46%–48.10%) and in 0/3,296 non-attack rows. The candidate flagged 33 of those 34 visible-write rows and missed 1. Thus a visible write can be missed; the feature is not always populated, and its low global importance (rank 25/37, 0.5099%) does not prove that writes are irrelevant.

### T2 persistence selection

Persistence was implemented as a per-RTU rolling k-of-n count over current and preceding ticks. A cooldown suppresses a new alert for the specified number of subsequent seconds after an alert. For each k/n, cooldown was selected on validation only by: maximize attack-episode recall, then minimize primary false-alarm episodes/hour, then minimize median delay. The global validation-selected setting was **2-of-3 with a 1-second cooldown**. No test result was used for selection.

| Setting | Validation-selected cooldown | Test per-reading recall | Test episode recall | Median / p90 delay | Primary FA episodes/hour | Inclusive-sensor FA episodes/hour |
|---|---:|---:|---:|---:|---:|---:|
| 1-of-1 | 0 s | 54.90% | 17/17 (100%) | 0 / 1 s | 5.14 | 97.71 |
| **2-of-3 (selected)** | **1 s** | **28.43%** | **17/17 (100%)** | **1 / 2 s** | **0.00** | **360.00** |
| 2-of-4 | 5 s | 14.22% | 17/17 (100%) | 1 / 2 s | 15.43 | 169.71 |
| 3-of-5 | 5 s | 12.25% | 16/17 (94.12%) | 2 / 3 s | 0.00 | 144.00 |

T2 is an isolated post-processing experiment; no model, threshold, production schema, or production artifact was changed.
