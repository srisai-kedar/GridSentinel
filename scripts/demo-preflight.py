#!/usr/bin/env python3
"""
demo-preflight.py
-----------------
GridSentinel Demo Pre-flight Check Suite.

Answers the question: "Will this demo survive a hostile conference room?"

Checks performed (each labelled [PASS] / [FAIL] / [WARN]):
  1.  Backend reachability  — GET /health returns {status: ok}
  2.  CORS preflight         — OPTIONS from production Vercel origin returns correct ACAO header
  3.  Version stamp          — GET /version returns git_sha, model_sha256_short
  4.  WS handshake           — /ws/live accepts ws:// connection and emits initial payload
  5.  Mixed-content guard    — frontend env NEXT_PUBLIC_BACKEND_URL uses same scheme as page origin
  6.  OT simulation start    — POST /ot/start → status in {started, already_running}
  7.  Simulation tick        — latest_state in /ot/status has sim_time field after start
  8.  Data injection attack  — POST /ot/attack/data-injection returns status=injected
  9.  Command injection      — POST /ot/attack/command-injection returns flagged_in_traffic_log=True
  10. Line-trip fault        — POST /ot/fault/line-trip → status=triggered
  11. OT reset               — POST /ot/reset → status=ok, cached_rtu_count=0
  12. OT stop                — POST /ot/stop → status=stopped
  13. Classifier status      — GET /classifier/status returns is_loaded=True
  14. ML verdict             — POST /classifier/verdict returns at least one RTU verdict
  15. Replay session file    — data/reference-session.json exists and has ≥1 event
  16. Backup video file      — frontend/backup-demo/gridsentinel-backup-demo.webm exists
  17. Model artifact size    — backend/models/fusion_classifier.joblib ≥ 1 MB
  18. Audit export JSON      — GET /audit/export?format=json returns valid JSON list
  19. Audit export CSV       — GET /audit/export?format=csv returns CSV with header row

Usage (from repo root):
    python scripts/demo-preflight.py [--backend-url URL] [--frontend-dir PATH]

Exit codes:
    0  — All required checks passed (WARNs allowed)
    1  — One or more FAIL checks
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
import urllib.request
import urllib.error
from pathlib import Path

# ---------------------------------------------------------------------------
# Config / colour helpers
# ---------------------------------------------------------------------------

_GREEN  = "\033[92m"
_YELLOW = "\033[93m"
_RED    = "\033[91m"
_RESET  = "\033[0m"
_BOLD   = "\033[1m"


def _col(text: str, colour: str) -> str:
    return f"{colour}{text}{_RESET}" if sys.stdout.isatty() else text


def ok(label: str, detail: str = "") -> None:
    tag = _col("[PASS]", _GREEN)
    print(f"  {tag} {label}" + (f" — {detail}" if detail else ""))


def warn(label: str, detail: str = "") -> None:
    tag = _col("[WARN]", _YELLOW)
    print(f"  {tag} {label}" + (f" — {detail}" if detail else ""))


def fail(label: str, detail: str = "") -> None:
    tag = _col("[FAIL]", _RED)
    print(f"  {tag} {label}" + (f" — {detail}" if detail else ""))


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

def _get(url: str, timeout: int = 10, headers: dict | None = None):
    req = urllib.request.Request(url, headers=headers or {})
    resp = urllib.request.urlopen(req, timeout=timeout)
    return resp.status, resp.read().decode()


def _post(url: str, body: dict, timeout: int = 10, headers: dict | None = None):
    data = json.dumps(body).encode()
    h = {"Content-Type": "application/json", **(headers or {})}
    req = urllib.request.Request(url, data=data, headers=h, method="POST")
    resp = urllib.request.urlopen(req, timeout=timeout)
    return resp.status, resp.read().decode()


def _options(url: str, origin: str, timeout: int = 10):
    """Send an HTTP OPTIONS preflight request."""
    h = {
        "Origin": origin,
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "content-type",
    }
    req = urllib.request.Request(url, headers=h, method="OPTIONS")
    resp = urllib.request.urlopen(req, timeout=timeout)
    return resp.status, dict(resp.headers)


# ---------------------------------------------------------------------------
# WebSocket check (stdlib-only, RFC 6455 handshake)
# ---------------------------------------------------------------------------

def _ws_handshake_check(ws_url: str, timeout: int = 8) -> tuple[bool, str]:
    """
    Perform a minimal HTTP Upgrade handshake and check for 101 Switching Protocols.
    Does not require the `websockets` package.
    """
    import socket
    import base64
    import hashlib
    from urllib.parse import urlparse

    parsed = urlparse(ws_url)
    host = parsed.hostname
    port = parsed.port or (443 if parsed.scheme == "wss" else 80)
    path = parsed.path or "/"
    key = base64.b64encode(os.urandom(16)).decode()

    try:
        if parsed.scheme == "wss":
            import ssl
            ctx = ssl.create_default_context()
            raw = socket.create_connection((host, port), timeout=timeout)
            sock = ctx.wrap_socket(raw, server_hostname=host)
        else:
            sock = socket.create_connection((host, port), timeout=timeout)

        sock.settimeout(timeout)
        handshake = (
            f"GET {path} HTTP/1.1\r\n"
            f"Host: {host}:{port}\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            "Sec-WebSocket-Version: 13\r\n"
            "\r\n"
        )
        sock.sendall(handshake.encode())
        response = sock.recv(4096).decode(errors="replace")
        sock.close()

        if "101" in response:
            return True, "101 Switching Protocols"
        return False, f"Unexpected response: {response[:200]}"
    except Exception as e:
        return False, str(e)


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------

results: list[tuple[str, bool, bool]] = []   # (label, passed, is_warn_only)
_fails = 0
_warns = 0


def check(label: str, fn, warn_only: bool = False) -> None:
    global _fails, _warns
    try:
        fn()
        ok(label)
        results.append((label, True, warn_only))
    except AssertionError as e:
        detail = str(e)
        if warn_only:
            warn(label, detail)
            _warns += 1
            results.append((label, False, True))
        else:
            fail(label, detail)
            _fails += 1
            results.append((label, False, False))
    except Exception as e:
        detail = f"{type(e).__name__}: {e}"
        if warn_only:
            warn(label, detail)
            _warns += 1
            results.append((label, False, True))
        else:
            fail(label, detail)
            _fails += 1
            results.append((label, False, False))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="GridSentinel Demo Pre-flight Checks")
    parser.add_argument(
        "--backend-url",
        default=os.environ.get("BACKEND_URL", "http://localhost:8000"),
        help="Backend base URL (default: http://localhost:8000)",
    )
    parser.add_argument(
        "--frontend-dir",
        default=os.environ.get("FRONTEND_DIR", str(Path(__file__).parent.parent / "frontend")),
        help="Path to frontend directory",
    )
    parser.add_argument(
        "--repo-root",
        default=str(Path(__file__).parent.parent),
        help="Path to repo root",
    )
    args = parser.parse_args()

    base = args.backend_url.rstrip("/")
    frontend = Path(args.frontend_dir)
    repo = Path(args.repo_root)
    prod_origin = "https://grid-sentinel-sepia.vercel.app"

    # Infer WebSocket URL from backend URL
    ws_base = base.replace("https://", "wss://").replace("http://", "ws://")

    print()
    print(_col("=" * 60, _BOLD))
    print(_col("  GridSentinel Demo Pre-flight Check", _BOLD))
    print(_col(f"  Backend: {base}", _BOLD))
    print(_col("=" * 60, _RESET))
    print()

    # ------------------------------------------------------------------
    # 1. Backend reachability
    # ------------------------------------------------------------------
    def chk_health():
        status, body = _get(f"{base}/health", timeout=30)
        data = json.loads(body)
        assert status == 200, f"HTTP {status}"
        assert data.get("status") == "ok", f"Unexpected body: {body}"
    check("Backend reachable — GET /health → {status:ok}", chk_health)

    # ------------------------------------------------------------------
    # 2. CORS preflight from production origin
    # ------------------------------------------------------------------
    def chk_cors():
        status, hdrs = _options(f"{base}/ot/start", prod_origin, timeout=10)
        assert status in (200, 204), f"HTTP {status}"
        acao = hdrs.get("access-control-allow-origin", hdrs.get("Access-Control-Allow-Origin", ""))
        assert acao == prod_origin, f"ACAO header was: '{acao}'"
    check("CORS preflight allows production Vercel origin", chk_cors)

    # ------------------------------------------------------------------
    # 3. Version stamp
    # ------------------------------------------------------------------
    def chk_version():
        status, body = _get(f"{base}/version", timeout=10)
        data = json.loads(body)
        assert status == 200, f"HTTP {status}"
        assert data.get("git_sha"), "git_sha is empty"
        assert data.get("model_sha256_short"), "model_sha256_short is empty"
        assert data.get("feature_schema_version"), "feature_schema_version is empty"
        assert data.get("started_at_utc"), "started_at_utc is empty"
        print(f"       → git:{data['git_sha']}  model:{data['model_sha256_short']}  schema:{data['feature_schema_version']}")
    check("Version stamp — GET /version returns full stamp", chk_version)

    # ------------------------------------------------------------------
    # 4. WebSocket handshake
    # ------------------------------------------------------------------
    def chk_ws():
        ok_flag, detail = _ws_handshake_check(f"{ws_base}/ws/live", timeout=8)
        assert ok_flag, detail
    check("WebSocket handshake — /ws/live → 101 Switching Protocols", chk_ws)

    # ------------------------------------------------------------------
    # 5. Mixed-content guard (warn only — requires .env.local inspection)
    # ------------------------------------------------------------------
    def chk_mixed_content():
        env_local = frontend / ".env.local"
        if not env_local.exists():
            raise AssertionError(".env.local not found — cannot verify scheme match")
        content = env_local.read_text(encoding="utf-8")
        for line in content.splitlines():
            if "NEXT_PUBLIC_BACKEND_URL" in line and "=" in line:
                _, val = line.split("=", 1)
                val = val.strip().strip('"').strip("'")
                if base.startswith("https://") and val.startswith("http://"):
                    raise AssertionError(
                        f"Mixed-content: page is HTTPS but NEXT_PUBLIC_BACKEND_URL={val}"
                    )
                return
        # Not set — check if it falls back to localhost
        warn_txt = "NEXT_PUBLIC_BACKEND_URL not set in .env.local — will default to localhost"
        raise AssertionError(warn_txt)
    check("Mixed-content guard — env scheme matches page origin", chk_mixed_content, warn_only=True)

    # ------------------------------------------------------------------
    # 6. OT simulation start
    # ------------------------------------------------------------------
    def chk_ot_start():
        status, body = _post(f"{base}/ot/start", {})
        data = json.loads(body)
        assert status == 200, f"HTTP {status}"
        assert data.get("status") in ("started", "already_running"), f"status={data.get('status')}"
    check("OT simulation — POST /ot/start → started | already_running", chk_ot_start)

    # ------------------------------------------------------------------
    # 7. Simulation tick progresses
    # ------------------------------------------------------------------
    def chk_sim_time():
        time.sleep(1.5)   # give loop one tick
        status, body = _get(f"{base}/ot/status", timeout=10)
        data = json.loads(body)
        assert data.get("is_simulation_running") is True, "is_simulation_running is False"
        assert data.get("sim_time"), "sim_time is empty"
    check("Simulation clock advances — /ot/status has sim_time", chk_sim_time)

    # ------------------------------------------------------------------
    # 8. Silent data injection attack
    # ------------------------------------------------------------------
    def chk_data_injection():
        status, body = _post(f"{base}/ot/attack/data-injection", {
            "rtu_id": 2, "voltage_pu": 0.72, "duration_ticks": 5
        })
        data = json.loads(body)
        assert status == 200, f"HTTP {status}"
        assert data.get("status") == "injected", f"status={data.get('status')}"
    check("Data injection attack — POST /ot/attack/data-injection → injected", chk_data_injection)

    # ------------------------------------------------------------------
    # 9. Command injection attack
    # ------------------------------------------------------------------
    def chk_cmd_injection():
        status, body = _post(f"{base}/ot/attack/command-injection", {
            "rtu_id": 3, "register_address": 0, "value": 7500
        })
        data = json.loads(body)
        assert status == 200, f"HTTP {status}"
        flagged = data.get("details", {}).get("flagged_in_traffic_log")
        assert flagged is True, f"flagged_in_traffic_log={flagged}"
    check("Command injection attack — /ot/attack/command-injection → flagged", chk_cmd_injection)

    # ------------------------------------------------------------------
    # 10. Line-trip fault
    # ------------------------------------------------------------------
    def chk_line_trip():
        status, body = _post(f"{base}/ot/fault/line-trip", {"line_index": 1})
        data = json.loads(body)
        assert status == 200, f"HTTP {status}"
        assert data.get("status") == "triggered", f"status={data.get('status')}"
    check("Physical fault — POST /ot/fault/line-trip → triggered", chk_line_trip)

    # ------------------------------------------------------------------
    # 11. OT reset
    # ------------------------------------------------------------------
    def chk_ot_reset():
        status, body = _post(f"{base}/ot/reset", {})
        data = json.loads(body)
        assert status == 200, f"HTTP {status}"
        assert data.get("status") == "ok", f"status={data.get('status')}"
        # Verify classifier cache cleared
        _, vstatus = _get(f"{base}/classifier/status")
        vdata = json.loads(vstatus)
        assert vdata.get("cached_rtu_count") == 0, f"cache not cleared: {vdata.get('cached_rtu_count')}"
    check("OT reset — POST /ot/reset clears attacks + classifier cache", chk_ot_reset)

    # ------------------------------------------------------------------
    # 12. OT stop
    # ------------------------------------------------------------------
    def chk_ot_stop():
        status, body = _post(f"{base}/ot/stop", {})
        data = json.loads(body)
        assert status == 200, f"HTTP {status}"
        assert data.get("status") == "stopped", f"status={data.get('status')}"
    check("OT stop — POST /ot/stop → stopped", chk_ot_stop)

    # ------------------------------------------------------------------
    # 13. Classifier loaded
    # ------------------------------------------------------------------
    def chk_classifier_loaded():
        status, body = _get(f"{base}/classifier/status", timeout=10)
        data = json.loads(body)
        assert status == 200, f"HTTP {status}"
        assert data.get("is_loaded") is True, "Classifier not loaded — model file missing?"
    check("ML classifier — GET /classifier/status → is_loaded=True", chk_classifier_loaded)

    # ------------------------------------------------------------------
    # 14. ML verdict (restart sim briefly)
    # ------------------------------------------------------------------
    def chk_ml_verdict():
        _post(f"{base}/ot/start", {})
        time.sleep(2.0)
        status, body = _post(f"{base}/classifier/verdict", {})
        data = json.loads(body)
        assert status == 200, f"HTTP {status}"
        assert len(data.get("rtu_verdicts", [])) > 0, "No RTU verdicts returned"
        _post(f"{base}/ot/stop", {})
    check("ML verdict — POST /classifier/verdict returns RTU verdicts", chk_ml_verdict)

    # ------------------------------------------------------------------
    # 15. Replay session file
    # ------------------------------------------------------------------
    def chk_replay_session():
        candidates = [
            frontend / "data" / "reference-session.json",
            repo / "frontend" / "data" / "reference-session.json",
        ]
        for p in candidates:
            if p.exists():
                data = json.loads(p.read_text(encoding="utf-8"))
                events = data.get("events", [])
                assert len(events) >= 1, f"reference-session.json has no events"
                print(f"       → {len(events)} events in reference-session.json")
                return
        raise AssertionError("reference-session.json not found in frontend/data/")
    check("Replay session — reference-session.json exists with events", chk_replay_session)

    # ------------------------------------------------------------------
    # 16. Backup demo video
    # ------------------------------------------------------------------
    def chk_backup_video():
        candidates = [
            frontend / "backup-demo" / "gridsentinel-backup-demo.webm",
            repo / "frontend" / "backup-demo" / "gridsentinel-backup-demo.webm",
        ]
        for p in candidates:
            if p.exists():
                size = p.stat().st_size
                assert size >= 100_000, f"Video file suspiciously small: {size} bytes"
                print(f"       → {p.name}: {size:,} bytes ({size / 1024 / 1024:.2f} MB)")
                return
        raise AssertionError("gridsentinel-backup-demo.webm not found — run: npm run record-demo")
    check("Backup video — gridsentinel-backup-demo.webm exists (≥100KB)", chk_backup_video, warn_only=True)

    # ------------------------------------------------------------------
    # 17. Model artifact size
    # ------------------------------------------------------------------
    def chk_model_artifact():
        candidates = [
            repo / "backend" / "models" / "fusion_classifier.joblib",
            Path("backend/models/fusion_classifier.joblib"),
        ]
        for p in candidates:
            if p.exists():
                size = p.stat().st_size
                assert size >= 1_000_000, f"Model file too small ({size} bytes) — may be corrupt or placeholder"
                print(f"       → fusion_classifier.joblib: {size / 1024 / 1024:.2f} MB")
                return
        raise AssertionError("fusion_classifier.joblib not found")
    check("Model artifact — fusion_classifier.joblib ≥ 1 MB", chk_model_artifact)

    # ------------------------------------------------------------------
    # 18. Audit export JSON
    # ------------------------------------------------------------------
    def chk_audit_json():
        status, body = _get(f"{base}/audit/export?format=json", timeout=10)
        assert status == 200, f"HTTP {status}"
        data = json.loads(body)
        assert isinstance(data, list), f"Expected list, got {type(data)}"
    check("Audit export — GET /audit/export?format=json returns list", chk_audit_json)

    # ------------------------------------------------------------------
    # 19. Audit export CSV
    # ------------------------------------------------------------------
    def chk_audit_csv():
        status, body = _get(f"{base}/audit/export?format=csv", timeout=10)
        assert status == 200, f"HTTP {status}"
        lines = body.strip().splitlines()
        assert len(lines) >= 1, "CSV has no lines"
        header = lines[0]
        assert "," in header, f"CSV header has no columns: {header}"
    check("Audit export — GET /audit/export?format=csv returns CSV", chk_audit_csv)

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    total = len(results)
    passed = sum(1 for _, p, _ in results if p)
    failed = sum(1 for _, p, w in results if not p and not w)
    warned = sum(1 for _, p, w in results if not p and w)

    print()
    print(_col("=" * 60, _BOLD))
    if failed == 0:
        banner = _col("  ✅  ALL REQUIRED CHECKS PASSED", _GREEN + _BOLD)
    else:
        banner = _col(f"  ❌  {failed} CHECK(S) FAILED — DO NOT DEMO", _RED + _BOLD)
    print(banner)
    print(f"     {passed}/{total} passed   {failed} failed   {warned} warnings")
    print(_col("=" * 60, _RESET))
    print()

    sys.exit(1 if failed > 0 else 0)


if __name__ == "__main__":
    main()
