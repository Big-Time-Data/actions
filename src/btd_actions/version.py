"""Semantic version tags and release channels."""

from __future__ import annotations

import re
from dataclasses import dataclass

TAG_RE = re.compile(
    r"^(?P<prefix>.*?)(?P<major>\d+)\.(?P<minor>\d+)\.(?P<patch>\d+)(?:-(?P<pre>[0-9A-Za-z.-]+))?$"
)


@dataclass(frozen=True)
class Version:
    tag: str
    prefix: str
    major: int
    minor: int
    patch: int
    pre: str

    @classmethod
    def parse(cls, tag: str) -> Version | None:
        m = TAG_RE.match(tag)
        if not m or re.search(r"\d", m["prefix"]):
            return None
        return cls(tag, m["prefix"], int(m["major"]), int(m["minor"]), int(m["patch"]), m["pre"] or "")

    @property
    def channel(self) -> str:
        """'stable', or the prerelease label without numbers: beta.2 and beta are both 'beta'."""
        label = re.sub(r"[\d.-]+", "", self.pre)
        return label or "stable"

    @property
    def key(self) -> tuple[int, int, int, int, int]:
        """Sort key: a prerelease comes before the stable release of the same number."""
        digits = re.findall(r"\d+", self.pre)
        return (self.major, self.minor, self.patch, 0 if self.pre else 1, int(digits[-1]) if digits else 0)

    @property
    def number(self) -> str:
        """The version without the prefix, e.g. 1.2.3-beta."""
        return self.tag[len(self.prefix) :]

    def previous(self, tags: list[str], prerelease_since: str = "channel") -> str:
        """The highest older tag with the same prefix and channel, or ''.

        prerelease_since="any": a prerelease compares with the highest older tag of any channel.
        """
        any_channel = prerelease_since == "any" and self.pre
        older = [
            v
            for v in (Version.parse(t) for t in tags)
            if v and v.prefix == self.prefix and (any_channel or v.channel == self.channel) and v.key < self.key
        ]
        return max(older, key=lambda v: v.key).tag if older else ""
