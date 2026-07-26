"""Shared fixtures: temp workspace, engine, sample texts."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import Engine

from research_intel.config import Settings
from research_intel.storage.db import get_engine
from research_intel.storage.migrations import migrate

PROJECT_ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = PROJECT_ROOT / "examples"

MOMENTUM_TEXT = (EXAMPLES / "sample_manual_source.md").read_text(encoding="utf-8")
HFT_TEXT = (EXAMPLES / "sample_hft_source.md").read_text(encoding="utf-8")


@pytest.fixture()
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Isolated working directory so data/exports/reports land in tmp."""
    monkeypatch.chdir(tmp_path)
    # Keep provider env from leaking into tests.
    for var in ("LLM_PROVIDER", "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GITHUB_TOKEN"):
        monkeypatch.delenv(var, raising=False)
    return tmp_path


@pytest.fixture()
def settings(workspace: Path) -> Settings:
    s = Settings()
    s.ensure_dirs()
    return s


@pytest.fixture()
def engine(settings: Settings) -> Engine:
    eng = get_engine(settings)
    migrate(eng)
    return eng

