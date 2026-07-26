"""External Agent Mode: packet export, output import, gates, evaluation."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from research_intel.agent_mode import (
    evaluate_agent_batch,
    import_agent_outputs,
    prepare_agent_batch,
)
from research_intel.storage import repositories as repo
from research_intel.storage.db import session_scope

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCES = PROJECT_ROOT / "examples" / "agent_mode_sources"
FIXTURES = PROJECT_ROOT / "tests" / "fixtures" / "agent_outputs" / "dry_run"

PACKET_FILES = (
    "source.md", "metadata.json", "extraction_schema.json", "hypothesis_schema.json",
    "scoring_schema.json", "instructions.md", "expected_outputs.json",
)


# 1-2: packet export


def test_packet_export_creates_all_required_files(settings, tmp_path):
    packet_ids = prepare_agent_batch(SOURCES, tmp_path / "packets", settings)
    assert len(packet_ids) == 3
    for packet_id in packet_ids:
        packet_dir = tmp_path / "packets" / packet_id
        for name in PACKET_FILES:
            assert (packet_dir / name).is_file(), f"{packet_id} missing {name}"
        metadata = json.loads((packet_dir / "metadata.json").read_text())
        assert metadata["packet_id"] == packet_id
        assert metadata["content_sha256"]
        schema = json.loads((packet_dir / "extraction_schema.json").read_text())
        assert "extracted_parameters" in schema["properties"]
        expected = json.loads((packet_dir / "expected_outputs.json").read_text())
        assert set(expected["required"]) == {"extraction.json", "hypothesis.json", "score.json"}


def test_packet_instructions_include_anti_hallucination_constraints(settings, tmp_path):
    prepare_agent_batch(SOURCES, tmp_path / "packets", settings)
    instructions = (tmp_path / "packets" / "p003_volatility_note" / "instructions.md").read_text()
    for phrase in (
        "Source-faithful extraction", "No invented parameters",
        "No generic defaults masquerading as source facts",
        "Concrete entry/exit/risk rules", "Source asset universe preservation",
        "Risk/cost preservation", "Non-HFT compatibility classification",
        "requires_hft_or_low_latency_edge", "review_only for vague sources",
        "Source condition preservation", "Spec consistency",
    ):
        assert phrase in instructions, f"instructions missing '{phrase}'"
    assert "p003_volatility_note" in instructions  # packet id rendered


# 3-6: import + gates


def test_valid_outputs_import_with_expected_statuses(settings, engine):
    summary = import_agent_outputs(FIXTURES, settings, engine)
    assert summary["imported"] == 3
    assert summary["errors"] == 0
    assert summary["statuses"] == {
        "rejected_hft": 1, "rejected_unbacktestable": 1, "candidate": 1,
    }
    with session_scope(engine) as session:
        assert len(repo.list_sources(session)) == 3
        assert all(s.source_type == "external_agent" for s in repo.list_sources(session))


def test_invalid_json_is_rejected_and_logged(settings, engine, tmp_path):
    bad = tmp_path / "outputs" / "p001_bad"
    bad.mkdir(parents=True)
    (bad / "extraction.json").write_text("{not valid json")
    errors_path = tmp_path / "errors.jsonl"
    summary = import_agent_outputs(
        tmp_path / "outputs", settings, engine, errors_path=errors_path
    )
    assert summary["imported"] == 0 and summary["errors"] == 1
    rows = [json.loads(line) for line in errors_path.read_text().splitlines()]
    assert rows[0]["entity_ref"] == "p001_bad"
    assert "invalid JSON" in rows[0]["reason"]
    assert rows[0]["parsed_output_path"] is None


def test_vague_external_output_is_gated_even_if_agent_claims_candidate(
    settings, engine, tmp_path
):
    """An over-optimistic agent cannot smuggle a vague source past the gates."""
    src = FIXTURES / "p002_vague_source"
    packet = tmp_path / "outputs" / "p002_vague_source"
    packet.mkdir(parents=True)
    extraction = json.loads((src / "extraction.json").read_text())
    hypothesis = json.loads((src / "hypothesis.json").read_text())
    # Agent lies: claims candidate + export-allowed despite ungrounded source.
    hypothesis.update({
        "status": "candidate", "candidate_export_allowed": True,
        "backtest_spec_export_allowed": True,
    })
    (packet / "extraction.json").write_text(json.dumps(extraction))
    (packet / "hypothesis.json").write_text(json.dumps(hypothesis))
    summary = import_agent_outputs(tmp_path / "outputs", settings, engine)
    # Either validation rejects the vague rules outright, or the grounding
    # gate demotes it — a candidate must never survive.
    assert summary["statuses"].get("candidate") is None
    if summary["imported"]:
        (status,) = summary["statuses"].keys()
        assert status in ("review_only", "rejected_unbacktestable")


def test_hft_external_output_is_rejected(settings, engine):
    import_agent_outputs(FIXTURES, settings, engine)
    with session_scope(engine) as session:
        hft = [h for h in repo.list_hypotheses(session) if h.status == "rejected_hft"]
        assert len(hft) == 1
        assert hft[0].payload["non_applicable_reason"] == "requires_hft_or_low_latency_edge"
        with pytest.raises(ValueError, match="rejected"):
            from research_intel.hypotheses.exporter import export_backtest_spec

            export_backtest_spec(session, hft[0].hypothesis_id, settings.exports_dir / "s")


# 7: score recomputation


def test_score_is_recomputed_by_default(settings, engine, tmp_path):
    src = FIXTURES / "p003_volatility_note"
    packet = tmp_path / "outputs" / "p003_volatility_note"
    packet.mkdir(parents=True)
    shutil.copy(src / "extraction.json", packet / "extraction.json")
    shutil.copy(src / "hypothesis.json", packet / "hypothesis.json")
    # Agent supplies an absurd perfect score.
    hyp = json.loads((src / "hypothesis.json").read_text())
    from research_intel.extraction.schemas import SCORING_DIMENSIONS

    (packet / "score.json").write_text(json.dumps({
        "hypothesis_id": hyp["hypothesis_id"],
        "dimensions": dict.fromkeys(SCORING_DIMENSIONS, 10.0),
    }))
    import_agent_outputs(tmp_path / "outputs", settings, engine)
    with session_scope(engine) as session:
        (h,) = repo.list_hypotheses(session)
        score = repo.latest_score(session, h.hypothesis_id)
        assert score.weighted_total < 100.0  # internal recompute, not the agent's 100


def test_trust_agent_score_uses_validated_agent_dimensions(settings, engine, tmp_path):
    src = FIXTURES / "p003_volatility_note"
    packet = tmp_path / "outputs" / "p003_volatility_note"
    packet.mkdir(parents=True)
    shutil.copy(src / "extraction.json", packet / "extraction.json")
    shutil.copy(src / "hypothesis.json", packet / "hypothesis.json")
    hyp = json.loads((src / "hypothesis.json").read_text())
    from research_intel.extraction.schemas import SCORING_DIMENSIONS

    (packet / "score.json").write_text(json.dumps({
        "hypothesis_id": hyp["hypothesis_id"],
        "dimensions": dict.fromkeys(SCORING_DIMENSIONS, 5.0),
    }))
    import_agent_outputs(tmp_path / "outputs", settings, engine, trust_agent_score=True)
    with session_scope(engine) as session:
        (h,) = repo.list_hypotheses(session)
        score = repo.latest_score(session, h.hypothesis_id)
        assert score.weighted_total == 50.0  # trusted (validated) agent dimensions


# 8-9: spec export gating


def test_valid_candidate_exports_spec_and_gated_ones_cannot(settings, engine, tmp_path):
    import_agent_outputs(FIXTURES, settings, engine)
    from research_intel.hypotheses.exporter import export_backtest_spec

    with session_scope(engine) as session:
        for hyp in repo.list_hypotheses(session):
            if hyp.status == "candidate":
                path = export_backtest_spec(session, hyp.hypothesis_id, tmp_path / "specs")
                spec = path.read_text()
                assert "Primary: ETH-USDT perpetual futures" in spec
                assert "Spec consistency: strong" in spec
            else:
                with pytest.raises(ValueError):
                    export_backtest_spec(session, hyp.hypothesis_id, tmp_path / "specs")


# 10: evaluate-agent-batch report artifacts


def test_evaluate_agent_batch_creates_required_reports(settings, engine, tmp_path):
    report_dir = tmp_path / "report"
    summary = evaluate_agent_batch(FIXTURES, report_dir, settings, engine)
    assert summary["imported"] == 3
    for name in (
        "source_inventory.csv", "manual_grading_table.csv", "manual_grading_report.md",
        "failure_analysis.md", "ranked_candidates.md", "ranked_candidates.csv",
        "ranked_candidates.jsonl", "research_digest.md", "agent_import_errors.jsonl",
    ):
        assert (report_dir / name).exists(), f"missing {name}"
    for category in ("top_A_candidates", "top_B_candidates", "rejected_or_review_only"):
        assert (report_dir / category).is_dir()
    # Exactly one gate-passing candidate got its spec exported.
    assert len(summary["exported_specs"]) == 1
    specs = list((report_dir / "top_A_candidates").glob("backtest_spec_*.md"))
    assert len(specs) == 1
    csv_text = (report_dir / "ranked_candidates.csv").read_text()
    rejected = [h for h in summary["hypothesis_ids"]]
    candidate_rows_text = csv_text
    assert sum(1 for h in rejected if h in candidate_rows_text) == 1  # only the candidate
