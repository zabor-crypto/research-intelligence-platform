"""insolvency-taxonomy-v2 — additive equity-solvency classification.

Separates two distinct facts that prose routinely conflates:

* ``ever_nonpositive_equity``     — equity <= 0 at ANY event-level timestamp.
* ``terminal_nonpositive_equity`` — terminal equity <= 0.

``recovered_after_nonpositive_equity`` is exactly ``ever_nonpositive and not terminal_nonpositive``.

When unconstrained accounting is allowed to continue THROUGH an equity zero-crossing (no liquidation,
no margin call, no recapitalization modeled), percentage-return / Sharpe / Sortino computed on that
equity base are NOT economically interpretable: a return series that passes through zero equity has
no economic meaning. Those flags are therefore ``False`` for any run that ever went non-positive.

This module introduces NO liquidation, margin-call or external-recapitalization assumptions. It only
reclassifies already-computed, authoritative quantities — introducing a liquidation model *after*
seeing the result would be exactly the post-hoc rescue the process exists to prevent.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

SCHEMA_VERSION = "insolvency-taxonomy/2.0"

TERMINAL_RECOVERED = "recovered_after_nonpositive_equity"
TERMINAL_NONPOSITIVE = "terminal_nonpositive_equity"
TERMINAL_SOLVENT_THROUGHOUT = "solvent_throughout"


@dataclass(frozen=True)
class InsolvencyRecord:
    """One run's equity-solvency classification (insolvency-taxonomy-v2)."""

    run_id: str
    ever_nonpositive_equity: bool
    first_nonpositive_equity_timestamp: int | None
    minimum_equity: float
    minimum_equity_timestamp: int | None
    terminal_nonpositive_equity: bool
    terminal_equity: float
    recovered_after_nonpositive_equity: bool
    unconstrained_accounting_continued_after_insolvency: bool
    percentage_return_metrics_economically_interpretable: bool
    sharpe_economically_interpretable: bool
    sortino_economically_interpretable: bool
    terminal_state: str

    def to_dict(self) -> dict:
        return asdict(self)


def reconstruct_minimum_equity(max_drawdown_fraction: float, max_drawdown_quote: float) -> float:
    """Trough (minimum) equity reconstructed from a max-drawdown summary block.

    ``max_drawdown_fraction = max_drawdown_quote / peak_equity`` (both signed, negative for a real
    drawdown), so ``peak_equity = max_drawdown_quote / max_drawdown_fraction`` and
    ``minimum_equity = peak_equity + max_drawdown_quote``. This is a reconstruction from persisted
    summary statistics, NOT an event-level read; callers must record the basis.
    """
    if max_drawdown_fraction == 0:
        raise ValueError("max_drawdown_fraction == 0: cannot reconstruct peak equity")
    peak_equity = max_drawdown_quote / max_drawdown_fraction
    return peak_equity + max_drawdown_quote


def classify_from_max_drawdown(
    run_id: str,
    terminal_equity: float,
    max_drawdown_fraction: float,
    max_drawdown_quote: float,
    minimum_equity_timestamp: int | None,
    *,
    first_nonpositive_equity_timestamp: int | None = None,
    unconstrained_accounting: bool = True,
) -> InsolvencyRecord:
    """Classify a single run from its authoritative max-drawdown block + terminal equity.

    ``first_nonpositive_equity_timestamp`` is passed through only when an event-level equity curve
    is available; otherwise it stays ``None`` (not recoverable from a summary-only artifact).
    """
    minimum_equity = reconstruct_minimum_equity(max_drawdown_fraction, max_drawdown_quote)
    ever_nonpositive = minimum_equity <= 0.0
    terminal_nonpositive = terminal_equity <= 0.0
    recovered = ever_nonpositive and not terminal_nonpositive
    interpretable = not ever_nonpositive
    if terminal_nonpositive:
        terminal_state = TERMINAL_NONPOSITIVE
    elif ever_nonpositive:
        terminal_state = TERMINAL_RECOVERED
    else:
        terminal_state = TERMINAL_SOLVENT_THROUGHOUT
    return InsolvencyRecord(
        run_id=run_id,
        ever_nonpositive_equity=ever_nonpositive,
        first_nonpositive_equity_timestamp=first_nonpositive_equity_timestamp,
        minimum_equity=minimum_equity,
        minimum_equity_timestamp=minimum_equity_timestamp,
        terminal_nonpositive_equity=terminal_nonpositive,
        terminal_equity=terminal_equity,
        recovered_after_nonpositive_equity=recovered,
        unconstrained_accounting_continued_after_insolvency=(
            unconstrained_accounting and ever_nonpositive),
        percentage_return_metrics_economically_interpretable=interpretable,
        sharpe_economically_interpretable=interpretable,
        sortino_economically_interpretable=interpretable,
        terminal_state=terminal_state,
    )


def validate_record(rec: InsolvencyRecord) -> None:
    """Enforce the invariant relationships. Raises ``ValueError`` on any inconsistency."""
    if rec.recovered_after_nonpositive_equity != (
        rec.ever_nonpositive_equity and not rec.terminal_nonpositive_equity
    ):
        raise ValueError(f"{rec.run_id}: recovered flag inconsistent with ever/terminal")
    if rec.terminal_nonpositive_equity != (rec.terminal_equity <= 0.0):
        raise ValueError(
            f"{rec.run_id}: terminal_nonpositive_equity inconsistent with terminal_equity")
    if rec.ever_nonpositive_equity and rec.percentage_return_metrics_economically_interpretable:
        raise ValueError(
            f"{rec.run_id}: %-return cannot be interpretable through an equity zero-crossing")
    if rec.ever_nonpositive_equity and (rec.minimum_equity > 0.0):
        raise ValueError(f"{rec.run_id}: ever_nonpositive but minimum_equity > 0")
