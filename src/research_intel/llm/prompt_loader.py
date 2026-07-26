"""Load prompt templates from the prompts/ directory (never hard-coded)."""

from __future__ import annotations

from functools import cache
from pathlib import Path

PROMPT_FILES = {
    "extract_research": "extract_research.md",
    "generate_hypothesis": "generate_hypothesis.md",
    "score_hypothesis": "score_hypothesis.md",
    "backtest_spec": "backtest_spec.md",
    "external_agent_packet_instructions": "external_agent_packet_instructions.md",
}


@cache
def load_prompt(name: str, prompts_dir: str | Path | None = None) -> str:
    if name not in PROMPT_FILES:
        raise KeyError(f"unknown prompt '{name}'; available: {sorted(PROMPT_FILES)}")
    if prompts_dir is None:
        prompts_dir = Path(__file__).resolve().parents[3] / "prompts"
    path = Path(prompts_dir) / PROMPT_FILES[name]
    if not path.is_file():
        raise FileNotFoundError(f"prompt file missing: {path}")
    return path.read_text(encoding="utf-8")


def render_prompt(template: str, **variables: str) -> str:
    """Substitute {{variable}} placeholders. Missing variables raise."""
    rendered = template
    for key, value in variables.items():
        rendered = rendered.replace("{{" + key + "}}", value)
    return rendered
