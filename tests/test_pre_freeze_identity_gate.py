"""Pre-freeze market-identity gate: a field is closed only when the source closes it."""

from __future__ import annotations

import pytest

from research_process.pre_freeze import identity_gate as IG


def _field(name: str, value: str, **kw) -> IG.IdentityField:
    kw.setdefault("evidence_locator", f"{name}:p1")
    kw.setdefault("evidence_quote", f"the source states {value}")
    return IG.IdentityField(name=name, value=value, **kw)


VALUES = {
    IG.VENUE: "examplex",
    IG.MARKET_TYPE: "perpetual",
    IG.INSTRUMENT_CLASS: "perpetual",
    IG.BASE_ASSET: "BTC",
    IG.QUOTE_ASSET: "USDT",
    IG.VENUE_STRUCTURE: "single_venue",
    IG.INSTRUMENT_OR_UNIVERSE: "BTCUSDT",
    IG.TIMEFRAME: "1h",
    IG.BAR_TIMESTAMP_CONVENTION: "bar_open_time",
    IG.TIMEZONE: "UTC",
    IG.SIGNAL_OBSERVATION_TIMESTAMP: "bar_close",
    IG.EARLIEST_CAUSAL_DECISION_TIMESTAMP: "bar_close + 1s",
    IG.REFERENCE_ENTRY: "next bar open",
    IG.REFERENCE_EXIT: "next bar close",
    IG.PAYOFF_DEFINITION: "log return of the held leg",
    IG.CRITICAL_SOURCE_PARAMETERS: "lookback=20, threshold=2.0",
}


def complete_identity(source_id: str = "src-1", *, omit=(), override=()) -> IG.SourceIdentity:
    fields = [_field(n, v) for n, v in VALUES.items() if n not in omit]
    fields = [f for f in fields if f.name not in {o.name for o in override}]
    return IG.SourceIdentity(source_id=source_id, fields=tuple(fields) + tuple(override))


def test_complete_identity_passes_and_allows_freeze():
    r = IG.evaluate(complete_identity())
    assert r["state"] == IG.PASS
    assert r["passed"] is True
    assert r["freeze_allowed"] is True
    assert r["missing_fields"] == []
    assert r["closed_field_count"] == len(IG.REQUIRED_FIELDS)


def test_missing_non_timing_field_blocks_as_incomplete():
    r = IG.evaluate(complete_identity(omit=(IG.BASE_ASSET,)))
    assert r["state"] == IG.BLOCKED_INCOMPLETE
    assert r["freeze_allowed"] is False
    assert IG.BASE_ASSET in r["missing_non_timing_fields"]


def test_missing_only_timing_field_blocks_as_timing():
    r = IG.evaluate(complete_identity(omit=(IG.BAR_TIMESTAMP_CONVENTION,)))
    assert r["state"] == IG.BLOCKED_TIMING
    assert r["missing_timing_fields"] == [IG.BAR_TIMESTAMP_CONVENTION]
    assert r["missing_non_timing_fields"] == []


@pytest.mark.parametrize("ground", IG.PROHIBITED_INFERENCE_GROUNDS)
def test_prohibited_inference_never_closes_a_field(ground):
    bad = _field(IG.TIMEZONE, "UTC", inference_ground=ground)
    r = IG.evaluate(complete_identity(omit=(IG.TIMEZONE,), override=(bad,)))
    assert r["passed"] is False
    assert IG.TIMEZONE in r["missing_fields"]
    assert any(ground in p for p in r["prohibited_inferences"])


def test_value_without_evidence_locator_is_not_closed():
    unevidenced = IG.IdentityField(name=IG.VENUE, value="examplex", evidence_locator="")
    r = IG.evaluate(complete_identity(omit=(IG.VENUE,), override=(unevidenced,)))
    assert r["passed"] is False
    assert IG.VENUE in r["missing_fields"]


def test_not_closed_by_source_is_not_closed():
    asserted = _field(IG.VENUE, "examplex", closed_by_source=False)
    r = IG.evaluate(complete_identity(omit=(IG.VENUE,), override=(asserted,)))
    assert IG.VENUE in r["missing_fields"]


def test_market_type_contradicting_instrument_class_blocks():
    spot = _field(IG.MARKET_TYPE, "spot")
    r = IG.evaluate(complete_identity(omit=(IG.MARKET_TYPE,), override=(spot,)))
    assert r["state"] == IG.BLOCKED_CONTRADICTORY
    assert r["contradictions"]


def test_unknown_instrument_class_is_a_contradiction():
    weird = _field(IG.INSTRUMENT_CLASS, "warrant")
    r = IG.evaluate(complete_identity(omit=(IG.INSTRUMENT_CLASS,), override=(weird,)))
    assert r["state"] == IG.BLOCKED_CONTRADICTORY


def test_multi_venue_construction_may_not_collapse_to_one_venue():
    """The concrete failure the gate exists for: a multi-venue strategy mapped onto one venue."""
    multi = _field(IG.VENUE_STRUCTURE, "multi_venue")
    r = IG.evaluate(complete_identity(omit=(IG.VENUE_STRUCTURE,), override=(multi,)))
    assert r["state"] == IG.BLOCKED_CONTRADICTORY
    assert any("single venue" in c for c in r["contradictions"])


def test_multi_venue_with_a_real_venue_set_is_accepted():
    multi = _field(IG.VENUE_STRUCTURE, "multi_venue")
    venues = _field(IG.VENUE, "examplex,exampley")
    ident = complete_identity(omit=(IG.VENUE_STRUCTURE, IG.VENUE), override=(multi, venues))
    assert IG.evaluate(ident)["state"] == IG.PASS


def test_unknown_field_name_is_rejected():
    with pytest.raises(IG.IdentityGateError):
        IG.IdentityField(name="favourite_colour", value="blue", evidence_locator="p1")


def test_duplicate_field_is_rejected():
    dup = IG.SourceIdentity(
        source_id="src-1",
        fields=(_field(IG.VENUE, "examplex"), _field(IG.VENUE, "exampley")),
    )
    with pytest.raises(IG.IdentityGateError):
        dup.by_name()


def test_empty_identity_reports_every_required_field_missing():
    r = IG.evaluate(IG.SourceIdentity(source_id="src-empty"))
    assert r["closed_field_count"] == 0
    assert sorted(r["missing_fields"]) == sorted(IG.REQUIRED_FIELDS)
