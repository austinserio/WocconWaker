"""PDF text extraction with Claude vision OCR fallback for scanned pages."""
import io
import logging
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, Dict, List, Optional, Tuple

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


def _lossy_layer_recheck_enabled() -> bool:
    v = os.getenv("PDF_OCR_RECHECK_ASCII_SCANS", "true").strip().lower()
    return v in ("true", "1", "yes")


def _min_image_coverage() -> float:
    try:
        return min(1.0, max(0.0, float(os.getenv("PDF_OCR_SCAN_IMAGE_COVERAGE", "0.5"))))
    except ValueError:
        return 0.5


def _ocr_dpi() -> int:
    try:
        return max(72, int(os.getenv("PDF_OCR_DPI", "200")))
    except ValueError:
        return 200


def _ocr_parallel_workers() -> int:
    try:
        return max(1, int(os.environ.get("PDF_OCR_PARALLEL_WORKERS", "1")))
    except ValueError:
        return 1


def _ocr_num_predict() -> int:
    try:
        return max(512, int(os.getenv("PDF_OCR_NUM_PREDICT", "2048")))
    except ValueError:
        return 2048


def _free_vram_for_ocr() -> None:
    """Unload other models before vision OCR when text/vision use different Ollama tags."""
    from llm_client import ollama_models_unified, ollama_unload_loaded_models

    if ollama_models_unified():
        return
    if os.getenv("PDF_OCR_UNLOAD_TEXT_MODEL", "true").strip().lower() not in ("true", "1", "yes"):
        return
    log.info("Freeing VRAM before vision OCR (unloading loaded Ollama models)")
    ollama_unload_loaded_models()


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


# Accented Latin, IPA extensions, modifier letters and combining marks. Deliberately
# excludes curly quotes and other typographic non-ASCII, which say nothing about phonetics.
_PHONETIC_CHAR = re.compile(r"[\u00C0-\u024F\u0250-\u02FF\u0300-\u036F]")


def _page_image_coverage(page) -> float:
    """Largest single embedded image as a fraction of page area."""
    try:
        rect = page.rect
        page_area = float(rect.width) * float(rect.height)
        if page_area <= 0:
            return 0.0
        best = 0.0
        for info in page.get_image_info():
            bbox = info.get("bbox")
            if not bbox:
                continue
            x0, y0, x1, y1 = bbox
            area = abs((x1 - x0) * (y1 - y0))
            best = max(best, area / page_area)
        return best
    except Exception:
        return 0.0


def pages_with_lossy_text_layer(data: bytes, page_texts: List[str]) -> List[bool]:
    """Flag image-backed pages whose embedded text layer carries no phonetic characters.

    Scanned journal PDFs ship an OCR text layer that reads as dense, clean English while
    having silently dropped every diacritic. Character-count thresholds score those pages
    as good text, so the phonetic notation the comparative pipeline depends on is lost
    without any error. Requiring a full-page image keeps born-digital English documents,
    which legitimately contain no diacritics, from being re-OCRed.
    """
    if not _lossy_layer_recheck_enabled() or not page_texts:
        return [False] * len(page_texts)

    try:
        import fitz
    except ImportError:
        return [False] * len(page_texts)

    min_coverage = _min_image_coverage()
    threshold = _min_chars_per_page()
    flags = [False] * len(page_texts)
    try:
        with fitz.open(stream=data, filetype="pdf") as doc:
            for i, text in enumerate(page_texts):
                if i >= len(doc):
                    break
                body = (text or "").strip()
                if len(body) < threshold or _PHONETIC_CHAR.search(body):
                    continue
                if _page_image_coverage(doc[i]) >= min_coverage:
                    flags[i] = True
    except Exception as e:
        log.warning("Could not inspect PDF pages for a lossy text layer: %s", e)
        return [False] * len(page_texts)
    return flags


def render_pdf_page_images(data: bytes, *, dpi: Optional[int] = None) -> List[bytes]:
    import fitz

    doc = fitz.open(stream=data, filetype="pdf")
    page_numbers = list(range(1, len(doc) + 1))
    doc.close()
    rendered = render_pdf_pages(data, page_numbers, dpi=dpi)
    return [rendered.get(n, b"") for n in page_numbers]


def render_pdf_pages(
    data: bytes,
    page_numbers: List[int],
    *,
    dpi: Optional[int] = None,
) -> Dict[int, bytes]:
    """Render selected 1-based page numbers to PNG bytes."""
    if not page_numbers:
        return {}
    import fitz

    doc = fitz.open(stream=data, filetype="pdf")
    scale = (dpi or _ocr_dpi()) / 72.0
    matrix = fitz.Matrix(scale, scale)
    images: Dict[int, bytes] = {}
    try:
        for page_num in page_numbers:
            if page_num < 1 or page_num > len(doc):
                continue
            pix = doc[page_num - 1].get_pixmap(matrix=matrix, alpha=False)
            images[page_num] = pix.tobytes("png")
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
        options={"temperature": 0.0, "num_predict": _ocr_num_predict()},
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
    Extract marked text from PDF bytes. Uses pdfplumber first; sends pages that are sparse
    or backed by a diacritic-free scan text layer to vision OCR.
    Returns (marked_text, method) where method is text | vision | hybrid.
    """
    page_texts = extract_pages_with_pdfplumber(data)
    if not page_texts:
        page_texts = [""]

    sparse_flags = pages_needing_ocr(page_texts)
    lossy_flags = pages_with_lossy_text_layer(data, page_texts)
    if any(lossy_flags):
        log.info(
            "%d page(s) have a dense but diacritic-free text layer over a full-page scan; "
            "re-OCRing them to recover phonetic characters",
            sum(lossy_flags),
        )
    ocr_flags = [s or l for s, l in zip(sparse_flags, lossy_flags)]
    method = _extraction_method(ocr_flags)

    if not any(ocr_flags):
        return mark_text_with_pages(page_texts), "text"

    if not _ocr_enabled():
        log.warning("PDF has pages needing OCR but PDF_OCR_ENABLED=false; using pdfplumber text only")
        return mark_text_with_pages(page_texts), "text"

    from llm_client import _allow_anthropic_fallback, _is_local_llm, _use_anthropic

    if not _is_local_llm() and (not _allow_anthropic_fallback() or not _use_anthropic()):
        raise ScannedPdfOcrRequiredError(
            "Scanned PDF detected; set LOCAL_LLM=true with OLLAMA_VISION_MODEL, "
            "or set ANTHROPIC_API_KEY and ALLOW_ANTHROPIC_FALLBACK=true for vision OCR."
        )

    if on_progress:
        on_progress(2, "Rendering PDF pages for OCR…")

    import fitz

    with fitz.open(stream=data, filetype="pdf") as doc:
        pdf_page_count = len(doc)

    if pdf_page_count != len(page_texts):
        while len(page_texts) < pdf_page_count:
            page_texts.append("")
        while len(ocr_flags) < pdf_page_count:
            ocr_flags.append(True)
        page_texts = page_texts[:pdf_page_count]
        ocr_flags = ocr_flags[:pdf_page_count]

    ocr_page_nums = [i for i, flag in enumerate(ocr_flags, start=1) if flag]
    log.info(
        "OCR %d pages (of %d total) at %d DPI",
        len(ocr_page_nums),
        len(page_texts),
        _ocr_dpi(),
    )

    _free_vram_for_ocr()
    page_images = render_pdf_pages(data, ocr_page_nums)

    ocr_jobs: List[Tuple[int, bytes]] = []
    for page_num in ocr_page_nums:
        png = page_images.get(page_num)
        if png:
            ocr_jobs.append((page_num, png))

    workers = _ocr_parallel_workers()
    if ocr_jobs:
        if workers > 1 and len(ocr_jobs) > 1:
            log.info("OCR %d pages with %d parallel workers", len(ocr_jobs), workers)

            def _ocr_one(job: Tuple[int, bytes]) -> Tuple[int, str]:
                page_num, png = job
                started = time.monotonic()
                text = ocr_page_vision(png, page_num)
                log.info(
                    "OCR page %d/%d done in %.1fs (%d chars)",
                    page_num,
                    len(ocr_jobs),
                    time.monotonic() - started,
                    len(text),
                )
                return page_num, text

            completed = 0
            with ThreadPoolExecutor(max_workers=workers) as pool:
                futures = {pool.submit(_ocr_one, job): job[0] for job in ocr_jobs}
                for fut in as_completed(futures):
                    page_num = futures[fut]
                    completed += 1
                    if on_progress:
                        pct = int(20 * completed / max(len(ocr_jobs), 1))
                        on_progress(pct, f"OCR page {completed}/{len(ocr_jobs)}")
                    try:
                        _, text = fut.result()
                        page_texts[page_num - 1] = text
                    except Exception as e:
                        log.warning("Vision OCR failed for page %d: %s", page_num, e)
                        if not (page_texts[page_num - 1] or "").strip():
                            raise
        else:
            for idx, (page_num, png) in enumerate(ocr_jobs, start=1):
                if on_progress:
                    pct = int(20 * idx / max(len(ocr_jobs), 1))
                    on_progress(pct, f"OCR page {idx}/{len(ocr_jobs)}")
                try:
                    started = time.monotonic()
                    page_texts[page_num - 1] = ocr_page_vision(png, page_num)
                    log.info(
                        "OCR page %d/%d done in %.1fs (%d chars)",
                        page_num,
                        len(ocr_jobs),
                        time.monotonic() - started,
                        len(page_texts[page_num - 1]),
                    )
                except Exception as e:
                    log.warning("Vision OCR failed for page %d: %s", page_num, e)
                    if not (page_texts[page_num - 1] or "").strip():
                        raise

    if ocr_jobs:
        from llm_client import ollama_models_unified, ollama_unload_model

        unload_vision = os.getenv("PDF_OCR_UNLOAD_VISION_MODEL", "true").strip().lower() in (
            "true",
            "1",
            "yes",
        )
        if unload_vision and not ollama_models_unified():
            vision_model = (os.getenv("OLLAMA_VISION_MODEL") or "qwen2.5vl:32b").strip()
            ollama_unload_model(vision_model)

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
