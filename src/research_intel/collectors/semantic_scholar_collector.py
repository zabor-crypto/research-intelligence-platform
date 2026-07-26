"""Semantic Scholar collector (Graph API; key optional, raises rate limits)."""

from __future__ import annotations

import logging

import httpx

from research_intel.collectors.base import (
    RawDocument,
    RawSourceRecord,
    SourceCollector,
    request_with_retries,
)

logger = logging.getLogger(__name__)

API_BASE = "https://api.semanticscholar.org/graph/v1"
SEARCH_FIELDS = (
    "title,abstract,authors,year,citationCount,externalIds,url,venue,publicationDate"
)


class SemanticScholarCollector(SourceCollector):
    name = "semantic_scholar"

    def __init__(
        self,
        client: httpx.Client | None = None,
        timeout: float = 30.0,
        retries: int = 3,
        api_key: str = "",
    ):
        headers = {"x-api-key": api_key} if api_key else {}
        self._client = client or httpx.Client(
            timeout=timeout, follow_redirects=True, headers=headers
        )
        self._retries = retries

    def search(self, query: str, limit: int, since: str | None = None) -> list[RawSourceRecord]:
        params: dict[str, str | int] = {
            "query": query,
            "limit": min(limit, 100),
            "fields": SEARCH_FIELDS,
        }
        if since:
            params["publicationDateOrYear"] = f"{since}:"
        response = request_with_retries(
            self._client, "GET", f"{API_BASE}/paper/search", retries=self._retries, params=params
        )
        papers = response.json().get("data", [])
        records: list[RawSourceRecord] = []
        for paper in papers[:limit]:
            paper_id = paper.get("paperId")
            if not paper_id:
                continue
            external_ids = paper.get("externalIds") or {}
            records.append(
                RawSourceRecord(
                    source_type="semantic_scholar",
                    external_id=paper_id,
                    title=paper.get("title") or "(untitled)",
                    url=paper.get("url"),
                    authors=[a.get("name", "") for a in paper.get("authors", [])],
                    published_date=paper.get("publicationDate")
                    or (str(paper["year"]) if paper.get("year") else None),
                    abstract=paper.get("abstract"),
                    doi=external_ids.get("DOI"),
                    citation_count=paper.get("citationCount"),
                    extra={"venue": paper.get("venue"), "external_ids": external_ids},
                )
            )
        return records

    def fetch(self, source_id: str) -> RawDocument:
        """Fetch one paper with abstract plus reference/citation titles."""
        response = request_with_retries(
            self._client,
            "GET",
            f"{API_BASE}/paper/{source_id}",
            retries=self._retries,
            params={"fields": "title,abstract,references.title,citations.title"},
        )
        paper = response.json()
        parts = [paper.get("title") or "", paper.get("abstract") or ""]
        return RawDocument(
            source_type="semantic_scholar",
            external_id=source_id,
            content_type="text",
            text="\n\n".join(p for p in parts if p),
            metadata={
                "references": [r.get("title") for r in paper.get("references", [])[:50]],
                "citations": [c.get("title") for c in paper.get("citations", [])[:50]],
            },
        )
