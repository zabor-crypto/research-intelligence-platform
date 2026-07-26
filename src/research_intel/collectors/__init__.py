"""Source collectors: arXiv, OpenAlex, Semantic Scholar, GitHub, manual files."""

from __future__ import annotations

from research_intel.collectors.base import RawDocument, RawSourceRecord, SourceCollector

__all__ = ["RawDocument", "RawSourceRecord", "SourceCollector", "get_collector"]


def get_collector(name: str, **kwargs):  # noqa: ANN003 - kwargs forwarded per collector
    """Factory used by the CLI. Import lazily to keep startup fast."""
    from research_intel.collectors.arxiv_collector import ArxivCollector
    from research_intel.collectors.github_collector import GitHubCollector
    from research_intel.collectors.manual_collector import ManualCollector
    from research_intel.collectors.openalex_collector import OpenAlexCollector
    from research_intel.collectors.semantic_scholar_collector import SemanticScholarCollector

    registry: dict[str, type[SourceCollector]] = {
        "arxiv": ArxivCollector,
        "openalex": OpenAlexCollector,
        "semantic_scholar": SemanticScholarCollector,
        "github": GitHubCollector,
        "manual": ManualCollector,
    }
    if name not in registry:
        raise ValueError(f"unknown collector '{name}'; available: {sorted(registry)}")
    return registry[name](**kwargs)
