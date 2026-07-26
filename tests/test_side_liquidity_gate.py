"""Unit + adversarial tests for GATE_EXECUTION_SIDE_LIQUIDITY (v0.3)."""

from __future__ import annotations

import pytest

from research_gates.side_liquidity_gate import (
    BLOCKED_INVALID_SIDE_MAPPING,
    BLOCKED_INVALID_UNITS,
    BLOCKED_MISSING_SIDE_DATA,
    FAILED_SIDE_DEPTH,
    FAILED_SNAPSHOT_FRESHNESS,
    PASSED,
    SideLiquidityContract,
    evaluate_leg,
    evaluate_market_neutral,
    required_book_side,
    required_book_side_for,
)

FULL = SideLiquidityContract(max_participation_rate=1.0)


# --------------------------------------------------------------------------- #
# directional side mapping
# --------------------------------------------------------------------------- #
def test_required_book_side_buy_is_ask():
    assert required_book_side("buy") == "ask"


def test_required_book_side_sell_is_bid():
    assert required_book_side("sell") == "bid"


def test_required_book_side_unknown_raises():
    with pytest.raises(ValueError):
        required_book_side("hold")


@pytest.mark.parametrize(
    "pos,stage,side",
    [("long", "entry", "ask"), ("long", "exit", "bid"),
     ("short", "entry", "bid"), ("short", "exit", "ask")],
)
def test_direction_side_mapping(pos, stage, side):
    assert required_book_side_for(pos, stage) == side


# --------------------------------------------------------------------------- #
# capacity: side depth, not total depth
# --------------------------------------------------------------------------- #
def test_high_total_depth_but_thin_required_bid_fails():
    # §17 adversarial: bid 20k, ask 180k, total 200k, but a SELL needs the bid.
    r = evaluate_leg(
        {"symbol": "X", "order_action": "sell", "position_side": "short",
         "execution_stage": "entry", "bid_depth_usd": 20_000, "ask_depth_usd": 180_000,
         "target_notional_usd": 50_000},
        FULL,
    )
    assert r.admission_status == FAILED_SIDE_DEPTH
    assert r.required_book_side == "bid"
    assert r.required_side_depth_usd == 20_000
    assert r.total_depth_usd == 200_000  # retained for diagnostics only


def test_same_book_passes_for_the_liquid_side():
    # same book, but a BUY needs the (deep) ask -> passes.
    r = evaluate_leg(
        {"symbol": "X", "order_action": "buy", "position_side": "long",
         "execution_stage": "entry", "bid_depth_usd": 20_000, "ask_depth_usd": 180_000,
         "target_notional_usd": 50_000},
        FULL,
    )
    assert r.admission_status == PASSED
    assert r.required_book_side == "ask"


def test_side_capacity_uses_participation_rate():
    r = evaluate_leg(
        {"symbol": "X", "order_action": "buy", "bid_depth_usd": 1_000,
         "ask_depth_usd": 100_000, "target_notional_usd": 60_000},
        SideLiquidityContract(max_participation_rate=0.5),
    )
    assert r.side_capacity_usd == 50_000  # 100k * 0.5
    assert r.admission_status == FAILED_SIDE_DEPTH  # 50k < 60k


# --------------------------------------------------------------------------- #
# blockers: missing side, invalid mapping, invalid units, stale
# --------------------------------------------------------------------------- #
def test_missing_ask_for_buy_blocks_never_uses_total():
    # §17 adversarial: buy action, ask depth missing.
    r = evaluate_leg(
        {"symbol": "X", "order_action": "buy", "bid_depth_usd": 100_000,
         "ask_depth_usd": None, "target_notional_usd": 50_000},
        FULL,
    )
    assert r.admission_status == BLOCKED_MISSING_SIDE_DATA
    assert r.required_side_depth_usd is None  # never fell back to the 100k bid / total


def test_inconsistent_mapping_blocks():
    # §17 adversarial: sell action declared with required_book_side=ask.
    r = evaluate_leg(
        {"symbol": "X", "order_action": "sell", "required_book_side": "ask",
         "bid_depth_usd": 100_000, "ask_depth_usd": 100_000, "target_notional_usd": 50_000},
        FULL,
    )
    assert r.admission_status == BLOCKED_INVALID_SIDE_MAPPING


def test_position_stage_action_disagreement_blocks():
    # long/entry should be a buy (ask); declaring sell contradicts it.
    r = evaluate_leg(
        {"symbol": "X", "position_side": "long", "execution_stage": "entry",
         "order_action": "sell", "bid_depth_usd": 100_000, "ask_depth_usd": 100_000,
         "target_notional_usd": 50_000},
        FULL,
    )
    assert r.admission_status == BLOCKED_INVALID_SIDE_MAPPING


def test_negative_depth_blocks_units():
    r = evaluate_leg(
        {"symbol": "X", "order_action": "buy", "bid_depth_usd": 100_000,
         "ask_depth_usd": -5, "target_notional_usd": 50_000},
        FULL,
    )
    assert r.admission_status == BLOCKED_INVALID_UNITS


def test_nonpositive_target_blocks_units():
    r = evaluate_leg(
        {"symbol": "X", "order_action": "buy", "bid_depth_usd": 1, "ask_depth_usd": 100_000,
         "target_notional_usd": 0},
        FULL,
    )
    assert r.admission_status == BLOCKED_INVALID_UNITS


def test_stale_snapshot_fails():
    r = evaluate_leg(
        {"symbol": "X", "order_action": "buy", "bid_depth_usd": 1, "ask_depth_usd": 1_000_000,
         "target_notional_usd": 50_000, "snapshot_age_ms": 10_000_000},
        SideLiquidityContract(max_participation_rate=1.0, max_snapshot_age_ms=3_600_000),
    )
    assert r.admission_status == FAILED_SNAPSHOT_FRESHNESS


# --------------------------------------------------------------------------- #
# scalable sizing (only when A-spec authorizes it)
# --------------------------------------------------------------------------- #
def test_scalable_sizing_admits_at_side_capacity():
    r = evaluate_leg(
        {"symbol": "X", "order_action": "buy", "bid_depth_usd": 1, "ask_depth_usd": 30_000,
         "target_notional_usd": 50_000},
        SideLiquidityContract(max_participation_rate=1.0, allow_scalable_sizing=True),
    )
    assert r.admission_status == PASSED
    assert r.admitted_notional_usd == 30_000


# --------------------------------------------------------------------------- #
# market-neutral book: one failed leg blocks the candidate
# --------------------------------------------------------------------------- #
def test_one_failed_short_leg_blocks_high_average_book():
    # §17 adversarial: two liquid longs + one illiquid short -> candidate blocked.
    passed_long = {"symbol": "BTC", "order_action": "buy", "position_side": "long",
                   "execution_stage": "entry", "bid_depth_usd": 5_000_000,
                   "ask_depth_usd": 5_000_000, "target_notional_usd": 50_000}
    failed_short = {"symbol": "ASTER", "order_action": "sell", "position_side": "short",
                    "execution_stage": "entry", "bid_depth_usd": 24_000,
                    "ask_depth_usd": 500_000, "target_notional_usd": 50_000}
    adm = evaluate_market_neutral([passed_long, dict(passed_long), failed_short], FULL)
    assert adm.promotion_authorized is False
    assert adm.gate_status == FAILED_SIDE_DEPTH
    assert adm.failed_symbols == ["ASTER"]
    # conservative aggregation: candidate capacity is the MIN leg, not the average.
    assert adm.candidate_side_capacity_usd == 24_000
    assert adm.total_depth_used_for_admission is False


def test_all_legs_pass_authorizes():
    legs = [
        {"symbol": "BTC", "order_action": "buy", "position_side": "long",
         "execution_stage": "entry", "bid_depth_usd": 5e6, "ask_depth_usd": 5e6,
         "target_notional_usd": 50_000},
        {"symbol": "ETH", "order_action": "sell", "position_side": "short",
         "execution_stage": "entry", "bid_depth_usd": 5e6, "ask_depth_usd": 5e6,
         "target_notional_usd": 50_000},
    ]
    adm = evaluate_market_neutral(legs, FULL)
    assert adm.promotion_authorized is True
    assert adm.gate_status == PASSED
    assert adm.failed_symbols == []


def test_blocker_outranks_depth_failure_in_candidate_verdict():
    missing = {"symbol": "A", "order_action": "buy", "bid_depth_usd": 100, "ask_depth_usd": None,
               "target_notional_usd": 50_000}
    thin = {"symbol": "B", "order_action": "sell", "bid_depth_usd": 100, "ask_depth_usd": 1e6,
            "target_notional_usd": 50_000}
    adm = evaluate_market_neutral([missing, thin], FULL)
    assert adm.gate_status == BLOCKED_MISSING_SIDE_DATA  # more severe than failed_side_depth
    assert set(adm.failed_symbols) == {"A", "B"}
