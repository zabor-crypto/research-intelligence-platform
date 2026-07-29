"""Source-internal contradiction detection.

The single most serious error this pipeline ever made was a source whose README and whose executable
code specified opposite trade directions. The pipeline read the README, asserted that direction, and
never noticed the code said the reverse — an inverted strategy presented with full confidence.

This detector compares a source's own representations against each other and fails closed. Two
design rules follow from how that failure happened:

* **No silent precedence.** The detector never decides that code beats prose or that prose beats
  code. An unresolved material conflict blocks eligibility; a resolution must be supplied
  explicitly, carry evidence from *both* sides, name its precedence rule, justify why the chosen
  representation is authoritative, and confirm the choice matches the intended executable strategy.
* **Cosmetic differences are not conflicts.** Wording, casing, punctuation and controlled-vocabulary
  synonyms are normalised per field before comparison, so "Long the winner" and "long the winner."
  do not manufacture a critical direction conflict.

Output is deterministic: claims and conflicts are emitted in sorted order.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from dataclasses import field as dc_field

SCHEMA_VERSION = "source-contradiction-detector/1.0"

REPRESENTATIONS = (
    "paper_prose",
    "equations",
    "tables",
    "supplementary_material",
    "readme",
    "notebook",
    "configuration",
    "executable_code",
    "later_source_revision",
)

SIGNAL_DIRECTION = "signal_direction_conflict"
ENTRY_RULE = "entry_rule_conflict"
EXIT_RULE = "exit_rule_conflict"
POSITION_LEG = "position_leg_conflict"
WEIGHTING = "weighting_conflict"
TIMEFRAME = "timeframe_conflict"
TIMESTAMP_SEMANTICS = "timestamp_semantics_conflict"
UNIVERSE = "universe_conflict"
PARAMETER = "parameter_conflict"
PAYOFF_DEFINITION = "payoff_definition_conflict"

CONTRADICTION_CLASSES = (
    SIGNAL_DIRECTION, ENTRY_RULE, EXIT_RULE, POSITION_LEG, WEIGHTING,
    TIMEFRAME, TIMESTAMP_SEMANTICS, UNIVERSE, PARAMETER, PAYOFF_DEFINITION,
)

# An unresolved conflict affecting signal direction, portfolio, timing, entry, exit or payoff must
# block candidate eligibility. Portfolio covers legs/weighting/universe; timing covers timeframe and
# timestamp semantics. A bare numeric parameter disagreement is material but not automatically
# eligibility-blocking unless the caller marks it so.
BLOCKING_CLASSES = frozenset({
    SIGNAL_DIRECTION, ENTRY_RULE, EXIT_RULE, POSITION_LEG, WEIGHTING,
    TIMEFRAME, TIMESTAMP_SEMANTICS, UNIVERSE, PAYOFF_DEFINITION,
})

NO_MATERIAL = "no_material_contradiction"
RESOLVED_BY_PRECEDENCE = "material_contradiction_resolved_by_authoritative_precedence"
UNRESOLVED = "material_contradiction_unresolved"

# An earlier iteration called ``detect([])`` for every source in the pool and recorded
# ``no_material_contradiction`` each time — absence of evidence reported as evidence of absence.
# A comparison needs at least two independently evidenced representations of the same field; when
# it does not have them, the honest output is that nothing was evaluated.
NOT_EVALUATED_INSUFFICIENT = "contradiction_not_evaluated_insufficient_claim_inventory"
NOT_EVALUATED_SINGLE_REPRESENTATION = "contradiction_not_evaluated_single_representation"
NOT_EVALUATED_MISSING_EVIDENCE = "contradiction_not_evaluated_missing_evidence"

NOT_EVALUATED_STATES = frozenset({
    NOT_EVALUATED_INSUFFICIENT, NOT_EVALUATED_SINGLE_REPRESENTATION,
    NOT_EVALUATED_MISSING_EVIDENCE,
})

STATES = (NO_MATERIAL, RESOLVED_BY_PRECEDENCE, UNRESOLVED, NOT_EVALUATED_INSUFFICIENT,
          NOT_EVALUATED_SINGLE_REPRESENTATION, NOT_EVALUATED_MISSING_EVIDENCE)

# A single representation is enough to *describe* a strategy but never enough to *corroborate* one.
# It does not block on its own — a lone primary paper is a normal, legitimate situation — but it
# must not be reported as though a comparison had been performed and passed.
NON_BLOCKING_NOT_EVALUATED = frozenset({NOT_EVALUATED_SINGLE_REPRESENTATION})

# Fields without which a claim inventory cannot describe an executable strategy: what is traded,
# when, and against which price mark. An unresolved "entry at the 23:00 open or the 23:00 close" is
# a TIMESTAMP_SEMANTICS question and moves the entry price, so timing belongs here alongside
# direction and entry/exit.
#
# Weighting, universe and bare parameters are deliberately excluded: each presupposes a trade rule
# rather than supplying one. An inventory that says only "lookback = 20" describes no strategy.
EXECUTABLE_MECHANICS_CLASSES = frozenset({
    SIGNAL_DIRECTION, ENTRY_RULE, EXIT_RULE, POSITION_LEG, PAYOFF_DEFINITION,
    TIMEFRAME, TIMESTAMP_SEMANTICS,
})

# Controlled vocabularies: synonyms that mean the same thing collapse; opposites never do.
_DIRECTION_VOCAB = {
    "long": "long", "buy": "long", "+1": "long", "1": "long", "bullish": "long",
    "short": "short", "sell": "short", "-1": "short", "bearish": "short",
    "flat": "flat", "0": "flat", "neutral": "flat", "no position": "flat",
}
_TIMESTAMP_VOCAB = {
    "open": "bar_open", "bar open": "bar_open", "open time": "bar_open",
    "opentime": "bar_open", "bar_open": "bar_open",
    "close": "bar_close", "bar close": "bar_close", "close time": "bar_close",
    "closetime": "bar_close", "bar_close": "bar_close",
}
FIELD_VOCABULARIES = {
    SIGNAL_DIRECTION: _DIRECTION_VOCAB,
    POSITION_LEG: _DIRECTION_VOCAB,
    TIMESTAMP_SEMANTICS: _TIMESTAMP_VOCAB,
}

_PUNCT = re.compile(r"[^\w\s+-]")
_WS = re.compile(r"\s+")


class ContradictionError(ValueError):
    """Malformed contradiction input. The detector never guesses past bad input."""


def normalise(value, contradiction_class: str | None = None) -> str:
    """Canonical comparison form for a claimed value.

    Strips cosmetic variation (case, padding, trailing punctuation) and maps controlled-vocabulary
    synonyms onto one token, so only substantive disagreements survive. Opposing terms are never
    collapsed: "long" and "short" remain distinct under every vocabulary.
    """
    text = _WS.sub(" ", _PUNCT.sub("", str(value).strip().casefold())).strip()
    vocab = FIELD_VOCABULARIES.get(contradiction_class or "")
    if vocab:
        return vocab.get(text, text)
    return text


@dataclass(frozen=True)
class Claim:
    """One representation's statement about one strategy field."""

    representation: str
    contradiction_class: str
    value: str
    evidence_locator: str
    evidence_quote: str

    def __post_init__(self) -> None:
        if self.representation not in REPRESENTATIONS:
            raise ContradictionError(f"unknown representation {self.representation!r}")
        if self.contradiction_class not in CONTRADICTION_CLASSES:
            raise ContradictionError(f"unknown contradiction class {self.contradiction_class!r}")
        if not str(self.evidence_locator).strip():
            raise ContradictionError(
                f"{self.contradiction_class}/{self.representation}: evidence_locator is required")
        if not str(self.evidence_quote).strip():
            raise ContradictionError(
                f"{self.contradiction_class}/{self.representation}: evidence_quote is required")

    @property
    def normalised(self) -> str:
        return normalise(self.value, self.contradiction_class)


@dataclass(frozen=True)
class Resolution:
    """An explicit, evidence-backed precedence decision for one contradiction class."""

    contradiction_class: str
    chosen_representation: str
    precedence_rule: str
    justification: str
    executable_identity_confirmed: bool
    evidence_locators: tuple = dc_field(default=())

    def __post_init__(self) -> None:
        if self.contradiction_class not in CONTRADICTION_CLASSES:
            raise ContradictionError(f"unknown contradiction class {self.contradiction_class!r}")
        if self.chosen_representation not in REPRESENTATIONS:
            raise ContradictionError(f"unknown representation {self.chosen_representation!r}")


def _resolution_defects(res: Resolution, conflicting: list) -> list:
    """Why a supplied resolution does not count. Empty list == the resolution stands."""
    defects = []
    reps = {c.representation for c in conflicting}
    if res.chosen_representation not in reps:
        defects.append(
            f"chosen representation {res.chosen_representation!r} is not one of the conflicting "
            f"representations {sorted(reps)}")
    if not str(res.precedence_rule).strip():
        defects.append("no explicit precedence rule")
    if not str(res.justification).strip():
        defects.append("no justification for why the chosen representation is authoritative")
    if res.executable_identity_confirmed is not True:
        defects.append("chosen representation not confirmed against the intended executable "
                       "strategy identity")
    cited = {str(loc) for loc in res.evidence_locators}
    missing = sorted(rep for rep in reps
                     if not any(c.evidence_locator in cited
                                for c in conflicting if c.representation == rep))
    if missing:
        defects.append(f"no cited evidence from conflicting representation(s) {missing}")
    return defects


def _inventory_defect(claims, by_class, unevidenced_representations) -> tuple:
    """Why this claim inventory cannot support a contradiction verdict.

    Returns ``(state, reasons)``, or ``(None, [])`` when the inventory is adequate — at least two
    independently evidenced representations, covering the mechanics that make a strategy
    executable. Anything less can describe a strategy but cannot corroborate one.
    """
    if not claims:
        return NOT_EVALUATED_INSUFFICIENT, ["no claims supplied: nothing was compared"]

    covered = EXECUTABLE_MECHANICS_CLASSES & set(by_class)
    if not covered:
        return NOT_EVALUATED_INSUFFICIENT, [
            "no claim covers executable mechanics "
            f"({sorted(EXECUTABLE_MECHANICS_CLASSES)}); "
            f"only {sorted(by_class)} present"]

    unevidenced = sorted({str(r) for r in unevidenced_representations if str(r).strip()})
    if unevidenced:
        # The direction inversion described in the module docstring was invisible precisely because
        # one representation existed and was never read. A known-but-uncaptured representation
        # therefore fails closed even when the captured ones agree with each other.
        return NOT_EVALUATED_MISSING_EVIDENCE, [
            f"representation(s) {unevidenced} exist but no evidence was captured from them"]

    reps = sorted({c.representation for c in claims})
    if len(reps) < 2:
        return NOT_EVALUATED_SINGLE_REPRESENTATION, [
            f"only one representation ({reps[0]!r}) is present; agreement cannot be established "
            "from a single account of the strategy"]

    return None, []


def detect(claims, resolutions=(), *, source_id: str = "",
           unevidenced_representations=()) -> dict:
    """Compare a source's representations and classify its internal contradictions.

    ``claims`` are per-representation statements; ``resolutions`` are explicit precedence
    decisions. A class with two or more distinct normalised values is a material contradiction and
    stays unresolved unless a *valid* resolution is supplied for it.

    ``unevidenced_representations`` names representations known to exist whose claims were never
    captured. They cannot be compared, so their presence puts the audit into
    ``contradiction_not_evaluated_missing_evidence`` rather than letting the captured
    representations agree amongst themselves.

    When the inventory cannot support a comparison at all, the result is one of the
    ``NOT_EVALUATED_*`` states — never ``no_material_contradiction``. Absence of evidence is not
    evidence of absence.
    """
    claims = list(claims)
    by_class: dict[str, list] = {}
    for c in claims:
        if not isinstance(c, Claim):
            raise ContradictionError(f"expected Claim, got {type(c).__name__}")
        by_class.setdefault(c.contradiction_class, []).append(c)

    res_by_class: dict[str, Resolution] = {}
    for r in resolutions:
        if r.contradiction_class in res_by_class:
            raise ContradictionError(
                f"more than one resolution supplied for {r.contradiction_class!r}")
        res_by_class[r.contradiction_class] = r

    conflicts = []
    for cls in sorted(by_class):
        group = by_class[cls]
        distinct = sorted({c.normalised for c in group})
        if len(distinct) < 2:
            continue

        entry = {
            "contradiction_class": cls,
            "distinct_values": distinct,
            "representations": sorted({c.representation for c in group}),
            "claims": sorted(
                ({"representation": c.representation, "value": c.value,
                  "normalised": c.normalised, "evidence_locator": c.evidence_locator,
                  "evidence_quote": c.evidence_quote} for c in group),
                key=lambda d: (d["representation"], d["normalised"])),
            "blocking_class": cls in BLOCKING_CLASSES,
        }

        res = res_by_class.get(cls)
        if res is None:
            entry["resolution_state"] = UNRESOLVED
            entry["resolution_defects"] = ["no resolution supplied"]
        else:
            defects = _resolution_defects(res, group)
            entry["resolution_defects"] = defects
            entry["resolution_state"] = UNRESOLVED if defects else RESOLVED_BY_PRECEDENCE
            entry["resolution"] = {
                "chosen_representation": res.chosen_representation,
                "chosen_value": next((c.normalised for c in group
                                      if c.representation == res.chosen_representation), None),
                "precedence_rule": res.precedence_rule,
                "justification": res.justification,
                "executable_identity_confirmed": res.executable_identity_confirmed,
                "evidence_locators": sorted(str(x) for x in res.evidence_locators),
            }
        conflicts.append(entry)

    unresolved = [c for c in conflicts if c["resolution_state"] == UNRESOLVED]
    blocking = [c for c in unresolved if c["blocking_class"]]

    inventory_state, inventory_reasons = _inventory_defect(
        claims, by_class, unevidenced_representations)

    # A conflict that was actually found outranks any inventory shortfall: the comparison did run
    # far enough to prove the source disagrees with itself, and that finding stands on its own.
    if conflicts:
        state = UNRESOLVED if unresolved else RESOLVED_BY_PRECEDENCE
        evaluated = True
    elif inventory_state is not None:
        state = inventory_state
        evaluated = False
    else:
        state = NO_MATERIAL
        evaluated = True

    eligible = not blocking and (
        state not in NOT_EVALUATED_STATES or state in NON_BLOCKING_NOT_EVALUATED)

    return {
        "schema_version": SCHEMA_VERSION,
        "source_id": source_id,
        "state": state,
        "evaluated": evaluated,
        "eligible": eligible,
        "blocked_by": sorted(c["contradiction_class"] for c in blocking),
        "inventory_defect_reasons": inventory_reasons,
        "executable_mechanics_covered": sorted(EXECUTABLE_MECHANICS_CLASSES & set(by_class)),
        "unevidenced_representations": sorted(
            {str(r) for r in unevidenced_representations if str(r).strip()}),
        "material_contradiction_count": len(conflicts),
        "unresolved_count": len(unresolved),
        "resolved_count": len(conflicts) - len(unresolved),
        "conflicts": conflicts,
        "classes_examined": sorted(by_class),
        "representations_examined": sorted({c.representation for c in claims}),
        "silent_precedence_applied": False,
    }
