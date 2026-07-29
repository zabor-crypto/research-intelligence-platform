"""Pre-freeze market-identity gate.

``pre-freeze-market-identity-gate-v1``.

An earlier iteration of this pipeline scored candidates on broad categories — "BTC data
availability", "venue data availability", "funding data availability" — and froze three candidates
on that basis. Every one of them then failed, and all three failed for the same reason: the *exact*
market identity did not match. A spot multi-venue strategy had been mapped onto perpetuals; one
source explicitly reported no effect on the target venue; a third's venue was never resolved at all.

This gate closes exact identity **before** a source may be frozen as a candidate. Nothing here is
inferred: not from market convention, not from a similarly-named product on the same venue, not from
what happens to sit in the local inventory, not from a publication's performance table, and not from
operator preference. A field is closed only when the source itself closes it, with evidence.
"""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field as dc_field

SCHEMA_VERSION = "pre-freeze-market-identity-gate/1.0"
GATE_ID = "pre-freeze-market-identity-gate-v1"

PASS = "pre_freeze_identity_pass"
BLOCKED_INCOMPLETE = "pre_freeze_identity_blocked_incomplete"
BLOCKED_CONTRADICTORY = "pre_freeze_identity_blocked_contradictory"
BLOCKED_TIMING = "pre_freeze_identity_blocked_timing"
STATES = (PASS, BLOCKED_INCOMPLETE, BLOCKED_CONTRADICTORY, BLOCKED_TIMING)

VENUE = "venue"
MARKET_TYPE = "market_type"
INSTRUMENT_CLASS = "instrument_class"
BASE_ASSET = "base_asset"
QUOTE_ASSET = "quote_asset"
VENUE_STRUCTURE = "venue_structure"
INSTRUMENT_OR_UNIVERSE = "instrument_or_universe"
TIMEFRAME = "timeframe"
BAR_TIMESTAMP_CONVENTION = "bar_timestamp_convention"
TIMEZONE = "timezone"
SIGNAL_OBSERVATION_TIMESTAMP = "signal_observation_timestamp"
EARLIEST_CAUSAL_DECISION_TIMESTAMP = "earliest_causal_decision_timestamp"
REFERENCE_ENTRY = "reference_entry_timestamp_and_price"
REFERENCE_EXIT = "reference_exit_timestamp_and_price"
PAYOFF_DEFINITION = "economic_payoff_definition"
CRITICAL_SOURCE_PARAMETERS = "critical_source_parameters"

REQUIRED_FIELDS = (
    VENUE, MARKET_TYPE, INSTRUMENT_CLASS, BASE_ASSET, QUOTE_ASSET, VENUE_STRUCTURE,
    INSTRUMENT_OR_UNIVERSE, TIMEFRAME, BAR_TIMESTAMP_CONVENTION, TIMEZONE,
    SIGNAL_OBSERVATION_TIMESTAMP, EARLIEST_CAUSAL_DECISION_TIMESTAMP,
    REFERENCE_ENTRY, REFERENCE_EXIT, PAYOFF_DEFINITION, CRITICAL_SOURCE_PARAMETERS,
)

# Fields whose absence is specifically a *timing* failure rather than generic incompleteness.
TIMING_FIELDS = frozenset({
    TIMEFRAME, BAR_TIMESTAMP_CONVENTION, TIMEZONE, SIGNAL_OBSERVATION_TIMESTAMP,
    EARLIEST_CAUSAL_DECISION_TIMESTAMP, REFERENCE_ENTRY, REFERENCE_EXIT,
})

VALID_INSTRUMENT_CLASSES = ("spot", "perpetual", "futures", "option", "index")
VALID_VENUE_STRUCTURES = ("single_venue", "multi_venue", "composite")

# Grounds that may NOT close a field. Recording them explicitly means a would-be inference is
# rejected loudly instead of quietly becoming an assumption.
PROHIBITED_INFERENCE_GROUNDS = (
    "common_market_convention",
    "available_local_data",
    "similarly_named_venue_product",
    "publication_performance_table",
    "operator_preference",
)


class IdentityGateError(ValueError):
    """Malformed identity input."""


@dataclass(frozen=True)
class IdentityField:
    """One identity field as closed (or not) by the source itself."""

    name: str
    value: str | None
    evidence_locator: str = ""
    evidence_quote: str = ""
    closed_by_source: bool = True
    inference_ground: str | None = None

    def __post_init__(self) -> None:
        if self.name not in REQUIRED_FIELDS:
            raise IdentityGateError(f"unknown identity field {self.name!r}")

    @property
    def is_closed(self) -> bool:
        if self.inference_ground in PROHIBITED_INFERENCE_GROUNDS:
            return False
        if not self.closed_by_source:
            return False
        if self.value is None or not str(self.value).strip():
            return False
        return bool(str(self.evidence_locator).strip())


@dataclass(frozen=True)
class SourceIdentity:
    source_id: str
    fields: tuple = dc_field(default=())

    def by_name(self) -> dict:
        out: dict[str, IdentityField] = {}
        for f in self.fields:
            if f.name in out:
                raise IdentityGateError(f"{self.source_id}: duplicate identity field {f.name!r}")
            out[f.name] = f
        return out


def _consistency_defects(fields: dict) -> list:
    """Internal contradictions between identity fields that are individually well-formed."""
    defects = []

    market = fields.get(MARKET_TYPE)
    inst = fields.get(INSTRUMENT_CLASS)
    if market and inst and market.is_closed and inst.is_closed:
        m = str(market.value).strip().casefold()
        i = str(inst.value).strip().casefold()
        if i not in VALID_INSTRUMENT_CLASSES:
            defects.append(
                f"{INSTRUMENT_CLASS}: {i!r} is not one of {list(VALID_INSTRUMENT_CLASSES)}")
        elif m != i and i not in m and m not in i:
            defects.append(
                f"{MARKET_TYPE}={market.value!r} contradicts {INSTRUMENT_CLASS}={inst.value!r}")

    structure = fields.get(VENUE_STRUCTURE)
    venue = fields.get(VENUE)
    if structure and structure.is_closed:
        s = str(structure.value).strip().casefold()
        if s not in VALID_VENUE_STRUCTURES:
            defects.append(
                f"{VENUE_STRUCTURE}: {s!r} is not one of {list(VALID_VENUE_STRUCTURES)}")
        elif s in ("multi_venue", "composite") and venue and venue.is_closed:
            # a multi-venue construction collapsed onto one venue name is exactly the failure
            # described in the module docstring; it must be represented as the full venue set,
            # never silently reduced
            named = [v for v in str(venue.value).replace("+", ",").split(",") if v.strip()]
            if len(named) < 2:
                defects.append(
                    f"{VENUE_STRUCTURE}={s!r} but {VENUE}={venue.value!r} names a single venue; a "
                    "multi-venue construction may not be silently mapped to one venue")
    return defects


def evaluate(identity: SourceIdentity) -> dict:
    """Close-or-block the exact market/timing identity of one source."""
    fields = identity.by_name()

    missing, prohibited = [], []
    for name in REQUIRED_FIELDS:
        f = fields.get(name)
        if f is None:
            missing.append(name)
            continue
        if f.inference_ground in PROHIBITED_INFERENCE_GROUNDS:
            prohibited.append(f"{name}: closed by prohibited inference {f.inference_ground!r}")
            missing.append(name)
        elif not f.is_closed:
            missing.append(name)

    contradictions = _consistency_defects(fields)
    missing_timing = sorted(n for n in missing if n in TIMING_FIELDS)
    missing_other = sorted(n for n in missing if n not in TIMING_FIELDS)

    if contradictions:
        state = BLOCKED_CONTRADICTORY
    elif missing_other:
        state = BLOCKED_INCOMPLETE
    elif missing_timing:
        state = BLOCKED_TIMING
    else:
        state = PASS

    return {
        "schema_version": SCHEMA_VERSION,
        "gate_id": GATE_ID,
        "source_id": identity.source_id,
        "state": state,
        "passed": state == PASS,
        "freeze_allowed": state == PASS,
        "closed_fields": sorted(n for n in REQUIRED_FIELDS if n not in missing),
        "missing_fields": sorted(missing),
        "missing_timing_fields": missing_timing,
        "missing_non_timing_fields": missing_other,
        "contradictions": sorted(contradictions),
        "prohibited_inferences": sorted(prohibited),
        "required_field_count": len(REQUIRED_FIELDS),
        "closed_field_count": len(REQUIRED_FIELDS) - len(missing),
    }
