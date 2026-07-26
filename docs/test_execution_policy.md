# Test Execution Policy

**Since:** v0.6.10

A phase-scoped test policy so a task does not run the full suite more often than
needed, and never *less* than needed. The goal is to cut redundant time/cost while
keeping the guarantee that every released commit passed the full suite once.

## Phases

### Implementation phase
Run **targeted tests + affected regression tests**.

While iterating on a module, run the new/changed test file(s) plus the regression
tests for anything that imports or is imported by the changed code. Do not run the
whole suite on every edit.

```bash
python -m pytest tests/test_<this_feature>.py -q
python -m pytest tests/test_<affected_area>.py -q
```

### Pre-release phase
Run the **full test suite once** for the final commit.

Immediately before committing the release, run the entire suite against the exact
tree that will be committed. Record the pass/fail totals in the outcome's `tests`
block. This is the single authoritative full-suite result for the release.

```bash
python -m pytest -q
```

### Publish phase
**No full rerun required if the exact commit already passed the full suite.**

If the commit being published is byte-for-byte the one the pre-release full suite
passed, do not rerun it. Instead run git/tag/status verification and, optionally,
fast smoke tests.

```bash
git status --porcelain          # clean tree
git rev-parse HEAD              # exact commit matches the tested commit
git tag --list                  # tag policy: no force-update, no prior-tag mutation
```

## Always
Run **`ruff check` before every commit or release**, regardless of phase.

```bash
ruff check src/ tests/
```

## Rationale

- The **full suite runs exactly once per release** (pre-release phase), not on every
  edit and not again at publish — that is where the token/time savings come from.
- The **guarantee is preserved**: no commit is published unless *that exact commit*
  passed the full suite. Publish-phase git verification proves the commit is the tested
  one.
- Lint is cheap and catches drift early, so it runs every time.

## Related
- [`compact_release_checklist.md`](compact_release_checklist.md) — the test-policy gate references this file.
