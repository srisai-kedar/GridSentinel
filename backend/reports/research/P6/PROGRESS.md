# P6 progress

| Item | Command/result |
|---|---|
| Branch | `research/P6` |
| Protocol | `git commit 5835505 -- backend/reports/research/P6/PROTOCOL.md` before generation |
| Focused tests | `pytest -q tests/test_p6_train_v2.py tests/test_p6_test_lock.py` → 8 passed |
| Fresh generation | `python -m scripts.expo.train_v2 --ticks 10 --out experiments/P6` → 25 fresh run CSVs, then validation-only grouped selection completed |
| Full backend suite | Collection stopped with 6 pre-existing import errors in unrelated GSBP tests; see `full_pytest.txt` |
| Production model SHA-256 | Before/after: `EE5211510E41EDDAC32ED1EED405AF982A0A550BD0B75E8867253135B812CCAE` |
| Frozen metrics SHA-256 | Before/after: `601F6D6ADE33D4F870511C5857ACC6042F992BB2C058C78603EE065661ADAA79` |

No final held-out evaluation was run.
