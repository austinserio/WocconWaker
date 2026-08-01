"""
Phase 1: Google Drive folder ingest.
Lists files in a shared folder, exports Google Docs as text, downloads PDFs and extracts text.
Uses service account credentials (folder must be shared with the service account email).
"""
import io
import json
import logging
import os
from typing import Any, Dict, List, Optional

log = logging.getLogger("drive_ingest")

GOOGLE_DOCS_MIME = "application/vnd.google-apps.document"
PDF_MIME = "application/pdf"
GOOGLE_FOLDER_MIME = "application/vnd.google-apps.folder"


def _resolved_folder_id(folder_id: Optional[str]) -> str:
    """Drive folder to ingest: explicit arg, else DRIVE_FOLDER_ID env (required for public installs)."""
    if folder_id is not None and str(folder_id).strip():
        return str(folder_id).strip()
    env_id = (os.environ.get("DRIVE_FOLDER_ID") or "").strip()
    if env_id:
        return env_id
    raise RuntimeError(
        "DRIVE_FOLDER_ID is not set. Export it or add it to .env (copy from .env.example), "
        "or pass folder_id when calling ingest APIs."
    )


# Sync state: only re-fetch and re-extract when Drive file modifiedTime changes
SYNC_STATE_FILENAME = "sync_state.json"


def _staging_dir() -> str:
    """Staging directory for Drive extraction. Haiku uses drive_staging_haiku so Sonnet output is not overwritten."""
    if os.environ.get("DRIVE_STAGING_DIR"):
        return os.environ.get("DRIVE_STAGING_DIR", "woccon_language/drive_staging")
    if "haiku" in (os.environ.get("ANTHROPIC_MODEL") or "").lower():
        return "woccon_language/drive_staging_haiku"
    return "woccon_language/drive_staging"


def load_sync_state() -> Dict[str, Any]:
    """Load sync_state.json from staging dir. Keys: file_id -> { modified_time, staging_file }."""
    path = os.path.join(_staging_dir(), SYNC_STATE_FILENAME)
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        log.warning("Could not load sync state from %s: %s", path, e)
        return {}


def save_sync_state(state: Dict[str, Any]) -> None:
    """Write sync_state.json to staging dir."""
    path = os.path.join(_staging_dir(), SYNC_STATE_FILENAME)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)
    log.info("Wrote sync state (%d entries) to %s", len(state), path)


def _get_credentials():
    """Build credentials: service account from JSON path, or API key (may not work for shared folders)."""
    creds = None
    json_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    if json_path and os.path.isfile(json_path):
        from google.oauth2 import service_account
        SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]
        creds = service_account.Credentials.from_service_account_file(json_path, scopes=SCOPES)
        log.info("Using service account credentials from %s", json_path)
        return creds

    api_key = os.environ.get("GOOGLE_DRIVE_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if api_key:
        log.info("Using API key for Drive (may not work for shared folders)")
        return api_key

    raise RuntimeError(
        "No Drive credentials. Set GOOGLE_APPLICATION_CREDENTIALS to the path of your service account JSON "
        "(recommended for shared folders), or GOOGLE_DRIVE_API_KEY for public access."
    )


def _build_drive_service(credentials: Any):
    """Build Drive API v3 service from credentials."""
    from googleapiclient.discovery import build
    from googleapiclient.http import build_http

    if isinstance(credentials, str):
        # API key: build with developerKey
        http = build_http()
        service = build("drive", "v3", http=http, developerKey=credentials)
        return service
    # Service account (or other Credentials)
    from googleapiclient.discovery import build
    service = build("drive", "v3", credentials=credentials)
    return service


def list_files_in_folder(
    folder_id: Optional[str] = None,
    *,
    service: Any = None,
    include_trashed: bool = False,
) -> List[Dict[str, Any]]:
    """
    List all files in the given Drive folder.
    Returns list of dicts with id, name, mimeType, modifiedTime.
    """
    folder_id = _resolved_folder_id(folder_id)
    if not service:
        creds = _get_credentials()
        service = _build_drive_service(creds)

    q = f"'{folder_id}' in parents"
    if not include_trashed:
        q += " and trashed = false"
    files: List[Dict[str, Any]] = []
    page_token = None
    while True:
        resp = service.files().list(
            q=q,
            pageSize=100,
            fields="nextPageToken, files(id, name, mimeType, modifiedTime)",
            pageToken=page_token,
        ).execute()
        files.extend(resp.get("files", []))
        page_token = resp.get("nextPageToken")
        if not page_token:
            break
    return files


def list_all_files_recursive(
    folder_id: str,
    service: Any,
    *,
    path_prefix: str = "",
    include_trashed: bool = False,
) -> List[Dict[str, Any]]:
    """
    Recursively list all files (Docs, PDFs, etc.) in folder_id and all subfolders.
    Returns a flat list of dicts with id, name, mimeType, modifiedTime, path (e.g. "Subfolder/name").
    Folders are not included in the result; only files are.
    """
    items = list_files_in_folder(folder_id, service=service, include_trashed=include_trashed)
    flat: List[Dict[str, Any]] = []
    for f in items:
        fid = f["id"]
        name = f.get("name", "")
        mime = f.get("mimeType", "")
        modified = f.get("modifiedTime", "")
        current_path = f"{path_prefix}{name}" if path_prefix else name
        if mime == GOOGLE_FOLDER_MIME:
            sub = list_all_files_recursive(
                fid, service, path_prefix=f"{current_path}/", include_trashed=include_trashed
            )
            flat.extend(sub)
        else:
            flat.append({
                "id": fid,
                "name": name,
                "mimeType": mime,
                "modifiedTime": modified,
                "path": current_path,
            })
    return flat


def fetch_doc_text(service: Any, file_id: str) -> str:
    """Export a Google Doc as plain text."""
    data = service.files().export(fileId=file_id, mimeType="text/plain").execute()
    if isinstance(data, bytes):
        return data.decode("utf-8", errors="replace")
    return str(data)


def fetch_doc_bytes(service: Any, file_id: str) -> bytes:
    return fetch_doc_text(service, file_id).encode("utf-8")


def fetch_pdf_bytes(service: Any, file_id: str) -> bytes:
    data = service.files().get_media(fileId=file_id).execute()
    if not isinstance(data, bytes):
        data = bytes(data) if data else b""
    return data


def _source_url(file_id: str) -> str:
    return f"https://drive.google.com/file/d/{file_id}/view"


def _text_from_pdf_bytes(data: bytes) -> tuple:
    import re

    from panel_api.services.pdf_text import extract_pdf_text

    marked, method = extract_pdf_text(data)
    plain = re.sub(r"\[\[PAGE\s+\d+\]\]\s*", "", marked).strip()
    return plain, method


def _text_from_doc_bytes(data: bytes) -> tuple:
    text = data.decode("utf-8", errors="replace")
    return text, "google_doc"


def resolve_file_text(
    service: Any,
    file_id: str,
    mime: str,
    modified: str,
    path: str,
) -> tuple:
    """Return (text, text_method). Prefers text cache, then archived source, then Drive."""
    import drive_ingest_archive as archive

    cached = archive.load_text_cache(file_id, modified)
    if cached and (cached.get("text") or "").strip():
        log.info("Using cached text for %s", path)
        return cached["text"], cached.get("text_method") or "cached"

    source_url = _source_url(file_id)
    raw = archive.read_archived_bytes(file_id, modified)
    if raw is not None:
        log.info("Using archived source for %s", path)
    else:
        log.info("Fetching from Drive: %s", path)
        if mime == GOOGLE_DOCS_MIME:
            raw = fetch_doc_bytes(service, file_id)
        else:
            raw = fetch_pdf_bytes(service, file_id)
        archive.archive_source(
            file_id=file_id,
            modified_time=modified,
            path=path,
            mime_type=mime,
            data=raw,
            source_url=source_url,
        )

    if mime == GOOGLE_DOCS_MIME:
        text, method = _text_from_doc_bytes(raw)
    else:
        text, method = _text_from_pdf_bytes(raw)

    if (text or "").strip():
        archive.save_text_cache(
            file_id=file_id,
            modified_time=modified,
            path=path,
            text=text,
            text_method=method,
        )
    return text, method


def fetch_pdf_text(service: Any, file_id: str) -> str:
    """Download a PDF and extract text (pdfplumber + optional vision OCR)."""
    try:
        text, _ = _text_from_pdf_bytes(fetch_pdf_bytes(service, file_id))
        return text
    except Exception as e:
        log.warning("PDF text extraction failed for %s: %s", file_id, e)
        return ""


def _is_403(e: Exception) -> bool:
    """Check if exception is a Drive API 403 (forbidden)."""
    try:
        from googleapiclient.errors import HttpError
        if isinstance(e, HttpError):
            return e.resp.status == 403
    except ImportError:
        pass
    return "403" in str(e).lower()


def ingest_folder(
    folder_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    List all files in the folder and fetch text for each Doc and PDF.
    Returns list of { "file_id", "name", "mime_type", "modified_time", "text" }.
    Files we don't support (e.g. Sheets) get text = "" and a log.
    """
    from googleapiclient.errors import HttpError
    folder_id = _resolved_folder_id(folder_id)
    creds = _get_credentials()
    service = _build_drive_service(creds)
    try:
        file_list = list_all_files_recursive(folder_id, service)
    except HttpError as e:
        status = getattr(e.resp, "status", None)
        if status == 401:
            raise RuntimeError(
                "Drive API returned 401. This API does not accept API keys; it requires OAuth2 or a service account. "
                "Set GOOGLE_APPLICATION_CREDENTIALS to the path of your service account JSON key, then share the "
                "Drive folder with that account's email (e.g. xxx@project.iam.gserviceaccount.com)."
            ) from e
        if status == 403:
            raise RuntimeError(
                "Drive API returned 403 Forbidden. Share the folder with your service account email and use "
                "GOOGLE_APPLICATION_CREDENTIALS pointing to that account's JSON key."
            ) from e
        raise
    limit_raw = os.environ.get("DRIVE_INGEST_LIMIT", "").strip()
    limit = int(limit_raw) if limit_raw.isdigit() else 0
    name_filter = (os.environ.get("DRIVE_INGEST_FILTER") or "").strip()
    if name_filter:
        file_list = [f for f in file_list if name_filter.lower() in (f.get("path") or f.get("name") or "").lower()]
        log.info("Filtering to %d files matching %r", len(file_list), name_filter)

    force_full = (os.environ.get("DRIVE_INGEST_FORCE_FULL") or "").strip().lower() in ("1", "true", "yes")
    sync_state = {} if force_full else load_sync_state()
    if force_full:
        log.info("DRIVE_INGEST_FORCE_FULL=1: re-fetching and re-extracting all files (ignoring sync_state)")
    results = []
    content_count = 0
    skipped_sync = 0
    for f in file_list:
        if limit and content_count >= limit:
            log.info("Stopping after %d files (DRIVE_INGEST_LIMIT=%d)", limit, limit)
            break
        fid = f["id"]
        name = f.get("name", "")
        mime = f.get("mimeType", "")
        modified = f.get("modifiedTime", "")
        path = f.get("path", name)
        entry = {
            "file_id": fid,
            "name": name,
            "path": path,
            "mime_type": mime,
            "modified_time": modified,
            "text": "",
        }
        if mime == GOOGLE_DOCS_MIME or mime == PDF_MIME:
            prev = sync_state.get(fid)
            if prev and prev.get("modified_time") == modified:
                entry["use_existing_staging"] = True
                entry["staging_file"] = prev.get("staging_file") or ""
                skipped_sync += 1
                log.info("Skipping unchanged (sync_state): %s", path)
            else:
                entry["use_existing_staging"] = False
                try:
                    if mime == GOOGLE_DOCS_MIME:
                        log.info("Fetching Google Doc: %s", path)
                    else:
                        log.info("Fetching PDF: %s", path)
                    text, text_method = resolve_file_text(service, fid, mime, modified, path)
                    entry["text"] = text
                    entry["text_method"] = text_method
                    if mime == PDF_MIME:
                        log.info("Fetched PDF: %s (%d chars, %s)", path, len(entry["text"] or ""), text_method)
                    content_count += 1
                except Exception as e:
                    log.exception("Failed to fetch %s (%s): %s", name, fid, e)
                    entry["error"] = str(e)
        else:
            log.info("Skipping unsupported type %s: %s", mime, name)
        results.append(entry)
    if skipped_sync:
        log.info("Skipped %d file(s) already synced (unchanged modifiedTime)", skipped_sync)
    return results


def run_phase1_verify(skip_extraction: bool = False) -> Dict[str, Any]:
    """
    Phase 1+3: list files, fetch text, then (unless skip_extraction) run structured extraction and write staging.
    Returns a summary dict for inspection.
    """
    folder_id = _resolved_folder_id(None)
    ingest_limit = os.environ.get("DRIVE_INGEST_LIMIT", "").strip()
    summary = {
        "folder_id": folder_id,
        "ingest_limit": int(ingest_limit) if ingest_limit.isdigit() else None,
        "files_listed": 0,
        "docs_fetched": 0,
        "pdfs_fetched": 0,
        "errors": [],
        "sample_doc_preview": None,
        "sample_pdf_preview": None,
        "extraction_lexicon_count": 0,
        "extraction_grammar_count": 0,
        "extraction_pronunciation_count": 0,
        "extraction_cultural_count": 0,
        "staging_path": None,
        "staging_dir": None,
        "staging_manifest": None,
        "staging_files_written": 0,
    }
    try:
        results = ingest_folder(folder_id)
    except Exception as e:
        summary["errors"].append(str(e))
        err_str = str(e).lower()
        if _is_403(e) or "403" in err_str or "401" in err_str or "api keys are not supported" in err_str:
            summary["errors"].append(
                "Fix: Drive requires a service account JSON. Set GOOGLE_APPLICATION_CREDENTIALS to its path and share the folder with that account's email. See DRIVE_INGEST.md."
            )
        log.exception("Phase 1 ingest failed")
        return summary

    summary["files_listed"] = len(results)
    summary["skipped_unchanged"] = sum(1 for r in results if r.get("use_existing_staging"))
    for r in results:
        mime = r.get("mime_type", "")
        if mime == GOOGLE_DOCS_MIME and r.get("text"):
            summary["docs_fetched"] += 1
            if summary["sample_doc_preview"] is None:
                summary["sample_doc_preview"] = {
                    "name": r["name"],
                    "preview": (r["text"] or "")[:500],
                }
        elif mime == PDF_MIME:
            if r.get("text"):
                summary["pdfs_fetched"] += 1
                if summary["sample_pdf_preview"] is None:
                    summary["sample_pdf_preview"] = {
                        "name": r["name"],
                        "preview": (r["text"] or "")[:500],
                    }
            if r.get("error"):
                summary["errors"].append(f"PDF {r['name']}: {r['error']}")
        if r.get("error"):
            summary["errors"].append(f"{r['name']}: {r['error']}")

    # Phase 3: structured extraction and staging (unless disabled via skip_extraction or SKIP_EXTRACTION=1)
    if os.environ.get("SKIP_EXTRACTION", "").strip().lower() in ("1", "true", "yes"):
        skip_extraction = True
    if not skip_extraction and any((r.get("text") or "").strip() for r in results):
        try:
            import ingest_progress

            ingest_progress.write(phase="starting", percent=0, message="Starting extraction")
            import drive_extract
            staging = drive_extract.extract_from_ingest_results(results, per_file=True)
            if staging.get("per_file"):
                summary["extraction_lexicon_count"] = staging.get("extraction_lexicon_count", 0)
                summary["extraction_grammar_count"] = staging.get("extraction_grammar_count", 0)
                summary["extraction_pronunciation_count"] = staging.get("extraction_pronunciation_count", 0)
                summary["extraction_cultural_count"] = staging.get("extraction_cultural_count", 0)
                summary["staging_dir"] = staging.get("staging_dir")
                summary["staging_manifest"] = staging.get("manifest_path")
                summary["staging_files_written"] = staging.get("files_written", 0)
            else:
                summary["extraction_lexicon_count"] = len(staging.get("lexicon_entries") or [])
                summary["extraction_grammar_count"] = len(staging.get("grammar_notes") or [])
                summary["extraction_pronunciation_count"] = len(staging.get("pronunciation_notes") or [])
                summary["staging_path"] = drive_extract.write_staging(staging)
        except Exception as e:
            log.exception("Phase 3 extraction failed: %s", e)
            summary["errors"].append(f"Extraction: {e}")

    return summary


if __name__ == "__main__":
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    import json
    import sys
    try:
        summary = run_phase1_verify()
        out = json.dumps(summary, indent=2)
        print(out, flush=True)
        sys.exit(0 if not summary.get("errors") else 1)
    except Exception as e:
        print(json.dumps({"error": str(e), "errors": [str(e)]}), flush=True)
        sys.exit(1)
