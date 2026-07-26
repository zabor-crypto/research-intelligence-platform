"""Runs LLM extraction over stored documents and persists validated results."""

from __future__ import annotations

import logging
import re
from pathlib import Path

from sqlalchemy.orm import Session

from research_intel.extraction.schemas import ExtractionRecord
from research_intel.extraction.validators import validate_extraction
from research_intel.llm.base import LLMClient
from research_intel.storage import repositories as repo
from research_intel.storage.models import Document, Extraction

logger = logging.getLogger(__name__)


def load_document_text(document: Document) -> str:
    """Read the parsed text for a document from disk (or fall back to abstract)."""
    if document.text_path and Path(document.text_path).is_file():
        return Path(document.text_path).read_text(encoding="utf-8")
    source = document.source
    if source is not None and source.abstract:
        return f"{source.title}\n\n{source.abstract}"
    raise FileNotFoundError(
        f"document {document.id} has no readable text (text_path={document.text_path})"
    )


_PAGE_MARKER_TITLE = re.compile(r"^\s*\[\[page:\d+\]\]\s*$")


def _title_is_valid(title: str) -> bool:
    stripped = title.strip()
    return (
        len(stripped) > 3
        and not _PAGE_MARKER_TITLE.match(stripped)
        and not stripped.startswith("<")  # HTML fragments from READMEs
        and not stripped.startswith("<!--")
    )


def _resolve_title(extracted_title: str, document: Document) -> str:
    """Fall back to source metadata / filename when the text-derived title is
    garbage like ``[[page:1]]`` or an HTML fragment (v0.2 P6)."""
    if _title_is_valid(extracted_title):
        return extracted_title
    source = document.source
    if source is not None and _title_is_valid(source.title or ""):
        return source.title
    if document.text_path:
        stem = Path(document.text_path).stem
        if _title_is_valid(stem):
            return stem
    return f"document-{document.id}-{document.content_hash[:8]}"


def extract_document(session: Session, document: Document, llm: LLMClient) -> Extraction:
    """Extract one document and store the validated payload."""
    text = load_document_text(document)
    payload = llm.extract_research(
        text,
        ExtractionRecord.json_schema_for_llm(),
        source_id=str(document.source_id),
        document_id=str(document.id),
    )
    # Authoritative ids come from the DB, not the model.
    payload["source_id"] = str(document.source_id)
    payload["document_id"] = str(document.id)
    payload["title"] = _resolve_title(payload.get("title", ""), document)
    # Evidence type is provenance the pipeline knows better than the model:
    # abstract-only and README documents are graded as such regardless of
    # how paper-like the text reads.
    if document.kind == "abstract":
        payload["source_evidence_type"] = "abstract_only"
    elif document.kind == "readme":
        payload["source_evidence_type"] = "github_readme"
    elif document.source is not None and document.source.source_type == "arxiv":
        payload["source_evidence_type"] = "preprint"
    record = validate_extraction(payload)
    extraction = repo.add_extraction(session, document, record.model_dump())
    logger.info(
        "extracted document=%s style=%s hft=%s backtestability=%s",
        document.id, record.strategy_style, record.hft_or_low_latency_dependency,
        record.backtestability,
    )
    return extraction


def extract_pending(session: Session, llm: LLMClient, limit: int | None = None) -> list[Extraction]:
    """Extract all documents that have no extraction yet."""
    extractions: list[Extraction] = []
    for document in repo.documents_without_extraction(session, limit=limit):
        try:
            extractions.append(extract_document(session, document, llm))
        except Exception as exc:
            logger.error("extraction failed for document %s: %s", document.id, exc)
            repo.add_rejection(
                session, stage="extraction", entity_type="document",
                entity_ref=str(document.id), reason=str(exc),
            )
    return extractions
