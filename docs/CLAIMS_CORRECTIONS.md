# GridSentinel claims corrections

This document records claims in `docs/GridSentinel_doc.txt` that are contradicted or unsupported by the corrected T1/T2 evidence. The figures below are measured or computed from the cited artifacts; they are not production-promotion claims.

| Existing claim or wording | Correction | Source |
|---|---|---|
| 22/22 Cyber episodes; older 22-episode held-out result | The corrected test has 17 global Cyber episodes, detected 17/17 by the raw candidate and selected latch. The older 22-episode file has different class counts and is not like-for-like. | `backend/reports/expo/t1_corrected_candidate/followup_counts.json`; `t2_decoupled_rule_20261027_v2.json` |
| 52.65% recall and 0.43% Cyber FPR as the corrected result | Corrected raw candidate: 112 TP, 1 FP, 92 FN, 3,104 TN; recall 54.90%, precision 99.12%, primary FPR 0.0322%. | `backend/reports/expo/t1_corrected_candidate/followup_counts.json` |
| FDI/replay/command recalls 73.81% / 46.88% / 38.10% | Corrected top-level detection recall is FDI 40/47 = 85.11%, replay 39/67 = 58.21%, command injection 33/90 = 36.67%. | `backend/reports/expo/t1_corrected_candidate/reconciliation_t2.json` |
| Sensor-drift test cell absent or not evaluated | The corrected test contains 191 Sensor Malfunction rows in 16 episodes. With the decoupled live-feature rule, the candidate and 28-feature production model both fire the drift rule on 119/191 readings and all 16/16 episodes; the production model still does not consume the nine extra fields in its classifier vector. | `backend/reports/expo/t1_corrected_candidate/t2_decoupled_rule_20261027_v2.json` |
| 8 false-alarm episodes in 436 seconds or similar low false-alarm wording | On the corrected 700-second test, raw primary false alarms are 1 episode, 5.14/hour (Poisson 95%: 0.13–28.65). The selected 2-of-3/M=4 latch has 23 primary episodes; after the four-second hold-tail grace, 12 genuine episodes remain, 61.71/hour (31.89–107.80). | `backend/reports/expo/t1_corrected_candidate/tail_reconciliation.json` |
| The 56 zero-write command rows are explained by the 30-record window aging out | Not established. They occur 3–17 ticks after onset and none is at least 30 ticks old. The implementation uses 30 global records, approximately six ticks × five RTU polls, not 30 seconds per RTU. | `backend/reports/expo/t1_corrected_candidate/t2_decoupled_rule_20261027_v2.json`; `backend/app/ml/dataset_generator.py:149,168-176` |

## Replacement wording for presentations

“On the corrected synthetic test split, the isolated candidate detected all 17 global Cyber episodes, with 54.90% per-reading Cyber recall and 0.0322% primary false-positive rate. These results are not independent-site validation and do not establish production improvement.”

“The live deterministic drift rule now uses the full feature dictionary computed by the feature extractor, while the frozen production classifier remains on its protected 28-feature schema. On the corrected test, it identified 119/191 drift readings and 16/16 drift episodes, with zero rule fires on FDI, replay, command-injection, natural-fault, and normal rows.”
