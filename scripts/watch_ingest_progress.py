#!/usr/bin/env python3
"""Live progress bar for drive_ingest / benchmark runs.

Usage (second terminal while ingest runs):
  .venv/bin/python scripts/watch_ingest_progress.py

Or tail the log:
  tail -f data/backups/benchmark_extraction.log
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ingest_progress import progress_path  # noqa: E402


def _bar(pct: int, width: int = 30) -> str:
    pct = max(0, min(100, pct))
    filled = int(width * pct / 100)
    return "[" + "#" * filled + "-" * (width - filled) + "]"


def main() -> int:
    path = progress_path()
    log_path = Path(os.environ.get("INGEST_LOG_FILE", "data/backups/ingest_live.log"))
    print(f"Watching {path}")
    if log_path.is_file():
        print(f"Detailed logs: tail -f {log_path}")
    print("Ctrl+C to stop\n")

    last_msg = ""
    while True:
        if path.is_file():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                time.sleep(0.5)
                continue
            pct = int(data.get("percent") or 0)
            phase = data.get("phase") or "?"
            doc = data.get("document") or ""
            doc_i = data.get("document_index")
            doc_n = data.get("document_total")
            chunk_i = data.get("chunk_index")
            chunk_n = data.get("chunk_total")
            overall_i = data.get("overall_chunk")
            overall_n = data.get("overall_chunks")
            workers = data.get("workers")
            msg = data.get("message") or ""

            parts = [f"{phase} {_bar(pct)} {pct:3d}%"]
            if doc:
                if doc_i and doc_n:
                    parts.append(f"doc {doc_i}/{doc_n}")
                parts.append(doc[:40])
            if chunk_i and chunk_n:
                parts.append(f"chunk {chunk_i}/{chunk_n}")
            if overall_i and overall_n:
                parts.append(f"overall {overall_i}/{overall_n}")
            if workers:
                parts.append(f"workers={workers}")
            if msg and msg != last_msg:
                parts.append(f"| {msg}")

            line = " ".join(parts)
            print(f"\r{line[:120]:<120}", end="", flush=True)
            last_msg = msg
        else:
            print("\rWaiting for ingest to start...                              ", end="", flush=True)
        time.sleep(1)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\nStopped watching.")
