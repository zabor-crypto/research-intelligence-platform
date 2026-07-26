"""Rule-shape validation: vague strategy logic must be rejected."""

from __future__ import annotations

import pytest

from research_intel.extraction.validators import (
    _entry_rule_is_concrete,
    _exit_rule_is_concrete,
    _risk_rule_is_concrete,
)

CONCRETE_ENTRIES = [
    "Enter long when 30-minute return > 0 and trend_strength = abs(ret_30m)/rv_60m > 0.5 "
    "while rv_short/rv_long > 1.2.",
    "Long entry: vol_ratio > 1.2 AND ret_30m > 0 AND trend_strength > 0.5",
    "Enter counter-trend when zscore of 12-bar return over rolling 100 bars exceeds 2.0 "
    "in absolute value",
    "Enter short perp when current funding rate > 90th percentile of its rolling 30-day history",
]

VAGUE_ENTRIES = [
    "Enter when signal is strong.",
    "Trade when market momentum appears.",
    "Enter during favorable regimes.",
    "Buy when conditions look good.",
    "Enter positions opportunistically based on flow.",
]


@pytest.mark.parametrize("rule", CONCRETE_ENTRIES)
def test_concrete_entry_rules_pass(rule: str):
    assert _entry_rule_is_concrete(rule)


@pytest.mark.parametrize("rule", VAGUE_ENTRIES)
def test_vague_entry_rules_fail(rule: str):
    assert not _entry_rule_is_concrete(rule)


CONCRETE_EXITS = [
    "Exit when trend_strength < 0.2",
    "Time stop: exit after 120 minutes in position",
    "Stop-loss at 1.5x ATR_60m from entry price",
    "Exit at pre-event VWAP anchor (take-profit)",
    "Exit on regime transition: vol_ratio < 0.8",
]

VAGUE_EXITS = [
    "Exit when appropriate.",
    "Close the position once momentum fades.",
    "Exit during unfavorable market conditions.",
]


@pytest.mark.parametrize("rule", CONCRETE_EXITS)
def test_concrete_exit_rules_pass(rule: str):
    assert _exit_rule_is_concrete(rule)


@pytest.mark.parametrize("rule", VAGUE_EXITS)
def test_vague_exit_rules_fail(rule: str):
    assert not _exit_rule_is_concrete(rule)


CONCRETE_RISK = [
    "max position risk 1% of equity per trade",
    "portfolio-level volatility target 15% annualized",
    "de-risk 50% when 30-day drawdown exceeds 10%",
    "leverage capped at 2x",
    "hard stop-loss on every position",
]

VAGUE_RISK = [
    "Manage risk prudently.",
    "Avoid excessive positions.",
    "Be careful in volatile markets.",
]


@pytest.mark.parametrize("rule", CONCRETE_RISK)
def test_concrete_risk_rules_pass(rule: str):
    assert _risk_rule_is_concrete(rule)


@pytest.mark.parametrize("rule", VAGUE_RISK)
def test_vague_risk_rules_fail(rule: str):
    assert not _risk_rule_is_concrete(rule)
