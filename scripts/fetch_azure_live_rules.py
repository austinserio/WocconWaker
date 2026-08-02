#!/usr/bin/env python3
"""Fetch canonical grammar/pronunciation rules from Azure panel (live)."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from urllib.parse import urlparse

import requests

ROOT = Path(__file__).resolve().parents[1]


def _base_url() -> str:
    webhook = (os.environ.get("AZURE_CONTAINER_APP_WEBHOOK_URL") or "").strip()
    if webhook:
        p = urlparse(webhook)
        return f"{p.scheme}://{p.netloc}"
    explicit = (os.environ.get("PANEL_BASE_URL") or os.environ.get("WOCCON_PANEL_URL") or "").strip()
    if explicit:
        return explicit.rstrip("/")
    raise SystemExit("Set AZURE_CONTAINER_APP_WEBHOOK_URL or PANEL_BASE_URL in .env")


def main() -> int:
    try:
        from dotenv import load_dotenv

        load_dotenv(ROOT / ".env")
    except ImportError:
        pass

    email = os.environ.get("PANEL_ADMIN_EMAIL", "").strip()
    password = os.environ.get("PANEL_ADMIN_PASSWORD", "").strip()
    if not email or not password:
        raise SystemExit("PANEL_ADMIN_EMAIL and PANEL_ADMIN_PASSWORD required")

    base = _base_url()
    session = requests.Session()
    login = session.post(
        f"{base}/api/auth/login/json",
        json={"email": email, "password": password},
        timeout=60,
    )
    login.raise_for_status()
    token = login.json().get("access_token")
    if not token:
        raise SystemExit("Login succeeded but no access_token returned")

    headers = {"Authorization": f"Bearer {token}"}
    out: dict = {"base_url": base, "fetched_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat()}

    for category in ("grammar", "pronunciation"):
        resp = session.get(
            f"{base}/api/rules",
            params={"category": category, "limit": 5000},
            headers=headers,
            timeout=120,
        )
        resp.raise_for_status()
        payload = resp.json()
        if isinstance(payload, list):
            rows = payload
        elif isinstance(payload, dict):
            rows = payload.get("items") or payload.get("rules") or []
        else:
            rows = []
        out[category] = rows
        print(f"{category}: {len(rows)} rules from {base}", file=sys.stderr)

    out_path = Path(os.environ.get("LIVE_RULES_OUT") or ROOT / "data/backups/azure_live_rules.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {out_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
