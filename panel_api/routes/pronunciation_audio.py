"""Serve pre-generated pronunciation MP3 clips."""
from pathlib import Path
from urllib.parse import unquote

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from starlette.responses import Response

from panel_api.services.pronunciation_audio import (
    audio_file_path,
    audio_path_for_content_hash,
    get_pronunciation_audio_dir,
)

router = APIRouter(prefix="/pronunciation-audio", tags=["pronunciation-audio"])

_AUDIO_HEADERS = {
    "Cache-Control": "public, max-age=86400",
    "Accept-Ranges": "bytes",
}


def _audio_file_response(path: Path) -> FileResponse:
    """Serve MP3 inline so Facebook/Messenger can fetch attachment URLs."""
    return FileResponse(
        path,
        media_type="audio/mpeg",
        headers=_AUDIO_HEADERS,
    )


def _resolve_audio_path(filename: str) -> Path:
    decoded = unquote(filename)
    if not decoded.endswith(".mp3") or "/" in decoded or ".." in decoded:
        raise HTTPException(status_code=400, detail="Invalid filename")
    path = audio_file_path(decoded, get_pronunciation_audio_dir())
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Audio clip not found")
    return path


def _head_audio(path: Path) -> Response:
    stat = path.stat()
    return Response(
        status_code=200,
        headers={
            "Content-Type": "audio/mpeg",
            "Content-Length": str(stat.st_size),
            **_AUDIO_HEADERS,
        },
    )


@router.head("/h/{content_hash}.mp3")
def head_pronunciation_audio_hash(content_hash: str):
    """HEAD for Messenger hash URLs (alphanumeric path, no encoding issues)."""
    path = audio_path_for_content_hash(content_hash, get_pronunciation_audio_dir())
    if path is None:
        raise HTTPException(status_code=404, detail="Audio clip not found")
    return _head_audio(path)


@router.get("/h/{content_hash}.mp3")
def get_pronunciation_audio_hash(content_hash: str):
    """Return a cached MP3 clip by stable pronunciation content hash."""
    path = audio_path_for_content_hash(content_hash, get_pronunciation_audio_dir())
    if path is None:
        raise HTTPException(status_code=404, detail="Audio clip not found")
    return _audio_file_response(path)


@router.head("/{filename:path}")
def head_pronunciation_audio(filename: str):
    """HEAD for Facebook/Messenger URL probes (must not return 405)."""
    path = _resolve_audio_path(filename)
    return _head_audio(path)


@router.get("/{filename:path}")
def get_pronunciation_audio(filename: str):
    """Return a cached MP3 clip by human-readable filename."""
    path = _resolve_audio_path(filename)
    return _audio_file_response(path)
