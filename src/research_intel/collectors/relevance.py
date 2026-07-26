"""Client-side relevance scoring for collector results.

Batch v1 showed date-sorted arXiv results are poisoned by off-topic papers.
Every API record is now scored against a domain profile; below-threshold
records are excluded (or marked, when callers ask to keep them).
"""

from __future__ import annotations

import re
from typing import Any

CRYPTO_STRATEGY_PROFILE: dict[str, Any] = {
    "must_have_any": [
        "crypto", "cryptocurrency", "bitcoin", "ethereum", "digital asset",
        "perpetual", "futures",
    ],
    "should_have_any": [
        "momentum", "volatility", "return", "trading", "strategy", "market",
        "liquidity", "funding", "basis", "order flow",
    ],
    "negative_any": [
        "option pricing only", "quantum", "climate", "image", "medical",
        "biology", "astronomy", "robotics",
    ],
    "min_relevance_score": 0.35,
}

_WORD_RE_CACHE: dict[str, re.Pattern[str]] = {}


def _contains(text: str, term: str) -> bool:
    pattern = _WORD_RE_CACHE.get(term)
    if pattern is None:
        pattern = re.compile(rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])")
        _WORD_RE_CACHE[term] = pattern
    return bool(pattern.search(text))


def score_relevance(
    title: str,
    abstract: str | None,
    query: str,
    profile: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Score a record 0..1 against the domain profile + query terms.

    Returns relevance metadata: relevance_score, matched_query_terms,
    matched_domain_terms, negative_terms, ranking_reason, below_threshold.
    """
    profile = profile or CRYPTO_STRATEGY_PROFILE
    text = f"{title} {abstract or ''}".lower()
    title_lower = title.lower()

    query_terms = [t for t in re.findall(r"[a-z]{3,}", query.lower())]
    matched_query = [t for t in query_terms if _contains(text, t)]
    matched_must = [t for t in profile["must_have_any"] if _contains(text, t)]
    matched_should = [t for t in profile["should_have_any"] if _contains(text, t)]
    negatives = [t for t in profile["negative_any"] if _contains(text, t)]

    score = 0.0
    if matched_must:
        score += 0.4
    if matched_should:
        score += 0.4 * min(1.0, len(matched_should) / 3)
    if query_terms:
        score += 0.2 * (len(matched_query) / len(query_terms))
    # Exact query-term hits in the title are a strong relevance signal.
    title_hits = [t for t in query_terms if _contains(title_lower, t)]
    score += 0.1 * min(1.0, len(title_hits) / 2)
    score -= 0.3 * len(negatives)
    score = max(0.0, min(1.0, round(score, 3)))

    threshold = profile["min_relevance_score"]
    reason_parts = []
    if matched_must:
        reason_parts.append(f"domain terms: {matched_must[:3]}")
    else:
        reason_parts.append("no crypto/market domain term found")
    if matched_should:
        reason_parts.append(f"strategy terms: {matched_should[:3]}")
    if negatives:
        reason_parts.append(f"negative terms: {negatives}")
    reason_parts.append(f"query terms matched {len(matched_query)}/{len(query_terms)}")

    return {
        "relevance_score": score,
        "matched_query_terms": matched_query,
        "matched_domain_terms": matched_must + matched_should,
        "negative_terms": negatives,
        "ranking_reason": "; ".join(reason_parts),
        "below_threshold": score < threshold,
    }
