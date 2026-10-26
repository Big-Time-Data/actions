"""OpenRouter chat completions with JSON schema output."""

from __future__ import annotations

import json
import re

from .httpclient import HttpClient, HttpError
from .runtime import ActionError

DEFAULT_MODEL = "anthropic/claude-haiku-5.5"
ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"
REFERER = "https://github.com/Big-Time-Data/actions"


class OpenRouterError(ActionError):
    pass


class OpenRouter:
    """models[0] is the main model; OpenRouter tries the others in order when it fails."""

    def __init__(self, api_key: str, models: list[str], http: HttpClient | None = None, endpoint: str = ENDPOINT) -> None:
        if not api_key:
            raise OpenRouterError("OpenRouter API key is empty")
        self.api_key = api_key
        self.models = models or [DEFAULT_MODEL]
        self.http = http or HttpClient(timeout=180)
        self.endpoint = endpoint

    def complete_json(self, *, system: str, user: str, name: str, schema: dict, max_tokens: int = 4000) -> dict:
        body: dict = {
            "model": self.models[0],
            "max_tokens": max_tokens,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": name, "strict": True, "schema": schema},
            },
            "provider": {"require_parameters": True},
        }
        if len(self.models) > 1:
            body["models"] = self.models

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "HTTP-Referer": REFERER,
            "X-Title": "Big-Time-Data actions",
        }
        try:
            resp = self.http.json("POST", self.endpoint, headers, body)
        except HttpError as exc:
            raise OpenRouterError(f"OpenRouter request failed: HTTP {exc.status}: {exc.body[:300]}") from None
        except OSError as exc:
            raise OpenRouterError(f"OpenRouter request failed: {exc}") from None

        if "error" in resp:
            raise OpenRouterError(f"OpenRouter error: {resp['error']}")
        try:
            choice = resp["choices"][0]
        except (KeyError, IndexError):
            raise OpenRouterError(f"OpenRouter returned no choices: {str(resp)[:300]}") from None

        usage = resp.get("usage") or {}
        print(
            f"openrouter: model={resp.get('model')} prompt_tokens={usage.get('prompt_tokens')} "
            f"completion_tokens={usage.get('completion_tokens')} finish={choice.get('finish_reason')}"
        )
        if choice.get("finish_reason") not in ("stop", "end_turn"):
            raise OpenRouterError(f"OpenRouter finish reason is {choice.get('finish_reason')}, not stop")
        return self.parse_json((choice.get("message") or {}).get("content") or "")

    @staticmethod
    def parse_json(text: str) -> dict:
        """Accept plain JSON, or JSON in a markdown fence or prose."""
        raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError:
            start, end = raw.find("{"), raw.rfind("}")
            try:
                obj = json.loads(raw[start : end + 1]) if 0 <= start < end else None
            except json.JSONDecodeError:
                obj = None
        if not isinstance(obj, dict):
            raise OpenRouterError(f"OpenRouter returned no JSON object: {text[:300]}")
        return obj
