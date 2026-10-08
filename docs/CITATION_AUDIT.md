# GridSentinel Citation Integrity Audit & Manifest

**Audit Date:** 2026-10-08  
**Auditor:** Codex / Antigravity pair programmer  
**Network Status:** **NETWORK AVAILABLE** (Landing pages and publisher DOIs fetched and verified directly)

---

## 1. External Verification of Canonical References (R1–R6)

Each canonical reference was verified by resolving its public registry / publisher landing page:

| Ref ID | Identifier / URL | Registry / Source | Online Title / Official Notice | Verification Result |
|:---|:---|:---|:---|:---:|
| **R1** | Gazette Notification dated 31 July 2026 | *Gazette of India*, Part III, Section 4 | Central Electricity Authority (Cyber Security in Power Sector) Regulations, 2026 (issued under Sec 177 / 73(c), effective 1 April 2027) | **VERIFIED** |
| **R2** | `10.1109/TPWRS.2018.2829021` | IEEE Xplore / *IEEE Transactions on Power Systems* | "pandapower — An Open-Source Python Tool for Convenient Modeling, Analysis, and Optimization of Electric Power Systems" (Thurner et al., 2018) | **VERIFIED** |
| **R3** | `arXiv:2306.00234` | arXiv.org (cs.CR) | "Implementing Man-in-the-Middle Attack to Investigate Network Vulnerabilities in Smart Grid Test-bed" (Accepted at 2023 IEEE AIIoT) | **VERIFIED** |
| **R4** | `arXiv:2003.02229` | arXiv.org (eess.SY) | "Detection of False Data Injection Attacks Using the Autoencoder Approach" (Wang, Tindemans, Pan, Palensky, 2020) | **VERIFIED** |
| **R5** | Proc. ICCSP '17, ACM | ACM Digital Library / ResearchGate | "Real-Time Intrusion Detection Method Based on Bidirectional Access of Modbus/TCP Protocol" (Xin, Liu, Wang, 2017) | **VERIFIED** |
| **R6** | MSU/ORNL Testbed (2014) | Mississippi State University HPC / ORNL | Mississippi State University / Oak Ridge National Laboratory, Power System Attack Datasets (2014): hardware-in-the-loop RTDS testbed, 4 PMUs, 37 labeled event scenarios | **VERIFIED** (Dataset level) |
| **R7** | 2019 Springer Nature / Science China Press | Springer / Science China Press | Review of false data injection attacks against smart grid state estimation (Exact title, authors, DOI not confirmed) | **UNVERIFIED-PENDING** |

---

## 2. Source-Attributed Claims & Evidence Status

### A. MSU / ORNL Dataset Claims
- **Repo Investigation:** Scanned `backend/data/` for `data/msu_ornl/` or benchmark CSV outputs. No benchmark dataset files or stored result files exist in this repository.
- **Rule Applied:** Reworded claims in `backend/README.md` and docstrings in `backend/app/ml/msu_ornl_loader.py` to:  
  *"Feature categories informed by the MSU/ORNL Power System Attack Datasets (2014); GridSentinel has not been benchmarked on this dataset in this repository."*
- **Reference Kept:** R6 kept as canonical reference for taxonomy and feature category inspiration.

### B. Autoencoder Claims
- **Model Architecture in Repo:** Inspected `backend/models/fusion_classifier.joblib` and `backend/app/ml/train_classifier.py`.
  - Primary Triage (Stage 1): **XGBoost** (tree-based gradient boosted ensemble)
  - Forensic Subtyping (Stage 2): **Random Forest** (tree-based bagging ensemble)
- **Autoencoder Usage:** GridSentinel **does not** use autoencoders. Classifier is entirely tree-based.
- **Repository Audit:** Searched codebase for any claim implying GridSentinel uses autoencoders. Found **zero** occurrences. R4 is designated as related literature only.

### C. Metric Claims
All reported core performance metrics were audited against repository source files and benchmark logs:
- **90.77% Overall Accuracy:** Backed by `backend/reports/metrics.json` (`overall_accuracy: 0.9077`) produced by `backend/app/ml/train_classifier.py` on held-out `backend/data/generated/test_dataset_seed1337.csv`. Confirmed independently by `backend/verify_recall.py` (90.7714%). **[BACKED]**
- **0.43% False Positive Rate:** Backed by `backend/reports/metrics.json` (`cyber_intrusion_fpr: 0.0043`, 14 / 3,236 non-cyber ticks) and `backend/verify_recall.py` (0.4326%). **[BACKED]**
- **2.6 ms Latency:** Backed by `backend/reports/metrics.json` (`latency_ms_per_verdict: 2.617`, `latency_ms: 2.617`), benchmarked via 1,000 timed evaluations in `backend/app/ml/train_classifier.py`. **[BACKED]**

---

## 3. Comprehensive Citation & Reference Manifest

| Source text | File:line | Canonical match | Action taken | Status |
|:---|:---|:---:|:---|:---:|
| `Central Electricity Authority (Cyber Security in Power Sector) Regulations, 2026` | `frontend/data/compliance-mapping.ts:23` | R1 | Confirmed matches canonical R1; added canonical citation in file header | **CANONICAL** |
| `gazetteDate: "31 July 2026"` | `frontend/data/compliance-mapping.ts:24` | R1 | Confirmed matches canonical R1 gazette notification date | **CANONICAL** |
| `legalBasis: "Section 177 read with Section 73(c), Electricity Act 2003"` | `frontend/data/compliance-mapping.ts:25` | R1 | Confirmed matches canonical R1 statutory basis | **CANONICAL** |
| `effectiveDate: "1 April 2027 (general provisions)"` | `frontend/data/compliance-mapping.ts:26` | R1 | Confirmed matches canonical R1 general effective date | **CANONICAL** |
| `CEA-2026 Cyber Security Regulations Compliance Matrix` | `frontend/components/ComplianceMap.tsx:40` | R1 | UI header representing statutory compliance panel; verified consistent with R1 | **CANONICAL** |
| `GAZETTE NOTIFICATION` | `frontend/components/ComplianceMap.tsx:68` | R1 | UI metadata tag displaying gazette date from CEA_2026_FACTS | **CANONICAL** |
| `CEA-2026 Incident Audit Trail Log` | `frontend/components/AuditLog.tsx:194` | R1 | UI label mapping incident log to CEA-2026 compliance reporting window | **CANONICAL** |
| `CEA-2026 Cyber-Physical Incident Audit Trail` | `frontend/README.md:20` | R1 | Documentation describing incident audit trail adhering to CEA-2026 | **CANONICAL** |
| `CEA-2026 Compliance Panel: Print-friendly compliance matrix...` | `frontend/README.md:40` | R1 | Documentation describing statutory compliance panel | **CANONICAL** |
| `Paragraph("CEA-2026 operational reference · advisory incident record", subtitle)` | `backend/app/audit_report.py:110` | R1 | Incident report PDF subtitle referencing CEA-2026 statutory advisory framework | **CANONICAL** |
| `Verified compliance-mapping.ts contains strictly verified CEA-2026 facts` | `VERIFICATION_REPORT.md:22` | R1 | Verification report item documenting CEA-2026 factual accuracy | **CANONICAL** |
| `PCD: Newton-Raphson power flow & WLS state estimation... in pandapower` | `README.md:11` | R2 | Refers to pandapower tool; canonical reference R2 added to `docs/REFERENCES.md` | **CANONICAL** |
| `pandapower Physics (Ground Truth Model)` | `backend/README.md:21` | R2 | Architecture diagram reference to pandapower physics simulation | **CANONICAL** |
| `Built entirely on open-source tooling (pandapower, FastAPI, Next.js)` | `frontend/data/compliance-mapping.ts:50` | R2 | Feeder software stack reference | **CANONICAL** |
| `## 10. External Dataset Reference: MSU/ORNL ICS Dataset` | `backend/README.md:351` | R6 | Reworded heading from "External Benchmark" to "External Dataset Reference" | **REPLACED** |
| `GridSentinel includes app/ml/msu_ornl_loader.py for coarse feature alignment...` | `backend/README.md:353` | R6 | Reworded to state feature categories informed by dataset; GridSentinel not benchmarked in repo | **REPLACED** |
| `The MSU/ORNL dataset captures Modbus TCP traffic...` | `backend/README.md:355` | R6 | Replaced with exact canonical reference R6 and category mapping description | **REPLACED** |
| `Loader and mapper for the Mississippi State University / Oak Ridge National Laboratory...` | `backend/app/ml/msu_ornl_loader.py:4` | R6 | Module docstring updated with canonical reference R6 | **REPLACED** |
| `Validation against MSU/ORNL datasets serves as a coarse sanity check...` | `backend/app/ml/msu_ornl_loader.py:13` | R6 | Reworded to clarify feature categories informed by dataset without benchmarking claim | **REPLACED** |
| `Evaluate how the trained model's logic holds up against mapped MSU/ORNL data.` | `backend/app/ml/msu_ornl_loader.py:115` | R6 | Function docstring reworded to reflect category mapping without benchmark claim | **REPLACED** |
| `- ML Pipeline: ... msu_ornl_loader.py ...` | `VERIFICATION_REPORT.md:35` | R6 | File listing in verification report; retained | **CANONICAL** |
| `from a 15-bus transmission system (IEEE 9-bus or 39-bus with PMU/relay telemetry)` | `backend/app/ml/msu_ornl_loader.py:15` | none | Retained as technical engineering context for standard IEEE test transmission feeders | **UNVERIFIED** |
| `11kV bus voltages should stay within ±10% (0.90–1.10 pu) per CEA standards.` | `backend/tests/test_feeder.py:100` | none | Retained as CEA statutory grid code distribution voltage limits | **UNVERIFIED** |
| `Bus {bus_idx} voltage {vm:.4f} pu outside CEA statutory limits` | `backend/tests/test_feeder.py:105` | none | Retained as CEA statutory grid code distribution voltage limits | **UNVERIFIED** |
| `90.77% overall accuracy, 0.43% cyber FPR` | `VERIFICATION_REPORT.md:16` | none | Verified metric backed by `metrics.json` and `test_dataset_seed1337.csv` | **CANONICAL** |
| `Overall Accuracy: 0.9077 (90.77%)` | `VERIFICATION_REPORT.md:75` | none | Verified metric backed by `metrics.json` and `train_classifier.py` | **CANONICAL** |
| `Cyber Intrusion False Positive Rate: 0.0043 (0.43%)` | `VERIFICATION_REPORT.md:76` | none | Verified metric backed by `metrics.json` and `verify_recall.py` | **CANONICAL** |
| `| **Overall Accuracy** | **90.77%** |` | `backend/README.md:153` | none | Verified metric backed by `metrics.json` and `verify_recall.py` | **CANONICAL** |
| `| **Cyber Intrusion FPR** | **0.43%** (14 / 3,236 non-cyber ticks) |` | `backend/README.md:154` | none | Verified metric backed by `metrics.json` and `verify_recall.py` | **CANONICAL** |
| `The ultra-low FPR of 0.43% is the key operational achievement...` | `backend/README.md:161` | none | Verified metric backed by `metrics.json` and `verify_recall.py` | **CANONICAL** |
| `"latency_ms_per_verdict": 2.617` | `backend/reports/metrics.json:12` | none | Verified metric backed by 1,000 timed evaluations in `train_classifier.py` | **CANONICAL** |
| `2019 review of false data injection attacks against smart grid state estimation` | `docs/REFERENCES.md:9` | R7 | Listed as pending external verification; tag applied | **UNVERIFIED-PENDING** |

---

## 4. Summary Status Counts

- **CANONICAL:** 22
- **REPLACED:** 6
- **UNVERIFIED:** 3
- **UNVERIFIED-PENDING:** 1
- **UNBACKED:** 0 (All metrics backed by reproducible scripts and output files)
- **Total Audited Hits:** 32
