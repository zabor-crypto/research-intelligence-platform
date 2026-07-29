# Research Process Architecture

This document describes the **full research process** this repository belongs to,
including the parts that are not published here. It exists because the public code
alone would misrepresent the project: what is public is the *front half* of the
pipeline — discovery, extraction, triage, specification. The half that decides
whether a hypothesis is true is a separate, larger layer, and its design is the
actual subject of the work.

Nothing in this document requires the private code to be understood. It is a
methodology description, not an implementation manual.

## The problem this architecture solves

An LLM-assisted research pipeline is very good at producing plausible strategy
hypotheses and very bad at stopping. The failure mode is not that the model
hallucinates a signal — it is that a human, holding a negative backtest and a
knob, turns the knob. Every degree of freedom exercised *after* seeing a result
(a shifted start date, a re-tuned threshold, a re-estimated cost model, a quietly
substituted dataset) converts a falsification into a "promising preliminary result".

So the design goal is not accuracy. It is **making the process auditable and
irreversible**: at every point where a human could rescue a dying hypothesis,
there is a machine-checkable artifact that records what was committed to
beforehand, and a gate that fails closed if the commitment is violated.

## Two layers

```
┌─ PUBLIC (this repository) ───────────────────────────────────────────┐
│  collect → parse → extract → hypothesize → score → rank → spec       │
│  arXiv / OpenAlex / Semantic Scholar / GitHub / local documents      │
│  12-dimension scoring, code-enforced non-HFT filters, cost gates     │
│  Output: a backtest specification, not a result                      │
└──────────────────────────────┬───────────────────────────────────────┘
                               │  handoff artifact
┌──────────────────────────────▼─ PRIVATE (research process engine) ───┐
│  admission control → operator scoping → source-faithful A-spec       │
│    → pre-freeze gates → data semantics certification                 │
│    → immutable snapshot materialization → preregistration + freeze   │
│    → controlled backtest → execution accounting                      │
│    → independent reconciliation → adjudication → terminal closure    │
└──────────────────────────────────────────────────────────────────────┘
```

The boundary is deliberate and is not only about secrecy. The public layer is
generic research infrastructure and is useful standalone. The private layer is
coupled to a specific data estate, a specific venue, and a specific strategy
corpus, and publishing it would leak the research content rather than the method.

## Lifecycle stages

### 1. Admission control

Sources do not enter the pipeline because they are interesting. They enter because
they are *scoped*: the venue, market type, instrument class, timeframe, bar
timestamp convention and timezone are resolvable from the source itself. Anything
unresolved goes to an operator completion queue rather than being guessed. A
source with an unresolvable identity is parked, not admitted.

### 2. Source-faithful specification (A-spec)

A specification is derived from the source, and every claim in it carries a
pointer back to the passage that justifies it. The distinction that matters is
between what the source *says* and what the implementer would *prefer* it to say.
Fields the source does not close stay open and are named as open — an A-spec with
unresolved questions is a valid artifact; an A-spec with silently filled gaps is not.

### 3. Pre-freeze gates

Before a candidate may be frozen, exact market identity must be closed with
evidence — not inferred from market convention, not from a similarly-named product
on the target venue, not from what happens to sit in the local data inventory, not
from a publication's performance table, and not from operator preference.

This gate exists because of a real failure: an earlier iteration scored candidates
on broad categories ("BTC data availability", "funding data availability") and
froze three of them on that basis. All three later failed for the same reason —
the *exact* identity did not match. A spot multi-venue strategy had been mapped
onto perpetuals; one source explicitly reported no effect on the target venue; a
third's venue was never resolved at all.

Gate outcomes are structured: `pass`, `blocked_incomplete`, `blocked_contradictory`,
`blocked_timing`.

### 3b. The federated data catalog

Before a dataset can be certified it has to be *findable and identifiable*. The estate is
indexed as a federated catalog — logical datasets and their replicas across local and remote
sections — behind a content-addressed pointer. The catalog carries a semantic hash, and a
changed hash means the estate moved: every data assumption must be revalidated before the
next run, rather than silently inherited.

Clients see explicit states — ready, partial failure, stale, hash mismatch, schema
unsupported, representation mismatch, unavailable — and only the first two are queryable. A
section that failed to probe does not erase the last known-good metadata for that section,
and equally does not let stale metadata authorize a transfer.

### 4. Data semantics certification

A dataset is not usable because it parses. It is usable when the meaning of every
column that a backtest could silently get wrong has been established with evidence:
which edge of the bar a timestamp labels, whether the interval is half-open, when a
row first became *knowable* as opposed to when it is dated.

Each field carries its own confidence rather than inheriting one certificate-wide
optimism, and the certificate is bound to a dataset *version*. When the collector,
parser, manifest or schema changes, the old certificate does not quietly carry over.

A dataset whose bytes are sound but whose causal semantics could not be established
gets an honest terminal state of its own — `snapshot_validated_but_causal_semantics_incomplete`
— instead of being rounded up to "validated".

### 5. Immutable materialization

A backtest that reads a live data directory is not reproducible even if it is
correct today, because that directory will not be the same tomorrow. Materialization
converts "the data as it happens to be right now" into "these exact bytes, hashed,
with these exact semantics, from this exact catalog state".

A mutable source directory can never be promoted to `screen_ready`. This is
structural rather than procedural: promotion requires content hashes over a
finalized destination, and a mutable source has no finalized destination to hash.

Snapshot states: `staging → quarantined | validated → screen_ready → backtest_frozen`.

### 6. Preregistration and freeze

The hypothesis, the market identity, the universe, the interval, the weighting
scheme, the cost model and the acceptance criteria are committed **before** the run,
in a machine-readable frozen manifest. The run then reads the frozen manifest, not
the operator's current intent.

### 7. Controlled backtest and execution accounting

The engine and the accounting ledger are separate. The ledger consumes a scenario,
a sizing contract, a quantity model and a schedule of rebalances, lifecycle exits
and funding events, and produces modeled fills, per-timestamp accounting snapshots,
and an exact reconciliation. Event ordering at each timestamp is fixed and
deterministic:

1. funding on the pre-event positions;
2. lifecycle eligibility transition and mandatory lifecycle exits;
3. rebalance eligibility validation (atomic);
4. rebalance executions;
5. post-event mark and accounting snapshot.

The core hardcodes no fee, no slippage model, no sizing base, no reference time and
no strategy name — all of it arrives through contracts.

### 8. Independent reconciliation

Results are reconciled against an *independently written* reference implementation
(a differential oracle), not merely re-run. The accounting identity
`net = reference_gross − slippage − fees + funding` must hold to numerical
tolerance, and the reconciliation is performed by code that does not share the
engine's assumptions. In the most recent completed adjudication the maximum
absolute residual across production and independent reconciliation was `2.2e-10`.

### 9. Adjudication and failure attribution

A negative result is not filed as "did not work". It is attributed: was the gross
signal absent, or was a real gross edge consumed by costs? Was funding a cost or —
as it turned out in one case — a contributor? Explicit non-causes are recorded with
evidence, so that the same failure is not rediscovered later under a new name.

Scope is normalized in both directions. A falsification establishes that *this
frozen identity, over this corpus and interval, on this venue* had no edge. It
does not establish that the whole strategy family is invalid, and the artifact
says so.

### 10. Terminal closure

A strategy closed for absence of edge is removed from every promotion path
*mechanically*. The closure registry fails closed for candidate, code-generation,
historical-backtest, robustness, optimization, deployment, live-trading and
forward-validation selectors, returning a structured exclusion reason. It admits
the closed strategy only for diagnostic reuse: negative controls, regression
fixtures, failure-pattern examples, benchmarks.

Reopening is not a permission that can be granted. `reopen()` raises.

## Cross-cutting enforcement

| Mechanism | What it prevents |
|---|---|
| Canonical lifecycle state machine | Skipping a gate; prose recommendations acting as authorization; terminal states re-promoting |
| Non-authorizing note vocabulary | "Conditional after data", "gross edge only", "reportedly passed" being read as approval |
| Post-result modification enforcement | Parameters, logic, start date or cost model changing after a result is seen |
| Frozen screen windows | Interval shopping |
| Closure registry | A dead strategy quietly re-entering the funnel |
| Release integrity ledger and manifests | Artifacts of an earlier release being edited retroactively |

Each released iteration emits a process-metrics artifact recording, among other
counters, how many parameters were optimized, how many strategies were rescued,
and how many historical artifacts were modified. The expected value of all three
is zero, and it is checked rather than asserted.

## Release discipline

Every iteration is a release with a prepublication authorization receipt, a
provenance and hash manifest, a release integrity manifest, and a postpublication
completion receipt. Tags are recorded in an immutable committed ledger; a remote
tag that no longer matches its ledger entry is treated as an integrity incident and
the ledger is never auto-repaired.

The governance model states its own residual risk accurately rather than
overstating it: on a single-owner repository without protected branches, a direct
push or a hand-cut tag is **prohibited by policy and designed to be detected** — it
is not *prevented*. Claiming otherwise would be exactly the kind of unearned
assurance the rest of the architecture exists to prevent.

## What of this is published as code

The enforcement primitives above are not only described here — several of them ship in
`src/research_process/`. They are standard-library only, have no dependency on the private
engines, and each carries the concrete failure that motivated it in its module docstring.

| Module | Stage | What it enforces |
|---|---|---|
| [`pre_freeze/identity_gate.py`](../src/research_process/pre_freeze/identity_gate.py) | 3 | Sixteen identity fields, each closed only by the source with evidence; five named grounds that may never close a field; multi-venue constructions that may not collapse onto one venue |
| [`pre_freeze/contradiction.py`](../src/research_process/pre_freeze/contradiction.py) | 3 | A source that disagrees with itself blocks; no silent precedence between prose and code; cosmetic differences are normalised away; an inventory too thin to compare reports *not evaluated* rather than *clean* |
| [`pre_freeze/dataset_gate.py`](../src/research_process/pre_freeze/dataset_gate.py) | 3 | Exact dataset intersection — category claims ("data exists") rejected, causality verified, bounded normalisations enumerated, new acquisition blocked rather than triggered |
| [`pre_freeze/authority_gate.py`](../src/research_process/pre_freeze/authority_gate.py) | 3 | A secondary summary can never be a primary source; content must be strategy-bearing *and* frozen; a role may not claim more authority than it has |
| [`process_taxonomy/backtest_artifact_contract.py`](../src/research_process/process_taxonomy/backtest_artifact_contract.py) | 7 | Event-level equity curve with a full cost decomposition is mandatory; a summary-only result is not a valid backtest |
| [`process_taxonomy/insolvency.py`](../src/research_process/process_taxonomy/insolvency.py) | 9 | Ever-insolvent and terminally-insolvent are separate facts; returns, Sharpe and Sortino through an equity zero-crossing are marked non-interpretable; no liquidation model is introduced after the fact |
| [`process_taxonomy/replay.py`](../src/research_process/process_taxonomy/replay.py) | 9 | Reruns counted by cause, so a determinism reproduction is never reported as zero recomputation and never confused with a rescue |
| [`closure/registry.py`](../src/research_process/closure/registry.py) | 10 | Promotion selectors fail closed for a terminally closed strategy; diagnostic reuse still admitted; `reopen()` raises |

Not published: the backtest and execution-accounting engines, the cross-sectional and pair
strategy implementations, the data estate, the source registry, and the release-governance
machinery that is specific to one repository's operational setup.

## Scale and status

| | Public (this repo) | Private process engine |
|---|---|---|
| Source lines | ~8 500 | ~70 000 |
| Test functions | 264 (324 collected cases) | ~3 500 |
| Released iterations | 2 | 34 |

The private layer is active research and is not scheduled for publication. What is
published here is the part that is generic, self-contained, and useful without it.

See [12_research_outcomes.md](12_research_outcomes.md) for what the process has measured,
built and decided, and [13_current_status.md](13_current_status.md) for where it stands at
iteration 34 and what is still open.
