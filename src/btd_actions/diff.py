"""Fit a unified diff into a character budget for a prompt."""

from __future__ import annotations

from dataclasses import dataclass

# Git pathspec globs: lockfiles, generated output and binary assets.
DEFAULT_EXCLUDE = [
    "**/*.lock",
    "**/package-lock.json",
    "**/pnpm-lock.yaml",
    "**/go.sum",
    "**/go.work.sum",
    "**/*.min.js",
    "**/*.min.css",
    "**/*.map",
    "**/*.snap",
    "**/*.svg",
    "**/*.png",
    "**/*.jpg",
    "**/*.jpeg",
    "**/*.gif",
    "**/*.webp",
    "**/*.ico",
    "**/*.pdf",
    "**/*.woff",
    "**/*.woff2",
    "**/*.ttf",
    "**/*.eot",
    "**/*.mp4",
    "**/*.mov",
    "**/*.zip",
    "**/*.gz",
    "**/*.tgz",
    "**/*.dmg",
    "**/*.wasm",
]


@dataclass
class FileDiff:
    path: str
    text: str


class Diff:
    def __init__(self, files: list[FileDiff]) -> None:
        self.files = files

    @classmethod
    def parse(cls, text: str) -> Diff:
        files: list[FileDiff] = []
        for chunk in ("\n" + text).split("\ndiff --git ")[1:]:
            header = chunk.split("\n", 1)[0]
            path = header.rsplit(" b/", 1)[-1] if " b/" in header else header
            files.append(FileDiff(path=path, text="diff --git " + chunk))
        return cls(files)

    def render(self, max_chars: int, max_file_chars: int) -> str:
        """Cut each file at max_file_chars so one large file does not use the full budget."""
        parts: list[str] = []
        used = 0
        omitted: list[str] = []
        for f in self.files:
            piece = f.text
            if len(piece) > max_file_chars:
                piece = piece[:max_file_chars].rstrip() + f"\n... ({len(f.text) - max_file_chars} chars cut)"
            if used + len(piece) > max_chars:
                omitted.append(f.path)
                continue
            parts.append(piece)
            used += len(piece)
        if omitted:
            parts.append(f"... {len(omitted)} files omitted (budget): " + ", ".join(omitted[:50]))
        return "\n".join(parts) if parts else "(no diff)"
