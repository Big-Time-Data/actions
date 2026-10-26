"""Read commits, diffs and tags from the local checkout."""

from __future__ import annotations

import subprocess
import sys

from .runtime import ActionError


class Git:
    def __init__(self, cwd: str | None = None) -> None:
        self.cwd = cwd

    def run(self, *args: str) -> str:
        try:
            out = subprocess.run(["git", *args], cwd=self.cwd, check=True, capture_output=True, text=True)
        except FileNotFoundError:
            raise ActionError("git is not installed") from None
        except subprocess.CalledProcessError as exc:
            raise ActionError(f"git {' '.join(args)} failed: {exc.stderr.strip()}") from None
        return out.stdout.rstrip("\n")

    def has_commit(self, rev: str) -> bool:
        try:
            self.run("cat-file", "-e", f"{rev}^{{commit}}")
            return True
        except ActionError:
            return False

    def ensure_history(self, base: str, head: str, extra_refs: tuple[str, ...] = ()) -> None:
        """Fetch base and head when they are missing, and the merge base when the clone is shallow."""
        try:
            self.run("rev-parse", "--git-dir")
        except ActionError:
            raise ActionError("no git repository here; run actions/checkout first") from None

        for rev in (base, head):
            if self.has_commit(rev):
                continue
            for ref in (rev, *extra_refs):
                try:
                    self.run("fetch", "--no-tags", "origin", ref)
                except ActionError as exc:
                    print(f"fetch {ref}: {exc}", file=sys.stderr)
                    continue
                if self.has_commit(rev):
                    break
            if not self.has_commit(rev):
                raise ActionError(f"commit {rev} is not in the checkout and fetch failed")

        if self.run("rev-parse", "--is-shallow-repository") == "true" and not self.merge_base(base, head):
            print("shallow clone: fetching full history to find the merge base")
            self.run("fetch", "--no-tags", "--unshallow", "origin", base, head)

    def merge_base(self, base: str, head: str) -> str:
        try:
            return self.run("merge-base", base, head)
        except ActionError:
            return ""

    def commits(self, rev_range: str, limit: int, body: bool = False, paths: list[str] | None = None) -> list[str]:
        """One entry per commit: '- subject (sha)', plus the body when body is true."""
        fmt = "%x1e- %s (%h)%n%b" if body else "%x1e- %s (%h)"
        pathspec = ["--", *paths] if paths else []
        out = self.run("log", rev_range, "--no-merges", f"--max-count={limit}", f"--pretty=format:{fmt}", *pathspec)
        return [entry.strip() for entry in out.split("\x1e") if entry.strip()]

    def stat(self, rev_range: str, max_lines: int) -> str:
        lines = self.run("diff", "--stat=200", rev_range).splitlines()
        if len(lines) > max_lines:
            lines = lines[: max_lines - 1] + [f"... ({len(lines) - max_lines} more lines)", lines[-1]]
        return "\n".join(lines)

    def diff(self, rev_range: str, exclude: list[str]) -> str:
        pathspecs = [f":(exclude,glob){pattern}" for pattern in exclude]
        return self.run("diff", "--no-color", "--no-ext-diff", rev_range, "--", ".", *pathspecs)

    def tags(self) -> list[str]:
        return [t for t in self.run("tag", "--list").splitlines() if t]

    def rev(self, rev: str) -> str:
        return self.run("rev-parse", f"{rev}^{{commit}}")
