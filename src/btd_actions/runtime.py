"""GitHub Actions runtime: inputs, outputs, step summary and annotations."""

from __future__ import annotations

import json
import os
import sys
import uuid
from collections.abc import Callable, Mapping


class ActionError(Exception):
    """An error the action reports to the user and then fails."""


class Runtime:
    def __init__(self, environ: Mapping[str, str] | None = None) -> None:
        self.env = os.environ if environ is None else environ

    def input(self, name: str, default: str = "", required: bool = False) -> str:
        value = self.env.get("INPUT_" + name.upper().replace("-", "_"), "").strip()
        if value:
            return value
        if required:
            raise ActionError(f"input '{name}' is required")
        return default

    def bool_input(self, name: str, default: bool = False) -> bool:
        value = self.input(name).lower()
        if not value:
            return default
        if value in ("true", "1", "yes"):
            return True
        if value in ("false", "0", "no"):
            return False
        raise ActionError(f"input '{name}' must be true or false, got '{value}'")

    def int_input(self, name: str, default: int) -> int:
        value = self.input(name)
        if not value:
            return default
        try:
            return int(value)
        except ValueError:
            raise ActionError(f"input '{name}' must be an integer, got '{value}'") from None

    def list_input(self, name: str, default: str = "") -> list[str]:
        """Split on newlines and commas."""
        raw = self.input(name, default)
        return [item.strip() for line in raw.splitlines() for item in line.split(",") if item.strip()]

    def event(self) -> dict:
        path = self.env.get("GITHUB_EVENT_PATH", "")
        if not path or not os.path.isfile(path):
            return {}
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)

    def set_output(self, name: str, value: str) -> None:
        path = self.env.get("GITHUB_OUTPUT")
        if not path:
            print(f"[output] {name}={value}")
            return
        delimiter = f"ghadelimiter_{uuid.uuid4().hex}"
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(f"{name}<<{delimiter}\n{value}\n{delimiter}\n")

    def summary(self, markdown: str) -> None:
        path = self.env.get("GITHUB_STEP_SUMMARY")
        if not path:
            print(markdown)
            return
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(markdown.rstrip() + "\n\n")

    def notice(self, message: str) -> None:
        self._annotate("notice", message)

    def warning(self, message: str) -> None:
        self._annotate("warning", message)

    def error(self, message: str) -> None:
        self._annotate("error", message)

    def _annotate(self, level: str, message: str) -> None:
        escaped = message.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
        print(f"::{level}::{escaped}", flush=True)

    def run(self, main: Callable[[Runtime], None]) -> None:
        """Call main and turn an ActionError into an annotation and exit code 1."""
        try:
            main(self)
        except ActionError as exc:
            self.error(str(exc))
            sys.exit(1)
