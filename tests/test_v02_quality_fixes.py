"""v0.2 quality fixes: relevance ranking (P2), archetype fidelity (P3),
source fact fidelity (P4), parameter aliases (P5), stable ids (P6),
provider audit logging (P1)."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from research_intel.collectors.arxiv_collector import ArxivCollector
from research_intel.collectors.relevance import score_relevance
from research_intel.extraction.normalization import normalize_strategy_parameters
from research_intel.extraction.validators import validate_hypothesis
from research_intel.hypotheses.fidelity import assess_fidelity
from research_intel.llm.mock_client import MockLLMClient
from tests.conftest import EXAMPLES

EVAL = Path(__file__).resolve().parents[1] / "eval_sources" / "batch_v1"

LIQ_TEXT = (EVAL / "note_liquidation_reversal.md").read_text()
FUND_TEXT = (EVAL / "note_funding_mean_reversion.md").read_text()
VOL_TEXT = (EVAL / "note_volatility_regime_momentum.md").read_text()


def _pipeline(text: str, sid: str = "1"):
    llm = MockLLMClient()
    ext = llm.extract_research(text, {})
    ext["source_id"] = sid
    ext["document_id"] = sid
    hyp = llm.generate_hypothesis(ext)
    validate_hypothesis(hyp)
    return ext, hyp


# ------------------------------------------------------------------ P2


def test_relevance_offtopic_newer_ranks_below_relevant_older():
    relevant = score_relevance(
        "Momentum and Volatility Regimes in Cryptocurrency Markets",
        "We study crypto momentum strategies conditioned on volatility.",
        "crypto momentum volatility regime",
    )
    offtopic = score_relevance(
        "Well-invertible column subsets of sparse matrices are rare",
        "We study combinatorial properties of sparse random matrices.",
        "crypto momentum volatility regime",
    )
    assert relevant["relevance_score"] > offtopic["relevance_score"]
    assert offtopic["below_threshold"]
    assert not relevant["below_threshold"]


def test_relevance_title_match_boosts():
    with_title = score_relevance(
        "Order Flow Imbalance in Cryptocurrency Markets", "crypto trading study",
        "order flow imbalance cryptocurrency",
    )
    without_title = score_relevance(
        "A Study of Digital Markets", "crypto trading study order flow imbalance",
        "order flow imbalance cryptocurrency",
    )
    assert with_title["relevance_score"] >= without_title["relevance_score"]
    assert with_title["matched_query_terms"]


def test_relevance_negative_terms_penalize():
    clean = score_relevance("Crypto momentum trading", "bitcoin strategy returns", "crypto momentum")
    dirty = score_relevance(
        "Crypto momentum trading in astronomy image data",
        "bitcoin strategy returns for astronomy image pipelines", "crypto momentum",
    )
    assert dirty["relevance_score"] < clean["relevance_score"]
    assert set(dirty["negative_terms"]) >= {"astronomy", "image"}


def test_arxiv_filters_below_threshold_and_annotates():
    feed = """<?xml version="1.0"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>http://arxiv.org/abs/1.1</id>
    <title>Sparse matrix column subsets</title>
    <summary>Combinatorics of matrices.</summary>
    <published>2026-07-01T00:00:00Z</published>
    <category term="math.CO"/>
  </entry>
  <entry>
    <id>http://arxiv.org/abs/2.2</id>
    <title>Momentum in cryptocurrency markets under volatility regimes</title>
    <summary>Trading strategy for bitcoin futures with volatility regime filters.</summary>
    <published>2023-01-01T00:00:00Z</published>
    <category term="q-fin.TR"/>
  </entry>
</feed>"""

    def handler(request: httpx.Request) -> httpx.Response:
        assert "sortBy=relevance" in str(request.url)
        assert "cat%3Aq-fin.%2A" in str(request.url) or "cat:q-fin.*" in str(request.url)
        return httpx.Response(200, text=feed)

    collector = ArxivCollector(client=httpx.Client(transport=httpx.MockTransport(handler)))
    records = collector.search("crypto momentum volatility regime", limit=5)
    # Off-topic paper (newer) is excluded; relevant (older) survives with metadata.
    assert len(records) == 1
    rec = records[0]
    assert rec.external_id == "2.2"
    relevance = rec.extra["relevance"]
    assert relevance["relevance_score"] >= 0.35
    assert relevance["matched_query_terms"]
    assert relevance["ranking_reason"]


# ------------------------------------------------------------------ P3


def test_liquidation_source_without_trigger_is_blocked():
    ext, _ = _pipeline(LIQ_TEXT)
    fid = assess_fidelity(ext, ["Enter when 12-bar z-score > 2.0 over rolling 100 bars"], "generic_signal")
    assert fid["source_archetype"] == "liquidation_reversal"
    assert fid["archetype_fidelity"] == "broken"
    assert "liquidation" in fid["dropped_alpha_triggers"]


def test_funding_source_without_funding_signal_is_blocked():
    ext, _ = _pipeline(FUND_TEXT)
    fid = assess_fidelity(ext, ["Enter long when 30-minute return > 0.5"], "generic_signal")
    assert fid["source_archetype"] == "funding_rate_mean_reversion"
    assert fid["archetype_fidelity"] == "broken"


def test_volatility_source_preserving_both_components_passes():
    ext, hyp = _pipeline(VOL_TEXT)
    assert hyp["source_archetype"] == "volatility_regime_momentum"
    assert hyp["archetype_fidelity"] == "strong"
    assert set(hyp["preserved_alpha_triggers"]) == {"volatility", "momentum"}
    assert hyp["status"] == "candidate"


def test_generic_rewrite_of_liquidation_source_fails_end_to_end(settings, engine):
    """The Batch v1 misroute: liquidation note must not export as z-score fade."""
    from research_intel.collectors.manual_collector import ManualCollector
    from research_intel.extraction.extractor import extract_pending
    from research_intel.hypotheses.generator import generate_pending
    from research_intel.ingestion import ingest_records
    from research_intel.storage.db import session_scope

    llm = MockLLMClient()
    with session_scope(engine) as session:
        records = ManualCollector().search(str(EVAL / "note_liquidation_reversal.md"), limit=1)
        ingest_records(session, settings, ManualCollector(), records)
        extract_pending(session, llm)
        (hyp,) = generate_pending(session, llm)
        # v0.2: routed to the liquidation archetype with the trigger preserved.
        assert hyp.payload["generated_archetype"] == "liquidation_reversal"
        assert hyp.payload["archetype_fidelity"] == "strong"
        assert any("liquidation" in r.lower() for r in hyp.payload["entry_rules"])
        assert hyp.status == "candidate"


def test_fidelity_appears_in_spec_and_hard_filters():
    from research_intel.extraction.schemas import SCORING_DIMENSIONS
    from research_intel.hypotheses.exporter import build_backtest_spec, render_backtest_spec_md
    from research_intel.hypotheses.scorer import apply_hard_filters
    from research_intel.storage.models import StrategyHypothesis

    _, hyp = _pipeline(LIQ_TEXT)
    dims = dict.fromkeys(SCORING_DIMENSIONS, 7.0)
    bad = dict(hyp, archetype_fidelity="broken", dropped_alpha_triggers=["liquidation"])
    excluded, _, flags = apply_hard_filters(bad, dims)
    assert excluded
    assert any(f.startswith("archetype_fidelity_failure") for f in flags)
    # Fidelity is visible in the rendered spec.
    record = StrategyHypothesis(
        hypothesis_id=hyp["hypothesis_id"], extraction_id=1, source_ids=["1"],
        payload=hyp, status="candidate", priority_score=70.0,
    )
    spec = render_backtest_spec_md(build_backtest_spec(record, None))
    assert "Archetype Fidelity" in spec
    assert "Source archetype: liquidation_reversal" in spec


# ------------------------------------------------------------------ P4


def test_vol_note_keeps_source_universe_and_risk_facts():
    _, hyp = _pipeline(VOL_TEXT)
    assert hyp["generated_asset_universe"] == "ETH-USDT perpetual futures"
    assert hyp["asset_universe_provenance"] == "source"
    assert hyp["optional_robustness_universe"] == "BTC/ETH perpetuals"
    risk = hyp["generated_risk_parameters"]
    prov = hyp["risk_parameter_provenance"]
    assert risk["portfolio_vol_target_pct"] == 12 and prov["portfolio_vol_target_pct"] == "source"
    assert risk["monthly_drawdown_halt_pct"] == 8 and prov["monthly_drawdown_halt_pct"] == "source"
    # Defaults must not overwrite source facts: no generic 15% target present.
    assert risk["portfolio_vol_target_pct"] != 15
    rules_text = " ".join(hyp["risk_rules"])
    assert "12% annualized (source)" in rules_text
    assert "8% monthly drawdown (source)" in rules_text
    assert "15% annualized" not in rules_text


def test_funding_note_keeps_universe_leverage_and_kill_switch():
    _, hyp = _pipeline(FUND_TEXT)
    assert hyp["generated_asset_universe"] == "top-10 liquid USDT perpetuals plus matching spot markets"
    risk = hyp["generated_risk_parameters"]
    assert risk["max_leverage_x"] == 2
    assert risk["per_pair_notional_cap_pct"] == 5
    assert risk["basis_kill_switch_stdev_mult"] == 3
    assert risk["carry_cost_clearance_mult"] == 2
    prov = hyp["risk_parameter_provenance"]
    assert all(prov[k] == "source" for k in
               ("max_leverage_x", "per_pair_notional_cap_pct", "basis_kill_switch_stdev_mult"))


def test_liquidation_note_keeps_risk_facts():
    _, hyp = _pipeline(LIQ_TEXT)
    risk = hyp["generated_risk_parameters"]
    assert risk["risk_per_trade_pct"] == 0.5
    assert risk["max_trades_per_day"] == 1
    assert risk["exchange_outage_derisk"] is True
    assert hyp["generated_cost_parameters"]["fee_slippage_bps_per_side"] == 7
    assert hyp["cost_parameter_provenance"]["fee_slippage_bps_per_side"] == "source"
    # Source 0.5% must not be replaced by the generic 1% default.
    assert "0.5% of equity per trade (source)" in " ".join(hyp["risk_rules"])


def test_spec_renders_source_fact_lines():
    from research_intel.hypotheses.exporter import build_backtest_spec, render_backtest_spec_md
    from research_intel.storage.models import StrategyHypothesis

    _, hyp = _pipeline(VOL_TEXT)
    record = StrategyHypothesis(
        hypothesis_id=hyp["hypothesis_id"], extraction_id=1, source_ids=["1"],
        payload=hyp, status="candidate", priority_score=75.0,
    )
    spec = render_backtest_spec_md(build_backtest_spec(record, None))
    assert "Primary source-faithful universe: ETH-USDT perpetual futures" in spec
    assert "Optional robustness universe: BTC/ETH perpetuals" in spec
    assert "Portfolio volatility target: 12% annualized (source)" in spec
    assert "Monthly drawdown halt: 8% (source)" in spec


def test_source_fact_drop_demotes_candidate(settings, engine):
    """If generation drops a source risk fact, the generator demotes it."""
    from sqlalchemy import select

    from research_intel.collectors.manual_collector import ManualCollector
    from research_intel.extraction.extractor import extract_pending
    from research_intel.hypotheses.generator import generate_for_extraction
    from research_intel.ingestion import ingest_records
    from research_intel.storage.db import session_scope
    from research_intel.storage.models import Extraction

    class DroppingLLM(MockLLMClient):
        def generate_hypothesis(self, extraction):
            hyp = super().generate_hypothesis(extraction)
            hyp["generated_risk_parameters"] = {}  # sloppy LLM drops facts
            hyp["risk_parameter_provenance"] = {}
            return hyp

    with session_scope(engine) as session:
        records = ManualCollector().search(str(EVAL / "note_volatility_regime_momentum.md"), limit=1)
        ingest_records(session, settings, ManualCollector(), records)
        extract_pending(session, MockLLMClient())
        extraction = session.scalars(select(Extraction)).first()
        hyp = generate_for_extraction(session, extraction, DroppingLLM())
        assert hyp.status == "review_only"
        assert any("source risk/cost facts dropped" in m
                   for m in hyp.payload["missing_for_backtest"])


# ------------------------------------------------------------------ P5


def test_funding_alias_acceptance():
    template = {"funding_entry_percentile": 90, "funding_exit_percentile": 50,
                "funding_lookback_days": 30, "time_stop_minutes": 4320,
                "fee_slippage_bps_per_side": 7}
    raw = {"trend_strength_entry": 0.9, "trend_strength_exit": 0.5,
           "lookback_days": 30, "time_stop_minutes": 4320,
           "fee_slippage_bps_per_side": 7}
    norm = normalize_strategy_parameters(raw, "funding_rate_mean_reversion", template)
    assert norm.parameters == {
        "funding_entry_percentile": 90, "funding_exit_percentile": 50,
        "funding_lookback_days": 30, "time_stop_minutes": 4320,
        "fee_slippage_bps_per_side": 7,
    }
    assert norm.unmapped == {}
    by_canonical = {d.canonical_key: d for d in norm.details}
    assert by_canonical["funding_entry_percentile"].raw_key == "trend_strength_entry"
    assert by_canonical["funding_entry_percentile"].raw_value == 0.9
    assert 0 < by_canonical["funding_entry_percentile"].confidence <= 1


def test_unmappable_values_are_preserved_not_dropped():
    norm = normalize_strategy_parameters(
        {"mystery_window": 42}, "funding_rate_mean_reversion",
        {"funding_entry_percentile": 90},
    )
    assert norm.parameters == {}
    assert norm.unmapped == {"mystery_window": 42}


def test_unmapped_parameters_appear_in_spec():
    from research_intel.hypotheses.exporter import build_backtest_spec, render_backtest_spec_md
    from research_intel.storage.models import StrategyHypothesis

    _, hyp = _pipeline(VOL_TEXT)
    hyp["unmapped_extracted_parameters"] = {"mystery_window": 42}
    record = StrategyHypothesis(
        hypothesis_id=hyp["hypothesis_id"], extraction_id=1, source_ids=["1"],
        payload=hyp, status="candidate", priority_score=75.0,
    )
    spec = render_backtest_spec_md(build_backtest_spec(record, None))
    assert "mystery_window = 42" in spec
    assert "resolve manually" in spec


# ------------------------------------------------------------------ P6


def test_bad_titles_produce_different_ids():
    llm = MockLLMClient()
    hyps = []
    for sid in ("1", "2"):
        ext = llm.extract_research("[[page:1]]\n\nmomentum trading with volatility regime", {})
        ext["source_id"] = sid
        ext["document_id"] = sid
        hyps.append(llm.generate_hypothesis(ext)["hypothesis_id"])
    assert hyps[0] != hyps[1]


def test_id_collision_is_logged_not_silent(settings, engine, caplog):
    import logging

    from sqlalchemy import select

    from research_intel.collectors.manual_collector import ManualCollector
    from research_intel.extraction.extractor import extract_pending
    from research_intel.hypotheses.generator import generate_for_extraction
    from research_intel.ingestion import ingest_records
    from research_intel.storage import repositories as repo
    from research_intel.storage.db import session_scope
    from research_intel.storage.models import Extraction

    with session_scope(engine) as session:
        records = ManualCollector().search(str(EXAMPLES / "sample_manual_source.md"), limit=1)
        ingest_records(session, settings, ManualCollector(), records)
        extract_pending(session, MockLLMClient())
        extraction = session.scalars(select(Extraction)).first()
        generate_for_extraction(session, extraction, MockLLMClient())
        with caplog.at_level(logging.ERROR):
            result = generate_for_extraction(session, extraction, MockLLMClient())
        assert result is None
        assert any("hypothesis_id_collision" in r.message for r in caplog.records)
        assert any("hypothesis_id_collision" in r.reason for r in repo.list_rejections(session))


def test_extractor_title_fallback_for_page_markers(settings, engine):
    from research_intel.extraction.extractor import _resolve_title
    from research_intel.storage.models import Document, Source

    source = Source(source_type="arxiv", external_id="x", title="Real Paper Title")
    doc = Document(source_id=1, content_hash="deadbeef00", kind="fulltext")
    doc.source = source
    assert _resolve_title("[[page:1]]", doc) == "Real Paper Title"
    assert _resolve_title("<div align=\"center\">", doc) == "Real Paper Title"
    assert _resolve_title("A Genuine Title", doc) == "A Genuine Title"


# ------------------------------------------------------------------ P1


def _provider_client(tmp_path, monkeypatch, handler):
    from research_intel.config import Settings
    from research_intel.llm.provider_client import ProviderLLMClient

    monkeypatch.chdir(tmp_path)
    prompts = tmp_path / "prompts"
    if not prompts.exists():
        prompts.mkdir()
        for name in ("extract_research", "generate_hypothesis", "score_hypothesis",
                     "backtest_spec"):
            (prompts / f"{name}.md").write_text(
                "{{document_text}}{{json_schema}}{{extraction_json}}{{hypothesis_json}}"
            )
    settings = Settings(llm_provider="anthropic", anthropic_api_key="test-key",
                        data_dir=tmp_path / "data")
    return ProviderLLMClient(
        settings,
        client=httpx.Client(base_url="https://api.anthropic.com",
                            transport=httpx.MockTransport(handler)),
        log_dir=tmp_path / "logs",
    )


def _anthropic_body(text: str) -> str:
    return json.dumps({"content": [{"type": "text", "text": text}]})


def test_provider_audit_logs_and_survives_bad_json(tmp_path, monkeypatch):
    from research_intel.llm.provider_client import ProviderResponseError

    responses = iter([
        _anthropic_body('{"ok": 1}'),
        _anthropic_body('{"gen": 2}'),
        _anthropic_body('{"score": 3}'),
        _anthropic_body("NOT JSON AT ALL"),
    ])

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=next(responses))

    client = _provider_client(tmp_path, monkeypatch, handler)
    logs = tmp_path / "logs"

    # extract / generate / score all audit with context ids where available.
    assert client.extract_research("doc", {"type": "object"},
                                   source_id="7", document_id="9") == {"ok": 1}
    assert client.generate_hypothesis({"source_id": "7", "document_id": "9"}) == {"gen": 2}
    assert client.score_hypothesis({"hypothesis_id": "hyp-x"}) == {"score": 3}
    with pytest.raises(ProviderResponseError):
        client.extract_research("doc2", {"type": "object"}, source_id="8", document_id="10")

    calls = [json.loads(line) for line in (logs / "calls.jsonl").read_text().splitlines()]
    assert len(calls) == 4
    for record in calls:
        for field in ("call_id", "kind", "provider", "model", "temperature",
                      "prompt_hash", "source_id", "document_id",
                      "raw_response_path", "parsed_output_path", "error"):
            assert field in record, f"calls.jsonl missing '{field}'"
    extract_ok = calls[0]
    assert extract_ok["source_id"] == "7" and extract_ok["document_id"] == "9"
    assert extract_ok["raw_response_path"].endswith(".txt")
    assert extract_ok["parsed_output_path"].endswith(".json")
    assert json.loads(Path(extract_ok["parsed_output_path"]).read_text()) == {"ok": 1}
    generate_call = calls[1]
    assert generate_call["kind"] == "generate_hypothesis"
    assert generate_call["source_id"] == "7" and generate_call["document_id"] == "9"

    failed = calls[3]
    assert failed["error"] and failed["parsed_output_path"] is None
    assert failed["raw_response_path"].endswith(".txt")
    assert failed["source_id"] == "8"
    errors = [json.loads(line) for line in (logs / "schema_errors.jsonl").read_text().splitlines()]
    assert len(errors) == 1 and errors[0]["parsed_output_path"] is None
    assert len(list((logs / "raw_responses").glob("*.txt"))) == 4
    assert len(list((logs / "parsed_outputs").glob("*.json"))) == 3


def test_provider_failure_does_not_kill_batch(settings, engine, tmp_path, monkeypatch):
    """One invalid provider response is logged per-document; the batch continues."""
    from research_intel.collectors.manual_collector import ManualCollector
    from research_intel.extraction.extractor import extract_pending
    from research_intel.ingestion import ingest_records
    from research_intel.storage import repositories as repo
    from research_intel.storage.db import session_scope

    mock = MockLLMClient()
    calls = {"n": 0}

    class FlakyLLM(MockLLMClient):
        def extract_research(self, text, schema, *, source_id=None, document_id=None):
            calls["n"] += 1
            if calls["n"] == 1:
                from research_intel.llm.provider_client import ProviderResponseError

                raise ProviderResponseError("provider returned invalid JSON (call x)")
            return mock.extract_research(text, schema)

    with session_scope(engine) as session:
        for name in ("sample_manual_source.md", "sample_vague_source.md"):
            records = ManualCollector().search(str(EXAMPLES / name), limit=1)
            ingest_records(session, settings, ManualCollector(), records)
        extractions = extract_pending(session, FlakyLLM())
        # First document failed but was logged; second succeeded.
        assert len(extractions) == 1
        rejections = repo.list_rejections(session)
        assert any("invalid JSON" in r.reason for r in rejections)
