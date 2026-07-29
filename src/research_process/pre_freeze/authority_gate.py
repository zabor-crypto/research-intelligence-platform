"""Authoritative-content availability gate.

``authoritative-content-availability-gate-v1``.

An earlier iteration decided whether a source's content was authoritative with a substring test::

    authoritative_source_available = ("not_retrievable" not in avail and "paywalled" not in avail)

``summary_retrieved`` contains neither substring, so a *secondary summary* — a commercial vendor's
write-up of someone else's paper — satisfied the authoritative-content gate and went on to close
sixteen identity fields. The gate could not distinguish "we hold the paper" from "we read someone's
description of the paper", because it was matching English rather than classifying authority.

This gate replaces that test. Availability is a closed enumeration of nine states; six of them never
pass. Passing additionally requires that the retained content actually *bears the strategy* — an
authoritative PDF whose strategy-bearing sections were never captured is metadata, not mechanics —
and that the artifact is frozen: hashed, timestamped and stored, so a later release can re-read the
same bytes rather than a later revision of the same URL.

Navigation value is preserved without conferring authority. A secondary write-up may legitimately
point at a primary source; it may never *be* one. That is the whole of the defect, expressed as a
type rather than as a warning.
"""

from __future__ import annotations

from dataclasses import dataclass

SCHEMA_VERSION = "authoritative-content-availability-gate/1.0"
GATE_ID = "authoritative-content-availability-gate-v1"

# --- availability states -------------------------------------------------------------------

AUTHORITATIVE_FULL_TEXT = "authoritative_full_text_available"
AUTHORITATIVE_CODE = "authoritative_code_available"
AUTHORITATIVE_SUPPLEMENT = "authoritative_supplement_available"
AUTHORITATIVE_METADATA_ONLY = "authoritative_metadata_only"
SECONDARY_SUMMARY = "secondary_summary_available"
SECONDARY_NAVIGATION_ONLY = "secondary_navigation_only"
PAYWALLED_IDENTIFIED = "paywalled_authoritative_source_identified"
SOURCE_NOT_IDENTIFIED = "authoritative_source_not_identified"
SOURCE_UNAVAILABLE = "source_unavailable"

AVAILABILITY_STATES = (
    AUTHORITATIVE_FULL_TEXT, AUTHORITATIVE_CODE, AUTHORITATIVE_SUPPLEMENT,
    AUTHORITATIVE_METADATA_ONLY, SECONDARY_SUMMARY, SECONDARY_NAVIGATION_ONLY,
    PAYWALLED_IDENTIFIED, SOURCE_NOT_IDENTIFIED, SOURCE_UNAVAILABLE,
)

# Only these three can carry strategy mechanics. Everything else describes a source rather than
# supplying it.
AUTHORITATIVE_STATES = frozenset({
    AUTHORITATIVE_FULL_TEXT, AUTHORITATIVE_CODE, AUTHORITATIVE_SUPPLEMENT,
})

# States that must never pass. ``summary_retrieved`` is the literal legacy token and is retained
# here so historical values are rejected by name rather than by failing to parse.
LEGACY_SUMMARY_TOKEN = "summary_retrieved"
NON_PASSING_STATES = frozenset({
    LEGACY_SUMMARY_TOKEN, SECONDARY_SUMMARY, SECONDARY_NAVIGATION_ONLY,
    AUTHORITATIVE_METADATA_ONLY, SOURCE_NOT_IDENTIFIED, PAYWALLED_IDENTIFIED, SOURCE_UNAVAILABLE,
})

# --- source roles and authority classification ---------------------------------------------

ROLE_PRIMARY = "primary_research"
ROLE_AUTHOR_CODE = "author_implementation"
ROLE_SUPPLEMENT = "author_supplement"
ROLE_REVISION = "later_source_revision"
ROLE_SECONDARY = "secondary_representation"
ROLE_NAVIGATION = "navigation_lead"
SOURCE_ROLES = (
    ROLE_PRIMARY, ROLE_AUTHOR_CODE, ROLE_SUPPLEMENT, ROLE_REVISION, ROLE_SECONDARY,
    ROLE_NAVIGATION,
)

AUTHORITY_PRIMARY = "primary"
AUTHORITY_AUTHOR_DERIVED = "author_derived"
AUTHORITY_SECONDARY = "secondary"
AUTHORITY_CLASSES = (AUTHORITY_PRIMARY, AUTHORITY_AUTHOR_DERIVED, AUTHORITY_SECONDARY)

# A role may only claim authority up to its own standing. A vendor summary page classified as
# ``primary`` is the failure mode this mapping makes unrepresentable.
ROLE_MAX_AUTHORITY = {
    ROLE_PRIMARY: AUTHORITY_PRIMARY,
    ROLE_AUTHOR_CODE: AUTHORITY_AUTHOR_DERIVED,
    ROLE_SUPPLEMENT: AUTHORITY_AUTHOR_DERIVED,
    ROLE_REVISION: AUTHORITY_AUTHOR_DERIVED,
    ROLE_SECONDARY: AUTHORITY_SECONDARY,
    ROLE_NAVIGATION: AUTHORITY_SECONDARY,
}
_AUTHORITY_RANK = {AUTHORITY_SECONDARY: 0, AUTHORITY_AUTHOR_DERIVED: 1, AUTHORITY_PRIMARY: 2}

# Roles that may satisfy the gate for a strategy-bearing source. A secondary representation and a
# navigation lead never can, whatever content was retrieved from them.
AUTHORITATIVE_ROLES = frozenset({ROLE_PRIMARY, ROLE_AUTHOR_CODE, ROLE_SUPPLEMENT, ROLE_REVISION})

# --- gate outcome states -------------------------------------------------------------------

PASS = "authoritative_content_available"
BLOCKED_NOT_AUTHORITATIVE = "blocked_content_not_authoritative"
BLOCKED_NOT_STRATEGY_BEARING = "blocked_content_not_strategy_bearing"
BLOCKED_NOT_FROZEN = "blocked_source_artifact_not_frozen"
BLOCKED_ROLE_AUTHORITY_MISMATCH = "blocked_role_authority_mismatch"
STATES = (PASS, BLOCKED_NOT_AUTHORITATIVE, BLOCKED_NOT_STRATEGY_BEARING, BLOCKED_NOT_FROZEN,
          BLOCKED_ROLE_AUTHORITY_MISMATCH)

REQUIRED_ARTIFACT_FIELDS = (
    "source_id", "source_role", "canonical_identity", "authors", "title", "year",
    "stable_identifier", "content_type", "content_hash", "version", "retrieval_timestamp",
    "storage_location", "authority_classification", "strategy_bearing_content_present",
)

# ``stable_identifier`` (DOI/arXiv/repository) is required only where such an identifier exists for
# the content type. A vendor web page has no DOI; demanding one would push callers toward inventing
# identifiers, which is the opposite of what this gate is for.
STABLE_IDENTIFIER_OPTIONAL_ROLES = frozenset({ROLE_SECONDARY, ROLE_NAVIGATION})


class AuthorityGateError(ValueError):
    """Malformed source artifact. The gate never guesses past bad input."""


@dataclass(frozen=True)
class SourceArtifact:
    """One retrieved, frozen representation of a source.

    ``strategy_bearing_content_present`` is the caller's assertion that the retained bytes contain
    the mechanics the strategy needs — not merely that the document exists.
    """

    source_id: str
    source_role: str
    canonical_identity: str
    availability_state: str
    authority_classification: str
    content_type: str = ""
    content_hash: str = ""
    version: str = ""
    retrieval_timestamp: str = ""
    storage_location: str = ""
    strategy_bearing_content_present: bool = False
    authors: tuple = ()
    title: str = ""
    year: str = ""
    stable_identifier: str = ""

    def __post_init__(self) -> None:
        if not str(self.source_id).strip():
            raise AuthorityGateError("source_id is required")
        if self.source_role not in SOURCE_ROLES:
            raise AuthorityGateError(f"unknown source_role {self.source_role!r}")
        if self.authority_classification not in AUTHORITY_CLASSES:
            raise AuthorityGateError(
                f"unknown authority_classification {self.authority_classification!r}")
        # The legacy token is accepted as input so historical records can be re-evaluated by this
        # gate; it can never pass.
        if (self.availability_state not in AVAILABILITY_STATES
                and self.availability_state != LEGACY_SUMMARY_TOKEN):
            raise AuthorityGateError(f"unknown availability_state {self.availability_state!r}")


def _freeze_defects(art: SourceArtifact) -> list:
    """Fields whose absence means the content was read but not preserved."""
    defects = []
    for name in ("content_type", "content_hash", "version", "retrieval_timestamp",
                 "storage_location", "title"):
        if not str(getattr(art, name)).strip():
            defects.append(f"{name} is empty")
    if not art.authors:
        defects.append("authors is empty")
    if not str(art.year).strip():
        defects.append("year is empty")
    if (art.source_role not in STABLE_IDENTIFIER_OPTIONAL_ROLES
            and not str(art.stable_identifier).strip()):
        defects.append(
            "stable_identifier (DOI/arXiv/repository) is empty for an authoritative role")
    return defects


def evaluate(artifact: SourceArtifact) -> dict:
    """Decide whether one artifact may serve as authoritative strategy-bearing content."""
    role_cap = ROLE_MAX_AUTHORITY[artifact.source_role]
    over_claimed = (_AUTHORITY_RANK[artifact.authority_classification]
                    > _AUTHORITY_RANK[role_cap])

    authoritative_state = artifact.availability_state in AUTHORITATIVE_STATES
    authoritative_role = artifact.source_role in AUTHORITATIVE_ROLES
    freeze_defects = _freeze_defects(artifact)

    reasons = []
    if over_claimed:
        state = BLOCKED_ROLE_AUTHORITY_MISMATCH
        reasons.append(
            f"source_role {artifact.source_role!r} may claim at most "
            f"{role_cap!r} authority, not {artifact.authority_classification!r}")
    elif not authoritative_state or not authoritative_role:
        state = BLOCKED_NOT_AUTHORITATIVE
        if not authoritative_state:
            reasons.append(
                f"availability_state {artifact.availability_state!r} is not authoritative content")
        if not authoritative_role:
            reasons.append(
                f"source_role {artifact.source_role!r} cannot supply authoritative content")
    elif not artifact.strategy_bearing_content_present:
        state = BLOCKED_NOT_STRATEGY_BEARING
        reasons.append("retained content does not bear the required strategy mechanics")
    elif freeze_defects:
        state = BLOCKED_NOT_FROZEN
        reasons.extend(freeze_defects)
    else:
        state = PASS

    return {
        "schema_version": SCHEMA_VERSION,
        "gate_id": GATE_ID,
        "source_id": artifact.source_id,
        "source_role": artifact.source_role,
        "availability_state": artifact.availability_state,
        "authority_classification": artifact.authority_classification,
        "role_max_authority": role_cap,
        "state": state,
        "passed": state == PASS,
        "authoritative_content_available": state == PASS,
        "strategy_bearing_content_present": bool(artifact.strategy_bearing_content_present),
        "frozen": not freeze_defects,
        "freeze_defects": sorted(freeze_defects),
        "block_reasons": sorted(reasons),
        "navigation_value_only": artifact.source_role in (ROLE_SECONDARY, ROLE_NAVIGATION),
    }


def evaluate_source(source_id: str, artifacts) -> dict:
    """Decide whether a *source* — its whole artifact set — has authoritative content.

    A source passes when at least one of its artifacts passes. Secondary artifacts are still
    reported, because their navigation value is real even though their authority is not.
    """
    per_artifact = [evaluate(a) for a in artifacts]
    passing = [r for r in per_artifact if r["passed"]]

    if passing:
        state = PASS
        reasons = []
    elif not per_artifact:
        state = BLOCKED_NOT_AUTHORITATIVE
        reasons = ["no source artifact supplied"]
    else:
        # Report the least-bad blocking state so the caller sees the nearest miss, not the first.
        order = (BLOCKED_NOT_FROZEN, BLOCKED_NOT_STRATEGY_BEARING, BLOCKED_ROLE_AUTHORITY_MISMATCH,
                 BLOCKED_NOT_AUTHORITATIVE)
        state = next(s for s in order if any(r["state"] == s for r in per_artifact))
        reasons = sorted({m for r in per_artifact for m in r["block_reasons"]})

    return {
        "schema_version": SCHEMA_VERSION,
        "gate_id": GATE_ID,
        "source_id": source_id,
        "state": state,
        "passed": state == PASS,
        "authoritative_content_available": state == PASS,
        "artifact_count": len(per_artifact),
        "passing_artifact_count": len(passing),
        "passing_artifact_roles": sorted({r["source_role"] for r in passing}),
        "navigation_only_artifact_count": sum(
            1 for r in per_artifact if r["navigation_value_only"]),
        "block_reasons": reasons,
        "artifacts": sorted(per_artifact,
                            key=lambda r: (r["source_role"], r["availability_state"])),
    }
