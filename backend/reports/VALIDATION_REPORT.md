# GridSentinel — Machine Learning Classifier Validation Report

**Report Generated:** 2026-10-08T19:02:38.261598+00:00  
**Evaluation Mode:** Production inference path (`ClassifierService.predict`)  
**Dataset Evaluated:** Held-out test set (`data/generated/test_dataset_seed1337.csv`)  

---

## 1. Provenance & System Configuration

| Property | Value |
|:---|:---|
| **Git Commit Hash** | `c7a446af1bf4916c32a968860e57094c9ec52ef7` |
| **Model Artifact** | [`models/fusion_classifier.joblib`](models/fusion_classifier.joblib) |
| **Model SHA-256** | `ee5211510e41eddac32ed1eed405af982a0a550bd0b75e8867253135b812ccae` |
| **Model Selected** | **XGBoost** (decision threshold = 0.58) |
| **Feature Schema Version** | `2.0.0` (28 features) |
| **Test Dataset** | `data/generated/test_dataset_seed1337.csv` |
| **Test Dataset SHA-256** | `a8ca03f3dd18f2454f132bd8e41a4f95e35bd0d1426e2a5e9085c5b1c6e22f2c` |
| **Test Sample Count** | 3500 samples |
| **Simulation Tick Duration** | 1.0 s / tick |
| **Random Seeds** | Train: 42, Validation Tuning: 999, Held-out Test: 1337 |

---

## 2. Headline Performance Metrics (Held-Out Test Set)

| Metric | Value | 95% Confidence Interval (Wilson) | Support (n) |
|:---|:---:|:---:|:---:|
| **Overall Accuracy** | **90.77%** | [89.77%, 91.69%] | 3500 ticks |
| **Cyber Intrusion Recall (TPR)** | **52.65%** | [46.63%, 58.59%] | 264 true cyber ticks |
| **Cyber False Negative Rate (FNR)** | **47.35%** | [41.41%, 53.37%] | 264 true cyber ticks |
| **Cyber Intrusion Precision** | **90.85%** | [85.23%, 94.47%] | 153 cyber alerts |
| **Cyber False Positive Rate (FPR)** | **0.43%** | [0.26%, 0.72%] | 3236 non-cyber ticks |
| **Episode Detection Rate** | **100.00%** | [85.13%, 100.00%] | 22 attack episodes |

> [!NOTE]
> All headline metrics are measured strictly on the **held-out test set** (seed 1337) without row dropping, resampling, or reweighting.

---

## 3. Confusion Matrix

| True Label \ Predicted Label | Pred: Cyber Intrusion | Pred: Natural Fault | Pred: Normal | Total Support |
|:---|:---:|:---:|:---:|:---:|
| **True: Cyber Intrusion** | **139** | 9 | 116 | **264** |
| **True: Natural Fault** | **5** | 584 | 116 | **705** |
| **True: Normal** | **9** | 68 | 2454 | **2531** |
| **Total Predicted** | **153** | **661** | **2686** | **3500** |

---

## 4. Per-Class Precision, Recall, F1, FPR, and FNR

| Class | Support | TP | FP | FN | TN | Precision [95% CI] | Recall [95% CI] | F1-Score | FPR [95% CI] | FNR [95% CI] |
|:---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| **Cyber Intrusion** | 264 | 139 | 14 | 125 | 3222 | 90.85% [85.2%, 94.5%] | 52.65% [46.6%, 58.6%] | 66.67% | 0.43% [0.26%, 0.72%] | 47.35% [41.4%, 53.4%] |
| **Natural Fault** | 705 | 584 | 77 | 121 | 2718 | 88.35% [85.7%, 90.6%] | 82.84% [79.9%, 85.4%] | 85.51% | 2.75% [2.21%, 3.43%] | 17.16% [14.6%, 20.1%] |
| **Normal** | 2531 | 2454 | 232 | 77 | 737 | 91.36% [90.2%, 92.4%] | 96.96% [96.2%, 97.6%] | 94.08% | 23.94% [21.36%, 26.73%] | 3.04% [2.4%, 3.8%] |

---

## 5. Cyber Intrusion False Negative Detail

For the **264 true Cyber Intrusion ticks**:

| Category | Count | Proportion | 95% CI (Wilson) | Operational Meaning |
|:---|:---:|:---:|:---:|:---|
| **True Positives (Correctly Detected)** | **139** | **52.65%** | [46.63%, 58.59%] | Cyber alert raised promptly |
| **Silent Misses (`miss_to_normal`)** | **116** | **43.94%** | [38.08%, 49.97%] | **No alert raised**; attack unnoticed |
| **Attribution Misses (`miss_to_fault`)** | **9** | **3.41%** | [1.80%, 6.35%] | Alert raised, but misattributed to Natural Fault |
| **Total False Negatives (`fnr_strict`)** | **125** | **47.35%** | [41.41%, 53.37%] | All undetected cyber ticks |

> [!IMPORTANT]
> Exact Identity Verified: `fnr_strict` (125/264 = 47.3485%) equals `miss_to_normal` (116/264) + `miss_to_fault` (9/264).

---

## 6. Per-Attack-Subtype Breakdown

| Attack Subtype | Support (n) | True Positives | False Negatives | Miss to Normal | Miss to Fault | Recall [95% CI] | FNR [95% CI] |
|:---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| **command_injection** | 84 | 32 | 52 | 51 (60.7%) | 1 (1.2%) | 38.10% [28.4%, 48.8%] | 61.90% [51.2%, 71.6%] |
| **data_injection** | 84 | 62 | 22 | 17 (20.2%) | 5 (6.0%) | 73.81% [63.5%, 82.0%] | 26.19% [18.0%, 36.5%] |
| **replay** | 96 | 45 | 51 | 48 (50.0%) | 3 (3.1%) | 46.88% [37.2%, 56.8%] | 53.12% [43.2%, 62.8%] |

- **Data Injection:** Highest recall (73.81%), as falsified power-flow measurements trigger large state-estimation residuals (LNR).
- **Command Injection:** Lowest recall (38.10%), with 51/84 ticks misclassified as Normal when register writes do not distort immediate bus voltages.
- **Replay:** Moderate recall (46.88%), 48/96 ticks misclassified as Normal during steady-state load periods where replayed telemetry resembles nominal diurnal state.

---

## 7. Episode-Level Metrics

An attack episode is defined as a contiguous run of true Cyber Intrusion ticks:

| Episode Metric | Value | 95% Confidence Interval | Details |
|:---|:---:|:---:|:---|
| **Total Attack Episodes** | **22** | — | 22 contiguous attack sequences |
| **Detected Episodes** | **22** | — | Episodes with $\ge 1$ Cyber prediction |
| **Episode Detection Rate** | **100.00%** | [85.13%, 100.00%] | Every attack episode was caught |
| **Episode Alert Rate (Cyber or Fault)** | **100.00%** | [85.13%, 100.00%] | Triage alert raised for all episodes |
| **Median Detection Delay** | **0.0 ticks** | — | **0.0 seconds** simulated time |
| **90th Percentile Delay** | **1.0 ticks** | — | **1.0 seconds** simulated time |
| **Detected on Onset Tick (Delay = 0)** | **68.2%** | — | 15 / 22 episodes detected immediately |
| **Detected within 3 Ticks ($\le 2$ s)** | **100.00%** | — | 22 / 22 episodes |
| **Detected within 5 Ticks ($\le 4$ s)** | **100.00%** | — | 22 / 22 episodes |

> [!TIP]
> **Operational Contrast:** While tick-level cyber recall is 52.65%, **episode-level detection rate is 100%**. Because attacks persist over multi-tick windows, the classifier catches every single intrusion episode within at most 1–2 seconds of onset.

---

## 8. Operational False Alarms

| Metric | Value | Reference Basis |
|:---|:---:|:---|
| **Non-Attack Simulated Ticks** | 436 ticks | 700 total ticks − 264 cyber ticks |
| **Non-Attack Simulated Time** | 0.1211 hours | 436 seconds at 1.0 s/tick |
| **False-Alarm Episodes** | **8** | Maximal runs of consecutive Cyber predictions on non-attack ticks |
| **False-Alarm Rate per Simulated Hour** | **66.06 episodes / hr** | Extrapolated over 0.1211 h non-attack window |
| **False-Alarm Rate per 1,000 Non-Attack Ticks** | **18.35 episodes / 1k ticks** | Direct empirical count |

---

## 9. Reproducibility Check (Prior Pitch / Deck Claims)

| Claimed Metric | Stated Value | Recomputed Value | Exact Formula | Reproducibility Verdict |
|:---|:---:|:---:|:---|:---:|
| **Overall Accuracy** | 90.77% | **90.77%** | `total_correct / 3500` (3177/3500) | **MATCH (Reproduced)** |
| **Cyber False Positives** | 0.43% | **0.43%** | `non_cyber_predicted_cyber / non_cyber_ticks` (14/3236) | **MATCH (Reproduced)** |

Both headline claims match the held-out test evaluation to two decimal places.

---

## 10. Validation Set (Threshold Tuning Set — Seed 999)

> [!NOTE]
> This dataset (`data/generated/val_dataset_seed999.csv`) was used exclusively for decision threshold tuning during training. It is reported here for audit transparency and is **not** a headline evaluation set.

- **Overall Accuracy:** 91.57%
- **Cyber Intrusion Recall:** 62.13% (105/169)
- **Cyber Intrusion Precision:** 85.37%
- **Cyber False Positive Rate:** 0.54%

---

## 11. Limitations & Operational Considerations

1. **Tick Independence Assumption:** The Wilson 95% confidence intervals assume independent and identically distributed (i.i.d.) observations. Consecutive SCADA ticks within a continuous simulation exhibit temporal autocorrelation.
2. **Episode Sample Size:** The held-out test set contains 22 attack episodes across 700 ticks. While the observed episode detection rate is 100%, larger multi-day validation runs are recommended to tighten episode-level intervals.
3. **Simulated vs. Real-World Data:** Results are derived from synthetic Modbus TCP traffic and simulated 11kV radial feeder physics (pandapower). Field deployments across physical utility substations may present higher background network jitter and unmodeled switching transients.
4. **Decision Support Only:** GridSentinel operates strictly as a decision-support and situational awareness tool; physical breaker operations must remain subject to human operator verification and utility standard operating procedures.
