"""Serve pre-generated pronunciation MP3 clips."""
from pathlib import Path
from urllib.parse import unquote

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from panel_api.services.pronunciation_audio import audio_file_path, get_pronunciation_audio_dir

router = APIRouter(prefix="/pronunciation-audio", tags=["pronunciation-audio"])


@router.api_route("/{filename:path}", methods=["GET", "HEAD"])
def get_pronunciation_audio(filename: str):
    """Return a cached MP3 clip by human-readable filename."""
    decoded = unquote(filename)
    if not decoded.endswith(".mp3") or "/" in decoded or ".." in decoded:
        raise HTTPException(status_code=400, detail="Invalid filename")
    path = audio_file_path(decoded, get_pronunciation_audio_dir())
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Audio clip not found")
    return FileResponse(
        path,
        media_type="audio/mpeg",
        filename=decoded,
        headers={"Cache-Control": "public, max-age=86400"},
    )
