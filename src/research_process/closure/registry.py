"""Terminal strategy-closure registry + fail-closed selectors.

A closed strategy must never silently pass a promotion-oriented selector. Promotion selectors
(candidate / robustness / optimization / historical-backtest / deployment / live) return a
structured :class:`SelectorDecision` with ``admitted=False`` and a terminal-state exclusion reason.
Diagnostic selectors (negative-control / regression-fixture / benchmark) admit it, because a dead
strategy is genuinely useful as a negative control. Reopen is impossible: :meth:`reopen` raises.

The point of this module is that "we decided not to look at that one again" is a promise a human
makes and forgets. This is the same promise expressed as a data structure that a selector has to
consult.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass

CLOSURE_SCHEMA_VERSION = "terminal-closure/1.0"

# selector classes that must FAIL CLOSED for a terminally-closed strategy
PROMOTION_SELECTORS = frozenset({
    "candidate_pool", "code_generation_queue", "historical_backtest_queue", "robustness_queue",
    "optimization_queue", "deployment_queue", "live_trading_queue", "forward_validation_queue",
})
# selector classes that legitimately ADMIT a closed strategy for diagnostic reuse
DIAGNOSTIC_SELECTORS = frozenset({
    "negative_control", "cross_sectional_engine_regression_fixture", "accounting_regression_fixture",
    "lifecycle_regression_fixture", "failure_pattern_example", "research_benchmark",
})

#: The terminal state used when a strategy is closed for absence of gross edge — the signal lost
#: money before modeled friction, so no cost, sizing or execution change can rescue it.
CLOSED_NO_GROSS_EDGE = "closed_no_gross_edge"
#: Terminal state for a real gross edge that modeled friction consumed entirely.
CLOSED_EDGE_NEGATIVE_AFTER_COSTS = "closed_edge_negative_after_costs"

DEFAULT_DIAGNOSTIC_USES = (
    "negative_control", "cross_sectional_engine_regression_fixture",
    "accounting_regression_fixture", "lifecycle_regression_fixture",
    "failure_pattern_example", "research_benchmark",
)


@dataclass(frozen=True)
class ClosedStrategy:
    """One terminally closed strategy and the uses that remain open to it."""

    strategy_id: str
    terminal_state: str
    primary_failure: str
    closure_release: str
    closure_evidence_hash: str
    reopen_allowed: bool = False
    rescue_allowed: bool = False
    optimization_allowed: bool = False
    robustness_allowed: bool = False
    candidate_eligible: bool = False
    deployment_eligible: bool = False
    forward_validation_eligible: bool = False
    allowed_future_uses: tuple = ()
    disallowed_future_uses: tuple = ()


@dataclass(frozen=True)
class SelectorDecision:
    strategy_id: str
    selector: str
    admitted: bool
    reason: str


class TerminalClosureRegistry:
    """Holds closed strategies and adjudicates selector requests fail-closed."""

    def __init__(self):
        self._closed: dict = {}

    def register(self, strategy: ClosedStrategy) -> None:
        self._closed[strategy.strategy_id] = strategy

    def is_closed(self, strategy_id: str) -> bool:
        return strategy_id in self._closed

    def get(self, strategy_id: str) -> ClosedStrategy | None:
        return self._closed.get(strategy_id)

    def closed_strategy_ids(self) -> tuple:
        return tuple(sorted(self._closed))

    def select(self, strategy_id: str, selector: str) -> SelectorDecision:
        """Fail-closed for promotion selectors; admit for diagnostic selectors."""
        strat = self._closed.get(strategy_id)
        if strat is None:
            # not a closed strategy — this registry makes no claim; caller uses its own logic
            return SelectorDecision(strategy_id, selector, admitted=True, reason="not_closed")
        if selector in PROMOTION_SELECTORS:
            return SelectorDecision(strategy_id, selector, admitted=False,
                                    reason=f"terminal_strategy_{strat.terminal_state}")
        if selector in DIAGNOSTIC_SELECTORS:
            return SelectorDecision(strategy_id, selector, admitted=True,
                                    reason="diagnostic_reuse_of_closed_strategy")
        # unknown selector for a closed strategy: fail closed by default
        return SelectorDecision(strategy_id, selector, admitted=False,
                                reason=f"terminal_strategy_{strat.terminal_state}")

    def reopen(self, strategy_id: str):
        """Always raises. Reopening is not a permission that can be granted."""
        strat = self._closed.get(strategy_id)
        state = strat.terminal_state if strat else "not_closed"
        raise PermissionError(
            f"reopen prohibited: {strategy_id} is terminally closed ({state})")


def closed_no_gross_edge(
    strategy_id: str,
    *,
    closure_release: str,
    closure_evidence_hash: str = "",
    primary_failure: str = "gross_edge_absent",
    terminal_state: str = CLOSED_NO_GROSS_EDGE,
) -> ClosedStrategy:
    """Build a :class:`ClosedStrategy` with every promotion path disallowed.

    ``closure_evidence_hash`` should be the content hash of the frozen adjudication artifact that
    justified the closure, so the record points at evidence rather than at a decision.
    """
    return ClosedStrategy(
        strategy_id=strategy_id,
        terminal_state=terminal_state,
        primary_failure=primary_failure,
        closure_release=closure_release,
        closure_evidence_hash=closure_evidence_hash,
        allowed_future_uses=DEFAULT_DIAGNOSTIC_USES,
        disallowed_future_uses=tuple(sorted(PROMOTION_SELECTORS)),
    )


def registry_from(closures) -> TerminalClosureRegistry:
    """Build a registry from an iterable of :class:`ClosedStrategy` records."""
    reg = TerminalClosureRegistry()
    for c in closures:
        reg.register(c)
    return reg


def with_evidence_hash(strategy: ClosedStrategy, evidence_hash: str) -> ClosedStrategy:
    """Return a copy of ``strategy`` bound to a closure-evidence hash."""
    return dataclasses.replace(strategy, closure_evidence_hash=evidence_hash)
