"""Exact dataset-intersection gate.

``pre-freeze-dataset-intersection-gate-v1``.

The companion to :mod:`identity_gate`. Closing a source's exact market identity is worthless if the
next step is still "and we have some data for that venue". This gate demands that every required
source field maps onto a *named, hash- or inventory-identified* dataset whose venue, market type,
symbol, timeframe, timestamp semantics, columns and causal coverage all match the identity that was
just closed.

Broad category availability never satisfies the gate. "BTC data exists", "venue data exists" and
"funding data exists" — the three statements that let an earlier iteration freeze three unscreenable
candidates — are explicitly rejected as evidence.

A mapping that would require fetching a new corpus is blocked rather than satisfied: acquisition is
a separate, separately authorised act, and letting a gate trigger one turns "do we have this?" into
"go and get it".
"""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field as dc_field

SCHEMA_VERSION = "pre-freeze-dataset-intersection-gate/1.0"
GATE_ID = "pre-freeze-dataset-intersection-gate-v1"

EXACT_PASS = "exact_existing_dataset_pass"
NORMALIZED_PASS = "existing_dataset_pass_after_bounded_normalization"
BLOCKED_MARKET = "blocked_market_mismatch"
BLOCKED_INSTRUMENT = "blocked_instrument_mismatch"
BLOCKED_TIMEFRAME = "blocked_timeframe_or_timestamp_mismatch"
BLOCKED_FIELDS = "blocked_missing_required_fields"
BLOCKED_COVERAGE = "blocked_insufficient_recent_coverage"
BLOCKED_CAUSALITY = "blocked_causality"
BLOCKED_IDENTITY = "blocked_dataset_identity_unverifiable"

STATES = (EXACT_PASS, NORMALIZED_PASS, BLOCKED_MARKET, BLOCKED_INSTRUMENT, BLOCKED_TIMEFRAME,
          BLOCKED_FIELDS, BLOCKED_COVERAGE, BLOCKED_CAUSALITY, BLOCKED_IDENTITY)
PASSING_STATES = frozenset({EXACT_PASS, NORMALIZED_PASS})

REQUIRED_MAPPING_FIELDS = (
    "dataset_id", "manifest_id", "content_identity", "storage_location", "venue", "market_type",
    "symbol_or_universe", "timeframe", "coverage_start", "coverage_end", "required_warmup",
    "row_or_event_count", "required_columns", "timestamp_semantics", "timezone", "known_gaps",
    "lifecycle_coverage", "causal_availability", "source_field_mapping",
)

# Statements that describe a category rather than a dataset. Supplying one of these as the
# dataset identity is the failure named in the module docstring and is rejected outright.
BROAD_CATEGORY_CLAIMS = (
    "btc data exists", "venue data exists", "funding data exists", "eth data exists",
    "spot data exists", "perp data exists", "ohlcv data exists", "we have venue data",
    "data is available", "data exists",
)

# Normalisations small enough to apply to an already-validated local dataset without acquiring
# anything new. Anything outside this set is a blocked mismatch, not a normalisation.
BOUNDED_NORMALIZATIONS = (
    "bar_resample_finer_to_coarser",   # 1m -> 1h by aggregation of existing bars
    "timezone_normalisation_to_utc",
    "column_rename_to_canonical",
    "symbol_alias_resolution",
    "timestamp_convention_restatement",  # open-time <-> close-time, arithmetic on existing bars
)

MIN_RECENT_COVERAGE_DAYS = 90


class DatasetGateError(ValueError):
    """Malformed dataset-mapping input."""


@dataclass(frozen=True)
class DatasetMapping:
    """An exact mapping from one source requirement onto one existing validated dataset."""

    dataset_id: str = ""
    manifest_id: str = ""
    content_identity: str = ""
    storage_location: str = ""
    venue: str = ""
    market_type: str = ""
    symbol_or_universe: str = ""
    timeframe: str = ""
    coverage_start: str = ""
    coverage_end: str = ""
    required_warmup: str = ""
    row_or_event_count: int | None = None
    required_columns: tuple = dc_field(default=())
    available_columns: tuple = dc_field(default=())
    timestamp_semantics: str = ""
    timezone: str = ""
    known_gaps: tuple = dc_field(default=())
    lifecycle_coverage: str = ""
    causal_availability: str = ""
    source_field_mapping: dict = dc_field(default_factory=dict)
    normalizations_applied: tuple = dc_field(default=())
    recent_causal_coverage_days: float | None = None
    requires_new_acquisition: bool = False

    def missing_mapping_fields(self) -> list:
        missing = []
        for name in REQUIRED_MAPPING_FIELDS:
            if name == "required_columns":
                if not self.required_columns:
                    missing.append(name)
                continue
            if name == "row_or_event_count":
                if self.row_or_event_count is None:
                    missing.append(name)
                continue
            if name == "known_gaps":
                continue  # an empty gap list is a legitimate, meaningful value
            if name == "causal_availability":
                # owned by the dedicated causality check, which reports the far more actionable
                # blocked_causality instead of a generic "mapping incomplete"
                continue
            if name == "source_field_mapping":
                if not self.source_field_mapping:
                    missing.append(name)
                continue
            if not str(getattr(self, name, "")).strip():
                missing.append(name)
        return missing


def _is_broad_category_claim(text: str) -> bool:
    t = " ".join(str(text).strip().casefold().split())
    return any(claim in t for claim in BROAD_CATEGORY_CLAIMS)


def evaluate(mapping: DatasetMapping, required, *,
             min_recent_days: float = MIN_RECENT_COVERAGE_DAYS) -> dict:
    """Check one dataset mapping against the exact identity the source requires.

    ``required`` is the closed identity: venue, market_type, symbol_or_universe, timeframe,
    timestamp_semantics and (optionally) timezone, as established by the market-identity gate.
    Evaluation is ordered so the *first* substantive mismatch is reported, which keeps the blocked
    state meaningful rather than reporting whichever check happened to run last.
    """
    reasons: list[str] = []

    # 1. dataset identity must be verifiable and must not be a category statement
    missing = mapping.missing_mapping_fields()
    if missing:
        return _result(mapping, BLOCKED_IDENTITY, required,
                       [f"incomplete dataset mapping: missing {missing}"], missing_fields=missing)
    for label, value in (("dataset_id", mapping.dataset_id),
                         ("content_identity", mapping.content_identity),
                         ("storage_location", mapping.storage_location)):
        if _is_broad_category_claim(value):
            return _result(mapping, BLOCKED_IDENTITY, required,
                           [f"{label}={value!r} is a broad category claim, not a dataset identity"])

    if mapping.requires_new_acquisition:
        return _result(mapping, BLOCKED_IDENTITY, required,
                       ["mapping requires new market-data acquisition, which this gate does not "
                        "authorise"])

    # 2. unapproved normalisations are mismatches, not conveniences
    bad_norms = [n for n in mapping.normalizations_applied if n not in BOUNDED_NORMALIZATIONS]
    if bad_norms:
        return _result(mapping, BLOCKED_IDENTITY, required,
                       [f"normalisation(s) outside the bounded set: {sorted(bad_norms)}"])

    # 3. venue, then market type, then instrument
    if _differs(mapping.venue, required.get("venue")):
        reasons.append(f"venue {mapping.venue!r} != required {required.get('venue')!r}")
        return _result(mapping, BLOCKED_MARKET, required, reasons)
    if _differs(mapping.market_type, required.get("market_type")):
        reasons.append(
            f"market_type {mapping.market_type!r} != required {required.get('market_type')!r}")
        return _result(mapping, BLOCKED_MARKET, required, reasons)
    if _differs(mapping.symbol_or_universe, required.get("symbol_or_universe")):
        reasons.append(f"symbol/universe {mapping.symbol_or_universe!r} != required "
                       f"{required.get('symbol_or_universe')!r}")
        return _result(mapping, BLOCKED_INSTRUMENT, required, reasons)

    # 4. timeframe and timestamp semantics
    if _differs(mapping.timeframe, required.get("timeframe")):
        if "bar_resample_finer_to_coarser" not in mapping.normalizations_applied:
            reasons.append(
                f"timeframe {mapping.timeframe!r} != required {required.get('timeframe')!r}")
            return _result(mapping, BLOCKED_TIMEFRAME, required, reasons)
    req_ts = required.get("timestamp_semantics")
    if req_ts and _differs(mapping.timestamp_semantics, req_ts):
        if "timestamp_convention_restatement" not in mapping.normalizations_applied:
            reasons.append(f"timestamp semantics {mapping.timestamp_semantics!r} != required "
                           f"{req_ts!r}")
            return _result(mapping, BLOCKED_TIMEFRAME, required, reasons)
    req_tz = required.get("timezone")
    if req_tz and _differs(mapping.timezone, req_tz):
        if "timezone_normalisation_to_utc" not in mapping.normalizations_applied:
            reasons.append(f"timezone {mapping.timezone!r} != required {req_tz!r}")
            return _result(mapping, BLOCKED_TIMEFRAME, required, reasons)

    # 5. required columns must actually be present
    absent = sorted(set(mapping.required_columns) - set(mapping.available_columns))
    if absent:
        reasons.append(f"required column(s) absent from the dataset: {absent}")
        return _result(mapping, BLOCKED_FIELDS, required, reasons)

    # 6. causal availability
    causal = str(mapping.causal_availability).strip().casefold()
    if causal in ("", "unknown", "unverified"):
        reasons.append("causal availability unverified")
        return _result(mapping, BLOCKED_CAUSALITY, required, reasons)
    if causal in ("lookahead", "non_causal", "revised_after_the_fact"):
        reasons.append(f"causal availability is {causal!r}: the field is not observable at "
                       "decision time")
        return _result(mapping, BLOCKED_CAUSALITY, required, reasons)

    # 7. recent coverage
    days = mapping.recent_causal_coverage_days
    if days is None:
        reasons.append("recent causal coverage not measured")
        return _result(mapping, BLOCKED_COVERAGE, required, reasons)
    if days < min_recent_days:
        reasons.append(f"recent causal coverage {days} days < required {min_recent_days}")
        return _result(mapping, BLOCKED_COVERAGE, required, reasons)

    state = NORMALIZED_PASS if mapping.normalizations_applied else EXACT_PASS
    return _result(mapping, state, required, [])


def _differs(actual, required) -> bool:
    if required is None:
        return False
    return _canon(actual) != _canon(required)


def _canon(value) -> str:
    return " ".join(str(value or "").strip().casefold().replace("-", "_").split())


def _result(mapping: DatasetMapping, state: str, required: dict, reasons, *,
            missing_fields=()) -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "gate_id": GATE_ID,
        "state": state,
        "passed": state in PASSING_STATES,
        "freeze_allowed": state in PASSING_STATES,
        "dataset_id": mapping.dataset_id,
        "manifest_id": mapping.manifest_id,
        "content_identity": mapping.content_identity,
        "venue": mapping.venue,
        "market_type": mapping.market_type,
        "symbol_or_universe": mapping.symbol_or_universe,
        "timeframe": mapping.timeframe,
        "coverage_start": mapping.coverage_start,
        "coverage_end": mapping.coverage_end,
        "recent_causal_coverage_days": mapping.recent_causal_coverage_days,
        "normalizations_applied": sorted(mapping.normalizations_applied),
        "required_identity": dict(sorted(required.items())),
        "block_reasons": list(reasons),
        "missing_mapping_fields": sorted(missing_fields),
        "new_acquisition_required": mapping.requires_new_acquisition,
    }


def evaluate_all(mappings, required, *, min_recent_days: float = MIN_RECENT_COVERAGE_DAYS) -> dict:
    """A source is screenable only if *every* required dataset mapping passes."""
    results = [evaluate(m, required, min_recent_days=min_recent_days) for m in mappings]
    if not results:
        return {"schema_version": SCHEMA_VERSION, "gate_id": GATE_ID, "state": BLOCKED_IDENTITY,
                "passed": False, "freeze_allowed": False, "mappings": [],
                "block_reasons": ["no dataset mapping supplied"]}
    failed = [r for r in results if not r["passed"]]
    if failed:
        state = failed[0]["state"]
    elif any(r["state"] == NORMALIZED_PASS for r in results):
        state = NORMALIZED_PASS
    else:
        state = EXACT_PASS
    return {
        "schema_version": SCHEMA_VERSION,
        "gate_id": GATE_ID,
        "state": state,
        "passed": not failed,
        "freeze_allowed": not failed,
        "mapping_count": len(results),
        "failed_count": len(failed),
        "mappings": results,
        "block_reasons": [r for f in failed for r in f["block_reasons"]],
    }
