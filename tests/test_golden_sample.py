"""Golden-sample evaluation: source-derived values must survive the full
extraction -> hypothesis -> backtest-spec chain.

Not exact-JSON equality: asserts that the critical source parameters and
reported metrics are present at every stage.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from research_intel.extraction.validators import validate_extraction, validate_hypothesis
from research_intel.hypotheses.exporter import build_backtest_spec, render_backtest_spec_md
from research_intel.llm.mock_client import MockLLMClient
from research_intel.storage.models import StrategyHypothesis

GOLDEN = Path(__file__).parent / "golden"
SOURCE_TEXT = (GOLDEN / "volatility_regime_source.md").read_text(encoding="utf-8")
EXPECTED_EXTRACTION = json.loads(
    (GOLDEN / "expected_minimum_extraction.json").read_text(encoding="utf-8")
)
EXPECTED_SPEC_LINES = [
    line.strip()
    for line in (GOLDEN / "expected_minimum_backtest_spec_contains.txt").read_text().splitlines()
    if line.strip()
]


@pytest.fixture(scope="module")
def extraction() -> dict:
    payload = MockLLMClient().extract_research(SOURCE_TEXT, {})
    payload["source_id"] = "1"
    payload["document_id"] = "1"
    return validate_extraction(payload).model_dump()


@pytest.fixture(scope="module")
def spec_md(extraction: dict) -> str:
    hyp_payload = MockLLMClient().generate_hypothesis(extraction)
    record = validate_hypothesis(hyp_payload)
    hyp = StrategyHypothesis(
        hypothesis_id=record.hypothesis_id,
        extraction_id=1,
        source_ids=record.source_ids,
        payload=record.model_dump(),
        status="scored",
        priority_score=75.0,
    )
    return render_backtest_spec_md(build_backtest_spec(hyp, None))


def test_golden_extraction_contains_expected_minimum(extraction: dict):
    for key, expected in EXPECTED_EXTRACTION.items():
        actual = extraction[key]
        if isinstance(expected, dict):
            for sub_key, sub_value in expected.items():
                assert actual.get(sub_key) == sub_value, (
                    f"{key}.{sub_key}: expected {sub_value}, got {actual.get(sub_key)}"
                )
        else:
            assert actual == expected, f"{key}: expected {expected}, got {actual}"


def test_golden_backtest_spec_contains_source_values(spec_md: str):
    missing = [line for line in EXPECTED_SPEC_LINES if line not in spec_md]
    assert not missing, f"backtest spec is missing source-derived values: {missing}"


def test_golden_spec_has_computable_formulas(spec_md: str):
    assert "close / close.shift(30) - 1" in spec_md
    assert "std(1m log returns over 60 bars) * sqrt(60)" in spec_md
    assert "abs(ret_30m) / rv_60m" in spec_md
    assert "rv_60m / rv_240m" in spec_md


def test_golden_spec_marks_parameter_provenance(spec_md: str):
    # All nine parameters were explicit in the source.
    assert spec_md.count("| source |") == 9
    assert "Parameter Source Quality: explicit" in spec_md
