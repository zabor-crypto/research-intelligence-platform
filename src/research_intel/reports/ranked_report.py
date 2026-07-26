"""Render the ranked candidate list as Markdown."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from research_intel.storage import repositories as repo
from research_intel.storage.models import Score, StrategyHypothesis


def _source_titles(session: Session, hyp: StrategyHypothesis) -> list[str]:
    titles: list[str] = []
    for sid in hyp.payload.get("source_ids", []):
        try:
            source = repo.get_source(session, int(sid))
        except (TypeError, ValueError):
            source = None
        titles.append(source.title if source else str(sid))
    return titles or ["(unknown source)"]


def _score_breakdown(score: Score) -> str:
    return "\n".join(
        f"| {name} | {value:.1f} |" for name, value in sorted(score.dimensions.items())
    )


def render_candidate_section(
    session: Session, rank: int, hyp: StrategyHypothesis, score: Score
) -> str:
    p = hyp.payload
    sources = "; ".join(_source_titles(session, hyp))
    next_step = (
        f"Export the backtest spec (`research-intel export-backtest-spec "
        f"--hypothesis-id {hyp.hypothesis_id}`) and hand it to the backtesting agent."
    )
    return f"""### {rank}. {p.get('hypothesis_name', hyp.hypothesis_id)}

Score: {score.weighted_total}/100
Status: {hyp.status}
Non-HFT Compatible: {"Yes" if not p.get('hft_or_low_latency_dependency') else "No"}
Source(s): {sources}
Timeframe: {p.get('timeframe', '')}
Asset Universe: {p.get('asset_universe', '')}

#### Core Hypothesis

{p.get('core_alpha_hypothesis', '')}

#### Required Data

{chr(10).join(f"- {d}" for d in p.get('required_data', []))}

#### Strategy Logic

Entry:
{chr(10).join(f"- {r}" for r in p.get('entry_rules', []))}

Exit:
{chr(10).join(f"- {r}" for r in p.get('exit_rules', []))}

Risk:
{chr(10).join(f"- {r}" for r in p.get('risk_rules', []))}

#### Score Breakdown

| Dimension | Score (0-10) |
|---|---|
{_score_breakdown(score)}

#### Why This Is Worth Testing

{p.get('one_sentence_idea', '')} Included because it passed all non-HFT and
feasibility hard filters with a weighted score of {score.weighted_total}/100.

#### Failure Modes

{chr(10).join(f"- {m}" for m in p.get('expected_failure_modes', []))}

#### Backtest Plan

{p.get('minimum_viable_backtest', '')}

Walk-forward: {p.get('walk_forward_validation_plan', '')}

Next step: {next_step}

---
"""


def render_ranked_markdown(session: Session, top: int | None = None) -> str:
    generated = datetime.now(UTC).strftime("%Y-%m-%d")
    lines = [f"# Ranked Strategy Candidates\n\nGenerated: {generated}\n"]
    rank = 0
    excluded_sections: list[str] = []
    for hyp, score in repo.ranked_hypotheses(session):
        exportable = (
            not score.excluded
            and hyp.status == "candidate"
            and hyp.payload.get("candidate_export_allowed", False)
        )
        if not exportable:
            reason = (
                score.exclusion_reason
                or (
                    "insufficient source parameterization (manual review needed)"
                    if hyp.status == "review_only" else hyp.status
                )
            )
            missing = hyp.payload.get("missing_for_backtest", [])
            missing_line = (
                f"\nMissing for backtest: {', '.join(missing)}\n" if missing else ""
            )
            excluded_sections.append(
                f"### {hyp.payload.get('hypothesis_name', hyp.hypothesis_id)}\n\n"
                f"Status: {hyp.status}\n"
                f"Rejected reason: {reason}\n{missing_line}"
            )
            continue
        rank += 1
        if top and rank > top:
            continue
        lines.append(render_candidate_section(session, rank, hyp, score))
    if rank == 0:
        lines.append("_No scored candidates yet. Run the pipeline first._\n")
    if excluded_sections:
        lines.append("\n## Rejected / Low Priority Ideas\n")
        lines.extend(excluded_sections)
    return "\n".join(lines)
