# P0 Findings

Generated from `p0_evidence.json`; numerical values are read from run artifacts.

## Supported

- Same-seed reproducibility: labels equal = `True`; non-timing columns identical = `True` across `25` rows.
- Timing-affected columns and measured maximum absolute differences: `{"nbd_mean_response_time_ms": {"max_absolute_difference": 87.55799999999999, "rows_different": 25}, "nbd_std_response_time_ms": {"max_absolute_difference": 73.00299999999999, "rows_different": 25}}`.
- Concurrent isolation: `4` of `4` processes completed with distinct port bases; see `concurrency_smoke.json`.
- Clean-mode smoke run: `100` ticks, `500` rows, labels `{"Natural Fault": 115, "Normal": 385}`; labelled attack scenarios present = `False`.
- Each completed generator output has a `run_manifest.json` containing git SHA, Python/package versions, CPU, arguments, seeds, timestamps, throughput, and dataset SHA-256.

## Not supported

- The required clean run of `5000` ticks was completed = `False`.
- A pinned container image digest was recorded = `False`.
- The full backend suite is green: `1 failed, 321 passed`.

## Unresolved

- The clean-mode acceptance run was not completed in this environment; the measured smoke run demonstrates mode behaviour but is not a substitute.
- Docker CLI is present, but the daemon/image store was unavailable; no container digest could be verified.
- Real socket and simulator timing remain nondeterministic. The timing columns are documented rather than forced to bitwise equality.
- The existing citation-lint failure remains a pre-existing baseline failure and was not edited.

## Evidence

- `repro_check.json`
- `concurrency_smoke.json`
- `throughput.csv`
- `container_image_digest.json`
- `manifest_schema.json`
- `clean_smoke/run_manifest.json`
