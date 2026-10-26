"""Install a CLI binary from a GitHub release and check it against checksums.txt."""

from __future__ import annotations

import hashlib
import io
import platform
import re
import tarfile
import zipfile
from pathlib import Path

from .httpclient import HttpClient, HttpError
from .runtime import ActionError
from .version import Version


class ReleaseInstaller:
    """Releases must have <name>_<os>_<arch>.tar.gz (or .zip on Windows) and checksums.txt."""

    def __init__(self, repo: str, name: str, token: str = "", http: HttpClient | None = None) -> None:
        self.repo = repo
        self.name = name
        self.http = http or HttpClient(timeout=120)
        self.headers = {"Accept": "application/vnd.github+json"}
        if token:
            self.headers["Authorization"] = f"Bearer {token}"

    def resolve(self, version: str) -> str:
        """latest, vX.Y.Z, or a major such as v0 (the highest stable vX.Y.Z)."""
        version = version.strip() or "latest"
        if Version.parse(version):
            return version
        try:
            if version == "latest":
                return str(self._api("/releases/latest")["tag_name"])
            if re.fullmatch(r"v\d+", version):
                releases = self._api("/releases?per_page=100")
                matches = [
                    v
                    for v in (Version.parse(str(r.get("tag_name"))) for r in releases if not r.get("draft") and not r.get("prerelease"))
                    if v and v.prefix == "v" and v.channel == "stable" and f"v{v.major}" == version
                ]
                if not matches:
                    raise ActionError(f"no release of {self.repo} matches {version}")
                return max(matches, key=lambda v: v.key).tag
        except HttpError as exc:
            raise ActionError(f"list the releases of {self.repo}: HTTP {exc.status}") from None
        raise ActionError(f"version must be latest, vX.Y.Z or a major such as v0, got '{version}'")

    def asset(self) -> str:
        system = platform.system().lower()
        machine = platform.machine().lower()
        os_name = {"linux": "linux", "darwin": "darwin", "windows": "windows"}.get(system)
        arch = {"x86_64": "amd64", "amd64": "amd64", "aarch64": "arm64", "arm64": "arm64"}.get(machine)
        if not os_name or not arch:
            raise ActionError(f"no {self.name} build for {system}/{machine}")
        ext = "zip" if os_name == "windows" else "tar.gz"
        return f"{self.name}_{os_name}_{arch}.{ext}"

    def install(self, tag: str, dest: Path) -> Path:
        asset = self.asset()
        base = f"https://github.com/{self.repo}/releases/download/{tag}"
        try:
            archive = self.http.request("GET", f"{base}/{asset}")
            checksums = self.http.request("GET", f"{base}/checksums.txt").decode()
        except HttpError as exc:
            raise ActionError(f"download {self.name} {tag}: HTTP {exc.status}") from None

        self.verify(asset, archive, checksums)
        exe = self.name + (".exe" if asset.endswith(".zip") else "")
        data = self.extract(archive, exe, asset.endswith(".zip"))

        dest.mkdir(parents=True, exist_ok=True)
        target = dest / exe
        tmp = target.with_suffix(".new")
        tmp.write_bytes(data)
        tmp.chmod(0o755)
        tmp.replace(target)
        return target

    @staticmethod
    def verify(asset: str, data: bytes, checksums: str) -> None:
        want = next((line.split()[0] for line in checksums.splitlines() if line.split()[1:] == [asset]), "")
        if not want:
            raise ActionError(f"checksums.txt has no line for {asset}")
        if hashlib.sha256(data).hexdigest() != want:
            raise ActionError(f"checksum of {asset} does not match checksums.txt")

    @staticmethod
    def extract(archive: bytes, member: str, is_zip: bool) -> bytes:
        """Read one file by base name; nothing else is written to disk."""
        if is_zip:
            with zipfile.ZipFile(io.BytesIO(archive)) as zf:
                name = next((n for n in zf.namelist() if Path(n).name == member), None)
                if name:
                    return zf.read(name)
        else:
            with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as tf:
                info = next((m for m in tf.getmembers() if m.isfile() and Path(m.name).name == member), None)
                f = tf.extractfile(info) if info else None
                if f:
                    return f.read()
        raise ActionError(f"archive has no {member}")

    def _api(self, path: str):
        return self.http.json("GET", f"https://api.github.com/repos/{self.repo}{path}", self.headers)
