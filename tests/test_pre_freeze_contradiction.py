"""Source-internal contradiction detection.

The regression case is a source whose prose and whose executable code state opposite trade
directions, and which was read as confident and consistent because only one of them was consulted.
"""

from __future__ import annotations

import pytest

from research_process.pre_freeze import contradiction as CD


def claim(rep: str, cls: str, value: str) -> CD.Claim:
    return CD.Claim(
        representation=rep,
        contradiction_class=cls,
        value=value,
        evidence_locator=f"{rep}#L1",
        evidence_quote=f"{rep} says {value}",
    )


def direction_inversion() -> list:
    return [
        claim("readme", CD.SIGNAL_DIRECTION, "long the winner"),
        claim("executable_code", CD.SIGNAL_DIRECTION, "short the winner"),
    ]


def test_direction_inversion_is_detected_and_blocks():
    r = CD.detect(direction_inversion(), source_id="src-1")
    assert r["state"] == CD.UNRESOLVED
    assert r["eligible"] is False
    assert r["blocked_by"] == [CD.SIGNAL_DIRECTION]
    assert r["material_contradiction_count"] == 1


def test_detector_never_applies_precedence_by_itself():
    r = CD.detect(direction_inversion())
    assert r["silent_precedence_applied"] is False
    assert r["conflicts"][0]["resolution_defects"] == ["no resolution supplied"]


def test_cosmetic_difference_is_not_a_conflict():
    claims = [
        claim("readme", CD.SIGNAL_DIRECTION, "Long the winner."),
        claim("executable_code", CD.SIGNAL_DIRECTION, "long the winner"),
    ]
    r = CD.detect(claims)
    assert r["state"] == CD.NO_MATERIAL
    assert r["eligible"] is True
    assert r["material_contradiction_count"] == 0


def test_controlled_vocabulary_collapses_synonyms_but_never_opposites():
    assert CD.normalise("buy", CD.SIGNAL_DIRECTION) == CD.normalise("long", CD.SIGNAL_DIRECTION)
    assert CD.normalise("sell", CD.SIGNAL_DIRECTION) != CD.normalise("long", CD.SIGNAL_DIRECTION)
    assert CD.normalise("Close time", CD.TIMESTAMP_SEMANTICS) == "bar_close"


def test_synonyms_across_representations_do_not_manufacture_a_conflict():
    claims = [
        claim("paper_prose", CD.SIGNAL_DIRECTION, "buy"),
        claim("executable_code", CD.SIGNAL_DIRECTION, "+1"),
    ]
    assert CD.detect(claims)["state"] == CD.NO_MATERIAL


def _valid_resolution() -> CD.Resolution:
    return CD.Resolution(
        contradiction_class=CD.SIGNAL_DIRECTION,
        chosen_representation="executable_code",
        precedence_rule="executable code over prose for direction",
        justification="the code is what produced the published results",
        executable_identity_confirmed=True,
        evidence_locators=("readme#L1", "executable_code#L1"),
    )


def test_valid_resolution_clears_the_conflict():
    r = CD.detect(direction_inversion(), [_valid_resolution()])
    assert r["state"] == CD.RESOLVED_BY_PRECEDENCE
    assert r["eligible"] is True
    assert r["conflicts"][0]["resolution"]["chosen_value"] == "short the winner"


@pytest.mark.parametrize(
    "kw",
    [
        {"precedence_rule": ""},
        {"justification": ""},
        {"executable_identity_confirmed": False},
        {"evidence_locators": ("executable_code#L1",)},  # nothing cited from the other side
        {"chosen_representation": "notebook"},  # not one of the conflicting representations
    ],
)
def test_incomplete_resolution_does_not_clear_the_conflict(kw):
    base = dict(
        contradiction_class=CD.SIGNAL_DIRECTION,
        chosen_representation="executable_code",
        precedence_rule="executable code over prose",
        justification="code produced the results",
        executable_identity_confirmed=True,
        evidence_locators=("readme#L1", "executable_code#L1"),
    )
    base.update(kw)
    r = CD.detect(direction_inversion(), [CD.Resolution(**base)])
    assert r["state"] == CD.UNRESOLVED
    assert r["eligible"] is False
    assert r["conflicts"][0]["resolution_defects"]


def test_empty_inventory_is_not_evaluated_rather_than_clean():
    r = CD.detect([], source_id="src-empty")
    assert r["state"] == CD.NOT_EVALUATED_INSUFFICIENT
    assert r["evaluated"] is False
    assert r["eligible"] is False
    assert r["state"] != CD.NO_MATERIAL


def test_claims_that_miss_executable_mechanics_are_not_evaluated():
    r = CD.detect([claim("paper_prose", CD.PARAMETER, "lookback = 20")])
    assert r["state"] == CD.NOT_EVALUATED_INSUFFICIENT
    assert r["executable_mechanics_covered"] == []


def test_single_representation_is_reported_but_does_not_block():
    r = CD.detect([claim("paper_prose", CD.SIGNAL_DIRECTION, "long")])
    assert r["state"] == CD.NOT_EVALUATED_SINGLE_REPRESENTATION
    assert r["evaluated"] is False
    assert r["eligible"] is True


def test_a_known_but_uncaptured_representation_fails_closed():
    claims = [
        claim("paper_prose", CD.SIGNAL_DIRECTION, "long"),
        claim("readme", CD.SIGNAL_DIRECTION, "long"),
    ]
    r = CD.detect(claims, unevidenced_representations=("executable_code",))
    assert r["state"] == CD.NOT_EVALUATED_MISSING_EVIDENCE
    assert r["eligible"] is False
    assert r["unevidenced_representations"] == ["executable_code"]


def test_a_found_conflict_outranks_an_inventory_shortfall():
    r = CD.detect(direction_inversion(), unevidenced_representations=("notebook",))
    assert r["state"] == CD.UNRESOLVED
    assert r["evaluated"] is True


def test_non_blocking_class_conflict_is_reported_without_blocking():
    claims = [
        claim("paper_prose", CD.PARAMETER, "lookback = 20"),
        claim("executable_code", CD.PARAMETER, "lookback = 30"),
    ]
    r = CD.detect(claims)
    assert r["state"] == CD.UNRESOLVED
    assert r["blocked_by"] == []
    assert r["eligible"] is True


def test_claim_requires_evidence():
    with pytest.raises(CD.ContradictionError):
        CD.Claim("readme", CD.SIGNAL_DIRECTION, "long", "", "quote")
    with pytest.raises(CD.ContradictionError):
        CD.Claim("readme", CD.SIGNAL_DIRECTION, "long", "readme#L1", "")


def test_unknown_representation_and_class_are_rejected():
    with pytest.raises(CD.ContradictionError):
        CD.Claim("tea_leaves", CD.SIGNAL_DIRECTION, "long", "a", "b")
    with pytest.raises(CD.ContradictionError):
        CD.Claim("readme", "vibes_conflict", "long", "a", "b")


def test_two_resolutions_for_one_class_are_rejected():
    with pytest.raises(CD.ContradictionError):
        CD.detect(direction_inversion(), [_valid_resolution(), _valid_resolution()])


def test_non_claim_input_is_rejected():
    with pytest.raises(CD.ContradictionError):
        CD.detect([{"representation": "readme"}])


def test_output_is_deterministic():
    first = CD.detect(direction_inversion(), source_id="src-1")
    second = CD.detect(list(reversed(direction_inversion())), source_id="src-1")
    assert first == second
