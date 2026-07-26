"""Ingestion pipeline: collector records -> sources, documents, chunks on disk/DB."""

from __future__ import annotations

import hashlib
import logging
import re

from sqlalchemy.orm import Session

from research_intel.collectors.base import RawDocument, RawSourceRecord, SourceCollector
from research_intel.config import Settings
from research_intel.parsing.chunker import chunk_document, chunks_as_dicts
from research_intel.storage import repositories as repo
from research_intel.storage.models import Document, Source

logger = logging.getLogger(__name__)


def _safe_name(text: str, max_len: int = 80) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", text)[:max_len].strip("_") or "unnamed"


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()


def store_document_text(
    session: Session,
    settings: Settings,
    source: Source,
    text: str,
    *,
    kind: str,
    raw_doc: RawDocument | None = None,
) -> tuple[Document, bool]:
    """Persist parsed text to disk, create the document row, and chunk it."""
    settings.ensure_dirs()
    content_hash = _hash(text)
    base = f"{source.source_type}_{source.id}_{_safe_name(source.title)}"

    raw_path: str | None = None
    num_pages: int | None = None
    if raw_doc is not None:
        num_pages = raw_doc.metadata.get("num_pages")
        if raw_doc.binary:
            raw_file = settings.raw_dir / (raw_doc.suggested_filename or f"{base}.bin")
            raw_file.write_bytes(raw_doc.binary)
            raw_path = str(raw_file)
            if raw_doc.content_type == "pdf":
                source.pdf_path = raw_path

    text_file = settings.parsed_dir / f"{base}.txt"
    text_file.write_text(text, encoding="utf-8")
    source.raw_text_path = str(text_file)

    document, created = repo.add_document(
        session, source,
        kind=kind, content_hash=content_hash,
        raw_path=raw_path, text_path=str(text_file), num_pages=num_pages,
    )
    if created:
        repo.add_chunks(session, document, chunks_as_dicts(chunk_document(text)))
    return document, created


def ingest_records(
    session: Session,
    settings: Settings,
    collector: SourceCollector,
    records: list[RawSourceRecord],
    *,
    fetch_fulltext: bool = False,
) -> tuple[int, int]:
    """Store collector records. Returns (num_found, num_new_sources).

    For manual sources the fulltext is always fetched and stored. For API
    sources a document is created from the abstract so extraction can run
    even without downloading the fulltext; pass fetch_fulltext=True to also
    call collector.fetch() (e.g. arXiv PDFs, GitHub READMEs).
    """
    num_new = 0
    for record in records:
        source, created = repo.upsert_source(session, record)
        if created:
            num_new += 1
        text: str | None = None
        raw_doc: RawDocument | None = None
        kind = "abstract"
        if collector.name == "manual" or fetch_fulltext:
            try:
                raw_doc = collector.fetch(record.external_id)
                if raw_doc.content_type == "pdf" and raw_doc.text is None:
                    # API PDF download without local parsing: parse now.
                    from research_intel.parsing.pdf_parser import extract_pdf_text

                    tmp = settings.raw_dir / (
                        raw_doc.suggested_filename or f"{_safe_name(record.external_id)}.pdf"
                    )
                    settings.ensure_dirs()
                    tmp.write_bytes(raw_doc.binary or b"")
                    text, num_pages = extract_pdf_text(tmp)
                    raw_doc.metadata["num_pages"] = num_pages
                else:
                    text = raw_doc.text
                kind = "readme" if collector.name == "github" else "fulltext"
            except Exception as exc:
                logger.error("fetch failed for %s: %s", record.external_id, exc)
                repo.add_rejection(
                    session, stage="ingestion", entity_type="source",
                    entity_ref=record.external_id, reason=f"fetch_failed: {exc}",
                )
        if text is None and record.abstract:
            text = f"{record.title}\n\n{record.abstract}"
            kind = "abstract"
        if text:
            store_document_text(session, settings, source, text, kind=kind, raw_doc=raw_doc)
        else:
            logger.warning("no text available for source %s", record.external_id)
    return len(records), num_new
