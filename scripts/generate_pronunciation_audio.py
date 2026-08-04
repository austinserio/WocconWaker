#!/usr/bin/env python3
"""Batch-generate MP3 pronunciation clips from lexicon guides via Kokoro (CPU).

Full docs: docs/PRONUNCIATION_AUDIO.md

Output files use human-readable names:
  roosome - Acorns (rue-sa-may).mp3

Usage:
  python scripts/generate_pronunciation_audio.py
  python scripts/generate_pronunciation_audio.py --sample-only
  python scripts/generate_pronunciation_audio.py --staging woccon_language/drive_staging/English-Woccon.json
  python scripts/generate_pronunciation_audio.py --force --staging woccon_language/drive_staging/English-Woccon.json

Requires: pip install -r requirements-tts.txt, system espeak-ng + ffmpeg.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from panel_api.services.kokoro_phonemes import prepare_kokoro_text
from panel_api.services.pronunciation_audio import (  # noqa: E402
    audio_file_path,
    audio_filename,
    cleanup_stale_audio,
    get_pronunciation_audio_dir,
    is_speakable_pronunciation,
    load_manifest,
    pick_primary_lexicon_row,
    pronunciation_content_hash,
    save_manifest,
    unique_audio_filename,
)

SAMPLE_GUIDES = [
    ("roosome", "Acorns", "rue-sa-may"),
    ("roocheha", "Black", "RUE-chay-ha"),
    ("aycooch", "unknown", "ay-COOCH-ro-moan"),
    ("taoo", "unknown", "ta-oo oon-ta we-neek"),
    ("monwittetau", "unknown", "mahn-we-tay-ta-oo"),
    ("reheshiwau", "Afraid", "ray-hay-she-wa-oo"),
    ("choo", "unknown", "choo-ta-oo-nay"),
    ("wawn", "unknown", "WAWN-she"),
    ("wayka", "unknown", "WAY-ka-oo"),
    ("yauka", "unknown", "ya-oo-ka"),
    ("sauhau", "unknown", "sa-oo-ha-oo"),
    ("maray", "unknown", "ma-ray-nay"),
    ("whopka", "unknown", "whop-ka-ha-ray"),
    ("ruekay", "unknown", "RUE-kay-pa"),
    ("ohoonka", "unknown", "oh-oon-ka"),
    ("roomayen", "unknown", "roo-ma-yen"),
    ("itay", "unknown", "ee-tay"),
    ("yatay", "unknown", "ya-TAY-stay-ah"),
    ("rueyu", "unknown", "rue-YU-nay"),
    ("mothei", "unknown", "Mothei"),
]

DEFAULT_VOICE = os.environ.get("KOKORO_VOICE", "af_heart")
DEFAULT_SPEED = float(os.environ.get("KOKORO_SPEED", "0.8"))
DEFAULT_LANG = os.environ.get("KOKORO_LANG_CODE", "a")
SAMPLE_RATE = 24000


def _load_from_staging(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    entries = data.get("lexicon_entries") or data.get("lexicon") or []
    out: list[dict] = []
    for e in entries:
        pron = e.get("pronunciation")
        if not is_speakable_pronunciation(pron):
            continue
        out.append(
            {
                "id": e.get("woccon") or e.get("id") or "",
                "woccon": e.get("woccon") or "",
                "english": e.get("english") or "",
                "pronunciation": pron,
            }
        )
    return out


def _load_from_db() -> list[dict]:
    from panel_api.db import CanonicalLexicon, SessionLocal, init_db

    init_db()
    db = SessionLocal()
    try:
        rows = (
            db.query(CanonicalLexicon)
            .filter(CanonicalLexicon.pronunciation.isnot(None))
            .all()
        )
        out: list[dict] = []
        for row in rows:
            if not is_speakable_pronunciation(row.pronunciation):
                continue
            out.append(
                {
                    "id": row.id,
                    "woccon": row.woccon,
                    "english": row.english,
                    "pronunciation": row.pronunciation,
                }
            )
        return out
    finally:
        db.close()


def _collect_entries(args: argparse.Namespace) -> list[dict]:
    if args.sample_only:
        return [
            {"id": woccon, "woccon": woccon, "english": english, "pronunciation": pron}
            for woccon, english, pron in SAMPLE_GUIDES
        ]
    if args.staging:
        return _load_from_staging(Path(args.staging))
    entries = _load_from_db()
    if entries:
        return entries
    fallback = ROOT / "woccon_language/drive_staging/English-Woccon.json"
    if not fallback.is_file():
        fallback = ROOT / "woccon_language/drive_staging_local/English-Woccon.json"
    if fallback.is_file():
        print(f"No DB entries; falling back to {fallback}")
        return _load_from_staging(fallback)
    return []


def _group_by_hash(entries: list[dict]) -> dict[str, dict]:
    grouped: dict[str, dict] = {}
    for entry in entries:
        pron = entry.get("pronunciation")
        text = prepare_kokoro_text(pron)
        content_hash = pronunciation_content_hash(pron)
        if not text or not content_hash:
            continue
        bucket = grouped.setdefault(
            content_hash,
            {
                "hash": content_hash,
                "tts_text": text,
                "pronunciation": pron,
                "woccon_ids": [],
                "lexicon_rows": [],
            },
        )
        wid = entry.get("id") or entry.get("woccon")
        if wid and wid not in bucket["woccon_ids"]:
            bucket["woccon_ids"].append(wid)
        row_key = (entry.get("woccon") or "", entry.get("english") or "")
        existing = {(r.get("woccon"), r.get("english")) for r in bucket["lexicon_rows"]}
        if row_key not in existing:
            bucket["lexicon_rows"].append(
                {
                    "id": wid,
                    "woccon": entry.get("woccon") or "",
                    "english": entry.get("english") or "",
                }
            )
    return grouped


def _synthesize_kokoro(pipeline, text: str, voice: str, speed: float):
    chunks = []
    generator = pipeline(text, voice=voice, speed=speed)
    for _i, (_gs, _ps, audio) in enumerate(generator):
        chunks.append(audio)
    if not chunks:
        raise RuntimeError(f"Kokoro produced no audio for: {text!r}")
    if len(chunks) == 1:
        return chunks[0]
    import numpy as np

    return np.concatenate(chunks)


def _load_kokoro_pipeline(lang_code: str):
    from kokoro import KPipeline

    return KPipeline(lang_code=lang_code, repo_id="hexgrad/Kokoro-82M")


def _wav_to_mp3(wav_path: Path, mp3_path: Path, *, pad_ms: int = 0) -> None:
    mp3_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg",
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(wav_path),
    ]
    if pad_ms > 0:
        sec = pad_ms / 1000.0
        cmd.extend(["-af", f"apad=pad_dur={sec}"])
    cmd.extend(
        [
            "-codec:a",
            "libmp3lame",
            "-qscale:a",
            "2",
            str(mp3_path),
        ]
    )
    subprocess.run(cmd, check=True)


def _write_mp3(audio, mp3_path: Path, *, pad_ms: int = 0) -> None:
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        wav_path = Path(tmp.name)
    try:
        import soundfile as sf

        sf.write(str(wav_path), audio, SAMPLE_RATE)
        _wav_to_mp3(wav_path, mp3_path, pad_ms=pad_ms)
    finally:
        wav_path.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate pronunciation MP3 clips with Kokoro")
    parser.add_argument("--staging", help="Staging JSON path instead of panel DB")
    parser.add_argument(
        "--sample-only",
        action="store_true",
        help="Generate only the QA sample set (~20 hard cases)",
    )
    parser.add_argument(
        "--audio-dir",
        default=str(get_pronunciation_audio_dir()),
        help="Output directory for MP3 files and manifest.json",
    )
    parser.add_argument("--voice", default=DEFAULT_VOICE)
    parser.add_argument("--speed", type=float, default=DEFAULT_SPEED)
    parser.add_argument("--lang-code", default=DEFAULT_LANG)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true", help="Regenerate even if MP3 exists")
    args = parser.parse_args()

    audio_dir = Path(args.audio_dir)
    audio_dir.mkdir(parents=True, exist_ok=True)

    entries = _collect_entries(args)
    if not entries:
        print("No speakable pronunciation entries found.", file=sys.stderr)
        return 1

    grouped = _group_by_hash(entries)
    print(f"Found {len(entries)} entries → {len(grouped)} unique guides")

    reserved_names: set[str] = set()
    planned: dict[str, str] = {}
    for content_hash, info in grouped.items():
        primary = pick_primary_lexicon_row(info["lexicon_rows"])
        base_name = audio_filename(
            primary.get("woccon") or "unknown",
            primary.get("english") or primary.get("woccon") or "unknown",
            info.get("pronunciation"),
        )
        if args.force or args.dry_run:
            filename = base_name
        else:
            filename = unique_audio_filename(
                primary.get("woccon") or "unknown",
                primary.get("english") or primary.get("woccon") or "unknown",
                info.get("pronunciation"),
                audio_dir=audio_dir,
                reserved=reserved_names,
            )
        reserved_names.add(filename)
        planned[content_hash] = filename

    manifest = load_manifest(audio_dir)
    manifest["version"] = 2
    manifest["engine"] = "kokoro"
    manifest["voice"] = args.voice
    manifest["speed"] = args.speed
    manifest["lang_code"] = args.lang_code
    manifest["entries"] = {}

    generated = 0
    skipped = 0
    pending_hashes = [
        content_hash
        for content_hash in grouped
        if args.force or not audio_file_path(planned[content_hash], audio_dir).is_file()
    ]

    pipeline = None
    if not args.dry_run and pending_hashes:
        print(f"Loading Kokoro pipeline (lang={args.lang_code}, voice={args.voice}, speed={args.speed})")
        pipeline = _load_kokoro_pipeline(args.lang_code)

    for content_hash, info in sorted(grouped.items(), key=lambda x: planned[x[0]].lower()):
        filename = planned[content_hash]
        mp3_path = audio_file_path(filename, audio_dir)
        primary = pick_primary_lexicon_row(info["lexicon_rows"])

        if mp3_path.is_file() and not args.force:
            skipped += 1
        elif args.dry_run:
            print(f"  [dry-run] would generate {filename}: {info['tts_text']!r}")
            generated += 1
        else:
            print(f"Generating {filename}: {info['tts_text']!r}")
            audio = _synthesize_kokoro(pipeline, info["tts_text"], args.voice, args.speed)
            _write_mp3(audio, mp3_path)
            generated += 1

        manifest["entries"][content_hash] = {
            "hash": content_hash,
            "filename": filename,
            "woccon": primary.get("woccon"),
            "english": primary.get("english"),
            "pronunciation": info["pronunciation"],
            "kokoro_text": info["tts_text"],
            "tts_text": info["tts_text"],
            "woccon_ids": info["woccon_ids"],
            "lexicon_rows": info["lexicon_rows"],
            "voice": args.voice,
            "speed": args.speed,
            "model": "Kokoro-82M",
        }

    if not args.dry_run:
        save_manifest(manifest, audio_dir)
        removed = cleanup_stale_audio(audio_dir, keep_filenames=set(planned.values()))
        if removed:
            print(f"Removed {removed} stale clip(s)")

    print(f"Done. generated={generated} skipped={skipped} total={len(grouped)} dir={audio_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
