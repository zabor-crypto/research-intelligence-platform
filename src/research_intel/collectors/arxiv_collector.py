"""arXiv collector using the public Atom API (no key required)."""

from __future__ import annotations

import logging
import xml.etree.ElementTree as ET

import httpx

from research_intel.collectors.base import (
    RawDocument,
    RawSourceRecord,
    SourceCollector,
    request_with_retries,
)

logger = logging.getLogger(__name__)

ATOM_NS = {"atom": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}
API_URL = "https://export.arxiv.org/api/query"

# Finance-first category scope. stat.ML/cs.LG/econ are admitted only when the
# client-side relevance profile confirms trading/market/crypto content.
FINANCE_CATEGORIES = ("q-fin.*", "stat.ML", "cs.LG", "econ.*")


class ArxivCollector(SourceCollector):
    name = "arxiv"

    def __init__(
        self,
        client: httpx.Client | None = None,
        timeout: float = 30.0,
        retries: int = 3,
        sort_by: str = "relevance",
        min_relevance: float | None = None,
        category_filter: bool = True,
    ):
        from research_intel.collectors.relevance import CRYPTO_STRATEGY_PROFILE

        self._client = client or httpx.Client(timeout=timeout, follow_redirects=True)
        self._retries = retries
        self._sort_by = sort_by  # relevance | submittedDate | lastUpdatedDate
        self._min_relevance = (
            CRYPTO_STRATEGY_PROFILE["min_relevance_score"]
            if min_relevance is None else min_relevance
        )
        self._category_filter = category_filter

    def search(self, query: str, limit: int, since: str | None = None) -> list[RawSourceRecord]:
        from research_intel.collectors.relevance import score_relevance

        search_query = f"all:{query}"
        if self._category_filter:
            cats = " OR ".join(f"cat:{c}" for c in FINANCE_CATEGORIES)
            search_query += f" AND ({cats})"
        if since:
            # arXiv date filter format: YYYYMMDDHHMM
            start = since.replace("-", "") + "0000"
            search_query += f" AND submittedDate:[{start} TO 999912312359]"
        response = request_with_retries(
            self._client,
            "GET",
            API_URL,
            retries=self._retries,
            params={
                "search_query": search_query,
                "start": 0,
                # Over-fetch so client-side filtering can still fill `limit`.
                "max_results": max(limit * 5, 10),
                "sortBy": self._sort_by,
                "sortOrder": "descending",
            },
        )
        records = self._parse_feed(response.text)
        for record in records:
            relevance = score_relevance(record.title, record.abstract, query)
            # stat.ML / cs.LG / econ papers must prove domain relevance.
            categories = record.extra.get("categories") or []
            if not any(str(c).startswith("q-fin") for c in categories if c):
                if not relevance["matched_domain_terms"]:
                    relevance["below_threshold"] = True
                    relevance["ranking_reason"] += "; non-q-fin category without domain terms"
            record.extra["relevance"] = relevance
        kept = [
            r for r in records
            if not r.extra["relevance"]["below_threshold"]
            and r.extra["relevance"]["relevance_score"] >= self._min_relevance
        ]
        dropped = len(records) - len(kept)
        if dropped:
            logger.info("arxiv relevance filter dropped %d/%d results", dropped, len(records))
        kept.sort(key=lambda r: r.extra["relevance"]["relevance_score"], reverse=True)
        return kept[:limit]

    def _parse_feed(self, xml_text: str) -> list[RawSourceRecord]:
        root = ET.fromstring(xml_text)
        records: list[RawSourceRecord] = []
        for entry in root.findall("atom:entry", ATOM_NS):
            raw_id = entry.findtext("atom:id", default="", namespaces=ATOM_NS)
            arxiv_id = raw_id.rsplit("/abs/", 1)[-1] if raw_id else ""
            if not arxiv_id:
                continue
            pdf_url = None
            for link in entry.findall("atom:link", ATOM_NS):
                if link.get("title") == "pdf":
                    pdf_url = link.get("href")
            records.append(
                RawSourceRecord(
                    source_type="arxiv",
                    external_id=arxiv_id,
                    title=" ".join(
                        (entry.findtext("atom:title", default="", namespaces=ATOM_NS) or "").split()
                    ),
                    url=raw_id or None,
                    authors=[
                        a.findtext("atom:name", default="", namespaces=ATOM_NS)
                        for a in entry.findall("atom:author", ATOM_NS)
                    ],
                    published_date=(
                        entry.findtext("atom:published", default="", namespaces=ATOM_NS) or ""
                    )[:10]
                    or None,
                    abstract=" ".join(
                        (entry.findtext("atom:summary", default="", namespaces=ATOM_NS) or "").split()
                    )
                    or None,
                    doi=entry.findtext("arxiv:doi", default=None, namespaces=ATOM_NS),
                    extra={
                        "pdf_url": pdf_url,
                        "categories": [
                            c.get("term") for c in entry.findall("atom:category", ATOM_NS)
                        ],
                    },
                )
            )
        return records

    def fetch(self, source_id: str) -> RawDocument:
        """Download the PDF for an arXiv id (e.g. '2401.12345v1')."""
        pdf_url = f"https://arxiv.org/pdf/{source_id}"
        response = request_with_retries(self._client, "GET", pdf_url, retries=self._retries)
        return RawDocument(
            source_type="arxiv",
            external_id=source_id,
            content_type="pdf",
            binary=response.content,
            suggested_filename=f"arxiv_{source_id.replace('/', '_')}.pdf",
        )
