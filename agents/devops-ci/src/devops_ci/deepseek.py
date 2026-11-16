"""Bounded DeepSeek OpenAI-compatible client with tool-calling support."""

import json
import os
import random
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, ClassVar

import httpx


class DeepSeekError(RuntimeError):
    """A sanitized DeepSeek configuration, transport, or response error."""


@dataclass(frozen=True)
class DeepSeekConfig:
    api_key: str
    base_url: str = "https://api.deepseek.com"
    model: str = "deepseek-chat"
    timeout_seconds: float = 45.0
    max_retries: int = 2

    @classmethod
    def from_env(cls) -> "DeepSeekConfig":
        api_key = os.getenv("DEEPSEEK_API_KEY", "").strip()
        if not api_key:
            raise DeepSeekError("DEEPSEEK_API_KEY is not configured")
        return cls(
            api_key=api_key,
            base_url=os.getenv("DEEPSEEK_BASE_URL", cls.base_url).rstrip("/"),
            model=os.getenv("DEEPSEEK_MODEL", cls.model),
            timeout_seconds=float(os.getenv("DEEPSEEK_TIMEOUT_SECONDS", "45")),
            max_retries=int(os.getenv("DEEPSEEK_MAX_RETRIES", "2")),
        )


@dataclass
class DeepSeekResponse:
    message: dict[str, Any]
    prompt_tokens: int = 0
    completion_tokens: int = 0
    request_id: str | None = None
    tool_calls: list[dict[str, Any]] = field(default_factory=list)

    @property
    def content(self) -> str:
        content = self.message.get("content")
        return content if isinstance(content, str) else ""


class DeepSeekClient:
    RETRYABLE_STATUSES: ClassVar[set[int]] = {408, 429, 500, 502, 503, 504}

    def __init__(
        self,
        config: DeepSeekConfig,
        transport: httpx.BaseTransport | None = None,
        sleeper: Callable[[float], None] = time.sleep,
    ):
        self.config = config
        self.transport = transport
        self.sleeper = sleeper

    def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        json_mode: bool = False,
        max_tokens: int = 2_048,
    ) -> DeepSeekResponse:
        payload: dict[str, Any] = {
            "model": self.config.model,
            "messages": messages,
            "temperature": 0,
            "max_tokens": max_tokens,
            "stream": False,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        headers = {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json",
        }
        attempts = max(0, self.config.max_retries) + 1

        for attempt in range(attempts):
            try:
                with httpx.Client(
                    timeout=self.config.timeout_seconds,
                    transport=self.transport,
                ) as client:
                    response = client.post(
                        f"{self.config.base_url}/chat/completions",
                        headers=headers,
                        json=payload,
                    )
            except httpx.HTTPError as exc:
                if attempt + 1 < attempts:
                    self._backoff(attempt)
                    continue
                raise DeepSeekError(
                    f"DeepSeek request failed: {type(exc).__name__}"
                ) from exc

            if (
                response.status_code in self.RETRYABLE_STATUSES
                and attempt + 1 < attempts
            ):
                self._backoff(attempt)
                continue

            if response.status_code >= 400:
                detail = response.text[:500].replace(self.config.api_key, "[REDACTED]")
                raise DeepSeekError(
                    f"DeepSeek returned HTTP {response.status_code}: {detail}"
                )
            return self._parse_response(response)

        raise DeepSeekError("DeepSeek request exhausted its retry budget")

    def _parse_response(self, response: httpx.Response) -> DeepSeekResponse:
        try:
            body = response.json()
            choice = body["choices"][0]
            message = choice["message"]
            if not isinstance(message, dict):
                raise TypeError("assistant message is not an object")
            usage = body.get("usage") or {}
            tool_calls = message.get("tool_calls") or []
            if not isinstance(tool_calls, list):
                raise TypeError("tool_calls is not a list")
            return DeepSeekResponse(
                message=message,
                prompt_tokens=int(usage.get("prompt_tokens", 0)),
                completion_tokens=int(usage.get("completion_tokens", 0)),
                request_id=response.headers.get("x-request-id"),
                tool_calls=tool_calls,
            )
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise DeepSeekError("DeepSeek returned an invalid response") from exc

    def _backoff(self, attempt: int) -> None:
        self.sleeper((0.25 * (2**attempt)) + random.uniform(0, 0.1))

    def complete_json(self, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        response = self.complete(
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            json_mode=True,
            max_tokens=256,
        )
        try:
            result = json.loads(response.content)
        except (ValueError, TypeError) as exc:
            raise DeepSeekError("DeepSeek returned an invalid JSON response") from exc
        if not isinstance(result, dict):
            raise DeepSeekError("DeepSeek JSON response must be an object")
        return result

    def smoke_test(self) -> dict[str, Any]:
        """Send a tiny synthetic prompt; never include repository logs or code."""
        result = self.complete_json(
            "You perform connectivity checks. Return only a JSON object.",
            'Return exactly {"status":"ok"}.',
        )
        if result.get("status") != "ok":
            raise DeepSeekError("DeepSeek connectivity check returned unexpected JSON")
        return result
