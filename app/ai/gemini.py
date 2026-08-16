"""Gemini implementation of the existing LLMProvider abstraction."""

import json
import time
from typing import Any, Callable, Mapping, Optional, Type

from google import genai
from google.genai import types
from pydantic import BaseModel, ValidationError

from app.config.settings import Settings, get_settings
from app.ai.providers import LLMProvider


class GeminiProviderError(RuntimeError):
    """Controlled Gemini request or structured-output failure."""


class GeminiQuotaExceededError(GeminiProviderError):
    """Raised when the Gemini project or daily quota is genuinely exhausted."""


class GeminiProvider(LLMProvider):
    """Make one native structured-output Gemini request per logical analysis."""

    provider_name = "gemini"

    def __init__(
        self,
        settings: Optional[Settings] = None,
        client: Optional[Any] = None,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self.settings = settings or get_settings()
        if not self.settings.gemini_model:
            raise GeminiProviderError("GEMINI_MODEL is not configured")
        self._client = client
        if self._client is None:
            if not self.settings.gemini_api_key:
                raise GeminiProviderError("GEMINI_API_KEY is not configured")
            self._client = genai.Client(api_key=self.settings.gemini_api_key)
        self._sleep = sleep
        self._last_request_at = None

    @property
    def model_name(self):
        return self.settings.gemini_model

    def generate_structured(
        self,
        prompt: str,
        response_model: Type[BaseModel],
        context: Mapping[str, Any],
    ) -> BaseModel:
        """Call Gemini with its native JSON-schema structured-output setting."""
        config = types.GenerateContentConfig(
            response_mime_type="application/json",
            response_json_schema=response_model.model_json_schema(),
        )
        last_error = None
        for attempt in range(max(0, self.settings.llm_max_retries) + 1):
            self._wait_for_rate_limit()
            try:
                response = self._client.models.generate_content(
                    model=self.model_name,
                    contents=prompt,
                    config=config,
                )
                return self._parse_response(response, response_model)
            except (GeminiQuotaExceededError, GeminiProviderError, ValidationError, ValueError, json.JSONDecodeError) as exc:
                raise GeminiProviderError(str(exc))
            except Exception as exc:
                last_error = exc
                if self._is_quota_exhausted(exc):
                    raise GeminiQuotaExceededError(
                        "Gemini quota exhausted: {}. Please verify your API key plan or billing details.".format(exc)
                    )
                if not self._is_transient(exc) or attempt >= self.settings.llm_max_retries:
                    raise GeminiProviderError("Gemini request failed: {}".format(exc))
                # Bounded exponential backoff with jitter
                import random
                jitter = random.uniform(0.1, 1.0)
                backoff = min(30.0, (self.settings.llm_retry_backoff * (2 ** attempt)) + jitter)
                self._sleep(backoff)
        raise GeminiProviderError("Gemini request failed: {}".format(last_error))

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
    def _parse_response(response, response_model):
        parsed = getattr(response, "parsed", None)
        if isinstance(parsed, response_model):
            return parsed
        if isinstance(parsed, dict):
            return response_model.model_validate(parsed)
        text = getattr(response, "text", None)
        if not text:
            raise GeminiProviderError("Gemini returned no structured response")
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            raise GeminiProviderError("Gemini returned invalid JSON: {}".format(exc))
        return response_model.model_validate(payload)

    @staticmethod
    def _is_quota_exhausted(error: Exception) -> bool:
        message = str(error).lower()
        quota_terms = (
            "resource_exhausted",
            "quota exceeded",
            "quotafailure",
            "generaterequestsperday",
            "free_tier_requests",
            "plan and billing details",
        )
        return any(term in message for term in quota_terms)

    @staticmethod
    def _is_transient(error: Exception) -> bool:
        message = str(error).lower()
        # Daily/project quota errors are NOT transient retriable errors
        if GeminiProvider._is_quota_exhausted(error):
            return False
        transient_terms = (
            "timeout",
            "timed out",
            "temporarily unavailable",
            "rate limit",
            "429",
            "500",
            "502",
            "503",
            "504",
            "connection",
            "overloaded",
        )
        return any(term in message for term in transient_terms)

