"""Write live ingest progress to a JSON file for scripts/watch_ingest_progress.py."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

DEFAULT_PATH = "data/ingest_progress.json"


def progress_path() -> Path:
    return Path(os.environ.get("INGEST_PROGRESS_FILE", DEFAULT_PATH))


def write(**fields: Any) -> None:
    path = progress_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        **fields,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def clear() -> None:
    path = progress_path()
    if path.is_file():
        path.unlink()
