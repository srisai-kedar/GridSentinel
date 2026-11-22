# P4 Findings

## Supported

- A registry-backed scenario library is present with parameterized FDI, replay, command-injection, breaker-open, sustained-setpoint, natural-fault, drift, load-step, authorized-write, and communication-stall definitions.
- Breaker-open uses the real command-write path and then changes pandapower line service state; natural line trips change only physical state and do not emit a write.
- Authorized control writes use an explicit allow-listed source and remain non-unexpected; communication stalls emit failed polls while replay leaves polling available.
- Registry smoke summary produced by the script: `{"class_counts": {"Cyber Intrusion": 23, "Normal": 177}, "rows": 200, "scenario_columns_present": true, "scenario_types": ["Cyber Intrusion", "Normal"], "subtype_counts": {"breaker_open": 6, "normal": 177, "replay": 17}}`.

## Not supported

- No model was trained, tuned, selected, or evaluated in P4.
- The short smoke run does not establish scenario coverage for every registry entry or any detector performance claim.

## Unresolved

- The generator scheduler is registry-driven for the configured regimes, but targeted generation of all parameter combinations and all seed bands remains a later workload.
- Full physical validation of breaker-open and sustained-setpoint behavior still depends on live RTU-server execution; unit tests verify the state transition and write-path invocation without changing production artifacts.

## Test result

- Backend suite summary: `1 failed, 365 passed, 523 warnings`; the known citation-lint baseline failure, if present, is unchanged.
