"""PDF text extraction with Claude vision OCR fallback for scanned pages."""
import io
import logging
import os
from typing import Callable, List, Optional, Tuple

log = logging.getLogger("pdf_text")

PAGE_MARKER = "[[PAGE {n}]]"
OCR_PROMPT = """Transcribe all visible text from this document page exactly as written.
Preserve line breaks, columns, and list structure (e.g. English= woccon pairs).
Do not summarize, paraphrase, or add commentary.
Output only the transcribed text."""

ProgressCallback = Optional[Callable[[int, str], None]]


class ScannedPdfOcrRequiredError(RuntimeError):
    """Raised when a scanned PDF needs vision OCR but Anthropic is not configured."""


def _ocr_enabled() -> bool:
    v = os.getenv("PDF_OCR_ENABLED", "true").strip().lower()
    return v in ("true", "1", "yes")


def _min_chars_per_page() -> int:
    try:
        return max(1, int(os.getenv("PDF_OCR_MIN_CHARS_PER_PAGE", "50")))
    except ValueError:
        return 50


def _ocr_dpi() -> int:
    try:
        return max(72, int(os.getenv("PDF_OCR_DPI", "200")))
    except ValueError:
        return 200


def extract_pages_with_pdfplumber(data: bytes) -> List[str]:
    import pdfplumber

    buf = io.BytesIO(data)
    parts: List[str] = []
    with pdfplumber.open(buf) as pdf:
        for page in pdf.pages:
            parts.append(page.extract_text() or "")
    return parts


def pages_needing_ocr(page_texts: List[str], *, min_chars_per_page: Optional[int] = None) -> List[bool]:
    threshold = min_chars_per_page if min_chars_per_page is not None else _min_chars_per_page()
    return [len((t or "").strip()) < threshold for t in page_texts]


def needs_any_vision_ocr(page_texts: List[str], *, min_chars_per_page: Optional[int] = None) -> bool:
    flags = pages_needing_ocr(page_texts, min_chars_per_page=min_chars_per_page)
    if not page_texts:
        return True
    if sum(len((t or "").strip()) for t in page_texts) == 0:
        return True
    return any(flags)


def render_pdf_page_images(data: bytes, *, dpi: Optional[int] = None) -> List[bytes]:
    import fitz

    doc = fitz.open(stream=data, filetype="pdf")
    scale = (dpi or _ocr_dpi()) / 72.0
    matrix = fitz.Matrix(scale, scale)
    images: List[bytes] = []
    try:
        for page in doc:
            pix = page.get_pixmap(matrix=matrix, alpha=False)
            images.append(pix.tobytes("png"))
    finally:
        doc.close()
    return images


def mark_text_with_pages(parts: List[str]) -> str:
    marked = []
    for i, text in enumerate(parts, start=1):
        if text and text.strip():
            marked.append(f"{PAGE_MARKER.format(n=i)}\n{text.strip()}")
    return "\n\n".join(marked) if marked else ""


def ocr_page_vision(png_bytes: bytes, page_num: int, model: Optional[str] = None) -> str:
    from llm_client import llm_vision_chat

    prompt = f"{OCR_PROMPT}\n\nThis is page {page_num} of the document."
    out = llm_vision_chat(
        model or "",
        prompt,
        [png_bytes],
        options={"temperature": 0.0, "num_predict": 4096},
    )
    content = (out.get("message") or {}).get("content") or ""
    if content.startswith("Error:"):
        raise RuntimeError(content)
    return content.strip()


def _extraction_method(ocr_flags: List[bool]) -> str:
    if not ocr_flags:
        return "text"
    if all(ocr_flags):
        return "vision"
    if any(ocr_flags):
        return "hybrid"
    return "text"


def extract_pdf_text(
    data: bytes,
    *,
    on_progress: ProgressCallback = None,
) -> Tuple[str, str]:
    """
    Extract marked text from PDF bytes. Uses pdfplumber first; OCRs sparse pages via Claude vision.
    Returns (marked_text, method) where method is text | vision | hybrid.
    """
    page_texts = extract_pages_with_pdfplumber(data)
    if not page_texts:
        page_texts = [""]

    ocr_flags = pages_needing_ocr(page_texts)
    method = _extraction_method(ocr_flags)

    if not any(ocr_flags):
        return mark_text_with_pages(page_texts), "text"

    if not _ocr_enabled():
        log.warning("PDF has sparse pages but PDF_OCR_ENABLED=false; using pdfplumber text only")
        return mark_text_with_pages(page_texts), "text"

    from llm_client import _use_anthropic

    if not _use_anthropic():
        raise ScannedPdfOcrRequiredError(
            "Scanned PDF detected; set ANTHROPIC_API_KEY for vision OCR."
        )

    if on_progress:
        on_progress(2, "Rendering PDF pages for OCR…")

    page_images = render_pdf_page_images(data)
    total = len(page_images)
    if total != len(page_texts):
        # Align counts if pdfplumber and pymupdf disagree (rare)
        while len(page_texts) < total:
            page_texts.append("")
        while len(ocr_flags) < total:
            ocr_flags.append(True)
        page_texts = page_texts[:total]
        ocr_flags = ocr_flags[:total]

    for i, (needs_ocr, png) in enumerate(zip(ocr_flags, page_images), start=1):
        if not needs_ocr:
            continue
        if on_progress:
            pct = int(20 * i / max(total, 1))
            on_progress(pct, f"OCR page {i}/{total}")
        try:
            page_texts[i - 1] = ocr_page_vision(png, i)
        except Exception as e:
            log.warning("Vision OCR failed for page %d: %s", i, e)
            if not (page_texts[i - 1] or "").strip():
                raise

    marked = mark_text_with_pages(page_texts)
    if not marked.strip():
        raise RuntimeError("Vision OCR produced no text from scanned PDF")
    return marked, method


def extract_pdf_plain(data: bytes, *, on_progress: ProgressCallback = None) -> str:
    """Plain joined text without page markers (legacy bulk ingest)."""
    marked, _ = extract_pdf_text(data, on_progress=on_progress)
    if not marked:
        return ""
    import re

    return re.sub(r"\[\[PAGE\s+\d+\]\]\s*", "", marked).strip()
