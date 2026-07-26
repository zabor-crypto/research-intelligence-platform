"""Repository functions: all DB access for the pipeline goes through here."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from research_intel.collectors.base import RawSourceRecord
from research_intel.storage.models import (
    BacktestHandoffSpec,
    Document,
    DocumentChunk,
    Extraction,
    IngestionRun,
    RejectedItem,
    Score,
    Source,
    StrategyHypothesis,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------- sources


def find_duplicate_source(session: Session, record: RawSourceRecord) -> Source | None:
    """Dedup by (source_type, external_id), DOI, URL, then content checksum."""
    stmt = select(Source).where(
        Source.source_type == record.source_type, Source.external_id == record.external_id
    )
    if (existing := session.scalars(stmt).first()) is not None:
        return existing
    if record.doi:
        if (existing := session.scalars(select(Source).where(Source.doi == record.doi)).first()) is not None:
            return existing
    if record.url:
        if (existing := session.scalars(select(Source).where(Source.url == record.url)).first()) is not None:
            return existing
    if record.checksum:
        if (
            existing := session.scalars(
                select(Source).where(Source.checksum == record.checksum)
            ).first()
        ) is not None:
            return existing
    return None


def upsert_source(session: Session, record: RawSourceRecord) -> tuple[Source, bool]:
    """Insert the record unless a duplicate exists. Returns (source, created)."""
    if (existing := find_duplicate_source(session, record)) is not None:
        logger.debug("duplicate source skipped: %s/%s", record.source_type, record.external_id)
        return existing, False
    source = Source(
        source_type=record.source_type,
        external_id=record.external_id,
        url=record.url,
        title=record.title,
        authors=record.authors,
        published_date=record.published_date,
        abstract=record.abstract,
        doi=record.doi,
        citation_count=record.citation_count,
        checksum=record.checksum,
        extra=record.extra,
    )
    session.add(source)
    session.flush()
    return source, True


def list_sources(session: Session) -> list[Source]:
    return list(session.scalars(select(Source).order_by(Source.id)))


# ---------------------------------------------------------------- documents


def add_document(
    session: Session,
    source: Source,
    *,
    kind: str,
    content_hash: str,
    raw_path: str | None = None,
    text_path: str | None = None,
    num_pages: int | None = None,
    parse_status: str = "parsed",
) -> tuple[Document, bool]:
    """Insert a document unless one with the same content hash already exists."""
    existing = session.scalars(
        select(Document).where(Document.content_hash == content_hash)
    ).first()
    if existing is not None:
        return existing, False
    doc = Document(
        source_id=source.id,
        kind=kind,
        raw_path=raw_path,
        text_path=text_path,
        content_hash=content_hash,
        num_pages=num_pages,
        parse_status=parse_status,
    )
    session.add(doc)
    session.flush()
    return doc, True


def add_chunks(session: Session, document: Document, chunks: list[dict[str, Any]]) -> None:
    for i, chunk in enumerate(chunks):
        session.add(
            DocumentChunk(
                document_id=document.id,
                chunk_index=i,
                text=chunk["text"],
                page_number=chunk.get("page_number"),
                section_title=chunk.get("section_title"),
                char_start=chunk["char_start"],
                char_end=chunk["char_end"],
            )
        )


def get_document(session: Session, document_id: int) -> Document | None:
    return session.get(Document, document_id)


def documents_without_extraction(session: Session, limit: int | None = None) -> list[Document]:
    extracted = select(Extraction.document_id)
    stmt = select(Document).where(Document.id.not_in(extracted)).order_by(Document.id)
    if limit:
        stmt = stmt.limit(limit)
    return list(session.scalars(stmt))


# ---------------------------------------------------------------- extractions


def add_extraction(
    session: Session, document: Document, payload: dict[str, Any]
) -> Extraction:
    extraction = Extraction(
        document_id=document.id,
        source_id=document.source_id,
        payload=payload,
        hft_dependency=bool(payload.get("hft_or_low_latency_dependency", False)),
        backtestability=payload.get("backtestability"),
    )
    session.add(extraction)
    session.flush()
    return extraction


def extractions_without_hypothesis(session: Session, limit: int | None = None) -> list[Extraction]:
    used = select(StrategyHypothesis.extraction_id)
    stmt = select(Extraction).where(Extraction.id.not_in(used)).order_by(Extraction.id)
    if limit:
        stmt = stmt.limit(limit)
    return list(session.scalars(stmt))


# ---------------------------------------------------------------- hypotheses


def add_hypothesis(
    session: Session, extraction: Extraction, payload: dict[str, Any], status: str
) -> StrategyHypothesis:
    hyp = StrategyHypothesis(
        hypothesis_id=payload["hypothesis_id"],
        extraction_id=extraction.id,
        source_ids=payload.get("source_ids", []),
        payload=payload,
        status=status,
        priority_score=float(payload.get("priority_score", 0)),
    )
    session.add(hyp)
    session.flush()
    return hyp


def get_hypothesis(session: Session, hypothesis_id: str) -> StrategyHypothesis | None:
    return session.scalars(
        select(StrategyHypothesis).where(StrategyHypothesis.hypothesis_id == hypothesis_id)
    ).first()


def list_hypotheses(session: Session, status: str | None = None) -> list[StrategyHypothesis]:
    stmt = select(StrategyHypothesis).order_by(StrategyHypothesis.priority_score.desc())
    if status:
        stmt = stmt.where(StrategyHypothesis.status == status)
    return list(session.scalars(stmt))


def unscored_hypotheses(session: Session) -> list[StrategyHypothesis]:
    scored = select(Score.hypothesis_id)
    stmt = select(StrategyHypothesis).where(StrategyHypothesis.hypothesis_id.not_in(scored))
    return list(session.scalars(stmt))


# ---------------------------------------------------------------- scores


def add_score(
    session: Session,
    hypothesis: StrategyHypothesis,
    dimensions: dict[str, Any],
    weighted_total: float,
    excluded: bool,
    exclusion_reason: str | None,
    hard_filter_flags: list[str],
) -> Score:
    score = Score(
        hypothesis_id=hypothesis.hypothesis_id,
        dimensions=dimensions,
        weighted_total=weighted_total,
        excluded=excluded,
        exclusion_reason=exclusion_reason,
        hard_filter_flags=hard_filter_flags,
    )
    session.add(score)
    hypothesis.priority_score = weighted_total
    # Only demote plain candidates; review_only / rejected_* statuses carry
    # more specific information and must not be overwritten by scoring.
    if excluded and hypothesis.status == "candidate":
        hypothesis.status = "rejected"
    session.flush()
    return score


def latest_score(session: Session, hypothesis_id: str) -> Score | None:
    return session.scalars(
        select(Score)
        .where(Score.hypothesis_id == hypothesis_id)
        .order_by(Score.id.desc())
    ).first()


def ranked_hypotheses(session: Session) -> list[tuple[StrategyHypothesis, Score]]:
    """All scored hypotheses with their latest score, best first."""
    result: list[tuple[StrategyHypothesis, Score]] = []
    for hyp in session.scalars(select(StrategyHypothesis)):
        score = latest_score(session, hyp.hypothesis_id)
        if score is not None:
            result.append((hyp, score))
    result.sort(key=lambda pair: pair[1].weighted_total, reverse=True)
    return result


# ---------------------------------------------------------------- misc


def start_run(session: Session, collector: str, query: str | None) -> IngestionRun:
    run = IngestionRun(collector=collector, query=query)
    session.add(run)
    session.flush()
    return run


def finish_run(
    session: Session, run: IngestionRun, num_found: int, num_new: int, error: str | None = None
) -> None:
    run.num_found = num_found
    run.num_new = num_new
    run.finished_at = datetime.now(UTC)
    run.status = "failed" if error else "done"
    run.error = error


def add_rejection(
    session: Session, stage: str, entity_type: str, entity_ref: str, reason: str
) -> None:
    session.add(
        RejectedItem(stage=stage, entity_type=entity_type, entity_ref=str(entity_ref), reason=reason)
    )


def list_rejections(session: Session) -> list[RejectedItem]:
    return list(session.scalars(select(RejectedItem).order_by(RejectedItem.id)))


def add_backtest_spec(
    session: Session, hypothesis: StrategyHypothesis, fmt: str, path: str, payload: dict[str, Any]
) -> BacktestHandoffSpec:
    spec = BacktestHandoffSpec(
        hypothesis_id=hypothesis.hypothesis_id, format=fmt, path=path, payload=payload
    )
    session.add(spec)
    session.flush()
    return spec


def get_source(session: Session, source_id: int) -> Source | None:
    return session.get(Source, source_id)
