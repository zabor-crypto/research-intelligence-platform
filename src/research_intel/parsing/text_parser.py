"""Plain text / markdown normalization."""

from __future__ import annotations

import re


def extract_plain_text(raw: str) -> str:
    """Normalize whitespace and strip trivial boilerplate from text/markdown."""
    text = raw.replace("\r\n", "\n").replace("\r", "\n")
    # Collapse 3+ blank lines to a single blank line.
    text = re.sub(r"\n{3,}", "\n\n", text)
    # Strip trailing whitespace per line.
    text = "\n".join(line.rstrip() for line in text.split("\n"))
    return text.strip()
