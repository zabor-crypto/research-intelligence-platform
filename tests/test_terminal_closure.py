"""Terminal closure: a strategy closed for absence of edge cannot come back."""

from __future__ import annotations

import pytest

from research_process.closure import registry as REG

SID = "source-b-xsec-reversal-v1"


def closed() -> REG.ClosedStrategy:
    return REG.closed_no_gross_edge(
        SID,
        closure_release="research-pipeline-v1.0.29",
        closure_evidence_hash="sha256:ea8db390…",
    )


def a_registry() -> REG.TerminalClosureRegistry:
    return REG.registry_from([closed()])


def test_the_factory_disallows_every_promotion_path():
    c = closed()
    assert c.terminal_state == REG.CLOSED_NO_GROSS_EDGE
    assert c.primary_failure == "gross_edge_absent"
    assert not any((c.reopen_allowed, c.rescue_allowed, c.optimization_allowed,
                    c.robustness_allowed, c.candidate_eligible, c.deployment_eligible,
                    c.forward_validation_eligible))
    assert set(c.disallowed_future_uses) == REG.PROMOTION_SELECTORS


@pytest.mark.parametrize("selector", sorted(REG.PROMOTION_SELECTORS))
def test_every_promotion_selector_fails_closed(selector):
    d = a_registry().select(SID, selector)
    assert d.admitted is False
    assert d.reason == f"terminal_strategy_{REG.CLOSED_NO_GROSS_EDGE}"


@pytest.mark.parametrize("selector", sorted(REG.DIAGNOSTIC_SELECTORS))
def test_diagnostic_selectors_admit_a_closed_strategy(selector):
    d = a_registry().select(SID, selector)
    assert d.admitted is True
    assert d.reason == "diagnostic_reuse_of_closed_strategy"


def test_an_unknown_selector_fails_closed_by_default():
    d = a_registry().select(SID, "some_new_queue_added_next_quarter")
    assert d.admitted is False


def test_the_registry_makes_no_claim_about_strategies_it_has_not_closed():
    d = a_registry().select("some-other-strategy", "candidate_pool")
    assert d.admitted is True
    assert d.reason == "not_closed"


def test_reopen_always_raises():
    reg = a_registry()
    with pytest.raises(PermissionError) as exc:
        reg.reopen(SID)
    assert REG.CLOSED_NO_GROSS_EDGE in str(exc.value)


def test_reopen_raises_even_for_an_unregistered_strategy():
    with pytest.raises(PermissionError):
        a_registry().reopen("never-heard-of-it")


def test_closure_is_queryable():
    reg = a_registry()
    assert reg.is_closed(SID) is True
    assert reg.is_closed("other") is False
    assert reg.get(SID).closure_release == "research-pipeline-v1.0.29"
    assert reg.closed_strategy_ids() == (SID,)


def test_a_closure_points_at_evidence_not_at_a_decision():
    bound = REG.with_evidence_hash(
        REG.closed_no_gross_edge(SID, closure_release="r1"), "sha256:abc")
    assert bound.closure_evidence_hash == "sha256:abc"
    assert bound.strategy_id == SID


def test_edge_negative_after_costs_is_its_own_terminal_state():
    c = REG.closed_no_gross_edge(
        "source-a-pair-convergence-v1",
        closure_release="research-pipeline-v1.0.17",
        primary_failure="edge_negative_after_costs",
        terminal_state=REG.CLOSED_EDGE_NEGATIVE_AFTER_COSTS,
    )
    reg = REG.registry_from([c])
    d = reg.select(c.strategy_id, "optimization_queue")
    assert d.admitted is False
    assert d.reason == f"terminal_strategy_{REG.CLOSED_EDGE_NEGATIVE_AFTER_COSTS}"


def test_promotion_and_diagnostic_selectors_do_not_overlap():
    assert not (REG.PROMOTION_SELECTORS & REG.DIAGNOSTIC_SELECTORS)


def test_two_closed_strategies_are_both_enforced():
    a = REG.closed_no_gross_edge("source-a-pair-convergence-v1", closure_release="r1")
    b = closed()
    reg = REG.registry_from([a, b])
    assert reg.closed_strategy_ids() == ("source-a-pair-convergence-v1", SID)
    assert reg.select(a.strategy_id, "historical_backtest_queue").admitted is False
    assert reg.select(b.strategy_id, "historical_backtest_queue").admitted is False
