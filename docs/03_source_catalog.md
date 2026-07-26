# Source Catalog

## Supported (MVP)

### arXiv (`--source arxiv`)
- Access: public Atom API (`export.arxiv.org/api/query`), no key.
- Rate limits: ~1 request / 3s recommended; retries with backoff built in.
- Usefulness: high — q-fin, stat.ML, econ papers; PDFs downloadable
  (`--fetch-fulltext`).
- Limitations: abstract search quality is moderate; no citation counts.

### OpenAlex (`--source openalex`)
- Access: public REST API, no key; set `OPENALEX_MAILTO` for the polite pool.
- Rate limits: 10 req/s, 100k/day (polite pool).
- Usefulness: high — broadest coverage, citation counts, concepts, venues;
  abstracts arrive as inverted indexes (reconstructed automatically).
- Limitations: no fulltext; some abstracts missing.

### Semantic Scholar (`--source semantic_scholar`)
- Access: Graph API; free key (`SEMANTIC_SCHOLAR_API_KEY`) raises limits.
- Rate limits: 1 req/s unauthenticated (shared pool), higher with key.
- Usefulness: high — good relevance ranking, citation graph,
  references/citations on fetch.
- Limitations: abstracts sometimes withheld by publisher agreements.

### GitHub (`--source github`)
- Access: REST search API; `GITHUB_TOKEN` recommended (10 → 30 req/min search).
- Usefulness: medium-high — paper implementations, backtesting frameworks,
  crypto quant research repos. READMEs fetched with `--fetch-fulltext`.
  Results are re-ranked by research-term hits, then stars.
- Limitations: search quality varies; READMEs may lack methodology detail.

### Manual (`ingest --path`)
- Access: local filesystem; `.pdf`, `.txt`, `.md`, `.html`.
- Usefulness: highest signal — hand-picked papers, blog exports, notes.
- Limitations: scanned PDFs without a text layer are rejected (no OCR in MVP).

## Future (post-MVP)

| Source | Access | Notes |
|---|---|---|
| Crossref | public REST API | DOI metadata enrichment, venue quality signals |
| SSRN | scraping/metadata only | strong quant-finance preprints; no clean API — respect ToS |
| RSS research blogs | feedparser | practitioner research (e.g. quant blogs); high transferability |
| Conference proceedings | varies (ACM/IEEE/NeurIPS) | financial ML workshops |
| Patents | Google Patents/EPO APIs | occasionally useful for microstructure mechanisms |

## Starter query catalog

Crypto Trend / Momentum
```text
crypto momentum strategy volatility regime
time series momentum cryptocurrency
cross sectional momentum crypto assets
trend following digital assets
```

Liquidation / Capitulation
```text
liquidation cascades cryptocurrency
forced selling crypto market microstructure
capitulation reversal trading
extreme volume reversal crypto
```

Volume and Flow
```text
volume imbalance return predictability
order flow imbalance cryptocurrency
trade imbalance price impact crypto
volume shock reversal momentum
```

Volatility and Regimes
```text
volatility clustering crypto returns
regime switching trading strategy
realized volatility forecasting cryptocurrency
volatility breakout strategy
```

Statistical Arbitrage
```text
statistical arbitrage cryptocurrency
pairs trading crypto
cointegration digital assets
cross asset mean reversion crypto
```

Funding / Basis
```text
funding rate predictability perpetual futures
crypto basis trading
perpetual swap funding arbitrage
futures basis crypto market
```

Non-HFT Market Making
```text
inventory based market making
market making without low latency
optimal spread inventory risk
prediction market market making
automated market making risk control
```

Portfolio / Risk
```text
portfolio optimization crypto assets
risk parity cryptocurrency
drawdown control trading strategy
volatility targeting crypto
```
