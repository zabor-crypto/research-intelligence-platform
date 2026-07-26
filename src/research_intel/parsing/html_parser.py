"""HTML body-text extraction with boilerplate removal."""

from __future__ import annotations

from bs4 import BeautifulSoup

# Elements that are almost always boilerplate, not research content.
BOILERPLATE_TAGS = ("script", "style", "nav", "header", "footer", "aside", "form", "noscript")


def extract_html_text(raw_html: str) -> str:
    soup = BeautifulSoup(raw_html, "html.parser")
    for tag_name in BOILERPLATE_TAGS:
        for tag in soup.find_all(tag_name):
            tag.decompose()
    body = soup.body or soup
    text = body.get_text(separator="\n")
    lines = [line.strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line)
