"""Shared collector interface, record models, and HTTP retry helper."""

from __future__ import annotations

import abc
import hashlib
import logging
import time
from typing import Any

import httpx
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

RETRYABLE_STATUS = {429, 500, 502, 503, 504}


class RawSourceRecord(BaseModel):
    """Normalized metadata record returned by every collector's search()."""

    source_type: str
    external_id: str
    title: str
    url: str | None = None
    authors: list[str] = Field(default_factory=list)
    published_date: str | None = None  # ISO date string
    abstract: str | None = None
    doi: str | None = None
    citation_count: int | None = None
    checksum: str | None = None
    extra: dict[str, Any] = Field(default_factory=dict)


class RawDocument(BaseModel):
    """Full document content fetched for a source."""

    source_type: str
    external_id: str
    content_type: str  # pdf|text|markdown|html
    text: str | None = None
    binary: bytes | None = None
    suggested_filename: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class SourceCollector(abc.ABC):
    """All collectors implement search (metadata) and fetch (full content)."""

    name: str = "base"

    @abc.abstractmethod
    def search(self, query: str, limit: int, since: str | None = None) -> list[RawSourceRecord]:
        """Return normalized metadata records for a query."""

    @abc.abstractmethod
    def fetch(self, source_id: str) -> RawDocument:
        """Fetch full content for a single source by its external id."""


def content_checksum(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()


def request_with_retries(
    client: httpx.Client,
    method: str,
    url: str,
    *,
    retries: int = 3,
    backoff: float = 1.5,
    **kwargs: Any,
) -> httpx.Response:
    """HTTP request with exponential backoff on transient failures.

    Honors Retry-After on 429 when present. Raises on final failure —
    callers must not swallow errors silently.
    """
    last_exc: Exception | None = None
    for attempt in range(retries + 1):
        try:
            response = client.request(method, url, **kwargs)
            if response.status_code in RETRYABLE_STATUS and attempt < retries:
                delay = backoff * (2**attempt)
                retry_after = response.headers.get("Retry-After")
                if retry_after and retry_after.isdigit():
                    delay = max(delay, float(retry_after))
                logger.warning(
                    "HTTP %s from %s, retrying in %.1fs (attempt %d/%d)",
                    response.status_code, url, delay, attempt + 1, retries,
                )
                time.sleep(delay)
                continue
            response.raise_for_status()
            return response
        except httpx.TransportError as exc:
            last_exc = exc
            if attempt < retries:
                delay = backoff * (2**attempt)
                logger.warning("transport error on %s: %s; retrying in %.1fs", url, exc, delay)
                time.sleep(delay)
                continue
            raise
    # Only reachable if the loop exhausted without return/raise above.
    raise RuntimeError(f"request to {url} failed after {retries} retries") from last_exc
