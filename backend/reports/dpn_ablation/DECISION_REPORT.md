# Change 5: Physics-Network Disagreement Feature Family — Ablation & Decision Report

**Timestamp:** 2026-10-13T05:05:39.987124+00:00  
**Pre-Registered Protocol Decision:** **`NO-PROMOTE`**  

---

## 1. Executive Decision Summary

A **NULL RESULT** was obtained. No experimental arm satisfied all pre-registered criteria (including statistically significant delta FNR reduction >= 3.0 pp and FPR bounds).
Per protocol, the null result is an honest, scientifically valid outcome and is recorded as such. The deployed baseline artifact (`models/fusion_classifier.joblib`) remains untouched.

---

## 2. Full Arms Comparison Table (Selection Set Seed 2024)

| Arm | Features | Cyber FNR (mean ± sd) | Cyber FPR | Nat-Fault->Cyber | Ep Detection Rate | Paired Delta vs A0 (95% CI) |
|:---|:---:|:---:|:---:|:---:|:---:|:---:|
| **A0** | 28 | 33.55% ± 0.00% | 0.66% | 1.56% | 66.45% | 0.00% (Baseline) |
| **A1** | 29 | 33.55% ± 0.00% | 1.76% | 4.98% | 66.45% | +0.00% [+0.00%, +0.00%] |
| **A2** | 29 | 34.19% ± 0.00% | 0.66% | 1.66% | 65.81% | +0.65% [+0.00%, +2.10%] |
| **A3** | 30 | 33.55% ± 0.00% | 0.66% | 1.56% | 66.45% | +0.00% [+0.00%, +0.00%] |
| **A4** | 30 | 33.55% ± 0.00% | 0.66% | 1.56% | 66.45% | +0.00% [+0.00%, +0.00%] |
| **A5** | 32 | 33.55% ± 0.00% | 0.66% | 1.56% | 66.45% | +0.00% [+0.00%, +0.00%] |
| **A6** | 34 | 33.55% ± 0.00% | 1.61% | 4.68% | 66.45% | +0.00% [+0.00%, +0.00%] |
| **A7** | 29 | 34.19% ± 0.00% | 0.84% | 1.66% | 65.81% | +0.65% [+0.00%, +2.10%] |
| **C1** | 30 | 33.55% ± 0.00% | 0.54% | 1.17% | 66.45% | +0.00% [+0.00%, +0.00%] |

---

## 3. Single-Source vs Fusion Baselines (Slide 3 Evaluation)

| Source | Features | Overall Cyber FNR | Silent (Data) Injection | Command Injection | Replay | Slide 3 Agreement |
|:---|:---:|:---:|:---:|:---:|:---:|:---|
| **NBD-only** | 10 | 36.13% | 0.00% | 0.00% | 0.00% | Claim Tested |
| **PCD-only** | 18 | 47.10% | 0.00% | 0.00% | 0.00% | Claim Tested |
| **Fusion (A0)** | 28 | 33.55% | 0.00% | 0.00% | 0.00% | Claim Tested |

---

## 4. Pre-Registered Decision Rules Breakdown

### Arm A1
- **rule_a_delta_fnr_ci_negative**: `FAIL` ({'passed': False, 'delta_fnr_pp': 0.0, 'ci_upper_pp': 0.0})
- **rule_b_min_3pp_reduction**: `FAIL` ({'passed': False, 'abs_reduction_pp': 0.0, 'threshold_pp': 3.0})
- **rule_c_fpr_and_nat_cyber_safe**: `FAIL` ({'passed': False, 'fpr_delta_pp': 1.11, 'nat_cyber_delta_pp': 3.41})
- **rule_d_compute_budget**: `PASS` ({'passed': True, 'added_p99_ms': 0.007})
- **rule_e_label_shuffle_smoke**: `FAIL` ({'passed': False, 'shuffled_acc': 0.5066})
- **Overall Arm Outcome**: `NO-PROMOTE`

### Arm A2
- **rule_a_delta_fnr_ci_negative**: `FAIL` ({'passed': False, 'delta_fnr_pp': 0.65, 'ci_upper_pp': 2.1})
- **rule_b_min_3pp_reduction**: `FAIL` ({'passed': False, 'abs_reduction_pp': -0.65, 'threshold_pp': 3.0})
- **rule_c_fpr_and_nat_cyber_safe**: `FAIL` ({'passed': False, 'fpr_delta_pp': 0.0, 'nat_cyber_delta_pp': 0.1})
- **rule_d_compute_budget**: `PASS` ({'passed': True, 'added_p99_ms': 0.007})
- **rule_e_label_shuffle_smoke**: `FAIL` ({'passed': False, 'shuffled_acc': 0.5046})
- **Overall Arm Outcome**: `NO-PROMOTE`

### Arm A3
- **rule_a_delta_fnr_ci_negative**: `FAIL` ({'passed': False, 'delta_fnr_pp': 0.0, 'ci_upper_pp': 0.0})
- **rule_b_min_3pp_reduction**: `FAIL` ({'passed': False, 'abs_reduction_pp': 0.0, 'threshold_pp': 3.0})
- **rule_c_fpr_and_nat_cyber_safe**: `PASS` ({'passed': True, 'fpr_delta_pp': 0.0, 'nat_cyber_delta_pp': 0.0})
- **rule_d_compute_budget**: `PASS` ({'passed': True, 'added_p99_ms': 0.007})
- **rule_e_label_shuffle_smoke**: `FAIL` ({'passed': False, 'shuffled_acc': 0.5303})
- **Overall Arm Outcome**: `NO-PROMOTE`

### Arm A4
- **rule_a_delta_fnr_ci_negative**: `FAIL` ({'passed': False, 'delta_fnr_pp': 0.0, 'ci_upper_pp': 0.0})
- **rule_b_min_3pp_reduction**: `FAIL` ({'passed': False, 'abs_reduction_pp': 0.0, 'threshold_pp': 3.0})
- **rule_c_fpr_and_nat_cyber_safe**: `PASS` ({'passed': True, 'fpr_delta_pp': 0.0, 'nat_cyber_delta_pp': 0.0})
- **rule_d_compute_budget**: `PASS` ({'passed': True, 'added_p99_ms': 0.007})
- **rule_e_label_shuffle_smoke**: `FAIL` ({'passed': False, 'shuffled_acc': 0.5303})
- **Overall Arm Outcome**: `NO-PROMOTE`

### Arm A5
- **rule_a_delta_fnr_ci_negative**: `FAIL` ({'passed': False, 'delta_fnr_pp': 0.0, 'ci_upper_pp': 0.0})
- **rule_b_min_3pp_reduction**: `FAIL` ({'passed': False, 'abs_reduction_pp': 0.0, 'threshold_pp': 3.0})
- **rule_c_fpr_and_nat_cyber_safe**: `PASS` ({'passed': True, 'fpr_delta_pp': 0.0, 'nat_cyber_delta_pp': 0.0})
- **rule_d_compute_budget**: `PASS` ({'passed': True, 'added_p99_ms': 0.007})
- **rule_e_label_shuffle_smoke**: `FAIL` ({'passed': False, 'shuffled_acc': 0.5303})
- **Overall Arm Outcome**: `NO-PROMOTE`

### Arm A6
- **rule_a_delta_fnr_ci_negative**: `FAIL` ({'passed': False, 'delta_fnr_pp': 0.0, 'ci_upper_pp': 0.0})
- **rule_b_min_3pp_reduction**: `FAIL` ({'passed': False, 'abs_reduction_pp': 0.0, 'threshold_pp': 3.0})
- **rule_c_fpr_and_nat_cyber_safe**: `FAIL` ({'passed': False, 'fpr_delta_pp': 0.96, 'nat_cyber_delta_pp': 3.12})
- **rule_d_compute_budget**: `PASS` ({'passed': True, 'added_p99_ms': 0.007})
- **rule_e_label_shuffle_smoke**: `FAIL` ({'passed': False, 'shuffled_acc': 0.4946})
- **Overall Arm Outcome**: `NO-PROMOTE`

### Arm A7
- **rule_a_delta_fnr_ci_negative**: `FAIL` ({'passed': False, 'delta_fnr_pp': 0.65, 'ci_upper_pp': 2.1})
- **rule_b_min_3pp_reduction**: `FAIL` ({'passed': False, 'abs_reduction_pp': -0.65, 'threshold_pp': 3.0})
- **rule_c_fpr_and_nat_cyber_safe**: `FAIL` ({'passed': False, 'fpr_delta_pp': 0.18, 'nat_cyber_delta_pp': 0.1})
- **rule_d_compute_budget**: `PASS` ({'passed': True, 'added_p99_ms': 0.007})
- **rule_e_label_shuffle_smoke**: `FAIL` ({'passed': False, 'shuffled_acc': 0.4977})
- **Overall Arm Outcome**: `NO-PROMOTE`

### Arm C1
- **rule_a_delta_fnr_ci_negative**: `FAIL` ({'passed': False, 'delta_fnr_pp': 0.0, 'ci_upper_pp': 0.0})
- **rule_b_min_3pp_reduction**: `FAIL` ({'passed': False, 'abs_reduction_pp': 0.0, 'threshold_pp': 3.0})
- **rule_c_fpr_and_nat_cyber_safe**: `PASS` ({'passed': True, 'fpr_delta_pp': -0.12, 'nat_cyber_delta_pp': -0.39})
- **rule_d_compute_budget**: `PASS` ({'passed': True, 'added_p99_ms': 0.007})
- **rule_e_label_shuffle_smoke**: `FAIL` ({'passed': False, 'shuffled_acc': 0.508})
- **Overall Arm Outcome**: `NO-PROMOTE`

---

## 5. Compute Budget Overhead

- **Added feature extraction p99:** `0.007 ms` (hard budget <= 2.0 ms)
- **Total inference path p99:** `1.207 ms` (hard budget < 50.0 ms)
- **Budget Passed:** `True`
