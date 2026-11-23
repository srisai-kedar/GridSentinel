# P0-P12 Completion Findings

## Supported

- P0 measured `5000` clean ticks and `25000` rows with zero attack-active rows.
- P3 measured `40` seed files and `1250` train/validation rows across `25` runs.
- P6 executed `60` model/arm/policy result rows across the recorded model families and feature arms.

## Not supported

- P8, P9, P11 and P12 do not satisfy their original acceptance criteria because required exposure, scenario coverage, independent topology/data, or capture infrastructure is unavailable.
- P2 cannot reproduce the historical pre-PR16 comparison without the original scratch checkout and inputs.
- P6 validation results do not establish generalization or production improvement.

## Unresolved

- Obtain the exact P8 clean exposure, P9 scenario grid, P11 second feeder/OOD evaluation inputs, and elevated P12 packet-capture capability.
- Resolve the P10 13-versus-15 RTU-reported measurement contract before interpreting the frontier as production evidence.

## Task status table

- `P0`: **PASS_WITH_LIMITATION** — 5,000-tick clean run, prior reproducibility and concurrency evidence; Docker digest unavailable.
- `P2`: **PARTIAL** — Static provenance, blind re-extraction and canary evidence are present; fresh historical pre-PR16 checkout is unavailable.
- `P3`: **PASS_FOR_SEED_COVERAGE** — All configured train/validation/OOD/clean seed outputs exist at the recorded tick count.
- `P6`: **PASS_FOR_ISOLATED_VALIDATION** — All prescribed arms and available model families executed on train/validation only; no held-out evaluation.
- `P7`: **PARTIAL** — Pilot final comparison exists, but independent exposure and statistical power are insufficient for production claims.
- `P8`: **BLOCKED** — Required 24-hour real-clock clean validation and independent clean held-out exposure are not available.
- `P9`: **BLOCKED** — Required magnitude/profile grid and benign/natural-fault corpus are not available.
- `P10`: **PARTIAL** — Jacobian diagnostic exists, but the 13-versus-15 measurement contract is unresolved and traffic is unchanged.
- `P11`: **BLOCKED** — Second feeder and authorized cross-condition/cross-topology held-out evaluation are unavailable.
- `P12`: **BLOCKED** — Elevated Windows packet capture infrastructure is unavailable; no simulated substitute was used.
