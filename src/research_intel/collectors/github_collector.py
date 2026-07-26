"""GitHub repository collector for trading/quant research repos."""

from __future__ import annotations

import base64
import logging

import httpx

from research_intel.collectors.base import (
    RawDocument,
    RawSourceRecord,
    SourceCollector,
    request_with_retries,
)

logger = logging.getLogger(__name__)

API_BASE = "https://api.github.com"

# Terms that mark a repo as research-relevant; used to boost ranking client-side.
RESEARCH_TERMS = (
    "paper", "research", "backtest", "anomal", "alpha", "quant", "order book",
    "orderbook", "market", "trading", "crypto", "financial machine learning", "signal",
)


class GitHubCollector(SourceCollector):
    name = "github"

    def __init__(
        self,
        client: httpx.Client | None = None,
        timeout: float = 30.0,
        retries: int = 3,
        token: str = "",
    ):
        headers = {"Accept": "application/vnd.github+json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        self._client = client or httpx.Client(
            timeout=timeout, follow_redirects=True, headers=headers
        )
        self._retries = retries

    def search(self, query: str, limit: int, since: str | None = None) -> list[RawSourceRecord]:
        q = query
        if since:
            q += f" pushed:>={since}"
        response = request_with_retries(
            self._client,
            "GET",
            f"{API_BASE}/search/repositories",
            retries=self._retries,
            params={"q": q, "sort": "stars", "order": "desc", "per_page": min(limit, 100)},
        )
        repos = response.json().get("items", [])
        records: list[RawSourceRecord] = []
        for repo in repos[:limit]:
            full_name = repo.get("full_name")
            if not full_name:
                continue
            description = repo.get("description") or ""
            research_hits = sum(
                1 for term in RESEARCH_TERMS if term in (full_name + " " + description).lower()
            )
            records.append(
                RawSourceRecord(
                    source_type="github",
                    external_id=full_name,
                    title=full_name,
                    url=repo.get("html_url"),
                    authors=[(repo.get("owner") or {}).get("login", "")],
                    published_date=(repo.get("created_at") or "")[:10] or None,
                    abstract=description or None,
                    extra={
                        "stars": repo.get("stargazers_count", 0),
                        "language": repo.get("language"),
                        "last_update": repo.get("pushed_at"),
                        "topics": repo.get("topics", []),
                        "research_term_hits": research_hits,
                    },
                )
            )
        # Prioritize repos that look like research artifacts over generic tooling.
        records.sort(
            key=lambda r: (r.extra.get("research_term_hits", 0), r.extra.get("stars", 0)),
            reverse=True,
        )
        return records

    def fetch(self, source_id: str) -> RawDocument:
        """Fetch the README of a repo ('owner/name')."""
        response = request_with_retries(
            self._client, "GET", f"{API_BASE}/repos/{source_id}/readme", retries=self._retries
        )
        payload = response.json()
        content = payload.get("content", "")
        text = base64.b64decode(content).decode("utf-8", errors="replace") if content else ""
        return RawDocument(
            source_type="github",
            external_id=source_id,
            content_type="markdown",
            text=text,
            suggested_filename=f"github_{source_id.replace('/', '_')}_README.md",
        )
