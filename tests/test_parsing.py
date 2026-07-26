"""Parsing and chunking."""

from __future__ import annotations

from research_intel.parsing.chunker import chunk_document
from research_intel.parsing.html_parser import extract_html_text
from research_intel.parsing.text_parser import extract_plain_text


def test_plain_text_normalization():
    raw = "line one  \r\n\r\n\r\n\r\nline two\r\n"
    assert extract_plain_text(raw) == "line one\n\nline two"


def test_html_boilerplate_removed():
    html = """
    <html><head><style>.x{}</style></head><body>
    <nav>menu</nav><script>alert(1)</script>
    <h1>Momentum Paper</h1><p>Volatility regimes matter.</p>
    <footer>copyright</footer></body></html>
    """
    text = extract_html_text(html)
    assert "Momentum Paper" in text
    assert "Volatility regimes matter." in text
    assert "menu" not in text
    assert "alert" not in text
    assert "copyright" not in text


def test_chunker_splits_by_headings_and_keeps_offsets():
    text = "# Title\n\nintro text\n\n## Methods\n\nmethod body\n\n## Results\n\nresult body\n"
    chunks = chunk_document(text)
    titles = [c["section_title"] for c in chunks]
    assert titles == ["Title", "Methods", "Results"]
    for chunk in chunks:
        assert text[chunk["char_start"] : chunk["char_end"]] == chunk["text"]


def test_chunker_windows_oversized_sections():
    text = "word " * 3000  # no headings, ~15k chars
    chunks = chunk_document(text, max_chars=4000, overlap=200)
    assert len(chunks) >= 4
    assert all(len(c["text"]) <= 4000 for c in chunks)


def test_chunker_carries_page_markers():
    text = "[[page:1]]\n\n# Intro\n\nfirst page text\n\n[[page:2]]\n\n# Methods\n\nsecond page text"
    chunks = chunk_document(text)
    by_title = {c["section_title"]: c["page_number"] for c in chunks}
    assert by_title["Intro"] == 1
    assert by_title["Methods"] == 2


def test_chunker_empty_text():
    assert chunk_document("   \n ") == []
