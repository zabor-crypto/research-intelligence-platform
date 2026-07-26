"""Manual collector: ingest local .pdf/.txt/.md/.html files."""

from __future__ import annotations

import logging
from pathlib import Path

from research_intel.collectors.base import (
    RawDocument,
    RawSourceRecord,
    SourceCollector,
    content_checksum,
)
from research_intel.parsing.html_parser import extract_html_text
from research_intel.parsing.pdf_parser import extract_pdf_text
from research_intel.parsing.text_parser import extract_plain_text

logger = logging.getLogger(__name__)

SUPPORTED_SUFFIXES = {".pdf", ".txt", ".md", ".html", ".htm"}


class ManualCollector(SourceCollector):
    """Treats a local path (file or directory) as the search space."""

    name = "manual"

    def search(self, query: str, limit: int, since: str | None = None) -> list[RawSourceRecord]:
        """`query` is a filesystem path; returns one record per supported file."""
        root = Path(query).expanduser()
        if not root.exists():
            raise FileNotFoundError(f"path does not exist: {root}")
        files = (
            [root]
            if root.is_file()
            else sorted(p for p in root.rglob("*") if p.suffix.lower() in SUPPORTED_SUFFIXES)
        )
        records: list[RawSourceRecord] = []
        for path in files[:limit]:
            if path.suffix.lower() not in SUPPORTED_SUFFIXES:
                logger.warning("skipping unsupported file type: %s", path)
                continue
            doc = self.fetch(str(path))
            text = doc.text or ""
            records.append(
                RawSourceRecord(
                    source_type="manual",
                    external_id=str(path.resolve()),
                    title=_title_from(path, text),
                    url=path.resolve().as_uri(),
                    published_date=None,
                    abstract=text[:800] or None,
                    checksum=content_checksum(text),
                    extra={"suffix": path.suffix.lower(), "size_bytes": path.stat().st_size},
                )
            )
        return records

    def fetch(self, source_id: str) -> RawDocument:
        path = Path(source_id).expanduser()
        suffix = path.suffix.lower()
        if suffix == ".pdf":
            text, num_pages = extract_pdf_text(path)
            return RawDocument(
                source_type="manual",
                external_id=str(path.resolve()),
                content_type="pdf",
                text=text,
                binary=path.read_bytes(),
                suggested_filename=path.name,
                metadata={"num_pages": num_pages},
            )
        raw = path.read_text(encoding="utf-8", errors="replace")
        if suffix in (".html", ".htm"):
            text = extract_html_text(raw)
            content_type = "html"
        else:
            text = extract_plain_text(raw)
            content_type = "markdown" if suffix == ".md" else "text"
        return RawDocument(
            source_type="manual",
            external_id=str(path.resolve()),
            content_type=content_type,
            text=text,
            suggested_filename=path.name,
        )


def _title_from(path: Path, text: str) -> str:
    """Use the first markdown heading or first non-empty line, else filename."""
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            return stripped.lstrip("# ").strip() or path.stem
        if stripped:
            return stripped[:120]
    return path.stem
