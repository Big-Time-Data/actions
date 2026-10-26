"""HTTP JSON client with retry on rate limits and server errors."""

from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from urllib.parse import urlsplit

RETRY_STATUS = frozenset({408, 425, 429, 500, 502, 503, 504})
USER_AGENT = "Big-Time-Data-actions"


class HttpError(Exception):
    def __init__(self, method: str, url: str, status: int, body: str) -> None:
        # Host only: a webhook URL path is a secret.
        super().__init__(f"{method} {urlsplit(url).netloc}: HTTP {status}: {body[:500]}")
        self.status = status
        self.body = body


class HttpClient:
    def __init__(
        self,
        timeout: float = 60,
        retries: int = 3,
        backoff: float = 2.0,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.timeout = timeout
        self.retries = retries
        self.backoff = backoff
        self.sleep = sleep

    def request(self, method: str, url: str, headers: dict[str, str] | None = None, body: dict | None = None) -> bytes:
        data = None if body is None else json.dumps(body).encode()
        merged = {"User-Agent": USER_AGENT, **(headers or {})}
        if data is not None:
            merged.setdefault("Content-Type", "application/json")

        attempt = 0
        while True:
            req = urllib.request.Request(url, data=data, method=method, headers=merged)
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    return resp.read()
            except urllib.error.HTTPError as exc:
                text = exc.read().decode(errors="replace")
                exc.close()
                if exc.code not in RETRY_STATUS or attempt >= self.retries:
                    raise HttpError(method, url, exc.code, text) from None
                delay = self._retry_after(exc.headers.get("Retry-After")) or self.backoff * 2**attempt
                reason = f"HTTP {exc.code}"
            except (urllib.error.URLError, TimeoutError) as exc:
                if attempt >= self.retries:
                    raise
                delay = self.backoff * 2**attempt
                reason = str(exc)
            attempt += 1
            print(f"{method} {urlsplit(url).netloc}: {reason}; retry {attempt}/{self.retries} in {delay:.0f}s", file=sys.stderr)
            self.sleep(delay)

    def json(self, method: str, url: str, headers: dict[str, str] | None = None, body: dict | None = None) -> dict:
        raw = self.request(method, url, headers, body)
        return json.loads(raw) if raw.strip() else {}

    @staticmethod
    def _retry_after(value: str | None) -> float:
        try:
            return min(float(value or 0), 60.0)
        except ValueError:
            return 0.0
