.PHONY: repro

repro:
	backend/.venv/Scripts/python.exe scripts/repro_check.py
	backend/.venv/Scripts/python.exe scripts/concurrency_smoke.py
