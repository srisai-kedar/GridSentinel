"""P12 passive-observation equivalence harness.

The parser is deliberately delegated to ``adapt_modbus_pcap.py``.  This task
does not install a capture dependency or change the production traffic logger.
It records the local capture-tool probe and produces a machine-readable gap
report when an elevated loopback capture is unavailable.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from importlib import metadata
from pathlib import Path
from typing import Any, Iterable

try:
    from scripts.adapt_modbus_pcap import iter_modbus_events
except ModuleNotFoundError:  # direct execution with backend/scripts on sys.path
    from adapt_modbus_pcap import iter_modbus_events


COMMON_FIELDS = (
    "function_code",
    "response_matched",
    "success",
    "transaction_id",
    "unit_id",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git_sha(repo: Path) -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()


def package_versions() -> dict[str, str]:
    values: dict[str, str] = {}
    for name in ("numpy", "pandas", "pandapower", "pymodbus"):
        try:
            values[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            pass
    return values


def pytest_summary(path: Path | None) -> str:
    if path is None or not path.exists():
        return "not run by this command"
    text = path.read_text(encoding="utf-8", errors="replace")
    passed = re.findall(r"(\d+) passed", text)
    failed = re.findall(r"(\d+) failed", text)
    return f"{passed[-1] if passed else '0'} passed, {failed[-1] if failed else '0'} failed (raw output: {path})"


def function_name(function_code: int | None) -> str | None:
    names = {
        1: "READ_COILS",
        2: "READ_DISCRETE_INPUTS",
        3: "READ_HOLDING_REGISTERS",
        4: "READ_INPUT_REGISTERS",
        5: "WRITE_SINGLE_COIL",
        6: "WRITE_SINGLE_REGISTER",
        15: "WRITE_MULTIPLE_COILS",
        16: "WRITE_MULTIPLE_REGISTERS",
    }
    return names.get(function_code) if function_code is not None else None


def normalize_capture_event(event: dict[str, Any]) -> dict[str, Any]:
    """Map adapter output to the logger's comparable event vocabulary.

    Passive traffic cannot establish the RTU observer token or authorization;
    those fields are therefore explicitly false, never inferred from a write.
    """
    code = int(event["function_code"]) if event.get("function_code") is not None else None
    return {
        "timestamp": event.get("timestamp_utc"),
        "source": event.get("source_ip"),
        "target_rtu": event.get("target_rtu", "UNMAPPED"),
        "function_code": code,
        "function_name": function_name(code),
        "response_time_ms": event.get("response_time_ms"),
        "is_unexpected_write": False,
        "observer_verified": False,
        "success": event.get("success"),
        "transaction_id": event.get("transaction_id"),
        "unit_id": event.get("unit_id"),
        "response_matched": bool(event.get("response_matched", False)),
        "passive_capture_provenance": True,
    }


def compare_event_sequences(tap_events: Iterable[dict[str, Any]], capture_events: Iterable[dict[str, Any]], timing_tolerance_ms: float = 2.0) -> dict[str, Any]:
    """Compare already aligned event records without claiming alignment exists."""
    tap = list(tap_events)
    capture = list(capture_events)
    comparisons: dict[str, Any] = {
        "tap_event_count": len(tap),
        "capture_event_count": len(capture),
        "aligned_event_count": min(len(tap), len(capture)),
        "timing_tolerance_ms": timing_tolerance_ms,
        "feature_agreement": {},
        "timing_bias_ms": None,
        "alignment_method": "positional only; production capture run required before interpretation",
    }
    aligned = min(len(tap), len(capture))
    for field in COMMON_FIELDS:
        if aligned == 0:
            comparisons["feature_agreement"][field] = None
        else:
            equal = sum(tap[index].get(field) == capture[index].get(field) for index in range(aligned))
            comparisons["feature_agreement"][field] = {"matches": equal, "aligned": aligned, "fraction": equal / aligned}
    tap_times = [float(row["response_time_ms"]) for row in tap[:aligned] if row.get("response_time_ms") is not None]
    capture_times = [float(row["response_time_ms"]) for row in capture[:aligned] if row.get("response_time_ms") is not None]
    if tap_times and capture_times and len(tap_times) == len(capture_times):
        comparisons["timing_bias_ms"] = sum(c - t for t, c in zip(tap_times, capture_times)) / len(tap_times)
        comparisons["timing_within_tolerance"] = sum(abs(c - t) <= timing_tolerance_ms for t, c in zip(tap_times, capture_times)) / len(tap_times)
    return comparisons


def probe_capture_tool() -> dict[str, Any]:
    executable = shutil.which("pktmon")
    if executable is None:
        return {"tool": "pktmon", "available": False, "status": "blocked", "error": "pktmon executable not found"}
    completed = subprocess.run([executable, "status"], capture_output=True, text=True, check=False)
    output = (completed.stdout + completed.stderr).strip()
    return {
        "tool": "pktmon",
        "executable": executable,
        "available": True,
        "status_command_returncode": completed.returncode,
        "status_output": output,
        "capture_ready": completed.returncode == 0 and "access is denied" not in output.lower(),
        "status": "ready" if completed.returncode == 0 and "access is denied" not in output.lower() else "blocked",
    }


def write_outputs(repo: Path, result: dict[str, Any], out_dir: Path, report_dir: Path, args: argparse.Namespace, start: str, end: str) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)
    result_path = out_dir / "p12_results.json"
    result_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    report_path = report_dir / "FINDINGS.md"
    manifest_path = out_dir / "run_manifest.json"
    input_paths = [
        repo / "backend/scripts/adapt_modbus_pcap.py",
        repo / "backend/app/ot/traffic_logger.py",
        repo / "backend/app/ot/rtu_server.py",
    ]
    suite_path = Path(args.pytest_output) if args.pytest_output else None
    output_paths = [result_path, report_path]
    if suite_path is not None and suite_path.exists():
        output_paths.append(suite_path)
    manifest = {
        "task": "P12",
        "git_sha": git_sha(repo),
        "python": sys.version,
        "packages": package_versions(),
        "cpu_model": platform.processor(),
        "cli_arguments": vars(args),
        "seeds": {},
        "start_time_utc": start,
        "end_time_utc": end,
        "input_sha256": {str(path): sha256(path) for path in input_paths},
        "output_sha256": {str(path): sha256(path) for path in output_paths},
        "test_set_read": False,
        "pytest_summary": pytest_summary(suite_path),
    }
    lines = [
        "# P12 findings",
        "",
        "All numeric values in this report are generated by the committed P12 harness. No production capture, model, or held-out dataset was modified or read.",
        "",
        "## Supported",
        "",
        "- The passive parser delegates to the existing tested `adapt_modbus_pcap.py` implementation rather than duplicating packet parsing.",
        "- Passive records explicitly set `observer_verified=false` and `is_unexpected_write=false`; a write seen on the wire is not treated as an authorized/unauthorized ground-truth event.",
        "- The event-comparison function and capture-tool probe are covered by focused tests.",
        f"- Full backend suite result: {pytest_summary(suite_path)}.",
        "",
        "## Not supported",
        "",
        f"- Real loopback capture was not completed: PktMon probe status is `{result['capture_probe']['status']}`.",
        "- No per-feature agreement, timing bias/tolerance result, capture-only command-injection recall, or with/without-hook response/throughput comparison is reported.",
        "- The intended acceptance claim would be loopback capture on the same host, not a mirrored production network; no such capture was available in this run.",
        "",
        "## Unresolved",
        "",
        "- An elevated Windows capture session is required to run PktMon against the simulator's loopback Modbus ports and convert the ETL to PCAPNG.",
        "- The capture run must align RTU-side tap events and packet-derived requests by transaction ID, unit ID, function code, and capture time before any agreement metric is interpreted.",
        "- A valid overhead study requires paired simulator runs with the trace hook enabled and disabled under the same scenario schedule and timing controls.",
        "",
        "## Evidence paths",
        "",
        f"- Results: `{result_path}`",
        f"- Manifest: `{manifest_path}`",
        f"- Focused report: `{report_path}`",
        "",
        "## Reproduction",
        "",
        f"`backend/.venv/Scripts/python.exe backend/scripts/expo/p12_passive_observation.py --out-dir {args.out_dir} --report-dir {args.report_dir}`",
    ]
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    manifest["output_sha256"] = {str(path): sha256(path) for path in output_paths}
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", default="backend/experiments/P12")
    parser.add_argument("--report-dir", default="backend/reports/research/P12")
    parser.add_argument("--capture", type=Path, default=None)
    parser.add_argument("--pytest-output", default="")
    args = parser.parse_args()
    if args.capture is not None and not args.capture.exists():
        raise FileNotFoundError(args.capture)
    start = datetime.now(timezone.utc).isoformat()
    repo = Path(__file__).resolve().parents[3]
    capture_summary: dict[str, Any] = {"status": "not_run", "events": []}
    if args.capture is not None:
        events, summary = iter_modbus_events(args.capture, include_unmatched=True)
        capture_events = [normalize_capture_event(event) for event in events]
        capture_summary = {"status": "parsed", "summary": summary, "events": capture_events[:200], "truncated": len(capture_events) > 200}
    result = {
        "capture_probe": probe_capture_tool(),
        "capture": capture_summary,
        "comparison": compare_event_sequences([], capture_summary.get("events", [])),
        "overhead": {"status": "blocked", "reason": "No paired live loopback capture and trace-hook-disabled control run."},
    }
    end = datetime.now(timezone.utc).isoformat()
    write_outputs(repo, result, repo / args.out_dir, repo / args.report_dir, args, start, end)


if __name__ == "__main__":
    main()
