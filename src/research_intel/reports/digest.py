"""Full research digest: pipeline stats + ranked candidates + rejections."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from research_intel.reports.ranked_report import render_ranked_markdown
from research_intel.storage import repositories as repo
from research_intel.storage.models import Document, Extraction, Source, StrategyHypothesis


def render_digest(session: Session, top: int = 25) -> str:
    generated = datetime.now(UTC).strftime("%Y-%m-%d")
    counts = {
        "sources": session.scalar(select(func.count(Source.id))) or 0,
        "documents": session.scalar(select(func.count(Document.id))) or 0,
        "extractions": session.scalar(select(func.count(Extraction.id))) or 0,
        "hypotheses": session.scalar(select(func.count(StrategyHypothesis.id))) or 0,
    }
    rejections = repo.list_rejections(session)
    ranked_body = render_ranked_markdown(session, top=top)
    # Strip the ranked report's own H1; the digest provides one.
    ranked_body = ranked_body.split("\n", 1)[1] if ranked_body.startswith("#") else ranked_body

    rejection_lines = "\n".join(
        f"- [{r.stage}] {r.entity_type} {r.entity_ref}: {r.reason}" for r in rejections
    ) or "- (none)"

    return f"""# Research Intelligence Digest

Generated: {generated}

## Pipeline Summary

| Stage | Count |
|---|---|
| Sources | {counts['sources']} |
| Documents | {counts['documents']} |
| Extractions | {counts['extractions']} |
| Hypotheses | {counts['hypotheses']} |

## Top Strategy Candidates
{ranked_body}

## Pipeline Rejections Log

{rejection_lines}
"""


def write_digest(session: Session, output: Path, top: int = 25) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render_digest(session, top=top), encoding="utf-8")
    return output
