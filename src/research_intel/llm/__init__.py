"""Replaceable LLM layer: mock client for offline runs, provider client for APIs."""

from __future__ import annotations

from research_intel.config import Settings
from research_intel.llm.base import LLMClient


def get_llm_client(settings: Settings) -> LLMClient:
    """Build the configured LLM client. Defaults to the deterministic mock."""
    if settings.llm_provider == "mock":
        from research_intel.llm.mock_client import MockLLMClient

        return MockLLMClient()
    if settings.llm_provider in ("anthropic", "openai"):
        from research_intel.llm.provider_client import ProviderLLMClient

        return ProviderLLMClient(settings)
    if settings.llm_provider == "external_agent":
        raise ExternalAgentModeError(
            "LLM_PROVIDER=external_agent makes no API calls. Use the file-based "
            "workflow instead: `research-intel prepare-agent-batch` to create work "
            "packets, have an external agent (e.g. Claude Code) write the outputs, "
            "then `research-intel import-agent-outputs` / `evaluate-agent-batch`. "
            "See docs/10_external_agent_mode.md."
        )
    raise ValueError(
        f"unknown LLM_PROVIDER '{settings.llm_provider}'; use mock, anthropic, "
        "openai, or external_agent"
    )


class ExternalAgentModeError(RuntimeError):
    """Raised when an API-driven command runs under external_agent mode."""
