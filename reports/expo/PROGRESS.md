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

## 2026-10-27 — T2 follow-up: end-to-end drift and latch/hold

Command (run from repository root): `backend\\.venv\\Scripts\\python.exe backend\\scripts\\expo\\t2_followup_drift_hysteresis.py --train backend\\data\\generated\\nbd_fixed_train_seed42.csv --val backend\\data\\generated\\nbd_fixed_val_seed999.csv --test backend\\reports\\expo\\appendix_b_probe\\nbd_fixed_test_seed1337.csv --candidate backend\\models\\experiments\\expo_t1_corrected_candidate.joblib --production backend\\models\\fusion_classifier.joblib --out backend\\reports\\expo\\t1_corrected_candidate\\t2_followup.json`.

### End-to-end drift path

The evaluation used the same ClassifierService threshold logic and deterministic `detect_sensor_drift_signature` interception semantics, evaluated in batches to avoid per-row sklearn warning overhead. The production bundle has 28 features; the candidate has 37. Values below are **Measured/Computed** from the command.

| Final verdict on 191 sensor rows | Candidate | Old production |
|---|---:|---:|
| SENSOR_DRIFT | 119 | 0 |
| CYBER | 10 | 118 |
| NATURAL_FAULT | 25 | 36 |
| NORMAL | 37 | 37 |

| Final verdict by 16 drift episodes (majority of rows in each episode) | Candidate | Old production |
|---|---:|---:|
| SENSOR_DRIFT | 16 | 0 |
| CYBER | 0 | 15 |
| NATURAL_FAULT | 0 | 1 |
| NORMAL | 0 | 0 |

Candidate episode-level drift detection was 16/16, Wilson 95% interval 80.64%–100.00%. Old production was 0/16, Wilson 95% interval 0.00%–19.36%. Candidate per-reading drift recall was 119/191 = 62.30%, Wilson 55.25%–68.87%; old production was 0/191, Wilson 0.00%–1.96%.

| Drift-rule firing target | Fires / total | Wilson 95% interval |
|---|---:|---:|
| Sensor drift | 119 / 191 | 55.25%–68.87% |
| FDI/data injection | 0 / 47 | 0.00%–7.56% |
| Replay | 0 / 67 | 0.00%–5.42% |
| Command injection | 0 / 90 | 0.00%–4.09% |
| Natural fault | 0 / 495 | 0.00%–0.77% |
| Normal | 0 / 2,610 | 0.00%–0.15% |

Physics signatures were partially distinguishable: sensor drift versus FDI medians were residual concentration 0.9105 vs 0.9124, `dv/dt` 0.0019 vs 0.0555, voltage deviation 0.0583 vs 0.1583, max LNR 16.69 vs 41.18, and traffic volume 6 vs 6 with anomaly rate 0 vs 0. This supports a possible ramp/step distinction in this synthetic data, but does not establish complete separation: 72/191 sensor readings still did not receive the drift verdict. The existing rule produced zero FDI-as-drift errors, so FDI separation is good on this sample while drift coverage remains incomplete.

### Improvement A — ramp discriminator

Validation-only selection chose `abs(pcd_temporal_dv_dt_3tick) <= 0.0432`, with validation sensor recall 47.19%, zero FDI wrongly labelled drift, and 100% FDI detection preserved. On test it labelled 113/191 sensor rows as drift, zero FDI rows as drift, and reduced sensor rows called CYBER from 10 to 10. Because it did not reduce CYBER calls and reduced drift coverage from 119 to 113, the discriminator was rejected as an improvement. No fallback verdict was added; the honest unresolved state remains “single-measurement residual anomaly, cause undetermined—quarantine and inspect.”

### Improvement B — latch/hold hysteresis

The latch raises on k-of-n raw Cyber readings per RTU and remains active until M consecutive clear readings. `k`, `n`, and `M` were selected on validation only by episode recall, then sensor-inclusive false-alarm rate, then delay. The selected configuration was 2-of-3 with M=4.

| Configuration | Validation-selected M | Test episode recall | Median / P90 delay | Primary FA/h (Poisson 95%) | Including sensor FA/h (Poisson 95%) |
|---|---:|---:|---:|---:|---:|
| 1-of-1 | 4 | 17/17 | 0 / 1 s | 123.43 (79.08–183.65) | 128.57 (83.20–189.80) |
| **2-of-3 selected** | **4** | **17/17** | **1 / 2 s** | **118.29 (74.98–177.49)** | **128.57 (83.20–189.80)** |
| 2-of-4 | 4 | 17/17 | 1 / 2 s | 118.29 (74.98–177.49) | 128.57 (83.20–189.80) |
| 3-of-5 | 1 | 16/17 | 2 / 3 s | 30.86 (11.32–67.16) | 113.14 (70.91–171.30) |

The latch did not improve the sensor-inclusive false-alarm rate on this corrected test; it remained 25 episodes in 700 seconds. It is not retained as a production recommendation.

Selected 2-of-3/M=4 per-reading test counts were TP/FP/FN/TN = 152/41/52/3,064, giving recall 74.51% and primary Cyber FPR 1.32%. It called 25 of the 191 sensor rows CYBER after holding alerts, versus 10 raw candidate sensor rows called CYBER; this is additional evidence against promotion.

### T2 before/after summary

| Measure | Frozen candidate, 1-of-1 | Selected latch/hold, 2-of-3/M=4 |
|---|---:|---:|
| Cyber recall | 54.90% | 74.51% |
| Cyber FPR, primary | 0.0322% | 1.32% |
| Sensor rows called CYBER | 10 / 191 | 25 / 191 |
| Primary false-alarm episodes/hour | 5.14 | 118.29 |
| Sensor-inclusive false-alarm episodes/hour | 97.71 | 128.57 |
| Episode recall | 17/17 | 17/17 |
| Median / P90 delay | 0 / 1 s | 1 / 2 s |

The latch gains per-reading recall only by materially increasing false alarms and sensor rows called CYBER; it is rejected.

## 2026-10-27 — T2 demo check, tail reconciliation, and slide lock

### Deployed demo command and result

Commands run against `https://gridsentinel-72tf.onrender.com`:

```text
Invoke-RestMethod https://gridsentinel-72tf.onrender.com/health
Invoke-RestMethod https://gridsentinel-72tf.onrender.com/ot/fault/sensor-drift -Method Post -Body '{"rtu_id":1,"drift_percent":0.08,"duration_ticks":25}' -ContentType application/json
1..30 | ForEach-Object { Invoke-RestMethod https://gridsentinel-72tf.onrender.com/classifier/verdict -Method Post -Body '{}' -ContentType application/json; Start-Sleep -Milliseconds 1000 }
Invoke-RestMethod https://gridsentinel-72tf.onrender.com/ot/reset -Method Post -Body '{}' -ContentType application/json
```

The deployed health check returned `status=ok`; injection returned `SENSOR_DRIFT` for RTU-1; reset completed. The raw second run is stored at `backend/reports/expo/t1_corrected_candidate/live_sensor_drift_demo.json`.

| Deployed RTU-1 result over 30 samples | Count |
|---|---:|
| Natural Fault / physical_fault | 30 |
| Sensor Drift | 0 |
| Cyber | 0 |
| Model loaded | 30/30 true |

The old production model's offline 0/191 drift result is explained by the schema gap. `ClassifierService._predict_untimed` builds its vector from the bundle schema at `backend/app/ml/classifier_service.py:571`; the old bundle has 28 features, so the nine corrected residual/DPN fields are absent. The drift rule at `classifier_service.py:92-113` specifically reads `pcd_resid_concentration`, `pcd_resid_breadth_count`, and `pcd_resid_rtu_share`; absent keys default to zero, and the required concentration condition therefore fails. The interception is applied at `classifier_service.py:621-625`. The deployed demo currently displays `Natural Fault / physical_fault` for this scenario, not `SENSOR_DRIFT`.

### Latch-tail reconciliation

For each false-alarm episode, a hold tail was defined as a false-alarm run whose first alert tick was strictly after, and no more than four seconds after, the end tick of any Cyber episode. **Measured by `t2_tail_reconcile.py`:** the selected latch had 23 primary false-alarm episodes: 11 hold tails and 12 genuine episodes. The raw baseline had 1 primary false-alarm episode: 0 hold tails and 1 genuine episode. The same 4-second rule was applied to both. The selected-latch hold-tail intervals were `(59,59)`, `(127,129)`, `(147,147)`, `(167,168)`, `(191,192)`, `(287,287)`, `(378,378)`, `(486,488)`, `(519,520)`, `(546,548)`, and `(624,625)`; the remaining 12 intervals were genuine. Full raw episode lists and the exact command output are in `tail_reconciliation.json` and `tail_reconciliation_console_output.txt`.

| Method | Per-reading recall | Episode recall | Median / P90 delay | FA episodes after tail exclusion | FA/hour, Poisson 95% |
|---|---:|---:|---:|---:|---:|
| Raw candidate 1-of-1 | 54.90% | 17/17 | 0 / 1 s | 1 / 700 s | 5.14 (0.13–28.60) |
| Selected 2-of-3, M=4 latch | 74.51% | 17/17 | 1 / 2 s | 12 / 700 s | 61.71 (31.89–107.80) |

The 4-second grace rule removes no episodes and therefore does not explain the tail burden.

### Episode and window reconciliation

The subtype episode counts are computed independently within each subtype: FDI 6, replay 7, command injection 8. They sum to 21 because subtype runs can be adjacent in the global Cyber timeline and therefore merge into one contiguous global episode. The global test episode count is 17; subtype episodes are not additive to it.

The feature extractor calls `traffic_logger.get_recent_events(limit=30)` in `backend/app/ml/dataset_generator.py:149`. The generator creates five RTU records per simulation tick (`dataset_generator.py:170-203`), so the global 30-record window is approximately six ticks × five RTU polls. The 56 zero-write command rows occur only 3–17 ticks after their own episode onset, so none has aged beyond 30 ticks; the 30-record window is not a 30-second per-RTU window. This is why “aged out” is not supported as the sole explanation.

### Locked slide results

Every figure below is **Measured** or **Computed** from the cited command/output; no production promotion is implied.

| Slide figure | Locked value | Source command / artifact |
|---|---:|---|
| Corrected test rows | 3,500 | T1 follow-up counts command; `followup_counts.json` |
| Corrected Cyber readings / prevalence | 204 / 5.83% | T1 follow-up counts command |
| Candidate Cyber recall / precision / FPR | 54.90% / 99.12% / 0.0322% | T1 follow-up counts command |
| Old production Cyber recall / FPR on same corrected file | 52.94% / 0.0966% | T1 follow-up counts command |
| Candidate Cyber episodes | 17/17; median 0 s; p90 1 s | T1 follow-up counts command |
| Fusion ROC-AUC / TPR at validation-selected 0.5% target | 0.8376 / 55.88% | T1 follow-up counts command |
| NBD-only ROC-AUC | 0.6013 | T1 follow-up counts command |
| Candidate subtype detection recall: FDI / replay / command | 85.11% / 58.21% / 36.67% | T1 reconciliation command |
| Candidate service-path sensor rows: SENSOR_DRIFT / CYBER | 119 / 10 | T2 follow-up command |
| Deployed demo RTU-1 sensor-drift verdict | 30/30 Natural Fault; 0/30 Sensor Drift | deployed demo command; `live_sensor_drift_demo.json` |
| Selected latch per-reading recall / primary FPR | 74.51% / 1.32% | T2 follow-up command |
| Selected latch primary false-alarm rate after 4-second hold-tail exclusion | 61.71/hour (31.89–107.80) | `t2_tail_reconcile.py` command; `tail_reconciliation.json` |
| Selected latch sensor-inclusive false-alarm rate | 128.57/hour (83.20–189.80) | T2 follow-up command |

### Claims in `docs/GridSentinel_doc.txt` now contradicted or unsupported

- The headline `22 / 22` attack episodes, 52.65% recall, 0.43% FPR, and 8 false-alarm episodes in 436 seconds describe the older `test_dataset_seed1337.csv`; they are not results for the corrected 3,500-row test used here.
- The document's 22-episode assumption is contradicted by the corrected file's 17 global Cyber episodes; the older and corrected files have different class distributions and schemas.
- The document's per-subtype recalls 73.81% / 46.88% / 38.10% are pre-correction values and cannot be reused as corrected-test results. Corrected top-level detection values are 85.11% FDI, 58.21% replay, and 36.67% command injection.
- The document states that the held-out test contains no sensor-drift rows and has no drift performance numbers; the corrected test does contain 191 sensor rows, but the deployed 28-feature model still produces no SENSOR_DRIFT verdicts in the live demo.
- The document's 28-feature Appendix A and its 28-feature test description are inconsistent with the corrected 37-feature candidate and drift-rule dependence on the nine added fields.
- The document's planned “persistence and hysteresis” work is not a demonstrated improvement: the selected latch increased recall but raised primary false-alarm burden to 118.29/hour and sensor-inclusive burden to 128.57/hour.

### Episode results by subtype using the selected latch

| Subtype | Episodes detected / total | Median / P90 delay |
|---|---:|---:|
| FDI/data injection | 6/6 | 0 / 0 s |
| Replay | 7/7 | 1 / 1 s |
| Command injection | 8/8 | 0 / 0 s |

### Command-injection visibility

The 56 command-injection rows with zero observed writes occurred 3–17 ticks after their episode onset; 0/56 were at least 30 ticks old. None had aged out of the 30-record window. This rejects “all 56 are simply aged-out writes” as the explanation; it is a label/observation-timing or feature-population limitation, not proven to be a pure window-age artefact.

### Subtype features

The Random Forest subtype model uses the same 37 stored feature columns: the 10 `nbd_*` features, the 18 core `pcd_*`/`dpn_*` features through `pcd_cross_rtu_voltage_divergence`, and the nine corrected residual/DPN features (`pcd_resid_jump`, `pcd_resid_persist`, `pcd_resid_concentration`, `pcd_resid_rtu_share`, `pcd_resid_breadth_count`, `pcd_resid_breadth_frac`, `dpn_legacy`, `dpn_ing_delta`, `dpn_ing_resid`). None is a label column or an explicit label-derived field; they are measured/generated telemetry and network features. Their synthetic provenance and leakage risk still require broader validation.

### Clean-run bound

Skipped. `dataset_generator.py` has no clean-only mode; running it would mix scenarios. Adding a clean-only mode or approximating one would exceed this isolated follow-up. No clean-run false-alarm bound is claimed.
