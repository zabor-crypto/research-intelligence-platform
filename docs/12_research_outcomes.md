# Results

What the system described in [11_process_architecture.md](11_process_architecture.md) has
measured, built and decided across 34 released iterations. Current status and open
questions are in [13_current_status.md](13_current_status.md).

Every number below comes from a frozen release artifact. Where a metric has more than
one population, the population is named — reporting a regression-set score as though it
were a blind-set score is exactly the error this project spends its effort preventing.

Source identities are anonymized (`Source A`, `Source B`, `Source C`) where a verdict
attaches to a third party's public repository.

## 1. How good is the AI-assisted extraction?

The pipeline's first job is to read external research and produce a machine-checkable
specification. That is an empirical claim, so it is benchmarked rather than asserted.

**Blind scope — 13 documents, 134 explicit fields, no regression items:**

| Layer | Metric | Value |
|---|---|---|
| **Retrieval** | exact canonical hit@1 | 0.692 |
| | exact canonical hit@3 / hit@5 | 0.846 |
| | authoritative-equivalent hit@5 | **1.000** |
| | mean reciprocal rank | 1.000 |
| **Deconstruction** | explicit-field recall | 0.818 |
| | explicit-field precision | 0.903 |
| | unsupported-assertion rate | **0.021** |
| | incorrect-closure rate | 0.034 |
| | correct-unresolved rate | 0.844 |
| **Evidence** | evidence-link presence | **134/134 = 1.000** |
| | evidence-link validity | 131/134 = 0.978 |
| | evidence-span exactness | 101/128 = 0.789 |
| | unsupported evidence links | **0** |
| **Severity** | critical / major / minor | **0** / 2 / 41 |

**Full scope — 15 documents including regression items** (reported separately because it
is a different population): A-spec required-field accuracy 0.788, causal-timing accuracy
**0.926**, identity-closure accuracy **0.933**, source-faithful labelling accuracy 0.789,
unresolved-field blocking accuracy 0.861, unsupported-default rate 0.091, evidence-provenance
completeness **1.000**; end-to-end top-1-retrieval-then-full-chain success **0.889**.

The metrics worth reading twice are the negative ones. `unsupported_assertion_rate` 0.021 and
`unsupported_evidence_link_count` 0 say the model almost never invents a claim the source does
not make. `correct_unresolved_rate` 0.844 says that when a source genuinely does not close a
field, the pipeline usually says so instead of filling the gap — which is the behaviour that
makes the downstream gates meaningful. The leading error classes are named too:
over-blocking an explicit field, failing to block a missing one, unsupported invention,
wrong formula, source/derived identity conflation, and undetected contradiction.

## 2. What has been built

Eighteen components, validated by two complete vertical slices — a source carried end to
end from discovery through preregistered backtest to terminal closure, twice, in two
different strategy families.

**Generic platform (14):** batch kernel · protected-branch guard · single-writer lock ·
artifact writer · provenance registry · source-evidence recovery · A-spec generation ·
readiness adjudication · official market-data acquisition · execution/accounting engine ·
funding accounting · independent ledger reconciler · phase-aware release receipts ·
terminal-closure enforcement.

**Strategy-family specific (4):** cross-sectional engine · pair engine · lifecycle
reconstruction · dynamic universe membership.

The split is tracked deliberately: a component in the first list is reusable for the next
strategy family, one in the second is not. Known migration debt is recorded rather than
hidden — unify the corpus price/funding loaders across handlers, factor the engine→ledger
schedule builder into a shared adapter, promote the closure registry into the standing
strategy registry.

## 3. Selection discipline

The candidate pool for the most recent gated round: **12 sources across 10 economic
families** — carry/basis, funding carry, momentum, intraday time-series momentum, intraday
periodic microstructure, intraday calendar seasonality, daily extrema timing, ML forecast
timing, reinforcement-learning pairs, evolutionary parameter search. Nine new discoveries,
three from backlog.

Two flags on that round's manifest carry most of the methodological weight:

- `selection_used_performance_fields: false` — candidate selection never looked at the
  performance a source *reported*. A paper claiming a 3.0 Sharpe gets no advantage over one
  claiming nothing, because the reported number is not evidence.
- `weighted_score_used_to_compensate_failed_hard_gate: false` — no aggregate score was
  allowed to rescue a source that failed a hard gate. The gates run in a fixed order:
  authoritative source availability → source-internal contradiction audit → exact market
  identity → critical timestamp semantics → current market relevance → exact dataset
  intersection → recent causal coverage → screen complexity → candidate eligibility.

**Eligible after all nine gates that round: zero.** That is the system functioning, not
failing. It also produced the diagnosis that redirected the next four iterations: the
binding constraint was never the strategies, it was that the data underneath them had
never been proven to mean what everyone assumed it meant.

## 4. The data layer

That diagnosis produced the current capability set.

A **federated data catalog** of **183 logical datasets across 221 replicas**, with a
content-addressed pointer: the catalog carries a semantic hash, and a changed hash means
the estate moved and every data assumption must be revalidated before use. Clients have
explicit states — ready, partial failure, stale, hash mismatch, schema unsupported,
representation mismatch, unavailable — and only the first two are queryable.

On top of it, the path from a catalogued dataset to something a backtest may legitimately
read: **semantics certification** with an explicit evidence hierarchy, **targeted-deep
verification**, **controlled materialization** off read-only sources, **bounded acquisition**
from free official publishers with publisher-checksum verification, and **immutable
content-hashed snapshots**.

First dataset carried the whole way: **401 760 rows, 109 partitions**, covering
2025-12-12 → 2026-05-18, `cross_evidence_verified` certificate, no material contradiction,
passes the exact causal gate, `screen_ready`, content hash recorded.

### The second one deliberately did not pass

A funding dataset from a second venue was materialized successfully — 527 568 rows, bytes
verified, zero quality failures — and then **stopped one step short of `screen_ready`**.

The venue's documentation does not state whether a funding timestamp marks the moment the
rate becomes *effective* or the moment it is *published*. Those are different instants, and
the difference moves what a strategy could have known at decision time. No local evidence
can settle it, so the certificate stayed at `empirical_only` confidence on five fields
(timestamp role, interval-inclusion convention, earliest causal availability, decision-time
constraint) and the snapshot took the honest terminal state
`snapshot_validated_but_causal_semantics_incomplete`.

The gate held rather than being weakened to produce a second green result. This is the most
representative single outcome in the project: it would have cost nothing to relax one
confidence threshold and report two certified datasets instead of one.

## 5. Strategy outcomes so far

Two strategies have been carried to a preregistered historical backtest. Both were falsified.

| Stage | Count |
|---|---|
| Reaching a preregistered historical backtest | 2 |
| Gross-positive | 0 |
| Net-positive | 0 |
| Surviving cost stress | 0 |
| Terminally closed | 2 |
| Sources closed as non-strategies | 1 |

**Source A — cointegration / pair-convergence.** Gross price PnL **−57.80** before any
modeled friction; fees 6 568.27; slippage 1 313.65; funding +88.33; 657 trades; 90.4% time
in market; one leg structurally losing (+1 029 / −1 087 across the two legs). Verdict
`edge_negative_after_costs`. Near-continuous flipping at the entry threshold made costs
dominate the gross result by two orders of magnitude. Recorded for the run: parameters
optimized **0**, strategy logic modified **false**, start date changed **false**, costs
changed after results **false**.

**Source B — cross-sectional reversal**, causal dynamic top-30 USDT-M perpetual universe,
side-normalized market-neutral weights, 2025-09-01 → 2026-06-17, starting equity 10 000.
Preregistered hypothesis: positive gross historical PnL over the frozen interval. Outcome
**falsified**.

| run | reference gross | slippage | fees | funding | net | terminal equity |
|---|---|---|---|---|---|---|
| R1 primary | −5 402.38 | 942.99 | 2 357.47 | +791.46 | −7 911.38 | 2 088.62 |
| R2 cost stress | −5 402.38 | 2 357.47 | 3 536.21 | +791.46 | −10 504.60 | **−504.60** |
| R3 latency | −4 903.30 | 943.03 | 2 357.57 | +787.43 | −7 416.47 | 2 583.53 |
| R4 snapshot proxy | −5 415.09 | 942.42 | 2 356.05 | +791.46 | −7 922.10 | 2 077.90 |

`net = reference_gross − slippage − fees + funding` and `terminal_equity = 10 000 + net`
hold across all four runs, maximum absolute residual **2.2e-10** in both production and
independent reconciliation.

Primary failure `gross_edge_absent` — reference-price gross PnL is negative in R1, R3 and R4
alike. Costs *amplified* the loss (~471× turnover); funding, by its actual sign, **helped**
(+791 in R1). Explicit non-causes, each with evidence: not data incompleteness, not
reconciliation failure, not nondeterminism, not survivorship leakage, not source/derived
identity ambiguity, not quantity-proxy sign instability.

Reported rather than dropped: all four runs touch non-positive equity intraday and R2 ends
insolvent. The engine continued mechanically because no liquidation or margin model was
preregistered — and none was introduced afterwards. Post-insolvency daily returns, Sharpe
and Sortino are therefore labelled economically non-interpretable, with the original values
preserved. The verdict is unchanged either way: R1 gross is already negative, so insolvency
does not create the failure.

**Source C** was closed as a *source*, not a strategy: the repository turned out to be a
randomized demonstration rather than a strategy claim. It never entered the backtest stage.

### What these establish

That these specific frozen identities — this signal, this universe, this weighting, this
venue, this interval, this cost model — had no edge. They do **not** establish that
cointegration pair trading or cross-sectional reversal are universally invalid. That
boundary is written into the falsification artifacts themselves.

Two out of two negative is close to the expected base rate for strategies derived from
public sources, and it is reported for a specific reason: a research process whose published output
is only its successes provides no evidence that it can produce a negative result at all.
Both strategies are in the closure registry, neither can re-enter a promotion path, and
`reopen()` raises — see
[`src/research_process/closure/registry.py`](../src/research_process/closure/registry.py).

The solvency classification used above is
[`process_taxonomy/insolvency.py`](../src/research_process/process_taxonomy/insolvency.py).

## 6. Process integrity

Each release emits a process-metrics artifact with counters whose expected value is zero and
which are checked rather than asserted: parameters optimized, strategies rescued, historical
artifacts modified, rejected sources executed, results-conditioned reruns. Across the
completed strategy work these stand at zero — including in the releases that produced the
negative results, which is where the temptation to move one exists.
