"""PDF text extraction with page markers (no OCR in MVP)."""

from __future__ import annotations

import logging
from pathlib import Path

from pypdf import PdfReader

logger = logging.getLogger(__name__)

PAGE_MARKER = "\n\n[[page:{page}]]\n\n"


def extract_pdf_text(path: Path) -> tuple[str, int]:
    """Extract text from a PDF, inserting ``[[page:N]]`` markers between pages.

    Returns (text, num_pages). Raises ValueError when the PDF has no
    extractable text at all (scanned PDFs need OCR, which is out of MVP scope).
    """
    reader = PdfReader(str(path))
    parts: list[str] = []
    for page_number, page in enumerate(reader.pages, start=1):
        try:
            page_text = page.extract_text() or ""
        except Exception as exc:  # pypdf can fail on malformed pages
            logger.warning("failed to extract page %d of %s: %s", page_number, path, exc)
            page_text = ""
        parts.append(PAGE_MARKER.format(page=page_number) + page_text.strip())
    text = "".join(parts).strip()
    if not _has_meaningful_text(text):
        raise ValueError(
            f"no extractable text in {path.name}: likely a scanned PDF (OCR not supported in MVP)"
        )
    return text, len(reader.pages)


def _has_meaningful_text(text: str) -> bool:
    alnum = sum(1 for ch in text if ch.isalnum())
    return alnum >= 100
