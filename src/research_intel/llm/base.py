"""Abstract LLM client interface. All business logic depends only on this."""

from __future__ import annotations

import abc
from typing import Any


class LLMClient(abc.ABC):
    """Vendor-neutral LLM operations used by the pipeline."""

    @abc.abstractmethod
    def extract_research(
        self,
        text: str,
        schema: dict[str, Any],
        *,
        source_id: str | None = None,
        document_id: str | None = None,
    ) -> dict[str, Any]:
        """Extract structured trading-relevant fields from document text.

        source_id/document_id are optional call context used for provider
        audit logging; implementations may ignore them.
        """

    @abc.abstractmethod
    def generate_hypothesis(self, extraction: dict[str, Any]) -> dict[str, Any]:
        """Turn an extraction into a crypto-testable strategy hypothesis."""

    @abc.abstractmethod
    def score_hypothesis(self, hypothesis: dict[str, Any]) -> dict[str, Any]:
        """Return per-dimension 0-10 scores for a hypothesis."""
