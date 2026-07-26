"""OpenAlex collector (https://api.openalex.org, no key; mailto for polite pool)."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from research_intel.collectors.base import (
    RawDocument,
    RawSourceRecord,
    SourceCollector,
    request_with_retries,
)

logger = logging.getLogger(__name__)

API_URL = "https://api.openalex.org/works"


def reconstruct_abstract(inverted_index: dict[str, list[int]] | None) -> str | None:
    """OpenAlex stores abstracts as an inverted index; rebuild plain text."""
    if not inverted_index:
        return None
    positions: dict[int, str] = {}
    for word, idxs in inverted_index.items():
        for idx in idxs:
            positions[idx] = word
    return " ".join(positions[i] for i in sorted(positions)) or None


class OpenAlexCollector(SourceCollector):
    name = "openalex"

    def __init__(
        self,
        client: httpx.Client | None = None,
        timeout: float = 30.0,
        retries: int = 3,
        mailto: str = "",
    ):
        self._client = client or httpx.Client(timeout=timeout, follow_redirects=True)
        self._retries = retries
        self._mailto = mailto

    def search(self, query: str, limit: int, since: str | None = None) -> list[RawSourceRecord]:
        params: dict[str, Any] = {"search": query, "per-page": min(limit, 200)}
        if since:
            params["filter"] = f"from_publication_date:{since}"
        if self._mailto:
            params["mailto"] = self._mailto
        response = request_with_retries(
            self._client, "GET", API_URL, retries=self._retries, params=params
        )
        works = response.json().get("results", [])
        records: list[RawSourceRecord] = []
        for work in works[:limit]:
            work_id = (work.get("id") or "").rsplit("/", 1)[-1]
            if not work_id:
                continue
            doi = work.get("doi")
            if doi and doi.startswith("https://doi.org/"):
                doi = doi[len("https://doi.org/"):]
            venue = ((work.get("primary_location") or {}).get("source") or {}).get("display_name")
            records.append(
                RawSourceRecord(
                    source_type="openalex",
                    external_id=work_id,
                    title=work.get("display_name") or "(untitled)",
                    url=work.get("id"),
                    authors=[
                        (a.get("author") or {}).get("display_name", "")
                        for a in work.get("authorships", [])
                    ],
                    published_date=work.get("publication_date"),
                    abstract=reconstruct_abstract(work.get("abstract_inverted_index")),
                    doi=doi,
                    citation_count=work.get("cited_by_count"),
                    extra={
                        "venue": venue,
                        "concepts": [
                            c.get("display_name") for c in work.get("concepts", [])[:10]
                        ],
                        "open_access_url": (work.get("open_access") or {}).get("oa_url"),
                    },
                )
            )
        return records

    def fetch(self, source_id: str) -> RawDocument:
        """Fetch the single work record; OpenAlex has metadata, not fulltext."""
        params = {"mailto": self._mailto} if self._mailto else {}
        response = request_with_retries(
            self._client, "GET", f"{API_URL}/{source_id}", retries=self._retries, params=params
        )
        work = response.json()
        abstract = reconstruct_abstract(work.get("abstract_inverted_index"))
        return RawDocument(
            source_type="openalex",
            external_id=source_id,
            content_type="text",
            text=abstract or work.get("display_name") or "",
            metadata={"title": work.get("display_name")},
        )
