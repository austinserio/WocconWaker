"""Serve pre-generated pronunciation MP3 clips."""
from pathlib import Path
from urllib.parse import unquote

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from starlette.responses import Response

from panel_api.services.pronunciation_audio import audio_file_path, get_pronunciation_audio_dir

router = APIRouter(prefix="/pronunciation-audio", tags=["pronunciation-audio"])


def _resolve_audio_path(filename: str) -> Path:
    decoded = unquote(filename)
    if not decoded.endswith(".mp3") or "/" in decoded or ".." in decoded:
        raise HTTPException(status_code=400, detail="Invalid filename")
    path = audio_file_path(decoded, get_pronunciation_audio_dir())
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Audio clip not found")
    return path


@router.head("/{filename:path}")
def head_pronunciation_audio(filename: str):
    """HEAD for Facebook/Messenger URL probes (must not return 405)."""
    path = _resolve_audio_path(filename)
    stat = path.stat()
    return Response(
        status_code=200,
        headers={
            "Content-Type": "audio/mpeg",
            "Content-Length": str(stat.st_size),
            "Cache-Control": "public, max-age=86400",
            "Accept-Ranges": "bytes",
        },
    )


@router.get("/{filename:path}")
def get_pronunciation_audio(filename: str):
    """Return a cached MP3 clip by human-readable filename."""
    path = _resolve_audio_path(filename)
    decoded = unquote(filename)
    return FileResponse(
        path,
        media_type="audio/mpeg",
        filename=decoded,
        headers={"Cache-Control": "public, max-age=86400"},
    )
