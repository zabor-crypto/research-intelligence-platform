"""End-to-end CLI test of the full MVP flow with the mock LLM."""

from __future__ import annotations

import re
from pathlib import Path

from typer.testing import CliRunner

from research_intel.cli import app
from tests.conftest import EXAMPLES

runner = CliRunner()


def _run(*args: str, expect_exit: int = 0) -> str:
    result = runner.invoke(app, list(args))
    assert result.exit_code == expect_exit, f"{args}: {result.output}\n{result.exception}"
    return result.output


def test_help_works():
    output = _run("--help")
    for command in ("init", "search", "ingest", "extract-all", "generate-hypotheses",
                    "score", "export-ranked", "export-backtest-spec", "report"):
        assert command in output


def test_full_mvp_flow(workspace: Path):
    _run("init")
    assert (workspace / "data" / "research_intel.db").is_file()

    _run("ingest", "--path", str(EXAMPLES / "sample_manual_source.md"))
    _run("ingest", "--path", str(EXAMPLES / "sample_hft_source.md"))
    _run("ingest", "--path", str(EXAMPLES / "sample_vague_source.md"))
    # re-ingest is a no-op (dedup)
    output = _run("ingest", "--path", str(EXAMPLES / "sample_manual_source.md"))
    assert "new_sources=0" in output

    _run("extract-all")
    output = _run("generate-hypotheses")
    assert "rejected_hft" in output  # HFT paper detected and quarantined
    match = re.search(r"(hyp-[0-9a-f]+)\s+\[candidate\]", output)
    assert match, output
    candidate_id = match.group(1)
    rejected = re.search(r"(hyp-[0-9a-f]+)\s+\[rejected_hft\]", output).group(1)
    vague = re.search(
        r"(hyp-[0-9a-f]+)\s+\[(?:review_only|rejected_unbacktestable)\]", output
    ).group(1)

    output = _run("score", "--all")
    assert "EXCLUDED (requires_hft_or_low_latency_edge)" in output

    _run("export-ranked", "--top", "10", "--format", "md")
    _run("export-ranked", "--top", "10", "--format", "csv")
    _run("export-ranked", "--top", "10", "--format", "jsonl")
    md = next((workspace / "exports").glob("ranked_candidates_*.md")).read_text()
    assert candidate_id in md  # candidate section present (id shown in next-step line)
    assert "Realized-Volatility Regime Filter" in md
    assert "Rejected / Low Priority Ideas" in md
    assert "requires_hft_or_low_latency_edge" in md
    csv_text = next((workspace / "exports").glob("ranked_candidates_*.csv")).read_text()
    assert candidate_id in csv_text
    assert rejected not in csv_text  # excluded ideas never reach candidate export
    assert vague not in csv_text  # ungrounded ideas never reach candidate export
    jsonl_text = next((workspace / "exports").glob("ranked_candidates_*.jsonl")).read_text()
    assert vague not in jsonl_text and rejected not in jsonl_text

    output = _run("export-backtest-spec", "--hypothesis-id", candidate_id)
    spec_path = Path(output.strip().split("exported: ")[-1])
    spec = (workspace / spec_path).read_text() if not spec_path.is_absolute() else spec_path.read_text()
    for section in ("Core Hypothesis", "Feature Formulas", "Strategy Parameters",
                    "Order Assumptions", "Entry Rules", "Exit Rules", "Risk Rules",
                    "Fees and Slippage Assumptions", "Baseline Comparisons",
                    "Walk-Forward Validation Plan", "Rejection Criteria",
                    "Minimum Acceptance Metrics"):
        assert section in spec
    # The spec must carry the actual source thresholds, not template defaults.
    for value in ("> 1.2", "< 0.8", "ret_30m", "> 0.5", "< 0.2",
                  "120 minutes", "1.5x ATR_60m", "7 bps", "Sharpe 1.4"):
        assert value in spec, f"spec missing source-derived value: {value}"

    # exporting a spec for the rejected HFT or ungrounded idea must fail loudly
    _run("export-backtest-spec", "--hypothesis-id", rejected, expect_exit=1)
    _run("export-backtest-spec", "--hypothesis-id", vague, expect_exit=1)

    output = _run("report", "--output", "reports/research_digest.md")
    digest = (workspace / "reports" / "research_digest.md").read_text()
    assert "Research Intelligence Digest" in digest
    assert "Top Strategy Candidates" in digest


def test_dry_run_writes_nothing(workspace: Path):
    _run("--dry-run", "init")
    assert not (workspace / "data").exists()


def test_extract_missing_document_errors(workspace: Path):
    _run("init")
    _run("extract", "--document-id", "999", expect_exit=1)
