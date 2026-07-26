"""Real LLM provider client: Anthropic Messages API or any OpenAI-compatible API.

Uses plain httpx so no vendor SDK is required. Prompts live in prompts/*.md.
Requires ANTHROPIC_API_KEY or OPENAI_API_KEY depending on LLM_PROVIDER.

Every call is audited to <data_dir>/provider_logs/: the raw response text,
the parsed JSON (or the parse/validation error), and call metadata (model,
temperature, prompt name + hash). Invalid JSON raises ProviderResponseError,
which pipeline stages catch per-document — one bad response never kills a
batch.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from research_intel.collectors.base import request_with_retries
from research_intel.config import Settings
from research_intel.llm.base import LLMClient
from research_intel.llm.prompt_loader import load_prompt, render_prompt

logger = logging.getLogger(__name__)

MAX_INPUT_CHARS = 60_000  # keep requests bounded; long docs are truncated with a notice

DEFAULT_MODELS = {"anthropic": "claude-sonnet-5", "openai": "gpt-4o"}


class ProviderResponseError(ValueError):
    """The provider returned unparseable or schema-invalid output."""


class ProviderLLMClient(LLMClient):
    def __init__(
        self,
        settings: Settings,
        client: httpx.Client | None = None,
        log_dir: Path | None = None,
    ):
        self._provider = settings.llm_provider
        self._model = settings.llm_model or DEFAULT_MODELS[self._provider]
        self._temperature = settings.llm_temperature
        self._settings = settings
        self._prompts_dir = settings.prompts_dir
        self._log_dir = log_dir if log_dir is not None else settings.data_dir / "provider_logs"
        self._call_counter = 0
        if self._provider == "anthropic":
            if not settings.anthropic_api_key:
                raise ValueError("LLM_PROVIDER=anthropic requires ANTHROPIC_API_KEY")
            self._client = client or httpx.Client(
                base_url="https://api.anthropic.com",
                timeout=120.0,
                headers={
                    "x-api-key": settings.anthropic_api_key,
                    "anthropic-version": "2023-06-01",
                },
            )
        elif self._provider == "openai":
            if not settings.openai_api_key:
                raise ValueError("LLM_PROVIDER=openai requires OPENAI_API_KEY")
            self._client = client or httpx.Client(
                base_url=settings.openai_base_url,
                timeout=120.0,
                headers={"Authorization": f"Bearer {settings.openai_api_key}"},
            )
        else:
            raise ValueError(f"unsupported provider: {self._provider}")

    # ------------------------------------------------------------ interface

    def extract_research(
        self,
        text: str,
        schema: dict[str, Any],
        *,
        source_id: str | None = None,
        document_id: str | None = None,
    ) -> dict[str, Any]:
        prompt = render_prompt(
            load_prompt("extract_research", self._prompts_dir),
            document_text=_truncate(text),
            json_schema=json.dumps(schema, indent=2),
        )
        return self._complete_json(
            prompt, kind="extract_research", source_id=source_id, document_id=document_id
        )

    def generate_hypothesis(self, extraction: dict[str, Any]) -> dict[str, Any]:
        prompt = render_prompt(
            load_prompt("generate_hypothesis", self._prompts_dir),
            extraction_json=json.dumps(extraction, indent=2),
        )
        return self._complete_json(
            prompt, kind="generate_hypothesis",
            source_id=extraction.get("source_id"), document_id=extraction.get("document_id"),
        )

    def score_hypothesis(self, hypothesis: dict[str, Any]) -> dict[str, Any]:
        prompt = render_prompt(
            load_prompt("score_hypothesis", self._prompts_dir),
            hypothesis_json=json.dumps(hypothesis, indent=2),
        )
        return self._complete_json(
            prompt, kind="score_hypothesis", source_id=None,
            document_id=hypothesis.get("hypothesis_id"),
        )

    # ------------------------------------------------------------ audit log

    def _audit(
        self, record: dict[str, Any], raw: str | None, parsed: dict[str, Any] | None
    ) -> str:
        """Persist raw response, parsed output file, and call metadata.

        Layout: raw_responses/<call_id>.txt, parsed_outputs/<call_id>.json
        (successful calls only), calls.jsonl (every call), schema_errors.jsonl
        (failed calls; parsed_output_path is null there).
        """
        self._call_counter += 1
        call_id = f"{record.get('kind', 'call')}_{self._call_counter:05d}"
        record["call_id"] = call_id
        record.setdefault("error", None)
        record["raw_response_path"] = None
        record["parsed_output_path"] = None
        try:
            self._log_dir.mkdir(parents=True, exist_ok=True)
            if raw is not None:
                raw_dir = self._log_dir / "raw_responses"
                raw_dir.mkdir(parents=True, exist_ok=True)
                raw_path = raw_dir / f"{call_id}.txt"
                raw_path.write_text(raw, encoding="utf-8")
                record["raw_response_path"] = str(raw_path)
            if parsed is not None:
                parsed_dir = self._log_dir / "parsed_outputs"
                parsed_dir.mkdir(parents=True, exist_ok=True)
                parsed_path = parsed_dir / f"{call_id}.json"
                parsed_path.write_text(json.dumps(parsed, indent=2), encoding="utf-8")
                record["parsed_output_path"] = str(parsed_path)
            with (self._log_dir / "calls.jsonl").open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(record) + "\n")
            if record.get("error"):
                with (self._log_dir / "schema_errors.jsonl").open("a", encoding="utf-8") as fh:
                    fh.write(json.dumps(record) + "\n")
        except OSError as exc:  # audit failures must not kill the pipeline
            logger.error("provider audit logging failed: %s", exc)
        return call_id

    # ------------------------------------------------------------ transport

    def _complete_json(
        self,
        prompt: str,
        kind: str = "call",
        source_id: str | None = None,
        document_id: str | None = None,
    ) -> dict[str, Any]:
        meta: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "kind": kind,
            "provider": self._provider,
            "model": self._model,
            "temperature": self._temperature,
            "prompt_hash": hashlib.sha1(prompt.encode("utf-8")).hexdigest()[:12],
            "source_id": source_id,
            "document_id": document_id,
        }
        raw = self._complete(prompt)
        try:
            parsed = _parse_json_block(raw)
        except (ValueError, json.JSONDecodeError) as exc:
            meta["error"] = f"json_parse_error: {exc}"
            call_id = self._audit(meta, raw, parsed=None)
            raise ProviderResponseError(
                f"provider returned invalid JSON (call {call_id}): {exc}"
            ) from exc
        self._audit(meta, raw, parsed=parsed)
        return parsed

    def _complete(self, prompt: str) -> str:
        if self._provider == "anthropic":
            response = request_with_retries(
                self._client,
                "POST",
                "/v1/messages",
                retries=self._settings.http_retries,
                json={
                    "model": self._model,
                    "max_tokens": 4096,
                    "temperature": self._temperature,
                    "messages": [{"role": "user", "content": prompt}],
                },
            )
            blocks = response.json().get("content", [])
            return "".join(b.get("text", "") for b in blocks if b.get("type") == "text")
        response = request_with_retries(
            self._client,
            "POST",
            "/chat/completions",
            retries=self._settings.http_retries,
            json={
                "model": self._model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": self._temperature,
            },
        )
        return response.json()["choices"][0]["message"]["content"]


def _truncate(text: str) -> str:
    if len(text) <= MAX_INPUT_CHARS:
        return text
    return text[:MAX_INPUT_CHARS] + "\n\n[TRUNCATED: document exceeded input limit]"


def _parse_json_block(raw: str) -> dict[str, Any]:
    """Parse the first JSON object from a model response (handles ``` fences)."""
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
    candidate = fenced.group(1) if fenced else raw
    start = candidate.find("{")
    end = candidate.rfind("}")
    if start == -1 or end == -1:
        raise ValueError(f"LLM response contained no JSON object: {raw[:200]!r}")
    return json.loads(candidate[start : end + 1])
