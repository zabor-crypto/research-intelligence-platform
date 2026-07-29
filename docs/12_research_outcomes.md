# Research Outcomes

What the process described in [11_process_architecture.md](11_process_architecture.md)
has actually produced. These are results from the private research layer, reported
here because a process that only publishes its machinery and never its verdicts is
not auditable.

Source identities are anonymized (`Source A`, `Source B`, `Source C`). They are
public third-party repositories; the strategy families are named because the family
is the methodologically relevant fact, the author is not.

## The funnel

Reconstructed from authoritative registries and immutable release artifacts, not
from copied counts:

| Stage | Count |
|---|---|
| Strategies reaching a preregistered historical backtest | 2 |
| Gross-positive | **0** |
| Net-positive | **0** |
| Surviving cost stress | **0** |
| Terminally closed | 2 |
| Sources closed as non-strategies | 1 |
| Backtest engines implemented | 2 |

Two distinct strategies, in two different families — not two stages of one. Both
are independent negative results.

## Source A — cointegration / pair-convergence family

A two-leg convergence strategy derived from a public research repository.

| | |
|---|---|
| Gross price PnL | **−57.80** |
| Fees | 6 568.27 |
| Slippage | 1 313.65 |
| Funding | +88.33 |
| Trades | 657 |
| Time in market | 90.4% |
| Verdict | `edge_negative_after_costs` → `close_strategy_no_edge` |

The gross signal was already slightly negative before any modeled friction. Near-
continuous flipping at the entry threshold made fees and slippage dominate by two
orders of magnitude over the gross result. One leg was structurally losing
(+1 029 / −1 087 gross split across the two legs).

Recorded for the run: parameters optimized **0**, strategy logic modified **false**,
start date changed **false**, costs changed after results **false**. Nothing was
adjusted after the result was seen.

## Source B — cross-sectional reversal family

An intraday cross-sectional reversal signal applied to a causal dynamic top-30
Binance USDT-M perpetual universe with side-normalized market-neutral target
weights, over `2025-09-01 .. 2026-06-17`. Starting equity 10 000.

Preregistered hypothesis: *this configuration produces positive gross historical
PnL over the frozen interval.* Outcome: **falsified**.

| run | reference gross | slippage | fees | funding | net | terminal equity |
|---|---|---|---|---|---|---|
| R1 primary | −5 402.38 | 942.99 | 2 357.47 | +791.46 | −7 911.38 | 2 088.62 |
| R2 cost stress | −5 402.38 | 2 357.47 | 3 536.21 | +791.46 | −10 504.60 | **−504.60** |
| R3 latency | −4 903.30 | 943.03 | 2 357.57 | +787.43 | −7 416.47 | 2 583.53 |
| R4 snapshot proxy | −5 415.09 | 942.42 | 2 356.05 | +791.46 | −7 922.10 | 2 077.90 |

`net = reference_gross − slippage − fees + funding` and
`terminal_equity = 10 000 + net` hold across all four runs, with a maximum absolute
residual of **2.2e-10** in both production and independent reconciliation.

Primary failure: **`gross_edge_absent`** — reference-price gross PnL is negative in
R1, R3 and R4 alike. Costs *amplified* the loss (~471× turnover); funding, by its
actual sign, **helped** rather than hurt (+791 in R1). Explicit non-causes, each
with evidence: not data incompleteness, not reconciliation failure, not
nondeterminism, not survivorship leakage, not source/derived identity ambiguity,
not quantity-proxy sign instability.

Reported honestly rather than quietly: all four runs touch non-positive equity
intraday, and R2 ends insolvent. The engine continued mechanically because no
liquidation or margin model was preregistered — and none was introduced after the
fact. Post-insolvency daily returns, Sharpe and Sortino are therefore labelled
economically non-interpretable, with the original emitted values preserved for
reproducibility. This does not change the verdict: R1 gross is already negative, so
insolvency does not create the failure.

## Source C

Closed as a **source**, not as a strategy: the repository turned out to be a
randomized demonstration rather than a strategy claim. It never entered the
backtest stage. Recorded so that it is not rediscovered and re-scoped later.

## What these results do and do not establish

They establish that these specific frozen identities — this signal, this universe,
this weighting, this venue, this interval, this cost model — had no edge.

They do **not** establish that cointegration pair trading or cross-sectional
reversal are universally invalid, on other venues, in other periods, or under other
constructions. That boundary is written into the falsification artifacts themselves
rather than left to the reader.

## Why publish zeros

Two strategies entered a preregistered backtest and neither survived. That is the
expected base rate for research derived from public sources, and reporting it is
the point: a research process whose published output is only its successes provides
no evidence that it can produce a negative result at all.

The mechanically enforceable version of that claim is stronger than the rhetorical
one. Both strategies are in the closure registry. Neither can re-enter a promotion
path. `reopen()` raises — see
[`src/research_process/closure/registry.py`](../src/research_process/closure/registry.py)
and its tests in [`tests/test_terminal_closure.py`](../tests/test_terminal_closure.py).

The solvency classification used for R2 above is
[`process_taxonomy/insolvency.py`](../src/research_process/process_taxonomy/insolvency.py):
it separates *ever* non-positive from *terminally* non-positive equity, and marks return
metrics through a zero-crossing as economically non-interpretable rather than quietly
reporting them.
