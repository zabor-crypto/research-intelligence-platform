"""historical-backtest-artifact-contract-v2.

Makes the immutable, event-level equity curve a MANDATORY first-class artifact for every historical
backtest. A summary-only historical result fails the gate.

The reason is narrow and practical: a summary block can tell you a run ended at +8%, and cannot tell
you that it passed through zero equity on the way. Every question worth asking after the fact —
when did solvency break, which event caused the drawdown, does the accounting identity hold at each
step — needs the event-level rows, and they cannot be reconstructed later from a summary.
"""

from __future__ import annotations

SCHEMA_VERSION = "historical-backtest-artifact-contract/2.0"

# Every persisted event-level row must carry all of these fields.
REQUIRED_EVENT_FIELDS = (
    "event_level_timestamp",
    "cash",
    "position_market_value",
    "equity",
    "reference_price_gross_pnl",
    "execution_price_pnl",
    "cumulative_slippage",
    "cumulative_fees",
    "cumulative_funding",
    "net_pnl",
    "event_type",
    "valuation_basis",
    "source_hashes",
)

VALID = "historical_backtest_valid"
BLOCKED_MISSING_EVENT_EQUITY = "historical_backtest_blocked_missing_event_equity_artifact"


def historical_backtest_validity(event_level_equity_curve_persisted: bool) -> str:
    """The additive gate: validity REQUIRES a persisted event-level equity curve."""
    return VALID if event_level_equity_curve_persisted else BLOCKED_MISSING_EVENT_EQUITY


def missing_event_fields(row: dict) -> tuple:
    """Return the required event-row fields absent from ``row`` (empty tuple == complete)."""
    return tuple(f for f in REQUIRED_EVENT_FIELDS if f not in row)


def event_row_complete(row: dict) -> bool:
    return not missing_event_fields(row)
