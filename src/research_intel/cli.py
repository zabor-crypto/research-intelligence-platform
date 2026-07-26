"""research-intel command line interface."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Annotated

import typer

from research_intel import __version__
from research_intel.config import Settings, get_settings
from research_intel.logging_config import setup_logging

app = typer.Typer(
    name="research-intel",
    help="Research Intelligence Platform: turn external research into ranked, "
    "backtest-ready crypto strategy hypotheses (non-HFT).",
    no_args_is_help=True,
)

logger = logging.getLogger("research_intel.cli")

_state: dict[str, bool] = {"dry_run": False}


@app.callback()
def main(
    verbose: Annotated[bool, typer.Option("--verbose", "-v", help="Debug logging")] = False,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Show actions, write nothing")] = False,
) -> None:
    setup_logging(verbose)
    _state["dry_run"] = dry_run


def _ctx() -> tuple[Settings, object]:
    from research_intel.storage.db import get_engine
    from research_intel.storage.migrations import migrate

    settings = get_settings()
    engine = get_engine(settings)
    migrate(engine)
    return settings, engine


@app.command()
def version() -> None:
    """Print the platform version."""
    typer.echo(__version__)


@app.command()
def init() -> None:
    """Create local directories and the SQLite database."""
    settings = get_settings()
    if _state["dry_run"]:
        typer.echo(f"[dry-run] would create dirs under {settings.data_dir} and {settings.db_path}")
        return
    settings.ensure_dirs()
    from research_intel.storage.db import get_engine
    from research_intel.storage.migrations import migrate

    version_num = migrate(get_engine(settings))
    typer.echo(f"initialized: db={settings.db_path} schema_version={version_num}")


@app.command()
def search(
    source: Annotated[str, typer.Option(help="arxiv | openalex | semantic_scholar | github")],
    query: Annotated[str, typer.Option(help="search query")],
    limit: Annotated[int, typer.Option(help="max results")] = 25,
    since: Annotated[str | None, typer.Option(help="ISO date lower bound, e.g. 2024-01-01")] = None,
    fetch_fulltext: Annotated[
        bool, typer.Option(help="also download fulltext (arXiv PDF / GitHub README)")
    ] = False,
) -> None:
    """Search an external source and store results locally."""
    from research_intel.collectors import get_collector
    from research_intel.ingestion import ingest_records
    from research_intel.storage import repositories as repo
    from research_intel.storage.db import session_scope

    settings, engine = _ctx()
    kwargs: dict[str, object] = {"timeout": settings.http_timeout, "retries": settings.http_retries}
    if source == "github" and settings.github_token:
        kwargs["token"] = settings.github_token
    if source == "semantic_scholar" and settings.semantic_scholar_api_key:
        kwargs["api_key"] = settings.semantic_scholar_api_key
    if source == "openalex" and settings.openalex_mailto:
        kwargs["mailto"] = settings.openalex_mailto
    if source == "manual":
        kwargs = {}
    collector = get_collector(source, **kwargs)

    records = collector.search(query, limit=limit, since=since)
    if _state["dry_run"]:
        for r in records:
            typer.echo(f"[dry-run] {r.source_type}:{r.external_id} — {r.title}")
        typer.echo(f"[dry-run] {len(records)} results, nothing stored")
        return
    with session_scope(engine) as session:
        run = repo.start_run(session, collector=source, query=query)
        try:
            num_found, num_new = ingest_records(
                session, settings, collector, records, fetch_fulltext=fetch_fulltext
            )
            repo.finish_run(session, run, num_found, num_new)
        except Exception as exc:
            repo.finish_run(session, run, len(records), 0, error=str(exc))
            raise
    typer.echo(f"search done: found={num_found} new={num_new}")


@app.command()
def ingest(
    path: Annotated[Path, typer.Option(help="file or directory of .pdf/.txt/.md/.html")],
    limit: Annotated[int, typer.Option(help="max files")] = 1000,
) -> None:
    """Ingest local research documents."""
    from research_intel.collectors.manual_collector import ManualCollector
    from research_intel.ingestion import ingest_records
    from research_intel.storage import repositories as repo
    from research_intel.storage.db import session_scope

    settings, engine = _ctx()
    collector = ManualCollector()
    records = collector.search(str(path), limit=limit)
    if _state["dry_run"]:
        for r in records:
            typer.echo(f"[dry-run] would ingest {r.external_id}")
        return
    with session_scope(engine) as session:
        run = repo.start_run(session, collector="manual", query=str(path))
        num_found, num_new = ingest_records(session, settings, collector, records)
        repo.finish_run(session, run, num_found, num_new)
    typer.echo(f"ingested: found={num_found} new_sources={num_new}")


@app.command()
def extract(
    document_id: Annotated[int, typer.Option(help="document id to extract")],
) -> None:
    """Run structured extraction on one document."""
    from research_intel.extraction.extractor import extract_document
    from research_intel.llm import get_llm_client
    from research_intel.storage import repositories as repo
    from research_intel.storage.db import session_scope

    settings, engine = _ctx()
    llm = get_llm_client(settings)
    with session_scope(engine) as session:
        document = repo.get_document(session, document_id)
        if document is None:
            typer.echo(f"document {document_id} not found", err=True)
            raise typer.Exit(code=1)
        if _state["dry_run"]:
            typer.echo(f"[dry-run] would extract document {document_id}")
            return
        extraction = extract_document(session, document, llm)
        typer.echo(f"extraction {extraction.id} created for document {document_id}")


@app.command("extract-all")
def extract_all(
    limit: Annotated[int, typer.Option(help="max documents")] = 100,
) -> None:
    """Extract all documents that have no extraction yet."""
    from research_intel.extraction.extractor import extract_pending
    from research_intel.llm import get_llm_client
    from research_intel.storage.db import session_scope

    settings, engine = _ctx()
    llm = get_llm_client(settings)
    if _state["dry_run"]:
        typer.echo(f"[dry-run] would extract up to {limit} pending documents")
        return
    with session_scope(engine) as session:
        extractions = extract_pending(session, llm, limit=limit)
    typer.echo(f"extracted {len(extractions)} documents")


@app.command("generate-hypotheses")
def generate_hypotheses(
    limit: Annotated[int, typer.Option(help="max extractions to process")] = 50,
) -> None:
    """Generate crypto-testable strategy hypotheses from extractions."""
    from research_intel.hypotheses.generator import generate_pending
    from research_intel.llm import get_llm_client
    from research_intel.storage.db import session_scope

    settings, engine = _ctx()
    llm = get_llm_client(settings)
    if _state["dry_run"]:
        typer.echo(f"[dry-run] would generate hypotheses for up to {limit} extractions")
        return
    with session_scope(engine) as session:
        hypotheses = generate_pending(session, llm, limit=limit)
        for hyp in hypotheses:
            typer.echo(f"{hyp.hypothesis_id}  [{hyp.status}]  {hyp.payload.get('hypothesis_name')}")
    typer.echo(f"generated {len(hypotheses)} hypotheses")


@app.command()
def score(
    all_: Annotated[bool, typer.Option("--all", help="score all unscored hypotheses")] = False,
    hypothesis_id: Annotated[str | None, typer.Option(help="score one hypothesis")] = None,
    rescore: Annotated[bool, typer.Option(help="re-score already scored hypotheses too")] = False,
) -> None:
    """Score hypotheses on the 12-dimension framework with hard filters."""
    from research_intel.hypotheses.scorer import score_all, score_one
    from research_intel.llm import get_llm_client
    from research_intel.storage import repositories as repo
    from research_intel.storage.db import session_scope

    settings, engine = _ctx()
    llm = get_llm_client(settings)
    if not all_ and not hypothesis_id:
        typer.echo("provide --all or --hypothesis-id", err=True)
        raise typer.Exit(code=1)
    if _state["dry_run"]:
        typer.echo("[dry-run] would score hypotheses")
        return
    with session_scope(engine) as session:
        if hypothesis_id:
            hyp = repo.get_hypothesis(session, hypothesis_id)
            if hyp is None:
                typer.echo(f"hypothesis {hypothesis_id} not found", err=True)
                raise typer.Exit(code=1)
            result = score_one(session, hyp, llm)
            typer.echo(
                f"{hypothesis_id}: {result.weighted_total}/100"
                + (f" EXCLUDED ({result.exclusion_reason})" if result.excluded else "")
            )
        else:
            results = score_all(session, llm, rescore=rescore)
            for s in results:
                flag = f" EXCLUDED ({s.exclusion_reason})" if s.excluded else ""
                typer.echo(f"{s.hypothesis_id}: {s.weighted_total}/100{flag}")
            typer.echo(f"scored {len(results)} hypotheses")


@app.command("export-ranked")
def export_ranked_cmd(
    top: Annotated[int, typer.Option(help="number of top candidates")] = 25,
    format: Annotated[str, typer.Option("--format", "-f", help="csv | jsonl | md")] = "md",
) -> None:
    """Export ranked candidates (HFT-excluded ideas never appear here)."""
    from research_intel.hypotheses.exporter import export_ranked
    from research_intel.storage.db import session_scope

    settings, engine = _ctx()
    if _state["dry_run"]:
        typer.echo(f"[dry-run] would export top {top} as {format} to {settings.exports_dir}")
        return
    with session_scope(engine) as session:
        path = export_ranked(session, settings.exports_dir, top=top, fmt=format)
    typer.echo(f"exported: {path}")


@app.command("export-backtest-spec")
def export_backtest_spec_cmd(
    hypothesis_id: Annotated[str, typer.Option(help="hypothesis id to export")],
    format: Annotated[str, typer.Option("--format", "-f", help="md | json")] = "md",
) -> None:
    """Export the backtest handoff spec for one hypothesis."""
    from research_intel.hypotheses.exporter import export_backtest_spec
    from research_intel.storage.db import session_scope

    settings, engine = _ctx()
    if _state["dry_run"]:
        typer.echo(f"[dry-run] would export backtest spec for {hypothesis_id}")
        return
    try:
        with session_scope(engine) as session:
            path = export_backtest_spec(
                session, hypothesis_id, settings.exports_dir / "backtest_specs", fmt=format
            )
    except ValueError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(f"exported: {path}")


@app.command()
def report(
    output: Annotated[Path, typer.Option(help="output markdown path")] = Path(
        "reports/research_digest.md"
    ),
    top: Annotated[int, typer.Option(help="candidates to include")] = 25,
) -> None:
    """Write the full research digest markdown report."""
    from research_intel.reports.digest import write_digest
    from research_intel.storage.db import session_scope

    settings, engine = _ctx()
    if _state["dry_run"]:
        typer.echo(f"[dry-run] would write digest to {output}")
        return
    with session_scope(engine) as session:
        path = write_digest(session, output, top=top)
    typer.echo(f"report written: {path}")


@app.command("prepare-agent-batch")
def prepare_agent_batch_cmd(
    input: Annotated[Path, typer.Option("--input", help="source file or directory")],
    out: Annotated[Path, typer.Option("--out", help="work packet output directory")],
) -> None:
    """Create External Agent Mode work packets (no API calls)."""
    from research_intel.agent_mode import prepare_agent_batch

    settings = get_settings()
    if _state["dry_run"]:
        typer.echo(f"[dry-run] would prepare packets from {input} into {out}")
        return
    packet_ids = prepare_agent_batch(input, out, settings)
    for packet_id in packet_ids:
        typer.echo(f"packet: {out / packet_id}")
    typer.echo(f"prepared {len(packet_ids)} work packets")


@app.command("import-agent-outputs")
def import_agent_outputs_cmd(
    path: Annotated[Path, typer.Option("--path", help="agent outputs directory")],
    trust_agent_score: Annotated[
        bool, typer.Option(help="use the agent's validated score instead of recomputing")
    ] = False,
) -> None:
    """Import external agent outputs; validate, gate, and score them."""
    from research_intel.agent_mode import import_agent_outputs

    settings, engine = _ctx()
    if _state["dry_run"]:
        typer.echo(f"[dry-run] would import agent outputs from {path}")
        return
    summary = import_agent_outputs(
        path, settings, engine, trust_agent_score=trust_agent_score
    )
    typer.echo(json.dumps({k: v for k, v in summary.items() if k != "hypothesis_ids"},
                          indent=2))
    for hid in summary["hypothesis_ids"]:
        typer.echo(f"imported: {hid}")


@app.command("evaluate-agent-batch")
def evaluate_agent_batch_cmd(
    outputs: Annotated[Path, typer.Option("--outputs", help="agent outputs directory")],
    report_dir: Annotated[Path, typer.Option("--report-dir", help="report output directory")],
    trust_agent_score: Annotated[
        bool, typer.Option(help="use the agent's validated score instead of recomputing")
    ] = False,
) -> None:
    """Import agent outputs, re-run gates/scores, and build report artifacts."""
    from research_intel.agent_mode import evaluate_agent_batch

    settings, engine = _ctx()
    if _state["dry_run"]:
        typer.echo(f"[dry-run] would evaluate {outputs} into {report_dir}")
        return
    summary = evaluate_agent_batch(outputs, report_dir, settings, engine,
                                   trust_agent_score=trust_agent_score)
    typer.echo(json.dumps({k: v for k, v in summary.items() if k != "hypothesis_ids"},
                          indent=2))


@app.command()
def status() -> None:
    """Show pipeline counts."""
    from sqlalchemy import func, select

    from research_intel.storage.db import session_scope
    from research_intel.storage.models import (
        Document,
        Extraction,
        Source,
        StrategyHypothesis,
    )

    settings, engine = _ctx()
    with session_scope(engine) as session:
        counts = {
            "sources": session.scalar(select(func.count(Source.id))),
            "documents": session.scalar(select(func.count(Document.id))),
            "extractions": session.scalar(select(func.count(Extraction.id))),
            "hypotheses": session.scalar(select(func.count(StrategyHypothesis.id))),
        }
    typer.echo(json.dumps(counts, indent=2))


if __name__ == "__main__":
    app()
