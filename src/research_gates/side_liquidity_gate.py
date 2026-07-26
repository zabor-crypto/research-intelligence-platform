"""GATE_EXECUTION_SIDE_LIQUIDITY — per-side executable-liquidity gate (Research Pipeline v0.3).

Pure and dependency-light (stdlib only). This gate evaluates executable liquidity for the
**actual intended order direction** of each leg of a (possibly market-neutral) book. A
long/short book must cross a *specific* side of the order book to enter and exit each leg,
so a total-depth (bid+ask) sum can mask one-sided thinness. This gate exists because the
`xs_momentum_leg` bounded replication passed a total-depth10 filter yet failed required-side
depth for ASTER/LIT/HYPE/AAVE/SUI (see `xs_momentum_closure/`, golden case
`golden_xs_momentum_side_depth`).

Hard invariants encoded here:
  * required_book_side is derived from the order action (buy -> ask, sell -> bid). Total
    depth is retained for diagnostics only and is NEVER substituted for required-side depth.
  * A missing required side blocks the leg (`blocked_missing_side_data`); it never falls
    back to total depth.
  * side_capacity = required_side_depth * max_participation_rate.
  * A market-neutral candidate passes only if EVERY required leg passes. A single binding
    leg failure blocks the candidate — positive PnL / significance / average liquidity can
    never override it (that override is enforced upstream by the state machine + guards).
"""

from __future__ import annotations

from dataclasses import dataclass, field

# --------------------------------------------------------------------------- #
# gate identity + status vocabulary
# --------------------------------------------------------------------------- #
GATE_ID = "GATE_EXECUTION_SIDE_LIQUIDITY"

# per-leg admission statuses
PASSED = "passed"
FAILED_SIDE_DEPTH = "failed_side_depth"
FAILED_SNAPSHOT_FRESHNESS = "failed_snapshot_freshness"
FAILED_COVERAGE = "failed_coverage"
BLOCKED_MISSING_SIDE_DATA = "blocked_missing_side_data"
BLOCKED_INVALID_SIDE_MAPPING = "blocked_invalid_side_mapping"
BLOCKED_INVALID_UNITS = "blocked_invalid_units"

LEG_STATUSES: frozenset[str] = frozenset(
    {
        PASSED,
        FAILED_SIDE_DEPTH,
        FAILED_SNAPSHOT_FRESHNESS,
        FAILED_COVERAGE,
        BLOCKED_MISSING_SIDE_DATA,
        BLOCKED_INVALID_SIDE_MAPPING,
        BLOCKED_INVALID_UNITS,
    }
)

# any status other than PASSED is a non-authorizing (blocking) leg outcome
_NON_PASS = LEG_STATUSES - {PASSED}

# severity order for aggregating a candidate verdict from many legs (worst wins).
# structural blockers are the most severe (we could not even evaluate the leg),
# then execution failures, then freshness/coverage.
_SEVERITY: dict[str, int] = {
    BLOCKED_INVALID_SIDE_MAPPING: 6,
    BLOCKED_INVALID_UNITS: 5,
    BLOCKED_MISSING_SIDE_DATA: 4,
    FAILED_SIDE_DEPTH: 3,
    FAILED_SNAPSHOT_FRESHNESS: 2,
    FAILED_COVERAGE: 1,
    PASSED: 0,
}

_BUY_SIDE = "ask"
_SELL_SIDE = "bid"

# canonical directional mapping (position_side, execution_stage) -> required book side.
# long entry lifts the ask; long exit hits the bid; short entry hits the bid; short exit
# lifts the ask. This matches the required mapping in the audit spec.
_DIRECTION_SIDE: dict[tuple[str, str], str] = {
    ("long", "entry"): "ask",
    ("long", "exit"): "bid",
    ("short", "entry"): "bid",
    ("short", "exit"): "ask",
}
# and the order action implied by that (position_side, execution_stage)
_DIRECTION_ACTION: dict[tuple[str, str], str] = {
    ("long", "entry"): "buy",
    ("long", "exit"): "sell",
    ("short", "entry"): "sell",
    ("short", "exit"): "buy",
}


def required_book_side(order_action: str) -> str:
    """Map an order action to the book side that must be crossed to fill it.

    buy -> "ask" (you lift the ask), sell -> "bid" (you hit the bid). Raises ValueError on
    an unknown action so an invalid mapping can never silently default to total depth.
    """
    a = str(order_action).strip().lower()
    if a == "buy":
        return _BUY_SIDE
    if a == "sell":
        return _SELL_SIDE
    raise ValueError(f"unknown order_action: {order_action!r} (expected buy|sell)")


def required_book_side_for(position_side: str, execution_stage: str) -> str:
    """Required book side for a (position_side, execution_stage) leg.

    long/entry->ask, long/exit->bid, short/entry->bid, short/exit->ask.
    """
    key = (str(position_side).strip().lower(), str(execution_stage).strip().lower())
    if key not in _DIRECTION_SIDE:
        raise ValueError(
            f"unknown (position_side, execution_stage): {key!r} "
            "(expected long|short x entry|exit)"
        )
    return _DIRECTION_SIDE[key]


@dataclass(frozen=True)
class SideLiquidityContract:
    """Frozen thresholds the gate evaluates against (the side-aware capacity contract)."""

    depth_band_bps: float = 10.0
    max_participation_rate: float = 0.5
    max_snapshot_age_ms: float = 3_600_000.0  # 1h; stale snapshots do not pass
    min_observation_coverage: float = 1.0
    # scalable sizing: if True a leg is admitted at min(target, side_capacity) instead of
    # failing when capacity < target. Only legal when the immutable A-spec authorizes it.
    allow_scalable_sizing: bool = False

    def __post_init__(self) -> None:
        if not (0.0 < self.max_participation_rate <= 1.0):
            raise ValueError("max_participation_rate must be in (0, 1]")
        if self.depth_band_bps <= 0:
            raise ValueError("depth_band_bps must be > 0")
        if self.max_snapshot_age_ms < 0:
            raise ValueError("max_snapshot_age_ms must be >= 0")
        if not (0.0 <= self.min_observation_coverage <= 1.0):
            raise ValueError("min_observation_coverage must be in [0, 1]")


@dataclass(frozen=True)
class LegResult:
    symbol: str
    position_side: str
    execution_stage: str
    order_action: str
    required_book_side: str | None
    target_notional_usd: float
    bid_depth_usd: float | None
    ask_depth_usd: float | None
    total_depth_usd: float | None
    required_side_depth_usd: float | None
    side_capacity_usd: float | None
    capacity_ratio: float | None
    admitted_notional_usd: float | None
    snapshot_age_ms: float | None
    admission_status: str
    failure_reason: str | None

    @property
    def passed(self) -> bool:
        return self.admission_status == PASSED


def _num(x) -> float | None:
    if x is None:
        return None
    try:
        return float(x)
    except (TypeError, ValueError):
        return "invalid"  # sentinel handled by caller


def evaluate_leg(leg: dict, contract: SideLiquidityContract | None = None) -> LegResult:
    """Evaluate one execution leg against the side-aware capacity contract.

    `leg` fields (required unless noted):
        symbol, position_side, execution_stage, order_action,
        bid_depth_usd, ask_depth_usd, target_notional_usd
      optional:
        required_book_side (validated for consistency if supplied),
        snapshot_age_ms, coverage, total_depth_usd,
        max_participation_rate (overrides contract for this leg)

    Precedence (deterministic): invalid mapping -> invalid units -> missing side data ->
    stale snapshot -> insufficient coverage -> side-depth capacity -> passed.
    """
    contract = contract or SideLiquidityContract()
    symbol = str(leg.get("symbol", "?"))
    position_side = str(leg.get("position_side", "")).strip().lower()
    execution_stage = str(leg.get("execution_stage", "")).strip().lower()
    order_action = str(leg.get("order_action", "")).strip().lower()
    participation = leg.get("max_participation_rate", contract.max_participation_rate)

    bid = _num(leg.get("bid_depth_usd"))
    ask = _num(leg.get("ask_depth_usd"))
    target = _num(leg.get("target_notional_usd"))
    total = leg.get("total_depth_usd")
    total = _num(total) if total is not None else None
    # if total not supplied but both sides are real numbers, derive it (diagnostic only)
    if total is None and isinstance(bid, float) and isinstance(ask, float):
        total = bid + ask

    def _mk(status: str, reason: str | None, *, req_side=None, req_depth=None,
            cap=None, ratio=None, admitted=None, age=None) -> LegResult:
        return LegResult(
            symbol=symbol, position_side=position_side, execution_stage=execution_stage,
            order_action=order_action, required_book_side=req_side,
            target_notional_usd=target if isinstance(target, float) else float("nan"),
            bid_depth_usd=bid if isinstance(bid, float) else None,
            ask_depth_usd=ask if isinstance(ask, float) else None,
            total_depth_usd=total if isinstance(total, float) else None,
            required_side_depth_usd=req_depth, side_capacity_usd=cap,
            capacity_ratio=ratio, admitted_notional_usd=admitted,
            snapshot_age_ms=age, admission_status=status, failure_reason=reason,
        )

    # 1) directional mapping must resolve and be self-consistent.
    try:
        req_side = required_book_side(order_action)
    except ValueError:
        # fall back to (position_side, execution_stage) if the action is absent/unknown
        try:
            req_side = required_book_side_for(position_side, execution_stage)
            order_action = _DIRECTION_ACTION[(position_side, execution_stage)]
        except ValueError:
            return _mk(
                BLOCKED_INVALID_SIDE_MAPPING,
                f"cannot resolve required book side from order_action={order_action!r} / "
                f"({position_side!r},{execution_stage!r})",
            )
    # if the leg also declared a position/stage, it must agree with the action mapping.
    if (position_side, execution_stage) in _DIRECTION_SIDE:
        expected = _DIRECTION_SIDE[(position_side, execution_stage)]
        if expected != req_side:
            return _mk(
                BLOCKED_INVALID_SIDE_MAPPING,
                f"order_action={order_action!r} maps to {req_side!r} but "
                f"({position_side},{execution_stage}) requires {expected!r}",
                req_side=req_side,
            )
    # an explicitly supplied required_book_side must match the derived one.
    declared = leg.get("required_book_side")
    if declared is not None and str(declared).strip().lower() != req_side:
        return _mk(
            BLOCKED_INVALID_SIDE_MAPPING,
            f"declared required_book_side={declared!r} != derived {req_side!r}",
            req_side=req_side,
        )

    # 2) units / numeric validity.
    if target == "invalid" or bid == "invalid" or ask == "invalid":
        return _mk(BLOCKED_INVALID_UNITS, "non-numeric depth or notional", req_side=req_side)
    if not isinstance(target, float) or target <= 0:
        return _mk(BLOCKED_INVALID_UNITS, f"target_notional_usd must be > 0 (got {target!r})",
                   req_side=req_side)
    if not (0.0 < float(participation) <= 1.0):
        return _mk(BLOCKED_INVALID_UNITS,
                   f"max_participation_rate must be in (0,1] (got {participation!r})",
                   req_side=req_side)
    for name, val in (("bid_depth_usd", bid), ("ask_depth_usd", ask)):
        if isinstance(val, float) and val < 0:
            return _mk(BLOCKED_INVALID_UNITS, f"{name} is negative ({val})", req_side=req_side)

    # 3) the REQUIRED side must be present. Never substitute total depth.
    req_depth = ask if req_side == _BUY_SIDE else bid
    if not isinstance(req_depth, float):
        return _mk(
            BLOCKED_MISSING_SIDE_DATA,
            f"required {req_side}-side depth missing for a {order_action} "
            "(will not fall back to total depth)",
            req_side=req_side,
        )

    age = leg.get("snapshot_age_ms")
    age = _num(age) if age is not None else None

    # 4) stale snapshot.
    if isinstance(age, float) and age > contract.max_snapshot_age_ms:
        return _mk(FAILED_SNAPSHOT_FRESHNESS,
                   f"snapshot_age_ms={age:.0f} > max {contract.max_snapshot_age_ms:.0f}",
                   req_side=req_side, req_depth=req_depth, age=age)

    # 5) coverage.
    coverage = leg.get("coverage")
    coverage = _num(coverage) if coverage is not None else None
    if isinstance(coverage, float) and coverage < contract.min_observation_coverage:
        return _mk(FAILED_COVERAGE,
                   f"coverage={coverage:.3f} < min {contract.min_observation_coverage:.3f}",
                   req_side=req_side, req_depth=req_depth, age=age)

    # 6) side-aware capacity.
    side_capacity = req_depth * float(participation)
    ratio = side_capacity / target if target else float("inf")
    if side_capacity >= target:
        return _mk(PASSED, None, req_side=req_side, req_depth=req_depth,
                   cap=side_capacity, ratio=ratio, admitted=target, age=age)
    if contract.allow_scalable_sizing:
        admitted = min(target, side_capacity)
        return _mk(PASSED, "scaled to side capacity (A-spec authorized)",
                   req_side=req_side, req_depth=req_depth, cap=side_capacity,
                   ratio=ratio, admitted=admitted, age=age)
    return _mk(FAILED_SIDE_DEPTH,
               f"side_capacity {side_capacity:,.0f} < target_notional {target:,.0f} "
               f"(required {req_side}-side depth {req_depth:,.0f} x participation "
               f"{float(participation):.2f})",
               req_side=req_side, req_depth=req_depth, cap=side_capacity,
               ratio=ratio, admitted=None, age=age)


@dataclass(frozen=True)
class CandidateAdmission:
    gate_id: str
    gate_status: str  # passed | worst leg status
    promotion_authorized: bool
    n_legs: int
    n_failed: int
    failed_symbols: list[str]
    failed_legs: list[str]
    failure_dimensions: list[str]
    candidate_side_capacity_usd: float | None  # conservative (min) across legs
    total_depth_used_for_admission: bool
    leg_results: list[LegResult] = field(default_factory=list)


def evaluate_market_neutral(
    legs: list[dict], contract: SideLiquidityContract | None = None
) -> CandidateAdmission:
    """Evaluate a full (market-neutral) book. Passes ONLY if every required leg passes.

    Conservative aggregation: the candidate side capacity is the MINIMUM leg side capacity
    (never an average — a liquid long leg cannot offset an illiquid short leg). A single
    binding leg failure blocks promotion.
    """
    contract = contract or SideLiquidityContract()
    results = [evaluate_leg(leg, contract) for leg in legs]

    failed = [r for r in results if not r.passed]
    failed_symbols = sorted({r.symbol for r in failed})
    failed_legs = [
        f"{r.symbol}:{r.position_side}_{r.execution_stage}"
        for r in failed
    ]
    failure_dimensions = sorted({r.admission_status for r in failed})

    caps = [r.side_capacity_usd for r in results if r.side_capacity_usd is not None]
    candidate_cap = min(caps) if caps else None

    if failed:
        # worst-severity status becomes the candidate verdict
        worst = max((r.admission_status for r in failed), key=lambda s: _SEVERITY[s])
        status = worst
        authorized = False
    else:
        status = PASSED
        authorized = True

    return CandidateAdmission(
        gate_id=GATE_ID,
        gate_status=status,
        promotion_authorized=authorized,
        n_legs=len(results),
        n_failed=len(failed),
        failed_symbols=failed_symbols,
        failed_legs=failed_legs,
        failure_dimensions=failure_dimensions,
        candidate_side_capacity_usd=candidate_cap,
        total_depth_used_for_admission=False,  # invariant: never
        leg_results=results,
    )
