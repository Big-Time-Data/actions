"""pr-enhance: rewrite a pull request title and body from its diff."""

from __future__ import annotations

from dataclasses import dataclass

from .diff import DEFAULT_EXCLUDE, Diff
from .git import Git
from .github import GitHub
from .openrouter import OpenRouter, OpenRouterError
from .runtime import ActionError, Runtime

SYSTEM = """You write GitHub pull request titles and descriptions{product}.

The current title and body may already be good. Prefer to keep them.
- Keep the title when it is specific, accurate and not only a branch name.
- Keep the body when it describes the changes clearly. Fix small errors; do not rewrite for style.
- Change only what is wrong, missing or too vague for the actual diff.
- If both are good, return them unchanged.

Never invent changes. Use only the input.
Skip CI, chore, merge and lockfile noise unless that is the whole PR.
Never use only the branch name as the title (for example "Dev").

When you write or fill in:
- Title: one line, imperative mood, at most 72 characters. Use a conventional commit prefix when the PR has one theme.
- Body: markdown with "## Summary" then "## Changes" (bullets grouped by area). Omit empty sections.
  Keep PR and issue numbers. Keep existing intent, test notes and reviewer context that are still accurate.
{instructions}"""

SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string", "description": "PR title, one line"},
        "body": {"type": "string", "description": "PR body, markdown"},
    },
    "required": ["title", "body"],
    "additionalProperties": False,
}


@dataclass
class Config:
    number: int
    product: str
    instructions: str
    exclude: list[str]
    max_commits: int
    max_diff_chars: int
    max_file_chars: int
    skip_label: str
    dry_run: bool


@dataclass
class Result:
    title: str
    body: str
    updated: bool
    skipped: str = ""


class PullRequestEnhancer:
    def __init__(self, cfg: Config, github: GitHub, git: Git, llm: OpenRouter) -> None:
        self.cfg = cfg
        self.github = github
        self.git = git
        self.llm = llm

    def run(self) -> Result:
        pr = self.github.pull(self.cfg.number)
        title = str(pr.get("title") or "").strip()
        body = str(pr.get("body") or "").strip()

        labels = {label.get("name") for label in pr.get("labels") or []}
        if self.cfg.skip_label and self.cfg.skip_label in labels:
            return Result(title, body, updated=False, skipped=f"label '{self.cfg.skip_label}'")

        base, head = pr["base"]["sha"], pr["head"]["sha"]
        self.git.ensure_history(base, head, extra_refs=(f"refs/pull/{self.cfg.number}/head",))
        rev_range = f"{base}...{head}"

        new_title, new_body = self.generate(title, body, rev_range)
        changes: dict[str, str] = {}
        if new_title != title:
            changes["title"] = new_title
        if new_body != body:
            changes["body"] = new_body
        if changes and not self.cfg.dry_run:
            self.github.update_pull(self.cfg.number, changes)
        return Result(new_title, new_body, updated=bool(changes))

    def generate(self, title: str, body: str, rev_range: str) -> tuple[str, str]:
        commits = self.git.commits(rev_range, self.cfg.max_commits) or ["- (no commits)"]
        diff = Diff.parse(self.git.diff(rev_range, self.cfg.exclude))
        user = (
            f"Current title: {title or '(empty)'}\n\n"
            f"Current body:\n{body or '(empty)'}\n\n"
            f"Commits:\n" + "\n".join(commits) + "\n\n"
            f"Diff stat:\n{self.git.stat(rev_range, max_lines=200) or '(empty)'}\n\n"
            f"Diff:\n{diff.render(self.cfg.max_diff_chars, self.cfg.max_file_chars)}\n"
        )
        system = SYSTEM.format(
            product=f" for {self.cfg.product}" if self.cfg.product else "",
            instructions=f"\nExtra rules from the repository:\n{self.cfg.instructions}\n" if self.cfg.instructions else "",
        )
        out = self.llm.complete_json(system=system, user=user, name="pull_request", schema=SCHEMA)
        new_title = " ".join(str(out.get("title") or "").split())
        new_body = str(out.get("body") or "").strip()
        if not new_title or not new_body:
            raise OpenRouterError("model returned an empty title or body")
        if len(new_title) > 256:
            new_title = new_title[:253].rstrip() + "..."
        return new_title, new_body


def pr_number(rt: Runtime) -> int:
    raw = rt.input("pr_number")
    if not raw:
        event = rt.event()
        raw = str((event.get("pull_request") or {}).get("number") or (event.get("issue") or {}).get("number") or "")
    if not raw.isdigit():
        raise ActionError("no pull request number: set input 'pr_number' or run on a pull_request event")
    return int(raw)


def main(rt: Runtime) -> None:
    cfg = Config(
        number=pr_number(rt),
        product=rt.input("product"),
        instructions=rt.input("instructions"),
        exclude=DEFAULT_EXCLUDE + rt.list_input("exclude"),
        max_commits=rt.int_input("max_commits", 100),
        max_diff_chars=rt.int_input("max_diff_chars", 60_000),
        max_file_chars=rt.int_input("max_file_chars", 12_000),
        skip_label=rt.input("skip_label"),
        dry_run=rt.bool_input("dry_run"),
    )
    github = GitHub(rt.input("github_token", required=True), rt.env.get("GITHUB_REPOSITORY", ""), api_url=rt.env.get("GITHUB_API_URL", ""))
    llm = OpenRouter(rt.input("openrouter_api_key", required=True), rt.list_input("model"))

    try:
        result = PullRequestEnhancer(cfg, github, Git(), llm).run()
    except OpenRouterError as exc:
        if rt.bool_input("fail_on_error"):
            raise
        rt.warning(f"pr-enhance: PR left as is: {exc}")
        rt.set_output("updated", "false")
        return

    rt.set_output("updated", str(result.updated).lower())
    rt.set_output("title", result.title)
    rt.set_output("body", result.body)

    if result.skipped:
        print(f"skipped: {result.skipped}")
        rt.summary(f"## pr-enhance\n\nSkipped: {result.skipped}.")
        return

    state = "updated" if result.updated else "unchanged"
    if cfg.dry_run:
        state += " (dry run, PR not changed)"
    print(f"PR #{cfg.number}: {state}\ntitle: {result.title}\n\n{result.body}")
    rt.summary(f"## pr-enhance: PR #{cfg.number} {state}\n\n### Title\n\n`{result.title}`\n\n### Body\n\n{result.body}")


if __name__ == "__main__":
    Runtime().run(main)
