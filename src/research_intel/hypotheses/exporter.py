"""Export ranked candidates (CSV/JSONL/MD) and backtest handoff specs."""

from __future__ import annotations

import csv
import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from research_intel.storage import repositories as repo
from research_intel.storage.models import Score, StrategyHypothesis

logger = logging.getLogger(__name__)

RANKED_CSV_FIELDS = [
    "rank", "hypothesis_id", "hypothesis_name", "strategy_style", "timeframe",
    "asset_universe", "priority_score", "status", "non_hft_compatible",
    "required_data", "excluded", "exclusion_reason",
]


def is_exportable_candidate(hyp: StrategyHypothesis, score: Score) -> bool:
    """A row reaches candidate exports only if it survived every gate."""
    return (
        not score.excluded
        and hyp.status == "candidate"
        and bool(hyp.payload.get("candidate_export_allowed", False))
    )


def candidate_rows(session: Session, top: int | None = None) -> list[dict[str, Any]]:
    """Ranked, fully export-eligible candidates as flat dicts."""
    rows: list[dict[str, Any]] = []
    rank = 0
    for hyp, score in repo.ranked_hypotheses(session):
        if not is_exportable_candidate(hyp, score):
            continue
        rank += 1
        payload = hyp.payload
        rows.append({
            "rank": rank,
            "hypothesis_id": hyp.hypothesis_id,
            "hypothesis_name": payload.get("hypothesis_name", ""),
            "strategy_style": payload.get("strategy_style", ""),
            "timeframe": payload.get("timeframe", ""),
            "asset_universe": payload.get("asset_universe", ""),
            "priority_score": score.weighted_total,
            "status": hyp.status,
            "non_hft_compatible": not payload.get("hft_or_low_latency_dependency", False),
            "required_data": ";".join(payload.get("required_data", [])),
            "excluded": False,
            "exclusion_reason": "",
        })
        if top and rank >= top:
            break
    return rows


def export_ranked(
    session: Session, out_dir: Path, top: int, fmt: str
) -> Path:
    """Write ranked candidates in csv, jsonl, or md format. Returns the path."""
    out_dir.mkdir(parents=True, exist_ok=True)
    rows = candidate_rows(session, top=top)
    stamp = datetime.now(UTC).strftime("%Y%m%d")
    if fmt == "csv":
        path = out_dir / f"ranked_candidates_{stamp}.csv"
        with path.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=RANKED_CSV_FIELDS)
            writer.writeheader()
            writer.writerows(rows)
    elif fmt == "jsonl":
        path = out_dir / f"ranked_candidates_{stamp}.jsonl"
        with path.open("w", encoding="utf-8") as fh:
            for hyp, score in repo.ranked_hypotheses(session):
                if not is_exportable_candidate(hyp, score):
                    continue
                fh.write(json.dumps({
                    "hypothesis": hyp.payload,
                    "score": {
                        "dimensions": score.dimensions,
                        "weighted_total": score.weighted_total,
                    },
                }) + "\n")
    elif fmt == "md":
        from research_intel.reports.ranked_report import render_ranked_markdown

        path = out_dir / f"ranked_candidates_{stamp}.md"
        path.write_text(render_ranked_markdown(session, top=top), encoding="utf-8")
    else:
        raise ValueError(f"unsupported export format '{fmt}' (use csv, jsonl, or md)")
    logger.info("exported ranked candidates to %s", path)
    return path


# ---------------------------------------------------------------- backtest spec

SPEC_SECTIONS: list[tuple[str, str]] = [
    ("Core Hypothesis", "core_alpha_hypothesis"),
    ("Target Market", "market"),
    ("Target Assets", "asset_universe"),
    ("Timeframe", "timeframe"),
]


def build_source_references(session: Session, hyp: StrategyHypothesis) -> list[dict[str, Any]]:
    """Enrich source ids with title/type/url/authors/date from the DB."""
    from research_intel.storage.models import Extraction

    refs: list[dict[str, Any]] = []
    extraction = session.get(Extraction, hyp.extraction_id)
    document_id = extraction.document_id if extraction else None
    for sid in hyp.payload.get("source_ids", []):
        try:
            source = repo.get_source(session, int(sid))
        except (TypeError, ValueError):
            source = None
        if source is None:
            refs.append({"source_id": str(sid)})
            continue
        refs.append({
            "source_id": str(source.id),
            "document_id": str(document_id) if document_id is not None else None,
            "title": source.title,
            "source_type": source.source_type,
            "url_or_path": source.url or source.external_id,
            "authors": source.authors,
            "published_date": source.published_date,
        })
    return refs


def build_backtest_spec(
    hyp: StrategyHypothesis,
    score: Score | None,
    source_references: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    p = hyp.payload
    return {
        "strategy_name": p.get("hypothesis_name", hyp.hypothesis_id),
        "hypothesis_id": hyp.hypothesis_id,
        "research_sources": p.get("source_ids", []),
        "source_references": source_references or [],
        "parameterization_status": p.get("parameterization_status", ""),
        "optimization_constraints": p.get("optimization_constraints", []),
        "unmapped_extracted_parameters": p.get("unmapped_extracted_parameters", {}),
        "source_archetype": p.get("source_archetype", "unknown"),
        "generated_archetype": p.get("generated_archetype", "unknown"),
        "archetype_fidelity": p.get("archetype_fidelity", ""),
        "preserved_alpha_triggers": p.get("preserved_alpha_triggers", []),
        "dropped_alpha_triggers": p.get("dropped_alpha_triggers", []),
        "source_entry_conditions": p.get("source_entry_conditions", []),
        "preserved_entry_conditions": p.get("preserved_entry_conditions", []),
        "dropped_entry_conditions": p.get("dropped_entry_conditions", []),
        "entry_condition_fidelity": p.get("entry_condition_fidelity", ""),
        "spec_consistency": p.get("spec_consistency", ""),
        "consistency_failures": p.get("consistency_failures", []),
        "consistency_warnings": p.get("consistency_warnings", []),
        "source_asset_universe": p.get("source_asset_universe", ""),
        "generated_asset_universe": p.get("generated_asset_universe", p.get("asset_universe", "")),
        "asset_universe_provenance": p.get("asset_universe_provenance", ""),
        "optional_robustness_universe": p.get("optional_robustness_universe", ""),
        "source_risk_parameters": p.get("source_risk_parameters", {}),
        "generated_risk_parameters": p.get("generated_risk_parameters", {}),
        "risk_parameter_provenance": p.get("risk_parameter_provenance", {}),
        "source_cost_parameters": p.get("source_cost_parameters", {}),
        "generated_cost_parameters": p.get("generated_cost_parameters", {}),
        "cost_parameter_provenance": p.get("cost_parameter_provenance", {}),
        "core_hypothesis": p.get("core_alpha_hypothesis", ""),
        "target_market": p.get("market", "crypto"),
        "target_assets": p.get("asset_universe", ""),
        "timeframe": p.get("timeframe", ""),
        "required_data": p.get("required_data", []),
        "feature_definitions": p.get("features", []),
        "feature_formulas": p.get("feature_formulas", {}),
        "strategy_parameters": p.get("strategy_parameters", {}),
        "parameter_provenance": p.get("parameter_provenance", {}),
        "parameter_source_quality": p.get("parameter_source_quality", ""),
        "source_reported_metrics": p.get("source_reported_metrics", {}),
        "order_assumptions": p.get("order_assumptions", ""),
        "baseline_comparisons": p.get("baseline_comparisons", []),
        "entry_rules": p.get("entry_rules", []),
        "exit_rules": p.get("exit_rules", []),
        "risk_rules": p.get("risk_rules", []),
        "position_sizing": p.get("position_sizing", ""),
        "fees_slippage_assumptions": p.get("fees_slippage_model", ""),
        "optimization_parameters": p.get("optimization_parameters", {}),
        "walk_forward_validation_plan": p.get("walk_forward_validation_plan", ""),
        "expected_weaknesses": p.get("expected_failure_modes", []),
        "rejection_criteria": [
            "negative OOS expectancy after fees in majority of walk-forward folds",
            "edge concentrated in a single parameter cell or single market regime",
            "performance indistinguishable from randomized-entry baseline",
        ],
        "minimum_acceptance_metrics": {
            "oos_sharpe": ">= 1.0 after fees",
            "oos_profit_factor": ">= 1.15",
            "max_drawdown": "<= 25%",
            "min_trades": ">= 200 across the full backtest",
            "walk_forward_folds_positive": ">= 60%",
        },
        "priority_score": score.weighted_total if score else hyp.priority_score,
        "non_hft_compatible": not p.get("hft_or_low_latency_dependency", False),
        "non_hft_adaptation": p.get("non_hft_adaptation", ""),
        "minimum_viable_backtest": p.get("minimum_viable_backtest", ""),
    }


FACT_LABELS = {
    "portfolio_vol_target_pct": "Portfolio volatility target: {v}% annualized ({p})",
    "monthly_drawdown_halt_pct": "Monthly drawdown halt: {v}% ({p})",
    "risk_per_trade_pct": "Risk per trade: {v}% of equity ({p})",
    "max_trades_per_day": "Max trades per day per asset: {v} ({p})",
    "max_leverage_x": "Max leverage: {v}x ({p})",
    "per_pair_notional_cap_pct": "Per-pair notional cap: {v}% of equity ({p})",
    "basis_kill_switch_stdev_mult": "Basis kill-switch: {v}x rolling stdev ({p})",
    "carry_cost_clearance_mult": "Carry must clear costs by: {v}x ({p})",
    "exchange_outage_derisk": "De-risk during exchange outages ({p})",
    "drawdown_derisk_30d_pct": "De-risk 50% at 30-day drawdown: {v}% ({p})",
    "fee_slippage_bps_per_side": "Fees+slippage: {v} bps per side ({p})",
}


def _render_fact_lines(spec: dict[str, Any]) -> str:
    lines: list[str] = []
    for kind in ("risk", "cost"):
        generated = spec.get(f"generated_{kind}_parameters", {}) or {}
        provenance = spec.get(f"{kind}_parameter_provenance", {}) or {}
        for key, value in generated.items():
            template = FACT_LABELS.get(key, key.replace("_", " ") + ": {v} ({p})")
            display = "" if value is True else value
            lines.append(
                "- " + template.format(v=display, p=provenance.get(key, "default")).replace("  ", " ")
            )
    return "\n".join(lines) or "- (none stated by source; platform defaults apply)"


def render_backtest_spec_md(spec: dict[str, Any]) -> str:
    def bullets(items: list[Any]) -> str:
        return "\n".join(f"- {i}" for i in items) or "- (none specified)"

    metrics = "\n".join(f"- {k}: {v}" for k, v in spec["minimum_acceptance_metrics"].items())
    params = "\n".join(f"- {k}: {v}" for k, v in spec["optimization_parameters"].items()) or "- (none)"
    formulas = "\n".join(
        f"- `{name}` = {formula}" for name, formula in spec.get("feature_formulas", {}).items()
    ) or "- (none)"
    provenance = spec.get("parameter_provenance", {})
    param_rows = "\n".join(
        f"| {name} | {value} | {provenance.get(name, 'default')} |"
        for name, value in spec.get("strategy_parameters", {}).items()
    ) or "| (none) | | |"
    source_metrics = "\n".join(
        f"- {name.replace('_', ' ')}: {value}"
        for name, value in spec.get("source_reported_metrics", {}).items()
    ) or "- (none reported)"
    sharpe = spec.get("source_reported_metrics", {}).get("sharpe_after_costs")
    sharpe_line = (
        f"\nSource reports Sharpe {sharpe} after costs"
        + (
            f" (vs Sharpe {spec['source_reported_metrics']['sharpe_unconditional']} unconditional)."
            if "sharpe_unconditional" in spec.get("source_reported_metrics", {})
            else "."
        )
        if sharpe is not None
        else ""
    )
    refs = spec.get("source_references") or []
    if refs:
        ref_lines = []
        for ref in refs:
            parts = [f"**{ref.get('title', ref.get('source_id', '?'))}**"]
            if ref.get("source_type"):
                parts.append(f"type: {ref['source_type']}")
            if ref.get("authors"):
                parts.append(f"authors: {', '.join(a for a in ref['authors'] if a)}")
            if ref.get("published_date"):
                parts.append(f"published: {ref['published_date']}")
            if ref.get("url_or_path"):
                parts.append(f"location: {ref['url_or_path']}")
            parts.append(
                f"source_id: {ref.get('source_id')}, document_id: {ref.get('document_id')}"
            )
            ref_lines.append("- " + "; ".join(parts))
        sources_block = "\n".join(ref_lines)
    else:
        sources_block = bullets(spec["research_sources"])
    constraints = bullets(spec.get("optimization_constraints", [])) if spec.get(
        "optimization_constraints"
    ) else "- (none; all grid combinations are valid)"
    return f"""# Backtest Spec — {spec['strategy_name']}

Hypothesis ID: `{spec['hypothesis_id']}`
Priority Score: {spec['priority_score']}/100
Non-HFT Compatible: {"Yes" if spec['non_hft_compatible'] else "No"}
Parameter Source Quality: {spec.get('parameter_source_quality', 'unknown')}
Parameterization Status: {spec.get('parameterization_status', 'unknown')}

## Research Source(s)

{sources_block}

## Core Hypothesis

{spec['core_hypothesis']}

## Source Reported Metrics

{source_metrics}{sharpe_line}

## Target Market

{spec['target_market']}

## Archetype Fidelity

Source archetype: {spec.get('source_archetype', 'unknown')}
Generated archetype: {spec.get('generated_archetype', 'unknown')}
Fidelity: {spec.get('archetype_fidelity', 'unknown')}
Preserved alpha triggers: {', '.join(spec.get('preserved_alpha_triggers', [])) or '(none required)'}
Entry-condition fidelity: {spec.get('entry_condition_fidelity', 'unknown')}
Source entry conditions: {'; '.join(spec.get('source_entry_conditions', [])) or '(none stated)'}
Dropped entry conditions: {'; '.join(spec.get('dropped_entry_conditions', [])) or '(none)'}
Spec consistency: {spec.get('spec_consistency', 'unknown')}{(chr(10) + 'Consistency warnings: ' + '; '.join(spec.get('consistency_warnings', []))) if spec.get('consistency_warnings') else ''}

## Target Assets

Primary source-faithful universe: {spec.get('source_asset_universe') or spec['target_assets']}
Optional robustness universe: {spec.get('optional_robustness_universe') or '(none)'}

Universe provenance: {spec.get('asset_universe_provenance', 'unknown')}. The primary
backtest MUST run on the source-faithful universe; the robustness universe is
an optional secondary run, never a substitute.

## Source Risk & Cost Facts

{_render_fact_lines(spec)}

## Timeframe

Bar timeframe: {spec['timeframe']}

## Required Data

{bullets(spec['required_data'])}

## Feature Definitions

{bullets(spec['feature_definitions'])}

## Feature Formulas

{formulas}

## Strategy Parameters

| Parameter | Value | Provenance |
|---|---|---|
{param_rows}

Parameters marked `source` were extracted from the research source;
`default` values are platform defaults and must be treated as free
parameters, not findings.

## Unmapped Source Parameters

{chr(10).join(f"- {k} = {v} (extracted from source but not mapped to a template parameter — resolve manually)" for k, v in spec.get('unmapped_extracted_parameters', {}).items()) or "- (none)"}

## Order Assumptions

{spec.get('order_assumptions', '') or '(not specified)'}

## Entry Rules

{bullets(spec['entry_rules'])}

## Exit Rules

{bullets(spec['exit_rules'])}

## Risk Rules

{bullets(spec['risk_rules'])}

## Position Sizing

{spec['position_sizing']}

## Fees and Slippage Assumptions

{spec['fees_slippage_assumptions']}

## Optimization Parameters

Grid keys reference the strategy parameter / rule names above.

{params}

## Optimization Constraints

The backtester MUST enforce these when combining grid values; grid
combinations violating any constraint are invalid and must be skipped.

{constraints}

## Baseline Comparisons

{bullets(spec.get('baseline_comparisons', []))}

## Walk-Forward Validation Plan

{spec['walk_forward_validation_plan']}

## Minimum Viable Backtest

{spec['minimum_viable_backtest']}

## Expected Weaknesses

{bullets(spec['expected_weaknesses'])}

## Rejection Criteria

{bullets(spec['rejection_criteria'])}

## Minimum Acceptance Metrics

{metrics}
"""


def export_backtest_spec(
    session: Session, hypothesis_id: str, out_dir: Path, fmt: str = "md"
) -> Path:
    hyp = repo.get_hypothesis(session, hypothesis_id)
    if hyp is None:
        raise ValueError(f"hypothesis '{hypothesis_id}' not found")
    score = repo.latest_score(session, hypothesis_id)
    if hyp.status == "review_only":
        raise ValueError(
            f"hypothesis '{hypothesis_id}' is review_only because source lacks "
            "concrete parameters/rules; cannot export backtest spec"
        )
    if hyp.status != "candidate" or (score is not None and score.excluded):
        reason = (score.exclusion_reason if score and score.excluded else None) or (
            "requires_hft_or_low_latency_edge" if hyp.status == "rejected_hft" else hyp.status
        )
        raise ValueError(
            f"hypothesis '{hypothesis_id}' is rejected ({reason}) and cannot be "
            "exported as a backtest candidate"
        )
    if not hyp.payload.get("backtest_spec_export_allowed", False):
        raise ValueError(
            f"hypothesis '{hypothesis_id}' has backtest_spec_export_allowed=false; "
            "cannot export backtest spec"
        )
    if hyp.payload.get("parameterization_status") in ("default_parameterized", "unparameterized"):
        raise ValueError(
            f"hypothesis '{hypothesis_id}' is {hyp.payload.get('parameterization_status')}: "
            "default/absent parameters cannot masquerade as source logic; "
            "cannot export backtest spec"
        )
    # Execution / Cost Feasibility Gate enforcement (backward-compatible): only fires when
    # the hypothesis payload carries a `cost_gate_record` or is flagged `requires_cost_gate`.
    # Legacy candidates without either are unaffected (the pure hook returns None). The hook
    # lives in `research_gates` (DB-free) so it can be audited/tested without storage imports.
    from research_gates import enforce_cost_gate_export_hook

    guard = enforce_cost_gate_export_hook({**hyp.payload, "candidate_id": hypothesis_id})
    if guard is not None and not guard["export_allowed"]:
        raise ValueError(
            f"hypothesis '{hypothesis_id}' cost_gate_export_blocked: {guard['reason']} "
            f"(admission={guard['admission_decision']}, "
            f"cost_gate_status={guard['cost_gate_status']}); cannot export backtest spec"
        )
    spec = build_backtest_spec(hyp, score, build_source_references(session, hyp))
    if guard is not None and guard["export_allowed"]:
        # persist the guard result in the spec metadata (only for genuinely cost-gated
        # candidates; never fabricate a pass for legacy exports)
        spec["cost_gate_export_guard"] = {
            k: guard.get(k)
            for k in (
                "export_allowed",
                "admission_decision",
                "cost_gate_status",
                "export_scope",
                "forbidden_next_steps",
                "reason",
            )
        }
    out_dir.mkdir(parents=True, exist_ok=True)
    if fmt == "json":
        path = out_dir / f"backtest_spec_{hypothesis_id}.json"
        path.write_text(json.dumps(spec, indent=2), encoding="utf-8")
    else:
        path = out_dir / f"backtest_spec_{hypothesis_id}.md"
        path.write_text(render_backtest_spec_md(spec), encoding="utf-8")
    repo.add_backtest_spec(session, hyp, fmt, str(path), spec)
    logger.info("exported backtest spec to %s", path)
    return path
