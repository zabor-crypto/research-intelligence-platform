"""Spec consistency validator (v0.2.1 P1).

v0.2 preserved source facts in dedicated payload fields, but downstream
executable sections (position sizing, minimum viable backtest) could still
carry generic defaults that contradict them. This validator checks that
source-derived facts are actually used by the executable sections — presence
of a fact is not enough; nothing downstream may contradict it.
"""

from __future__ import annotations

import re
from typing import Any


def _num(value: Any) -> str:
    """Render a number the way rule text renders it (12, 0.5, 2)."""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def _contains_number(text: str, value: Any) -> bool:
    token = _num(value)
    return bool(re.search(rf"(?<![\d.]){re.escape(token)}(?![\d.])", text))


def validate_spec_consistency(hypothesis_payload: dict[str, Any]) -> dict[str, Any]:
    """Validate that source facts are not contradicted by executable sections.

    Returns {"spec_consistency": strong|partial|weak|broken,
             "consistency_failures": [...], "consistency_warnings": [...]}.
    Grading: no issues -> strong; warnings only -> partial; 1-2 failures ->
    weak; 3+ failures -> broken. weak/broken are hard-gated by the generator.
    """
    p = hypothesis_payload
    failures: list[str] = []
    warnings: list[str] = []

    risk = p.get("generated_risk_parameters", {}) or {}
    risk_prov = p.get("risk_parameter_provenance", {}) or {}
    sizing = (p.get("position_sizing", "") or "").lower()
    mvb = p.get("minimum_viable_backtest", "") or ""

    # --- source risk values must drive position sizing -----------------
    if risk_prov.get("portfolio_vol_target_pct") == "source":
        target = risk["portfolio_vol_target_pct"]
        if not _contains_number(sizing, target):
            failures.append(
                f"position_sizing does not use source portfolio vol target {_num(target)}%"
            )
        if target != 15 and _contains_number(sizing, 15):
            failures.append(
                f"position_sizing uses default 15% vol target; source says {_num(target)}%"
            )

    if risk_prov.get("risk_per_trade_pct") == "source":
        rpt = risk["risk_per_trade_pct"]
        if not _contains_number(sizing, rpt):
            failures.append(
                f"position_sizing does not use source risk-per-trade {_num(rpt)}%"
            )
        if rpt != 1 and re.search(r"(?<![\d.])1(?![\d.])\s*%\s*equity", sizing):
            failures.append(
                f"position_sizing uses generic 1% risk; source says {_num(rpt)}%"
            )

    if risk_prov.get("max_leverage_x") == "source":
        lev = risk["max_leverage_x"]
        if not _contains_number(sizing, lev):
            failures.append(f"position_sizing does not enforce source {_num(lev)}x leverage cap")

    if risk_prov.get("per_pair_notional_cap_pct") == "source":
        cap = risk["per_pair_notional_cap_pct"]
        if not _contains_number(sizing, cap):
            failures.append(
                f"position_sizing does not enforce source {_num(cap)}% per-pair notional cap"
            )

    # Hedged carry strategies must not default to generic ATR-stop sizing.
    if (
        risk_prov.get("max_leverage_x") == "source"
        or risk_prov.get("per_pair_notional_cap_pct") == "source"
    ) and "atr" in sizing and "optional" not in sizing:
        failures.append(
            "position_sizing uses generic ATR-stop sizing for a hedged carry "
            "strategy without marking it optional non-source robustness logic"
        )

    # --- source universe must be the primary backtest universe ---------
    source_universe = p.get("source_asset_universe", "") or ""
    if source_universe and p.get("asset_universe_provenance") == "source":
        if source_universe.lower() not in mvb.lower():
            failures.append(
                "minimum_viable_backtest does not use the source-faithful "
                f"universe '{source_universe}' as primary"
            )
        elif "primary" not in mvb.lower():
            warnings.append(
                "minimum_viable_backtest uses the source universe but does not "
                "label it 'Primary'"
            )
        robustness = p.get("optional_robustness_universe", "")
        if robustness and robustness.lower() not in mvb.lower():
            warnings.append(
                "optional robustness universe declared but absent from "
                "minimum_viable_backtest"
            )

    if failures:
        grade = "broken" if len(failures) >= 3 else "weak"
    elif warnings:
        grade = "partial"
    else:
        grade = "strong"
    return {
        "spec_consistency": grade,
        "consistency_failures": failures,
        "consistency_warnings": warnings,
    }
