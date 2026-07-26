"""Collectors with mocked HTTP transports — no live internet."""

from __future__ import annotations

import base64
import json
from pathlib import Path

import httpx
import pytest

from research_intel.collectors.arxiv_collector import ArxivCollector
from research_intel.collectors.github_collector import GitHubCollector
from research_intel.collectors.manual_collector import ManualCollector
from research_intel.collectors.openalex_collector import OpenAlexCollector, reconstruct_abstract
from research_intel.collectors.semantic_scholar_collector import SemanticScholarCollector

ARXIV_FEED = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:arxiv="http://arxiv.org/schemas/atom">
  <entry>
    <id>http://arxiv.org/abs/2401.01234v1</id>
    <title>Crypto Momentum  and Volatility Regimes</title>
    <summary>We study momentum in crypto markets.</summary>
    <published>2024-01-05T00:00:00Z</published>
    <author><name>A. Quant</name></author>
    <link title="pdf" href="http://arxiv.org/pdf/2401.01234v1" rel="related"/>
    <category term="q-fin.TR"/>
  </entry>
</feed>
"""


def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_arxiv_search_parses_atom():
    def handler(request: httpx.Request) -> httpx.Response:
        assert "search_query" in str(request.url)
        return httpx.Response(200, text=ARXIV_FEED)

    records = ArxivCollector(client=_client(handler)).search("crypto momentum", limit=5)
    assert len(records) == 1
    rec = records[0]
    assert rec.external_id == "2401.01234v1"
    assert rec.title == "Crypto Momentum and Volatility Regimes"
    assert rec.authors == ["A. Quant"]
    assert rec.published_date == "2024-01-05"
    assert rec.extra["pdf_url"] == "http://arxiv.org/pdf/2401.01234v1"


def test_arxiv_fetch_downloads_pdf():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"%PDF-1.4 fake")

    doc = ArxivCollector(client=_client(handler)).fetch("2401.01234v1")
    assert doc.content_type == "pdf"
    assert doc.binary is not None and doc.binary.startswith(b"%PDF")


def test_openalex_inverted_abstract_reconstruction():
    inv = {"momentum": [1], "Crypto": [0], "works": [2]}
    assert reconstruct_abstract(inv) == "Crypto momentum works"
    assert reconstruct_abstract(None) is None


def test_openalex_search():
    payload = {
        "results": [
            {
                "id": "https://openalex.org/W123",
                "display_name": "Volatility clustering in BTC",
                "publication_date": "2023-06-01",
                "doi": "https://doi.org/10.1000/xyz",
                "cited_by_count": 42,
                "abstract_inverted_index": {"Vol": [0], "clusters": [1]},
                "authorships": [{"author": {"display_name": "B. Author"}}],
                "primary_location": {"source": {"display_name": "J. Fin"}},
                "concepts": [{"display_name": "Volatility"}],
                "open_access": {"oa_url": "http://oa"},
            }
        ]
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    records = OpenAlexCollector(client=_client(handler)).search("volatility", limit=10)
    assert len(records) == 1
    rec = records[0]
    assert rec.external_id == "W123"
    assert rec.doi == "10.1000/xyz"
    assert rec.citation_count == 42
    assert rec.abstract == "Vol clusters"
    assert rec.extra["venue"] == "J. Fin"


def test_semantic_scholar_search():
    payload = {
        "data": [
            {
                "paperId": "abc123",
                "title": "Pairs trading crypto",
                "abstract": "Cointegration analysis.",
                "year": 2022,
                "citationCount": 7,
                "externalIds": {"DOI": "10.2/pairs"},
                "authors": [{"name": "C. Stat"}],
                "url": "https://s2/abc123",
            }
        ]
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    records = SemanticScholarCollector(client=_client(handler)).search("pairs", limit=5)
    assert records[0].external_id == "abc123"
    assert records[0].doi == "10.2/pairs"
    assert records[0].published_date == "2022"


def test_github_search_prioritizes_research_repos():
    payload = {
        "items": [
            {
                "full_name": "someone/webapp-starter",
                "html_url": "https://github.com/someone/webapp-starter",
                "description": "a web app template",
                "stargazers_count": 90000,
                "language": "TypeScript",
                "owner": {"login": "someone"},
                "created_at": "2020-01-01T00:00:00Z",
                "pushed_at": "2024-01-01T00:00:00Z",
            },
            {
                "full_name": "quant/crypto-backtest-research",
                "html_url": "https://github.com/quant/crypto-backtest-research",
                "description": "backtesting research for crypto trading anomalies (paper code)",
                "stargazers_count": 500,
                "language": "Python",
                "owner": {"login": "quant"},
                "created_at": "2021-01-01T00:00:00Z",
                "pushed_at": "2024-06-01T00:00:00Z",
            },
        ]
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    records = GitHubCollector(client=_client(handler)).search("crypto backtest", limit=5)
    assert records[0].external_id == "quant/crypto-backtest-research"
    assert records[0].extra["stars"] == 500


def test_github_fetch_readme():
    content = base64.b64encode(b"# Research Repo\nOrder flow features.").decode()

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/repos/quant/repo/readme"
        return httpx.Response(200, json={"content": content})

    doc = GitHubCollector(client=_client(handler)).fetch("quant/repo")
    assert doc.content_type == "markdown"
    assert "Order flow features" in (doc.text or "")


def test_retry_on_429_then_success(monkeypatch):
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(429, headers={"Retry-After": "0"})
        return httpx.Response(200, json={"results": []})

    monkeypatch.setattr("research_intel.collectors.base.time.sleep", lambda _: None)
    collector = OpenAlexCollector(client=_client(handler))
    assert collector.search("x", limit=1) == []
    assert calls["n"] == 2


def test_manual_collector_reads_files(tmp_path: Path):
    md = tmp_path / "note.md"
    md.write_text("# My Strategy Note\n\nMean reversion after volume spikes.", encoding="utf-8")
    txt = tmp_path / "raw.txt"
    txt.write_text("plain text idea", encoding="utf-8")
    (tmp_path / "ignored.docx").write_text("nope", encoding="utf-8")

    records = ManualCollector().search(str(tmp_path), limit=10)
    assert len(records) == 2
    titles = {r.title for r in records}
    assert "My Strategy Note" in titles
    assert all(r.checksum for r in records)


def test_manual_collector_missing_path():
    with pytest.raises(FileNotFoundError):
        ManualCollector().search("/nonexistent/nowhere", limit=1)


def test_manual_collector_html(tmp_path: Path):
    page = tmp_path / "post.html"
    page.write_text(
        "<html><body><nav>x</nav><h1>Funding Rate Study</h1><p>Perp funding predicts.</p></body></html>",
        encoding="utf-8",
    )
    doc = ManualCollector().fetch(str(page))
    assert "Funding Rate Study" in (doc.text or "")
    assert json.dumps(doc.metadata) is not None
