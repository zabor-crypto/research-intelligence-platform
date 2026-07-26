"""SQLAlchemy ORM models for the local research database."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    type_annotation_map = {dict[str, Any]: JSON, list[Any]: JSON}


class Source(Base):
    """One external research source (paper, repo, local file)."""

    __tablename__ = "sources"
    __table_args__ = (UniqueConstraint("source_type", "external_id", name="uq_source_ext"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    source_type: Mapped[str] = mapped_column(String(32), index=True)  # arxiv|openalex|s2|github|manual
    external_id: Mapped[str] = mapped_column(String(512))
    url: Mapped[str | None] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text)
    authors: Mapped[list[Any]] = mapped_column(JSON, default=list)
    published_date: Mapped[str | None] = mapped_column(String(32))
    retrieved_date: Mapped[datetime] = mapped_column(default=utcnow)
    abstract: Mapped[str | None] = mapped_column(Text)
    doi: Mapped[str | None] = mapped_column(String(256), index=True)
    citation_count: Mapped[int | None] = mapped_column(Integer)
    raw_text_path: Mapped[str | None] = mapped_column(Text)
    pdf_path: Mapped[str | None] = mapped_column(Text)
    checksum: Mapped[str | None] = mapped_column(String(64), index=True)
    extra: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    documents: Mapped[list[Document]] = relationship(back_populates="source")


class Document(Base):
    """Parsed textual content attached to a source."""

    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"), index=True)
    kind: Mapped[str] = mapped_column(String(16), default="fulltext")  # fulltext|abstract|readme
    raw_path: Mapped[str | None] = mapped_column(Text)
    text_path: Mapped[str | None] = mapped_column(Text)
    content_hash: Mapped[str] = mapped_column(String(64), index=True)
    num_pages: Mapped[int | None] = mapped_column(Integer)
    parse_status: Mapped[str] = mapped_column(String(16), default="parsed")
    created_at: Mapped[datetime] = mapped_column(default=utcnow)

    source: Mapped[Source] = relationship(back_populates="documents")
    chunks: Mapped[list[DocumentChunk]] = relationship(back_populates="document")


class DocumentChunk(Base):
    __tablename__ = "document_chunks"

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id"), index=True)
    chunk_index: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    page_number: Mapped[int | None] = mapped_column(Integer)
    section_title: Mapped[str | None] = mapped_column(Text)
    char_start: Mapped[int] = mapped_column(Integer)
    char_end: Mapped[int] = mapped_column(Integer)

    document: Mapped[Document] = relationship(back_populates="chunks")


class Extraction(Base):
    """Structured trading-relevant extraction from one document."""

    __tablename__ = "extractions"

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id"), index=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"), index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    hft_dependency: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    backtestability: Mapped[str | None] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class StrategyHypothesis(Base):
    __tablename__ = "strategy_hypotheses"

    id: Mapped[int] = mapped_column(primary_key=True)
    hypothesis_id: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    extraction_id: Mapped[int] = mapped_column(ForeignKey("extractions.id"), index=True)
    source_ids: Mapped[list[Any]] = mapped_column(JSON, default=list)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(32), default="candidate", index=True)
    priority_score: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class Score(Base):
    __tablename__ = "scores"

    id: Mapped[int] = mapped_column(primary_key=True)
    hypothesis_id: Mapped[str] = mapped_column(
        ForeignKey("strategy_hypotheses.hypothesis_id"), index=True
    )
    dimensions: Mapped[dict[str, Any]] = mapped_column(JSON)
    weighted_total: Mapped[float] = mapped_column(Float)
    excluded: Mapped[bool] = mapped_column(Boolean, default=False)
    exclusion_reason: Mapped[str | None] = mapped_column(Text)
    hard_filter_flags: Mapped[list[Any]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class BacktestHandoffSpec(Base):
    __tablename__ = "backtest_handoff_specs"

    id: Mapped[int] = mapped_column(primary_key=True)
    hypothesis_id: Mapped[str] = mapped_column(
        ForeignKey("strategy_hypotheses.hypothesis_id"), index=True
    )
    format: Mapped[str] = mapped_column(String(8), default="md")
    path: Mapped[str] = mapped_column(Text)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class IngestionRun(Base):
    __tablename__ = "ingestion_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    collector: Mapped[str] = mapped_column(String(32))
    query: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(default=None)
    num_found: Mapped[int] = mapped_column(Integer, default=0)
    num_new: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(16), default="running")
    error: Mapped[str | None] = mapped_column(Text)


class RejectedItem(Base):
    __tablename__ = "rejected_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    stage: Mapped[str] = mapped_column(String(32))  # extraction|hypothesis|scoring
    entity_type: Mapped[str] = mapped_column(String(32))
    entity_ref: Mapped[str] = mapped_column(String(64))
    reason: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class Tag(Base):
    __tablename__ = "tags"
    __table_args__ = (UniqueConstraint("entity_type", "entity_ref", "tag", name="uq_tag"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    entity_type: Mapped[str] = mapped_column(String(32))
    entity_ref: Mapped[str] = mapped_column(String(64))
    tag: Mapped[str] = mapped_column(String(64), index=True)
