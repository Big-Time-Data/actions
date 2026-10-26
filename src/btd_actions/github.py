"""GitHub REST API calls that the actions use."""

from __future__ import annotations

import sys

from .httpclient import HttpClient, HttpError
from .runtime import ActionError


class GitHub:
    def __init__(self, token: str, repo: str, http: HttpClient | None = None, api_url: str = "") -> None:
        if not token:
            raise ActionError("GitHub token is empty")
        if not repo:
            raise ActionError("GitHub repository is empty (GITHUB_REPOSITORY)")
        self.repo = repo
        self.http = http or HttpClient()
        self.api_url = (api_url or "https://api.github.com").rstrip("/")
        self.headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    def call(self, method: str, path: str, body: dict | None = None) -> dict:
        url = f"{self.api_url}/repos/{self.repo}{path}"
        try:
            return self.http.json(method, url, self.headers, body)
        except HttpError as exc:
            raise ActionError(f"GitHub API {method} {path} failed: HTTP {exc.status}: {exc.body[:300]}") from None

    def pull(self, number: int) -> dict:
        return self.call("GET", f"/pulls/{number}")

    def update_pull(self, number: int, fields: dict[str, str]) -> None:
        self.call("PATCH", f"/pulls/{number}", fields)

    def generate_notes(self, tag: str, previous_tag: str, target: str) -> str:
        """GitHub auto notes (merged PRs and new contributors). Empty on failure."""
        body = {"tag_name": tag, "target_commitish": target}
        if previous_tag:
            body["previous_tag_name"] = previous_tag
        try:
            return str(self.call("POST", "/releases/generate-notes", body).get("body") or "").strip()
        except ActionError as exc:
            print(f"generate-notes failed: {exc}", file=sys.stderr)
            return ""
