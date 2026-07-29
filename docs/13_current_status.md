# Current Status and Open Questions

Where the project actually is, how it got here, and what is genuinely unresolved.
Measured results are in [12_research_outcomes.md](12_research_outcomes.md); the design is in
[11_process_architecture.md](11_process_architecture.md).

This is an active research system at iteration 34, not a finished product. The
sections below are written to be falsifiable: each open question states what would
resolve it.

## How the work actually developed

The project did not proceed strategy by strategy. It proceeded by hitting a wall,
refusing to route around it, and building whatever the wall turned out to require.

**Iterations 1–12 — get one idea from a paper to a specification.** Discovery, retrieval,
deconstruction, source-faithful A-spec generation. The output is a specification whose every
claim points back at the passage that justifies it.

**13–19 — make a backtest mean something.** A deterministic engine, a separate execution and
accounting ledger with fixed event ordering, funding accounting with the correct sign, and an
independently written reconciler to check the first implementation rather than trusting it.

**20–29 — carry two strategies all the way through, and close them properly.** Two complete
vertical slices in two different families, both falsified, both terminally closed by
machine-enforced registry rather than by intention. This is also where failure attribution
became structured: not "it did not work", but *which* component failed, with the explicit
non-causes listed and evidenced.

**30–32 — discover that the gates themselves were too weak.** A blind benchmark quantified
the extraction layer for the first time. Then a gated candidate round returned **zero
eligible sources out of twelve** — and the post-mortem found the failures were not about
strategies at all. Candidates had been frozen on broad claims like "we have data for that
venue"; a secondary summary of a paper had passed as an authoritative source; a source whose
README and code specified opposite trade directions had been read confidently in one
direction. The pre-freeze identity, contradiction, dataset-intersection and authority gates
were built in response — all four are published in
[`src/research_process/`](../src/research_process/).

**33–34 — fix the layer underneath everything.** The remaining blocker was that nobody could
prove what the data *meant*. Which edge of the bar a timestamp names, whether an interval is
half-open, when a row first became knowable. So: a federated catalog of the whole data
estate, semantics certification with an explicit evidence hierarchy, controlled
materialization off read-only sources, bounded acquisition from free official publishers,
and immutable content-hashed snapshots.

Each of those five phases exists because the previous one refused to proceed on unsound
ground. That is the shape of the project.

## Where it stands now

| | |
|---|---|
| Released iterations | 34 |
| Logical datasets in the federated catalog | 183 (221 replicas) |
| Datasets carried to `screen_ready` | **1** |
| Datasets validated but semantics-incomplete | 1 |
| Datasets not yet certified | 181 |
| Datasets frozen for backtest | 0 |
| Strategies through a preregistered backtest | 2 (both falsified, both closed) |
| Platform components validated by two vertical slices | 18 |

The honest summary: **the machinery is built and proven end to end; the data estate it runs
on is 1 % certified.** The certification path is now mechanical, but it needs collector
source and official publisher documentation read once per dataset *family* — bounded work per
family rather than per dataset, and not work that can be automated away, because the whole
point is that a human established what a field means from an authoritative statement.

Nothing is frozen for backtest right now, and no strategy work of any kind happened in the
last two iterations. That is deliberate: running screens against uncertified data is exactly
the failure the last four iterations were built to prevent.

## Open questions

### 1. Effective time or publication time?

The one blocking a second certified dataset. A venue's funding timestamps could mark when a
rate becomes *effective* or when it is *published*; the documentation does not say, and the
difference changes what a strategy could have known at decision time. Three routes, all with
a real cost:

- **Resolve from documentation or an authoritative statement** — cheapest, but the search has
  already failed once.
- **Run a forward recorder** to observe publication latency directly. Proposal registered at
  high criticality, awaiting an explicit operator decision. Costs calendar time: it can only
  observe forward, so the answer arrives weeks after the recorder starts.
- **Buy history that includes publication latency.** Cost class currently unknown; this is the
  only route that would settle the past rather than the future.

Until one of them resolves, the dataset stays at `snapshot_validated_but_causal_semantics_incomplete`
and is not readable by a screen. It is not being quietly used in the meantime.

### 2. Does certification scale by family?

The claim is that per-family reading amortizes across the 181 uncertified datasets. That is a
hypothesis about *this* estate, and it will be falsified or confirmed by the next iteration,
which certifies the remaining local OHLCV families using the same evidence path. If families
turn out to be less homogeneous than assumed, the cost model for the whole data layer changes.

### 3. Does the funnel produce anything, given honest gates?

Two of two strategies falsified is a small sample and cannot distinguish between "public-source
strategies rarely survive honest testing" — the expected result — and "these gates are
mis-calibrated and would also reject a real edge". Discriminating between those needs a
positive control: a strategy with a known, documented edge carried through the same pipeline,
to confirm the machinery does not reject it. That control has not been run.

### 4. Where the migration debt sits

Recorded, not hidden: per-strategy corpus IO glue in each handler, a hardcoded corpus-root
path convention, and a snapshot-proxy uniform filter that is a placeholder rather than
exchange-exact. None blocks current work; all three would need resolving before a third
strategy family is added.

## Next iteration

Scope drafted, not yet authorized: certify the remaining local OHLCV families using the
established evidence path, add automatic bounded gap repair against certified snapshots, run
the **first catalog-native gross screens reading only `screen_ready` snapshots**, and resolve
the effective-versus-publication question or accept the forward-recorder proposal.

That last item is the one that decides whether the next iteration is a data iteration or,
for the first time in five, a strategy iteration.

## What would change the assessment

Stated in advance, so it is not rationalized later:

- If per-family certification does not amortize, the data layer is more expensive than the
  design assumes and the catalog-first approach should be reconsidered.
- If the positive control is rejected by the gates, the gates are mis-calibrated and the two
  existing falsifications carry less information than claimed.
- If the forward recorder shows publication latency is negligible and stable, several
  timing-sensitive families become testable that currently are not.
