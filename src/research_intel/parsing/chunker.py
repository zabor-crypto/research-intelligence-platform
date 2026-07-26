"""Chunking: semantic sections first, character windows as fallback."""

from __future__ import annotations

import re
from typing import Any, TypedDict

HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)
PAGE_MARKER_RE = re.compile(r"\[\[page:(\d+)\]\]")

DEFAULT_MAX_CHARS = 4000
DEFAULT_OVERLAP = 200


class Chunk(TypedDict):
    text: str
    section_title: str | None
    page_number: int | None
    char_start: int
    char_end: int


def chunk_document(
    text: str,
    max_chars: int = DEFAULT_MAX_CHARS,
    overlap: int = DEFAULT_OVERLAP,
) -> list[Chunk]:
    """Split text into chunks, preferring markdown-heading sections.

    Oversized sections are further split into overlapping character windows.
    Page numbers from ``[[page:N]]`` markers (PDF extraction) are carried
    through when present.
    """
    if not text.strip():
        return []
    sections = _split_by_headings(text)
    chunks: list[Chunk] = []
    for title, start, end in sections:
        body = text[start:end]
        if len(body) <= max_chars:
            _append(chunks, text, body, title, start)
        else:
            for win_start in range(0, len(body), max_chars - overlap):
                window = body[win_start : win_start + max_chars]
                if window.strip():
                    _append(chunks, text, window, title, start + win_start)
    return chunks


def _append(
    chunks: list[Chunk], full_text: str, body: str, title: str | None, offset: int
) -> None:
    stripped = body.strip()
    if not stripped:
        return
    lead = len(body) - len(body.lstrip())
    start = offset + lead
    chunks.append(
        Chunk(
            text=stripped,
            section_title=title,
            page_number=_page_at(full_text, start),
            char_start=start,
            char_end=start + len(stripped),
        )
    )


def _split_by_headings(text: str) -> list[tuple[str | None, int, int]]:
    """Return (section_title, start, end) spans. Whole text if no headings."""
    matches = list(HEADING_RE.finditer(text))
    if not matches:
        return [(None, 0, len(text))]
    sections: list[tuple[str | None, int, int]] = []
    if matches[0].start() > 0:
        sections.append((None, 0, matches[0].start()))
    for i, match in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        sections.append((match.group(2).strip(), match.start(), end))
    return sections


def _page_at(text: str, position: int) -> int | None:
    """Latest ``[[page:N]]`` marker starting at or before `position`, if any."""
    page: int | None = None
    for marker in PAGE_MARKER_RE.finditer(text):
        if marker.start() > position:
            break
        page = int(marker.group(1))
    return page


def chunks_as_dicts(chunks: list[Chunk]) -> list[dict[str, Any]]:
    return [dict(c) for c in chunks]
