"""Authoritative-content gate: reading a summary of a paper is not holding the paper."""

from __future__ import annotations

import pytest

from research_process.pre_freeze import authority_gate as AG


def artifact(**overrides) -> AG.SourceArtifact:
    base = dict(
        source_id="src-1",
        source_role=AG.ROLE_PRIMARY,
        canonical_identity="Author et al. (2024), A Paper",
        availability_state=AG.AUTHORITATIVE_FULL_TEXT,
        authority_classification=AG.AUTHORITY_PRIMARY,
        content_type="application/pdf",
        content_hash="sha256:9ab3…",
        version="v2",
        retrieval_timestamp="2026-05-01T10:00:00Z",
        storage_location="sources/src-1/paper-v2.pdf",
        strategy_bearing_content_present=True,
        authors=("A. Author", "B. Author"),
        title="A Paper",
        year="2024",
        stable_identifier="arXiv:2401.00001",
    )
    base.update(overrides)
    return AG.SourceArtifact(**base)


def test_primary_full_text_that_is_frozen_and_strategy_bearing_passes():
    r = AG.evaluate(artifact())
    assert r["state"] == AG.PASS
    assert r["authoritative_content_available"] is True
    assert r["frozen"] is True
    assert r["navigation_value_only"] is False


def test_secondary_summary_never_passes():
    r = AG.evaluate(artifact(
        source_role=AG.ROLE_SECONDARY,
        availability_state=AG.SECONDARY_SUMMARY,
        authority_classification=AG.AUTHORITY_SECONDARY,
        stable_identifier="",
    ))
    assert r["state"] == AG.BLOCKED_NOT_AUTHORITATIVE
    assert r["navigation_value_only"] is True


def test_the_legacy_summary_token_is_rejected_by_name():
    """The exact value that slipped through a substring test in an earlier iteration."""
    r = AG.evaluate(artifact(availability_state=AG.LEGACY_SUMMARY_TOKEN))
    assert r["state"] == AG.BLOCKED_NOT_AUTHORITATIVE
    assert AG.LEGACY_SUMMARY_TOKEN in AG.NON_PASSING_STATES


@pytest.mark.parametrize("state", sorted(AG.NON_PASSING_STATES))
def test_no_non_passing_availability_state_can_pass(state):
    assert AG.evaluate(artifact(availability_state=state))["passed"] is False


def test_a_role_may_not_claim_more_authority_than_it_has():
    r = AG.evaluate(artifact(
        source_role=AG.ROLE_SECONDARY,
        authority_classification=AG.AUTHORITY_PRIMARY,
        stable_identifier="",
    ))
    assert r["state"] == AG.BLOCKED_ROLE_AUTHORITY_MISMATCH
    assert r["role_max_authority"] == AG.AUTHORITY_SECONDARY


def test_author_code_may_claim_author_derived_authority():
    r = AG.evaluate(artifact(
        source_role=AG.ROLE_AUTHOR_CODE,
        availability_state=AG.AUTHORITATIVE_CODE,
        authority_classification=AG.AUTHORITY_AUTHOR_DERIVED,
        stable_identifier="github.com/example/repo@abc1234",
    ))
    assert r["state"] == AG.PASS


def test_authoritative_document_without_strategy_content_is_blocked():
    r = AG.evaluate(artifact(strategy_bearing_content_present=False))
    assert r["state"] == AG.BLOCKED_NOT_STRATEGY_BEARING


@pytest.mark.parametrize(
    "kw",
    [
        {"content_hash": ""},
        {"retrieval_timestamp": ""},
        {"storage_location": ""},
        {"version": ""},
        {"authors": ()},
        {"year": ""},
        {"stable_identifier": ""},
    ],
)
def test_content_read_but_not_preserved_is_blocked(kw):
    r = AG.evaluate(artifact(**kw))
    assert r["state"] == AG.BLOCKED_NOT_FROZEN
    assert r["frozen"] is False


def test_a_secondary_role_does_not_need_a_stable_identifier_to_be_well_formed():
    r = AG.evaluate(artifact(
        source_role=AG.ROLE_NAVIGATION,
        availability_state=AG.SECONDARY_NAVIGATION_ONLY,
        authority_classification=AG.AUTHORITY_SECONDARY,
        stable_identifier="",
    ))
    # blocked on authority, not on a missing DOI it could never have
    assert r["state"] == AG.BLOCKED_NOT_AUTHORITATIVE


def test_malformed_artifacts_are_rejected():
    with pytest.raises(AG.AuthorityGateError):
        artifact(source_id=" ")
    with pytest.raises(AG.AuthorityGateError):
        artifact(source_role="blog_post")
    with pytest.raises(AG.AuthorityGateError):
        artifact(authority_classification="definitive")
    with pytest.raises(AG.AuthorityGateError):
        artifact(availability_state="probably_somewhere")


def test_a_source_passes_when_any_one_artifact_passes():
    secondary = artifact(
        source_id="src-1",
        source_role=AG.ROLE_SECONDARY,
        availability_state=AG.SECONDARY_SUMMARY,
        authority_classification=AG.AUTHORITY_SECONDARY,
        stable_identifier="",
    )
    r = AG.evaluate_source("src-1", [secondary, artifact()])
    assert r["passed"] is True
    assert r["passing_artifact_count"] == 1
    assert r["navigation_only_artifact_count"] == 1


def test_a_source_with_only_secondary_artifacts_is_blocked():
    secondary = artifact(
        source_role=AG.ROLE_SECONDARY,
        availability_state=AG.SECONDARY_SUMMARY,
        authority_classification=AG.AUTHORITY_SECONDARY,
        stable_identifier="",
    )
    r = AG.evaluate_source("src-1", [secondary])
    assert r["passed"] is False
    assert r["block_reasons"]


def test_a_source_with_no_artifacts_is_blocked():
    r = AG.evaluate_source("src-1", [])
    assert r["passed"] is False
    assert r["block_reasons"] == ["no source artifact supplied"]


def test_nearest_miss_is_reported_rather_than_the_first_failure():
    not_frozen = artifact(content_hash="")
    not_authoritative = artifact(
        source_role=AG.ROLE_SECONDARY,
        availability_state=AG.SECONDARY_SUMMARY,
        authority_classification=AG.AUTHORITY_SECONDARY,
        stable_identifier="",
    )
    r = AG.evaluate_source("src-1", [not_authoritative, not_frozen])
    assert r["state"] == AG.BLOCKED_NOT_FROZEN
