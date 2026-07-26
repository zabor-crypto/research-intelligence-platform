"""Application settings loaded from environment / .env."""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All runtime configuration. Every field can be set via env or .env."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Storage
    data_dir: Path = Path("data")
    exports_dir: Path = Path("exports")
    reports_dir: Path = Path("reports")
    db_filename: str = "research_intel.db"

    # LLM
    llm_provider: str = "mock"  # mock | anthropic | openai
    llm_model: str = ""
    llm_temperature: float = 0.0
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"

    # Collectors
    github_token: str = ""
    semantic_scholar_api_key: str = ""
    openalex_mailto: str = ""

    # HTTP
    http_timeout: float = 30.0
    http_retries: int = 3

    @property
    def db_path(self) -> Path:
        return self.data_dir / self.db_filename

    @property
    def raw_dir(self) -> Path:
        return self.data_dir / "raw"

    @property
    def parsed_dir(self) -> Path:
        return self.data_dir / "parsed"

    @property
    def prompts_dir(self) -> Path:
        # prompts ship with the repo; resolve relative to the project root if present,
        # falling back to a "prompts" dir next to the working directory.
        candidate = Path(__file__).resolve().parents[2] / "prompts"
        return candidate if candidate.is_dir() else Path("prompts")

    def ensure_dirs(self) -> None:
        for d in (self.data_dir, self.raw_dir, self.parsed_dir, self.exports_dir, self.reports_dir):
            d.mkdir(parents=True, exist_ok=True)


def get_settings() -> Settings:
    """Build settings freshly so tests and CLI runs pick up env changes."""
    return Settings()
