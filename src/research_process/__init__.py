"""Enforcement primitives from the research-process layer.

These are the gates that decide whether a hypothesis produced by
:mod:`research_intel` is allowed to become a frozen, backtestable candidate — and,
once it has failed, what may never happen to it again.

They are deliberately dependency-free (standard library only) and deliberately
opinionated about failing closed. Each module's docstring names the concrete
failure that motivated it; the design rationale for the whole lifecycle is in
``docs/11_process_architecture.md``.

Not published here: the backtest and execution-accounting engines, the strategy
implementations, the data estate and the source registry these gates were built
around. What is published is the enforcement logic itself, which is generic.
"""

__all__ = ["closure", "pre_freeze", "process_taxonomy"]
