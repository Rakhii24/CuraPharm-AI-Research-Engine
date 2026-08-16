"""OpenAI-compatible structured LLM provider supporting Groq, Ollama, and OpenAI-format APIs."""

import json
import random
import re
import time
from typing import Any, Callable, Mapping, Optional, Type

import httpx
from pydantic import BaseModel, ValidationError

from app.ai.providers import LLMProvider
from app.config.settings import Settings, get_settings


class OpenAIProviderError(RuntimeError):
    """Controlled failure during OpenAI-compatible LLM execution."""


class OpenAIProviderQuotaError(OpenAIProviderError):
    """Raised when an external API quota is permanently exhausted."""


class OpenAICompatibleProvider(LLMProvider):
    """Call any OpenAI-compatible /v1/chat/completions endpoint with JSON-mode output."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        model_name: Optional[str] = None,
        provider_name: str = "openai_compatible",
        settings: Optional[Settings] = None,
        http_client: Optional[httpx.Client] = None,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self.settings = settings or get_settings()
        self._provider_name = provider_name
        self._base_url = (base_url or "https://api.openai.com/v1").rstrip("/")
        self._api_key = api_key or ""
        self._model_name = model_name or "llama-3.3-70b-versatile"
        self._http_client = http_client or httpx.Client(
            timeout=float(self.settings.llm_timeout),
            trust_env=False,
        )
        self._sleep = sleep
        self._last_request_at = None

    @property
    def provider_name(self) -> str:
        return self._provider_name

    @property
    def model_name(self) -> str:
        return self._model_name

    def close(self):
        self._http_client.close()

    def generate_structured(
        self,
        prompt: str,
        response_model: Type[BaseModel],
        context: Mapping[str, Any],
    ) -> BaseModel:
        """Execute one structured chat completion request and validate against response_model."""
        url = f"{self._base_url}/chat/completions"
        headers = {
            "Content-Type": "application/json",
        }
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        schema_json = json.dumps(response_model.model_json_schema(), indent=2)
        payload = {
            "model": self.model_name,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are a senior pharmaceutical and enterprise AI process intelligence analyst. "
                        "You MUST strictly output valid, raw JSON conforming exactly to this JSON schema:\n"
                        f"{schema_json}\n\n"
                        "Do not wrap output in markdown fences. Do not output preamble, extra fields, or conversational text."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.1,
        }

        last_error = None
        for attempt in range(max(0, self.settings.llm_max_retries) + 1):
            self._wait_for_rate_limit()
            try:
                response = self._http_client.post(url, headers=headers, json=payload)
                if response.status_code == 200:
                    data = response.json()
                    choices = data.get("choices") or []
                    if not choices:
                        raise OpenAIProviderError(f"{self.provider_name} returned no choices in response")
                    content = choices[0].get("message", {}).get("content", "")
                    return self._parse_structured_content(content, response_model)

                # Handle HTTP errors
                error_body = response.text
                if response.status_code in (401, 403):
                    raise OpenAIProviderError(
                        f"{self.provider_name} authentication failed (HTTP {response.status_code}): {error_body}"
                    )
                if response.status_code == 429:
                    if self._is_permanent_quota_error(error_body):
                        raise OpenAIProviderQuotaError(
                            f"{self.provider_name} quota exhausted (HTTP 429): {error_body}"
                        )
                    # Transient rate limit: extract wait duration if available
                    retry_match = re.search(r"try again in ([0-9.]+)s", error_body, re.IGNORECASE)
                    wait_seconds = float(retry_match.group(1)) + 0.5 if retry_match else 4.0
                    last_error = f"HTTP 429 Rate Limit (retrying after {wait_seconds:.1f}s): {error_body}"
                    self._sleep(wait_seconds)
                    continue
                elif response.status_code in (500, 502, 503, 504):
                    last_error = f"HTTP {response.status_code} Server Error: {error_body}"
                else:
                    raise OpenAIProviderError(
                        f"{self.provider_name} request failed with HTTP {response.status_code}: {error_body}"
                    )

            except (OpenAIProviderQuotaError, OpenAIProviderError):
                raise
            except ValidationError as exc:
                raise OpenAIProviderError(f"Schema validation error: {exc}")
            except httpx.HTTPError as exc:
                last_error = f"Network communication error: {exc}"
            except Exception as exc:
                last_error = str(exc)

            if attempt < self.settings.llm_max_retries:
                jitter = random.uniform(0.1, 1.0)
                backoff = min(30.0, (self.settings.llm_retry_backoff * (2 ** attempt)) + jitter)
                self._sleep(backoff)

        raise OpenAIProviderError(f"{self.provider_name} request failed after retries: {last_error}")

    def _wait_for_rate_limit(self):
        interval = max(
            float(self.settings.llm_request_delay),
            60.0 / float(self.settings.llm_rpm_limit)
            if self.settings.llm_rpm_limit > 0
            else 0.0,
        )
        now = time.monotonic()
        if self._last_request_at is not None:
            remaining = interval - (now - self._last_request_at)
            if remaining > 0:
                self._sleep(remaining)
        self._last_request_at = time.monotonic()

    @staticmethod
    def _parse_structured_content(content: str, response_model: Type[BaseModel]) -> BaseModel:
        if not content or not content.strip():
            raise OpenAIProviderError("Empty content returned from LLM provider")
        clean_text = content.strip()
        if clean_text.startswith("```"):
            clean_text = re.sub(r"^```(?:json)?\s*", "", clean_text)
            clean_text = re.sub(r"\s*```$", "", clean_text)
            clean_text = clean_text.strip()
        try:
            parsed = json.loads(clean_text)
            if isinstance(parsed, dict):
                for list_field in (
                    "limitations",
                    "technologies_ai_capabilities",
                    "business_benefits",
                    "risks",
                    "key_activities",
                    "current_challenges",
                    "evidence_references",
                ):
                    val = parsed.get(list_field)
                    if isinstance(val, str):
                        parsed[list_field] = [val] if val.strip() else []
                    elif val is None and list_field == "evidence_references":
                        parsed[list_field] = []
            return response_model.model_validate(parsed)
        except ValidationError as exc:
            raise OpenAIProviderError(f"Structured output validation failed against schema: {exc}")
        except Exception as exc:
            raise OpenAIProviderError(f"Failed to parse JSON response: {exc}")

    @staticmethod
    def _is_permanent_quota_error(body: str) -> bool:
        lower = body.lower()
        if "try again in" in lower or "rate_limit_exceeded" in lower or "tokens per minute" in lower or "requests per minute" in lower or "tpm" in lower or "rpm" in lower:
            return False
        return any(
            term in lower
            for term in (
                "insufficient_quota",
                "exceeded your current quota",
                "account has been deactivated",
                "invalid_api_key",
            )
        )


__all__ = [
    "OpenAICompatibleProvider",
    "OpenAIProviderError",
    "OpenAIProviderQuotaError",
]
