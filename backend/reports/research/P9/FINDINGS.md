# P9 findings

All dataset counts and readiness values below are rendered from `taxonomy_readiness.json`; no metric is hand-entered.

## Supported

- Readiness status: `BLOCKED`.
- The current drift-rule source audit found concentration comparison present=True and the old always-true key-presence clause present=False.
- Non-held-out inputs inspected: 25 P6 train/validation files; scenario-parameter records parsed=1250.
- Observed FDI sigma values: `[2, 10]`. Observed drift modes: `['step']`.

## Not supported

- The required 5×5 episode confusion matrix was not computed. `confusion.csv` is an empty schema only; filling it would fabricate results.
- No learned four-class model was trained because the required magnitude-by-profile study and independent held-out runs are not available.
- No drift-versus-FDI indistinguishability region can be claimed from the existing random/sparse scenarios.
- Full backend suite: 390 passed, 1 failed, 522 warnings in 120.65s (0:02:00). The known citation-lint baseline failure remains the only allowed failure.

## Unresolved

- Missing required FDI sigma values: `[1, 3, 5, 25]`.
- Missing required drift profiles: `['gain_error', 'noise_increase', 'ramp', 'stuck_at']`.
- The production drift rule still has hard-coded thresholds in the currently modified application file. The concentration tautology is corrected in the current working tree, but a validation-frozen configuration layer has not been introduced because that file contains pre-existing user changes and the targeted study is blocked.
- Required next data: a fresh, capture-separated validation and held-out corpus covering the same magnitudes and temporal profiles for drift and FDI, plus natural-fault and benign-event runs.

## Evidence paths

- Machine audit: `experiments\P9\taxonomy_readiness.json`
- Confusion schema: `reports\research\P9\confusion.csv`
- Run manifest: `reports\research\P9\run_manifest.json`
