"""LLM client for Research Readiness agents.

Supports:
  - placeholder (offline stub)
  - deepseek / openai (OpenAI-compatible chat completions)

Skills must call only this module — never hardcode vendor SDKs elsewhere.
"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional


def load_dotenv(path: Optional[Path] = None) -> None:
    """Load KEY=VALUE pairs from .env without overriding existing env vars."""
    env_path = path or Path(__file__).resolve().parents[2] / ".env"
    if not env_path.exists():
        return
    raw = env_path.read_text(encoding="utf-8-sig")  # strip BOM if present
    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key, value = key.strip().lstrip("\ufeff"), value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


load_dotenv()


@dataclass
class LLMMessage:
    role: str  # system | user | assistant
    content: str


@dataclass
class LLMResponse:
    text: str
    model: str
    provider: str
    raw: dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None

    @property
    def ok(self) -> bool:
        return not self.error and bool(self.text.strip())


class LLMClient:
    """Thin completion API.

    Env:
      LLM_PROVIDER=placeholder|deepseek|openai|anthropic
      LLM_API_KEY=...           (or DEEPSEEK_API_KEY / OPENAI_API_KEY)
      LLM_BASE_URL=...
      LLM_MODEL=...
    """

    def __init__(
        self,
        *,
        provider: Optional[str] = None,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
    ) -> None:
        self.provider = (provider or os.getenv("LLM_PROVIDER", "placeholder")).lower()
        self.api_key = (
            api_key
            or os.getenv("LLM_API_KEY")
            or os.getenv("DEEPSEEK_API_KEY")
            or os.getenv("OPENAI_API_KEY")
            or os.getenv("ANTHROPIC_API_KEY")
        )
        default_base = {
            "deepseek": os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
            "openai": os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
        }.get(self.provider)
        self.base_url = (base_url or os.getenv("LLM_BASE_URL") or default_base or "").rstrip("/")
        default_model = {
            "deepseek": os.getenv("DEEPSEEK_MODEL", "deepseek-chat"),
            "openai": "gpt-4o-mini",
            "placeholder": "placeholder-model",
        }.get(self.provider, "placeholder-model")
        self.model = model or os.getenv("LLM_MODEL") or default_model

    def complete(
        self,
        messages: list[LLMMessage] | list[dict[str, str]],
        *,
        temperature: float = 0.1,
        max_tokens: int = 2048,
        response_format: Optional[str] = None,
    ) -> LLMResponse:
        normalized = [
            m if isinstance(m, LLMMessage) else LLMMessage(role=m["role"], content=m["content"])
            for m in messages
        ]

        if self.provider == "placeholder":
            return self._placeholder_complete(normalized, response_format=response_format)

        if self.provider in {"deepseek", "openai"}:
            return self._openai_compatible_complete(
                normalized,
                temperature=temperature,
                max_tokens=max_tokens,
                response_format=response_format,
            )

        return LLMResponse(
            text="",
            model=self.model,
            provider=self.provider,
            error=(
                f"LLM provider '{self.provider}' is not implemented yet. "
                "Use placeholder, deepseek, or openai."
            ),
        )

    def complete_json(
        self,
        messages: list[LLMMessage] | list[dict[str, str]],
        *,
        temperature: float = 0.1,
        max_tokens: int = 2048,
    ) -> tuple[Optional[dict[str, Any]], LLMResponse]:
        resp = self.complete(
            messages,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format="json",
        )
        if not resp.ok:
            return None, resp
        try:
            parsed = json.loads(self._strip_fences(resp.text))
            if isinstance(parsed, dict):
                return parsed, resp
            resp.error = "JSON root was not an object"
            return None, resp
        except json.JSONDecodeError:
            extracted = self._extract_json_object(resp.text)
            if extracted is not None:
                return extracted, resp
            resp.error = "JSON parse failed"
            return None, resp

    def _openai_compatible_complete(
        self,
        messages: list[LLMMessage],
        *,
        temperature: float,
        max_tokens: int,
        response_format: Optional[str],
    ) -> LLMResponse:
        if not self.api_key:
            return LLMResponse(
                text="",
                model=self.model,
                provider=self.provider,
                error="Missing API key. Set LLM_API_KEY or DEEPSEEK_API_KEY in .env",
            )
        if not self.base_url:
            return LLMResponse(
                text="",
                model=self.model,
                provider=self.provider,
                error="Missing LLM_BASE_URL",
            )

        # DeepSeek docs use https://api.deepseek.com + /chat/completions
        url = self.base_url
        if url.endswith("/v1"):
            url = f"{url}/chat/completions"
        else:
            url = f"{url}/chat/completions"

        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
        }
        # DeepSeek supports json_object response format on chat models
        if response_format == "json":
            payload["response_format"] = {"type": "json_object"}

        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            return LLMResponse(
                text="",
                model=self.model,
                provider=self.provider,
                raw={"status": exc.code, "body": body[:2000]},
                error=f"HTTP {exc.code}: {body[:500]}",
            )
        except Exception as exc:  # noqa: BLE001
            return LLMResponse(
                text="",
                model=self.model,
                provider=self.provider,
                error=str(exc),
            )

        try:
            text = data["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError):
            return LLMResponse(
                text="",
                model=self.model,
                provider=self.provider,
                raw=data if isinstance(data, dict) else {},
                error="Unexpected response shape from provider",
            )

        return LLMResponse(
            text=text,
            model=data.get("model", self.model),
            provider=self.provider,
            raw=data if isinstance(data, dict) else {},
        )

    @staticmethod
    def _strip_fences(text: str) -> str:
        t = text.strip()
        if t.startswith("```"):
            lines = t.splitlines()
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            t = "\n".join(lines).strip()
        return t

    @classmethod
    def _extract_json_object(cls, text: str) -> Optional[dict[str, Any]]:
        t = cls._strip_fences(text)
        start = t.find("{")
        if start < 0:
            return None
        depth = 0
        for i in range(start, len(t)):
            if t[i] == "{":
                depth += 1
            elif t[i] == "}":
                depth -= 1
                if depth == 0:
                    try:
                        obj = json.loads(t[start : i + 1])
                    except json.JSONDecodeError:
                        return None
                    return obj if isinstance(obj, dict) else None
        return None

    def _placeholder_complete(
        self,
        messages: list[LLMMessage],
        *,
        response_format: Optional[str],
    ) -> LLMResponse:
        user_blob = "\n".join(m.content for m in messages if m.role == "user").lower()
        mentions_irb = any(k in user_blob for k in ("irb", "ethics board", "institutional review"))
        mentions_consent = "consent" in user_blob
        mentions_registry = any(k in user_blob for k in ("nct", "clinicaltrials.gov", "registry"))
        human_subjects = any(k in user_blob for k in ("patient", "participants", "subjects", "hospital"))

        payload = {
            "status": "assessed" if human_subjects else "not_assessed",
            "study_involves_human_subjects": human_subjects,
            "irb_status": "mentioned_unclear" if mentions_irb else ("missing" if human_subjects else "not_applicable"),
            "consent_status": "mentioned_unclear" if mentions_consent else ("missing" if human_subjects else "not_applicable"),
            "data_use_status": "unclear",
            "trial_registry_status": "mentioned" if mentions_registry else ("not_applicable" if not human_subjects else "missing"),
            "evidence_spans": [],
            "notes": [
                "Generated by LLMClient placeholder — replace with real API before production use."
            ],
            "confidence": 0.2,
        }
        return LLMResponse(
            text=json.dumps(payload, indent=2),
            model=self.model,
            provider="placeholder",
            raw={"placeholder": True},
        )


def get_default_client() -> LLMClient:
    load_dotenv()
    return LLMClient()
