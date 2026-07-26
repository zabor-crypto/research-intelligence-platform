"""External Agent Mode: file-based LLM operation without any API calls.

Workflow:
  prepare_agent_batch()  -> work packets (source + schemas + instructions)
  <external agent (e.g. Claude Code) writes extraction/hypothesis/score files>
  import_agent_outputs() -> validate, store, re-run every gate, re-score
  evaluate_agent_batch() -> ranked exports, specs, report artifacts

No gate is loosened: imported hypotheses pass through exactly the same
grounding/HFT/parameterization/fidelity/consistency enforcement as
LLM-generated ones, and scores are recomputed internally by default.
"""

from __future__ import annotations

import csv
import hashlib
import json
import logging
import shutil
from pathlib import Path
from typing import Any

from sqlalchemy import Engine

from research_intel.collectors.base import RawSourceRecord
from research_intel.collectors.manual_collector import SUPPORTED_SUFFIXES, ManualCollector
from research_intel.config import Settings
from research_intel.extraction.schemas import (
    SCORING_DIMENSIONS,
    ExtractionRecord,
    HypothesisRecord,
)
from research_intel.extraction.validators import (
    ExtractionValidationError,
    validate_dimension_scores,
    validate_extraction,
    validate_hypothesis,
)
from research_intel.llm.base import LLMClient
from research_intel.storage import repositories as repo
from research_intel.storage.db import session_scope

logger = logging.getLogger(__name__)

REQUIRED_OUTPUTS = ["extraction.json", "hypothesis.json", "score.json"]
CONDITIONAL_OUTPUTS = {
    "backtest_spec.md": "only if status=candidate and both export flags are true",
    "rejection_reason.md": "if status is review_only / rejected_*",
}


# ------------------------------------------------------------------ packets


def _packet_id(index: int, path: Path) -> str:
    return f"p{index:03d}_{path.stem}"


def prepare_agent_batch(input_path: Path, out_dir: Path, settings: Settings) -> list[str]:
    """Create one work packet per supported source file. Returns packet ids."""
    from research_intel.llm.prompt_loader import load_prompt

    input_path = input_path.expanduser()
    files = (
        [input_path]
        if input_path.is_file()
        else sorted(p for p in input_path.rglob("*") if p.suffix.lower() in SUPPORTED_SUFFIXES)
    )
    if not files:
        raise FileNotFoundError(f"no supported source files under {input_path}")
    instructions_template = load_prompt(
        "external_agent_packet_instructions", settings.prompts_dir
    )
    collector = ManualCollector()
    packet_ids: list[str] = []
    for index, path in enumerate(files, start=1):
        packet_id = _packet_id(index, path)
        packet_dir = out_dir / packet_id
        packet_dir.mkdir(parents=True, exist_ok=True)
        doc = collector.fetch(str(path))
        text = doc.text or ""
        (packet_dir / "source.md").write_text(text, encoding="utf-8")
        (packet_dir / "metadata.json").write_text(json.dumps({
            "packet_id": packet_id,
            "source_file": str(path),
            "source_type": "external_agent",
            "title": text.splitlines()[0].lstrip("# ").strip() if text.strip() else path.stem,
            "content_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "provider_mode": "external_agent",
            "schema_version": 1,
        }, indent=2), encoding="utf-8")
        (packet_dir / "extraction_schema.json").write_text(
            json.dumps(ExtractionRecord.model_json_schema(), indent=2), encoding="utf-8"
        )
        (packet_dir / "hypothesis_schema.json").write_text(
            json.dumps(HypothesisRecord.model_json_schema(), indent=2), encoding="utf-8"
        )
        (packet_dir / "scoring_schema.json").write_text(json.dumps({
            "description": "Score every dimension 0-10 (10 always better). "
            "The platform recomputes scores internally by default; yours is advisory.",
            "dimensions": list(SCORING_DIMENSIONS),
            "format": {"hypothesis_id": "<copy>", "dimensions": {d: "0-10" for d in SCORING_DIMENSIONS},
                       "rationale": {"<dimension>": "<one line>"}},
        }, indent=2), encoding="utf-8")
        (packet_dir / "instructions.md").write_text(
            instructions_template.replace("{{packet_id}}", packet_id), encoding="utf-8"
        )
        (packet_dir / "expected_outputs.json").write_text(json.dumps({
            "required": REQUIRED_OUTPUTS,
            "conditional": CONDITIONAL_OUTPUTS,
        }, indent=2), encoding="utf-8")
        packet_ids.append(packet_id)
    logger.info("prepared %d agent work packets in %s", len(packet_ids), out_dir)
    return packet_ids


# ------------------------------------------------------------------ import


class _TrustedScoreLLM(LLMClient):
    """Adapter that feeds a validated agent-provided score into the scorer.

    Hard filters and weighting still run in platform code — trusting the
    agent's score only replaces the dimension values, never the gates.
    """

    def __init__(self, score_payload: dict[str, Any]):
        self._score = score_payload

    def extract_research(self, text, schema, *, source_id=None, document_id=None):
        raise NotImplementedError

    def generate_hypothesis(self, extraction):
        raise NotImplementedError

    def score_hypothesis(self, hypothesis):
        return self._score


def _log_error(errors_path: Path, row: dict[str, Any]) -> None:
    errors_path.parent.mkdir(parents=True, exist_ok=True)
    with errors_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row) + "\n")


def import_agent_outputs(
    outputs_path: Path,
    settings: Settings,
    engine: Engine,
    *,
    trust_agent_score: bool = False,
    errors_path: Path | None = None,
) -> dict[str, Any]:
    """Import externally produced outputs, validate, gate, and score them.

    Returns a summary dict. Import errors are logged to
    reports/agent_import_errors.jsonl (or errors_path) and never abort the
    batch.
    """
    from research_intel.hypotheses.generator import admit_hypothesis
    from research_intel.hypotheses.scorer import score_one
    from research_intel.llm.mock_client import MockLLMClient

    errors_path = errors_path or (settings.reports_dir / "agent_import_errors.jsonl")
    packet_dirs = sorted(p for p in Path(outputs_path).iterdir() if p.is_dir())
    if not packet_dirs:
        raise FileNotFoundError(f"no packet output directories under {outputs_path}")

    summary: dict[str, Any] = {
        "packets": len(packet_dirs), "imported": 0, "skipped_already_imported": 0,
        "errors": 0, "statuses": {}, "hypothesis_ids": [],
    }
    internal_scorer = MockLLMClient()

    with session_scope(engine) as session:
        for packet_dir in packet_dirs:
            packet_id = packet_dir.name

            def fail(stage: str, reason: str, packet_id: str = packet_id, **extra: Any) -> None:
                summary["errors"] += 1
                _log_error(errors_path, {
                    "stage": stage, "entity_type": "agent_packet",
                    "entity_ref": packet_id, "reason": reason,
                    "source_id": extra.get("source_id"),
                    "document_id": extra.get("document_id"),
                    "hypothesis_id": extra.get("hypothesis_id"),
                    "raw_response_path": extra.get("file"),
                    "parsed_output_path": None,
                })
                repo.add_rejection(
                    session, stage=stage, entity_type="agent_packet",
                    entity_ref=packet_id, reason=reason,
                )

            # ---- extraction.json ----
            extraction_file = packet_dir / "extraction.json"
            if not extraction_file.is_file():
                fail("agent_import", "missing extraction.json", file=str(extraction_file))
                continue
            try:
                extraction_payload = json.loads(extraction_file.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                fail("agent_import", f"extraction.json invalid JSON: {exc}",
                     file=str(extraction_file))
                continue

            # Source/document rows for provenance (authoritative ids are ours).
            source, _created = repo.upsert_source(session, RawSourceRecord(
                source_type="external_agent",
                external_id=packet_id,
                title=str(extraction_payload.get("title") or packet_id),
                checksum=hashlib.sha256(
                    extraction_file.read_bytes()
                ).hexdigest(),
                extra={"outputs_dir": str(packet_dir)},
            ))
            document, doc_created = repo.add_document(
                session, source, kind="fulltext",
                content_hash=hashlib.sha256(f"agent:{packet_id}".encode()).hexdigest(),
            )
            if not doc_created:
                from sqlalchemy import select

                from research_intel.storage.models import Extraction as ExtractionModel

                existing = session.scalars(
                    select(ExtractionModel).where(ExtractionModel.document_id == document.id)
                ).first()
                if existing is not None:
                    summary["skipped_already_imported"] += 1
                    logger.info("packet %s already imported, skipping", packet_id)
                    continue

            extraction_payload["source_id"] = str(source.id)
            extraction_payload["document_id"] = str(document.id)
            try:
                extraction_record = validate_extraction(extraction_payload)
            except ExtractionValidationError as exc:
                fail("agent_extraction_validation", str(exc),
                     source_id=str(source.id), document_id=str(document.id),
                     file=str(extraction_file))
                continue
            extraction = repo.add_extraction(session, document, extraction_record.model_dump())

            # ---- hypothesis.json (validated, then pushed through ALL gates) ----
            hypothesis_file = packet_dir / "hypothesis.json"
            if not hypothesis_file.is_file():
                fail("agent_import", "missing hypothesis.json",
                     source_id=str(source.id), file=str(hypothesis_file))
                continue
            try:
                hypothesis_payload = json.loads(hypothesis_file.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                fail("agent_import", f"hypothesis.json invalid JSON: {exc}",
                     source_id=str(source.id), file=str(hypothesis_file))
                continue
            hypothesis_payload["source_ids"] = [str(source.id)]
            try:
                hypothesis_record = validate_hypothesis(hypothesis_payload)
            except ExtractionValidationError as exc:
                fail("agent_hypothesis_validation", str(exc),
                     source_id=str(source.id), document_id=str(document.id),
                     file=str(hypothesis_file))
                continue
            hyp = admit_hypothesis(session, extraction, hypothesis_record)
            if hyp is None:
                fail("agent_import", "hypothesis id collision on import",
                     source_id=str(source.id),
                     hypothesis_id=hypothesis_record.hypothesis_id,
                     file=str(hypothesis_file))
                continue

            # ---- score: recompute by default; agent score only if trusted ----
            scorer_llm: LLMClient = internal_scorer
            score_file = packet_dir / "score.json"
            if trust_agent_score and score_file.is_file():
                try:
                    agent_score = json.loads(score_file.read_text(encoding="utf-8"))
                    validate_dimension_scores(agent_score.get("dimensions", {}))
                    scorer_llm = _TrustedScoreLLM(agent_score)
                except (json.JSONDecodeError, ExtractionValidationError) as exc:
                    fail("agent_score_validation",
                         f"agent score rejected, falling back to internal: {exc}",
                         hypothesis_id=hyp.hypothesis_id, file=str(score_file))
                    scorer_llm = internal_scorer
            try:
                score_one(session, hyp, scorer_llm)
            except Exception as exc:  # scoring failure must not kill the batch
                fail("agent_scoring", str(exc), hypothesis_id=hyp.hypothesis_id)
                continue

            summary["imported"] += 1
            summary["statuses"][hyp.status] = summary["statuses"].get(hyp.status, 0) + 1
            summary["hypothesis_ids"].append(hyp.hypothesis_id)

    logger.info("agent import summary: %s", summary)
    return summary


# ------------------------------------------------------------------ evaluate


def evaluate_agent_batch(
    outputs_path: Path,
    report_dir: Path,
    settings: Settings,
    engine: Engine,
    *,
    trust_agent_score: bool = False,
) -> dict[str, Any]:
    """Import agent outputs, re-run gates/scores, and build report artifacts."""
    from research_intel.hypotheses.exporter import (
        export_backtest_spec,
        export_ranked,
        is_exportable_candidate,
    )
    from research_intel.reports.digest import write_digest

    report_dir.mkdir(parents=True, exist_ok=True)
    errors_path = report_dir / "agent_import_errors.jsonl"
    summary = import_agent_outputs(
        outputs_path, settings, engine,
        trust_agent_score=trust_agent_score, errors_path=errors_path,
    )
    if not errors_path.exists():
        errors_path.write_text("", encoding="utf-8")

    for category in ("top_A_candidates", "top_B_candidates", "rejected_or_review_only"):
        (report_dir / category).mkdir(exist_ok=True)

    with session_scope(engine) as session:
        for fmt in ("md", "csv", "jsonl"):
            path = export_ranked(session, report_dir, top=50, fmt=fmt)
            path.rename(report_dir / f"ranked_candidates.{fmt}")
        write_digest(session, report_dir / "research_digest.md")

        # Specs only for candidates passing every export gate.
        exported_specs: list[str] = []
        rows: list[dict[str, Any]] = []
        for hyp in repo.list_hypotheses(session):
            score = repo.latest_score(session, hyp.hypothesis_id)
            p = hyp.payload
            eligible = (
                score is not None
                and is_exportable_candidate(hyp, score)
                and p.get("parameterization_status") in (
                    "source_parameterized", "partially_source_parameterized")
                and p.get("archetype_fidelity") in ("strong", "partial")
                and p.get("spec_consistency") == "strong"
                and p.get("entry_condition_fidelity") in ("strong", "partial")
            )
            category = "top_A_candidates" if eligible else "rejected_or_review_only"
            target = report_dir / category
            (target / f"{hyp.hypothesis_id}_hypothesis.json").write_text(
                json.dumps(p, indent=2), encoding="utf-8"
            )
            if score is not None:
                (target / f"{hyp.hypothesis_id}_score.json").write_text(json.dumps({
                    "hypothesis_id": hyp.hypothesis_id, "status": hyp.status,
                    "dimensions": score.dimensions,
                    "weighted_total": score.weighted_total,
                    "excluded": score.excluded,
                    "exclusion_reason": score.exclusion_reason,
                    "hard_filter_flags": score.hard_filter_flags,
                }, indent=2), encoding="utf-8")
            if eligible:
                spec_path = export_backtest_spec(session, hyp.hypothesis_id, target)
                exported_specs.append(str(spec_path))
            rows.append({
                "source_id": (p.get("source_ids") or [""])[0],
                "hypothesis_id": hyp.hypothesis_id,
                "hypothesis_name": p.get("hypothesis_name", ""),
                "status": hyp.status,
                "parameterization_status": p.get("parameterization_status", ""),
                "archetype_fidelity": p.get("archetype_fidelity", ""),
                "spec_consistency": p.get("spec_consistency", ""),
                "entry_condition_fidelity": p.get("entry_condition_fidelity", ""),
                "score": score.weighted_total if score else "",
                "spec_exported": eligible,
                "manual_grade": "",
                "manual_grade_reason": "",
                "recommended_next_action": "",
            })

        fieldnames = list(rows[0].keys()) if rows else ["hypothesis_id"]
        for name in ("source_inventory.csv", "manual_grading_table.csv"):
            with (report_dir / name).open("w", newline="", encoding="utf-8") as fh:
                writer = csv.DictWriter(fh, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(rows)

        statuses = summary["statuses"]
        (report_dir / "manual_grading_report.md").write_text(
            "# Manual Grading Report — External Agent Batch\n\n"
            "Fill `manual_grading_table.csv` (grade A/B/C/D + reason per hypothesis) "
            "using the rubric in docs/10_external_agent_mode.md, then summarize "
            "grades and notable failures here.\n\n"
            f"Imported: {summary['imported']} | errors: {summary['errors']} | "
            f"statuses: {statuses}\n",
            encoding="utf-8",
        )
        (report_dir / "failure_analysis.md").write_text(
            "# Failure Analysis — External Agent Batch\n\n"
            f"- packets: {summary['packets']}\n"
            f"- imported: {summary['imported']}\n"
            f"- already imported (skipped): {summary['skipped_already_imported']}\n"
            f"- import errors: {summary['errors']} (see agent_import_errors.jsonl)\n"
            f"- statuses: {statuses}\n"
            f"- specs exported (all gates passed): {len(exported_specs)}\n\n"
            "All gates ran in platform code after import; agent-provided fidelity "
            "self-assessments were recomputed, and scores were "
            + ("taken from the agent (validated)" if trust_agent_score
               else "recomputed internally")
            + ".\n",
            encoding="utf-8",
        )

    summary["exported_specs"] = exported_specs
    summary["report_dir"] = str(report_dir)
    return summary


def copy_tree(src: Path, dst: Path) -> None:
    """Small helper used by CLI to mirror agent logs/artifacts."""
    if src.exists():
        shutil.copytree(src, dst, dirs_exist_ok=True)
