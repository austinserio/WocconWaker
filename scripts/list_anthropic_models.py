#!/usr/bin/env python3
"""List Anthropic models available for your API key. Loads .env from project root."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.chdir(os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
load_dotenv()

api_key = (os.getenv("ANTHROPIC_API_KEY") or "").strip()
if not api_key:
    print("ANTHROPIC_API_KEY not set in .env")
    sys.exit(1)

try:
    from anthropic import Anthropic
    client = Anthropic(api_key=api_key)
    # List models via the API (if available) or use a minimal chat to verify the key
    # Anthropic doesn't have a public list endpoint in the same way; we'll try a minimal message
    # to see which model works. Common ids:
    for model_id in ["claude-3-5-sonnet-latest", "claude-3-5-sonnet-20241022", "claude-3-sonnet-20240229", "claude-sonnet-4-20250514"]:
        try:
            r = client.messages.create(
                model=model_id,
                max_tokens=10,
                messages=[{"role": "user", "content": "Say OK"}],
            )
            text = (r.content[0].text if r.content else "").strip()
            print(f"  {model_id}: OK (response: {text[:50]!r})")
        except Exception as e:
            err = str(e).split("\n")[0]
            print(f"  {model_id}: FAIL - {err}")
except Exception as e:
    print("Error:", e)
    sys.exit(1)
