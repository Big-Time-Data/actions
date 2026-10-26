"""slack-notify: post a message with a colored bar to a Slack incoming webhook."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from .httpclient import HttpClient, HttpError
from .runtime import ActionError, Runtime

# Job and step status values map to Slack attachment colors.
STATUS_COLORS = {
    "success": "good",
    "failure": "danger",
    "cancelled": "warning",
    "skipped": "#9e9e9e",
}
SLACK_COLORS = {"good", "warning", "danger"}
MAX_TEXT = 7_500


@dataclass
class SlackMessage:
    title: str
    text: str
    color: str = "good"
    title_link: str = ""

    @staticmethod
    def resolve_color(value: str) -> str:
        value = value.strip().lower() or "good"
        value = STATUS_COLORS.get(value, value)
        if value in SLACK_COLORS or re.fullmatch(r"#[0-9a-f]{6}", value):
            return value
        raise ActionError(f"color must be good, warning, danger, #rrggbb or a job status, got '{value}'")

    def payload(self) -> dict:
        text = self.text if len(self.text) <= MAX_TEXT else self.text[:MAX_TEXT].rstrip() + "\n…"
        attachment = {
            "color": self.color,
            "fallback": f"{self.title}\n{text}".strip(),
            "text": text,
            "mrkdwn_in": ["text", "pretext"],
        }
        if self.title:
            attachment["title"] = self.title
        if self.title_link:
            attachment["title_link"] = self.title_link
        return {"attachments": [attachment]}


def main(rt: Runtime) -> None:
    text = rt.input("message")
    message_file = rt.input("message_file")
    if message_file:
        path = Path(message_file)
        if not path.is_file():
            raise ActionError(f"message_file '{message_file}' does not exist")
        text = path.read_text(encoding="utf-8").strip()
    msg = SlackMessage(
        title=rt.input("title"),
        text=text,
        color=SlackMessage.resolve_color(rt.input("color")),
        title_link=rt.input("title_link"),
    )
    if not msg.title and not msg.text:
        raise ActionError("set 'title', 'message' or 'message_file'")

    payload = msg.payload()
    webhook = rt.input("webhook")
    if not webhook:
        rt.warning("slack-notify: webhook is empty; message not sent")
    if not webhook or rt.bool_input("dry_run"):
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        rt.set_output("sent", "false")
        return

    try:
        HttpClient(timeout=30).request("POST", webhook, body=payload)
    except (HttpError, OSError) as exc:
        if rt.bool_input("fail_on_error", default=True):
            raise ActionError(f"Slack post failed: {exc}") from None
        rt.warning(f"slack-notify: Slack post failed: {exc}")
        rt.set_output("sent", "false")
        return
    print(f"posted to Slack: {msg.title}")
    rt.set_output("sent", "true")


if __name__ == "__main__":
    Runtime().run(main)
