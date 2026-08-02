#!/usr/bin/env python3
"""Poll UIC until policy analyzer idle, queue full Qwen reingest, run completeness check."""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORT_PATH = ROOT / "data" / "uic_reingest_monitor_report.json"
LOG_PATH = ROOT / "data" / "backups" / "uic_reingest_monitor.log"

SSH_KEY = os.environ.get("INGEST_SSH_KEY", str(Path.home() / ".ssh" / "uic-learning-deploy"))
SSH_HOST = os.environ.get("INGEST_SSH_HOST", "100.71.124.8")
SSH_USER = os.environ.get("INGEST_SSH_USER", "info@urbanindigenouscollective.org")
REMOTE_DIR = os.environ.get("INGEST_REMOTE_ROOT", "/root/WocconWaker")
STAGING_DIR = os.environ.get("DRIVE_STAGING_DIR", "woccon_language/drive_staging_qwen_full")
POLL_SEC = int(os.environ.get("UIC_LLM_WAIT_POLL_SEC", "60"))
MAX_POLICY_WAIT = int(os.environ.get("UIC_LLM_WAIT_MAX_SEC", "86400"))
MAX_REINGEST_WAIT = int(os.environ.get("UIC_REINGEST_MAX_WAIT_SEC", "28800"))


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def log(msg: str) -> None:
    line = f"{utc_now()} {msg}"
    print(line, flush=True)
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def ssh(cmd: str, timeout: int = 45) -> tuple[int, str]:
    full = [
        "ssh", "-i", SSH_KEY,
        "-o", "ConnectTimeout=20",
        "-o", "StrictHostKeyChecking=accept-new",
        f"{SSH_USER}@{SSH_HOST}",
        f'wsl -e bash -lc "{cmd}"',
    ]
    try:
        proc = subprocess.run(full, capture_output=True, text=True, timeout=timeout)
        out = (proc.stdout or "") + (proc.stderr or "")
        return proc.returncode, out.strip()
    except subprocess.TimeoutExpired:
        return 124, "ssh timeout"
    except Exception as exc:
        return 1, str(exc)


def save_report(report: dict) -> None:
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


def policy_status() -> dict:
    code, out = ssh(
        r"if pgrep -f 'python scripts/run_discovery.py' >/dev/null 2>&1; then echo busy; else echo idle; fi; "
        r"docker logs --tail 2 policy-tracker-scheduler-run-438b0876a907 2>/dev/null | tail -1 || "
        r"docker ps --filter name=scheduler-run --format '{{.Names}} {{.Status}}' | head -1"
    )
    idle = "idle" in out.splitlines()[0] if out else False
    progress = ""
    m = re.search(r"step=(\d+/\d+).*pct=(\d+)", out)
    if m:
        progress = f"step={m.group(1)} pct={m.group(2)}%"
    elif out:
        progress = out.splitlines()[-1][:200]
    return {"idle": idle, "raw": out, "progress": progress, "ssh_code": code}


def woccon_ingest_running() -> bool:
    _, out = ssh("pgrep -f 'drive_ingest.py' >/dev/null 2>&1 && echo yes || echo no")
    return "yes" in out


def main() -> int:
    report: dict = {
        "started_at": utc_now(),
        "uic_ingest_status": "monitoring_started",
        "completed_at": None,
        "reingest_command_run": None,
        "reingest_exit_code": None,
        "completeness_summary": None,
        "errors": [],
    }
    save_report(report)
    log("Monitor started")

    # Phase 1: wait for policy analyzer
    elapsed = 0
    while True:
        st = policy_status()
        if st["idle"]:
            report["uic_ingest_status"] = "policy_analyzer_idle"
            log("Policy analyzer idle")
            break
        report["uic_ingest_status"] = f"policy_analyzer_running {st['progress']}"
        save_report(report)
        log(f"Waiting: {report['uic_ingest_status']}")
        if elapsed >= MAX_POLICY_WAIT:
            report["errors"].append(f"Timeout after {MAX_POLICY_WAIT}s waiting for policy analyzer")
            report["uic_ingest_status"] = "timeout_waiting_for_policy_analyzer"
            save_report(report)
            return 1
        time.sleep(POLL_SEC)
        elapsed += POLL_SEC

    # Phase 2: deploy + queue reingest
    reingest_cmd = "./scripts/queue_full_qwen_ingest_uic.sh"
    report["reingest_command_run"] = (
        f"{reingest_cmd} -> remote wait_for_uic_llm_idle.sh + "
        f"EXTRACT_COMPLETENESS_FAIL=1 run_full_qwen_ingest.sh staging={STAGING_DIR}"
    )
    save_report(report)
    log("Queueing full Qwen reingest")

    # Patch remote run script env for completeness fail
    ssh(
        f"grep -q EXTRACT_COMPLETENESS_FAIL {REMOTE_DIR}/scripts/run_full_qwen_ingest.sh 2>/dev/null || "
        f"sed -i '/export PYTHONUNBUFFERED/a export EXTRACT_COMPLETENESS_FAIL=1' {REMOTE_DIR}/scripts/run_full_qwen_ingest.sh 2>/dev/null || true"
    )

    proc = subprocess.run(
        [str(ROOT / "scripts" / "queue_full_qwen_ingest_uic.sh")],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=600,
    )
    if proc.returncode != 0:
        report["errors"].append(f"queue failed: {proc.stderr or proc.stdout}")
        save_report(report)
        return 1

    report["uic_ingest_status"] = "qwen_reingest_queued"
    save_report(report)
    log("Reingest queued; waiting for completion")

    # Phase 3: wait for reingest
    elapsed = 0
    time.sleep(30)
    while woccon_ingest_running() or elapsed < POLL_SEC:
        _, tail = ssh(f"tail -3 {REMOTE_DIR}/data/backups/full_qwen_ingest.log 2>/dev/null || echo '(no log yet)'")
        report["uic_ingest_status"] = f"qwen_reingest_running: {tail.splitlines()[-1][:150] if tail else 'unknown'}"
        save_report(report)
        log(report["uic_ingest_status"])
        if not woccon_ingest_running() and elapsed > POLL_SEC:
            break
        if elapsed >= MAX_REINGEST_WAIT:
            report["errors"].append(f"Timeout after {MAX_REINGEST_WAIT}s waiting for reingest")
            save_report(report)
            return 1
        time.sleep(POLL_SEC)
        elapsed += POLL_SEC

    _, reingest_tail = ssh(f"tail -40 {REMOTE_DIR}/data/backups/full_qwen_ingest.log 2>/dev/null")
    reingest_exit = 1 if re.search(r"ERROR|Traceback|Phase 1 ingest failed", reingest_tail or "") else 0
    report["reingest_exit_code"] = reingest_exit
    if reingest_exit:
        report["errors"].append("Reingest log contains errors")
    report["uic_ingest_status"] = f"qwen_reingest_complete exit={reingest_exit}"
    save_report(report)
    log("Running completeness check on UIC")

    # Phase 4: completeness
    _, comp_out = ssh(
        f"cd {REMOTE_DIR} && set -a && source .env && set +a && "
        f".venv/bin/python scripts/check_extraction_completeness.py --bulk --staging-dir {STAGING_DIR}",
        timeout=600,
    )
    summary_lines = [ln for ln in (comp_out or "").splitlines() if "missing=" in ln or "Lowest completeness" in ln or "Bulk extraction" in ln]
    report["completeness_summary"] = "\n".join(summary_lines[-25:]) if summary_lines else (comp_out or "")[-2000:]
    report["completed_at"] = utc_now()
    save_report(report)
    log(f"Monitor complete exit={reingest_exit}")
    return reingest_exit


if __name__ == "__main__":
    raise SystemExit(main())
