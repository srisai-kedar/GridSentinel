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
