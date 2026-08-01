#!/usr/bin/env python3
"""
Timed A/B benchmark: serial vs parallel extraction for Drive ingest test docs.

Usage:
  python scripts/benchmark_extraction.py
  python scripts/benchmark_extraction.py --docs English-Woccon Resurrecting
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DOCS = ["English-Woccon", "Resurrecting"]
STAGING_BENCH = ROOT / "woccon_language" / "drive_staging_bench"
OLD_STAGING = ROOT / "woccon_language" / "drive_staging"


def _run_ingest(doc_filter: str, workers: int, ocr_workers: int, label: str) -> dict:
    env = os.environ.copy()
    env["DRIVE_INGEST_FILTER"] = doc_filter
    env["DRIVE_STAGING_DIR"] = str(STAGING_BENCH.relative_to(ROOT))
    env["EXTRACT_PARALLEL_WORKERS"] = str(workers)
    env["PDF_OCR_PARALLEL_WORKERS"] = str(ocr_workers)
    env["DRIVE_INGEST_FORCE_FULL"] = "1"
    env["PYTHONUNBUFFERED"] = "1"
    env.pop("DRIVE_INGEST_LIMIT", None)

    log_path = ROOT / "data" / "backups" / "ingest_live.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"\n--- {label}: {doc_filter} (extract={workers}, ocr={ocr_workers}) ---", flush=True)
    t0 = time.perf_counter()
    proc = subprocess.Popen(
        [sys.executable, str(ROOT / "drive_ingest.py")],
        cwd=ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    lines: list[str] = []
    with log_path.open("a", encoding="utf-8") as logf:
        logf.write(f"\n=== {label} {doc_filter} workers={workers} ===\n")
        assert proc.stdout is not None
        for line in proc.stdout:
            print(line, end="", flush=True)
            logf.write(line)
            lines.append(line)
    proc.wait()
    elapsed = time.perf_counter() - t0

    summary = {}
    for line in reversed(lines):
        line = line.strip()
        if line.startswith("{") and line.endswith("}"):
            try:
                summary = json.loads(line)
                break
            except json.JSONDecodeError:
                continue
    if not summary and lines:
        summary = {"raw_stdout_tail": "".join(lines[-30:])[-2000:]}

    summary["wall_seconds"] = round(elapsed, 2)
    summary["returncode"] = proc.returncode
    summary["workers"] = workers
    summary["ocr_workers"] = ocr_workers
    summary["label"] = label
    return summary


def _find_staging_file(doc_filter: str) -> Path | None:
    needle = doc_filter.lower().replace("_", " ")
    best: Path | None = None
    best_len = -1
    for p in STAGING_BENCH.glob("*.json"):
        if p.name in ("manifest.json", "sync_state.json"):
            continue
        stem = p.stem.lower().replace("_", " ")
        if needle in stem and len(stem) > best_len:
            best = p
            best_len = len(stem)
    return best


def _lexicon_count(doc_filter: str) -> int:
    p = _find_staging_file(doc_filter)
    if not p:
        return 0
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except UnicodeDecodeError:
        data = json.loads(p.read_text(encoding="utf-8", errors="replace"))
    return len(data.get("lexicon_entries") or [])


def _lexicon_count_from_summary(summary: dict, doc_filter: str) -> int:
    count = summary.get("extraction_lexicon_count")
    if isinstance(count, int) and count >= 0:
        return count
    return _lexicon_count(doc_filter)


def _run_diff(doc_filter: str) -> str:
    proc = subprocess.run(
        [
            sys.executable,
            "scripts/diff_staging_runs.py",
            "--old",
            str(OLD_STAGING),
            "--new",
            str(STAGING_BENCH),
            "--file",
            doc_filter,
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    return proc.stdout or proc.stderr


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark serial vs parallel Drive ingest")
    def _int_env(name: str, default: int) -> int:
        try:
            return int(os.environ.get(name, str(default)))
        except ValueError:
            return default

    parser.add_argument("--docs", nargs="+", default=DEFAULT_DOCS)
    parser.add_argument("--skip-serial", action="store_true", help="Skip serial baseline (faster)")
    parser.add_argument("--parallel-workers", type=int, default=_int_env("EXTRACT_PARALLEL_WORKERS", 3))
    parser.add_argument("--ocr-workers", type=int, default=_int_env("PDF_OCR_PARALLEL_WORKERS", 2))
    parser.add_argument("--json-out", type=Path, default=ROOT / "data" / "backups" / "benchmark_extraction.json")
    args = parser.parse_args()

    try:
        from dotenv import load_dotenv

        load_dotenv(ROOT / ".env")
    except ImportError:
        pass

    STAGING_BENCH.mkdir(parents=True, exist_ok=True)
    results = []

    for doc in args.docs:
        print(f"\n=== {doc} ===", flush=True)
        print("Tip: run `.venv/bin/python scripts/watch_ingest_progress.py` in another terminal", flush=True)
        serial = {"wall_seconds": 0, "returncode": 0, "workers": 1, "ocr_workers": 1, "skipped": True}
        if not args.skip_serial:
            serial = _run_ingest(doc, workers=1, ocr_workers=1, label="serial")
        parallel = _run_ingest(
            doc, workers=args.parallel_workers, ocr_workers=args.ocr_workers, label="parallel"
        )
        serial_count = _lexicon_count_from_summary(serial, doc) if not serial.get("skipped") else 0
        parallel_count = _lexicon_count_from_summary(parallel, doc)
        speedup = (
            round(serial["wall_seconds"] / parallel["wall_seconds"], 2)
            if parallel["wall_seconds"] > 0
            else None
        )
        row = {
            "doc": doc,
            "serial": {**serial, "lexicon_count": serial_count},
            "parallel": {**parallel, "lexicon_count": parallel_count},
            "speedup": speedup,
            "diff_vs_opus": _run_diff(doc),
        }
        results.append(row)
        try:
            args.json_out.parent.mkdir(parents=True, exist_ok=True)
            args.json_out.write_text(json.dumps(results, indent=2), encoding="utf-8")
        except OSError:
            pass
        print(
            f"  serial:   {serial['wall_seconds']}s, {serial_count} lexicon entries "
            f"(rc={serial.get('returncode')})"
        )
        print(
            f"  parallel: {parallel['wall_seconds']}s, {parallel_count} lexicon entries "
            f"(rc={parallel.get('returncode')}, speedup={speedup}x)"
        )

    args.json_out.parent.mkdir(parents=True, exist_ok=True)
    args.json_out.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"\nWrote {args.json_out}")
    failed = any(
        r["serial"].get("returncode") != 0 or r["parallel"].get("returncode") != 0 for r in results
    )
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
