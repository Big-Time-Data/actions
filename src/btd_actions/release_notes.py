"""release-notes: GitHub release notes and a Slack summary for a tag."""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path

from .git import Git
from .github import GitHub
from .openrouter import OpenRouter, OpenRouterError
from .runtime import ActionError, Runtime
from .version import Version

SYSTEM = """You write release notes{product}.
Never invent changes. Summarize only what is in the input.
Skip CI, chore, test, merge and dependency-only changes unless a user sees them.
Keep PR numbers like (#28) when present.

github_notes: markdown with these "###" sections in order: Highlights, Features, Fixes, Breaking Changes.
Omit empty sections. Do not add a top heading, download links or install steps.

slack_summary: {slack_lines} short lines for Slack mrkdwn, most important first.
Each line is one change. Use *bold* (one asterisk) and backticks for commands, flags and config keys.
Do not start lines with a bullet character. No headings and no links.
{instructions}"""

SCHEMA = {
    "type": "object",
    "properties": {
        "github_notes": {"type": "string", "description": "Release notes, markdown"},
        "slack_summary": {"type": "array", "items": {"type": "string"}, "description": "One change per line"},
    },
    "required": ["github_notes", "slack_summary"],
    "additionalProperties": False,
}

NOISE_RE = re.compile(r"^- (?:chore|ci|build|test|docs|style)(?:\(.*?\))?!?:|^- Merge ", re.IGNORECASE)


@dataclass
class Config:
    tag: str
    previous_tag: str
    target: str
    product: str
    instructions: str
    slack_lines: str
    max_commits: int
    header: str
    footer: str


@dataclass
class Notes:
    body: str
    slack: list[str]
    source: str


class ReleaseNotes:
    def __init__(self, cfg: Config, git: Git, github: GitHub | None, llm: OpenRouter | None) -> None:
        self.cfg = cfg
        self.git = git
        self.github = github
        self.llm = llm

    def generate(self) -> Notes:
        cfg = self.cfg
        rev_range = f"{cfg.previous_tag}..{cfg.target}" if cfg.previous_tag else cfg.target
        commits = self.git.commits(rev_range, cfg.max_commits, body=True)
        auto = self.github.generate_notes(cfg.tag, cfg.previous_tag, cfg.target) if self.github else ""

        if self.llm and (commits or auto):
            try:
                return self.with_ai(commits, auto)
            except OpenRouterError as exc:
                print(f"AI notes failed, using fallback: {exc}", file=sys.stderr)

        subjects = [c.splitlines()[0] for c in commits]
        useful = [s for s in subjects if not NOISE_RE.match(s)] or subjects
        slack = [s.removeprefix("- ") for s in useful[:5]]
        if auto:
            return Notes(auto, slack, "github")
        return Notes("### Changes\n\n" + ("\n".join(subjects) or "- (no commits)"), slack, "git")

    def with_ai(self, commits: list[str], auto: str) -> Notes:
        cfg = self.cfg
        user = (
            f"Tag: {cfg.tag}\nPrevious tag: {cfg.previous_tag or 'none'}\n\n"
            f"GitHub auto-generated notes:\n{auto or '(none)'}\n\n"
            "Commits:\n" + ("\n".join(commits)[:60_000] or "(none)")
        )
        system = SYSTEM.format(
            product=f" for {cfg.product}" if cfg.product else "",
            slack_lines=cfg.slack_lines,
            instructions=f"\nExtra rules from the repository:\n{cfg.instructions}\n" if cfg.instructions else "",
        )
        out = self.llm.complete_json(system=system, user=user, name="release_notes", schema=SCHEMA)
        body = str(out.get("github_notes") or "").strip()
        slack = [re.sub(r"^\s*(?:[-*•]\s+)", "", str(line)).strip() for line in out.get("slack_summary") or []]
        slack = [line for line in slack if line]
        if not body or not slack:
            raise OpenRouterError("model returned empty notes")
        return Notes(body, slack, "ai")

    def render(self, notes: Notes) -> str:
        parts = [self.expand(self.cfg.header), notes.body, self.expand(self.cfg.footer)]
        return "\n\n".join(p.strip() for p in parts if p.strip()) + "\n"

    def expand(self, template: str) -> str:
        """Replace {tag}, {version} and {previous_tag}."""
        v = Version.parse(self.cfg.tag)
        values = {
            "tag": self.cfg.tag,
            "version": v.number if v else self.cfg.tag.removeprefix("v"),
            "previous_tag": self.cfg.previous_tag or "none",
        }
        for key, value in values.items():
            template = template.replace("{" + key + "}", value)
        return template


def main(rt: Runtime) -> None:
    git = Git()
    tag = rt.input("tag", required=True)
    target = rt.input("target") or (tag if git.has_commit(tag) else "HEAD")
    target = git.rev(target)

    previous = rt.input("previous_tag")
    if not previous:
        v = Version.parse(tag)
        previous = v.previous(git.tags()) if v else ""
        if not v:
            rt.warning(f"release-notes: tag '{tag}' is not a semantic version; notes cover all history")
    if previous and not git.has_commit(previous):
        raise ActionError(f"previous tag '{previous}' is not in the checkout; use actions/checkout with fetch-depth: 0")

    cfg = Config(
        tag=tag,
        previous_tag=previous,
        target=target,
        product=rt.input("product"),
        instructions=rt.input("instructions"),
        slack_lines=rt.input("slack_lines", "3 to 5"),
        max_commits=rt.int_input("max_commits", 150),
        header=rt.input("header"),
        footer=rt.input("footer"),
    )

    token = rt.input("github_token")
    github = GitHub(token, rt.env.get("GITHUB_REPOSITORY", ""), api_url=rt.env.get("GITHUB_API_URL", "")) if token else None
    api_key = rt.input("openrouter_api_key")
    llm = OpenRouter(api_key, rt.list_input("model")) if api_key else None
    if not llm:
        rt.warning("release-notes: openrouter_api_key is empty; notes come from GitHub and git")

    generator = ReleaseNotes(cfg, git, github, llm)
    notes = generator.generate()
    markdown = generator.render(notes)
    slack = "\n".join(f"• {line}" for line in notes.slack)

    out_dir = Path(rt.input("out_dir") or rt.env.get("RUNNER_TEMP", ".")) / "release-notes"
    out_dir.mkdir(parents=True, exist_ok=True)
    notes_file = out_dir / "release-notes.md"
    notes_file.write_text(markdown, encoding="utf-8")
    (out_dir / "slack-summary.txt").write_text(slack + "\n", encoding="utf-8")

    for name, value in {
        "notes": markdown,
        "notes_file": str(notes_file),
        "slack_summary": slack,
        "previous_tag": previous,
        "source": notes.source,
    }.items():
        rt.set_output(name, value)

    if notes.source != "ai" and rt.bool_input("fail_on_error"):
        raise ActionError(f"AI notes are not available (source: {notes.source})")

    print(f"{tag} (previous: {previous or 'none'}, source: {notes.source})\n\n{markdown}\n--- slack ---\n{slack}")
    rt.summary(
        f"## release-notes: {tag}\n\nPrevious tag: `{previous or 'none'}`. Source: `{notes.source}`.\n\n"
        f"{markdown}\n### Slack summary\n\n```\n{slack}\n```"
    )


if __name__ == "__main__":
    Runtime().run(main)
