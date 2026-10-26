import hashlib
import io
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from btd_actions.installer import ReleaseInstaller
from btd_actions.mcp_query import needs_uv, resolve_config
from btd_actions.runtime import ActionError


def tarball(name: str, data: bytes) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tf:
        info = tarfile.TarInfo(name)
        info.size = len(data)
        tf.addfile(info, io.BytesIO(data))
    return buf.getvalue()


class InstallerTest(unittest.TestCase):
    def installer(self, http=None):
        return ReleaseInstaller("o/r", "mcpq", http=http or mock.Mock())

    def test_resolve_major_picks_highest_stable(self):
        http = mock.Mock()
        http.json.return_value = [
            {"tag_name": "v1.0.0"},
            {"tag_name": "v0.0.9"},
            {"tag_name": "v0.0.17"},
            {"tag_name": "v0.1.0-beta", "prerelease": True},
            {"tag_name": "v0.2.0", "draft": True},
        ]
        self.assertEqual(self.installer(http).resolve("v0"), "v0.0.17")

    def test_resolve_exact_and_latest(self):
        http = mock.Mock()
        http.json.return_value = {"tag_name": "v0.0.17"}
        self.assertEqual(self.installer(http).resolve("v0.0.3"), "v0.0.3")
        self.assertEqual(self.installer(http).resolve(""), "v0.0.17")
        with self.assertRaises(ActionError):
            self.installer(http).resolve("main")

    def test_verify(self):
        data = b"bin"
        good = f"{hashlib.sha256(data).hexdigest()}  a.tar.gz\n"
        ReleaseInstaller.verify("a.tar.gz", data, good)
        with self.assertRaisesRegex(ActionError, "does not match"):
            ReleaseInstaller.verify("a.tar.gz", b"other", good)
        with self.assertRaisesRegex(ActionError, "no line"):
            ReleaseInstaller.verify("b.tar.gz", data, good)

    def test_install(self):
        archive = tarball("mcpq", b"#!/bin/sh\n")
        inst = self.installer()
        asset = inst.asset()
        sums = f"{hashlib.sha256(archive).hexdigest()}  {asset}\n".encode()
        inst.http.request.side_effect = lambda method, url: archive if url.endswith(asset) else sums
        with tempfile.TemporaryDirectory() as d:
            target = inst.install("v0.0.1", Path(d))
            self.assertEqual(target.read_bytes(), b"#!/bin/sh\n")
            self.assertTrue(target.stat().st_mode & 0o100)

    def test_extract_missing_member(self):
        with self.assertRaisesRegex(ActionError, "no mcpq"):
            ReleaseInstaller.extract(tarball("README", b"x"), "mcpq", is_zip=False)


class ConfigTest(unittest.TestCase):
    def test_resolve_config(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            self.assertEqual(resolve_config("", root), "")
            (root / "mcpq").mkdir()
            (root / "mcpq/mcpq.yaml").write_text("x")
            self.assertEqual(resolve_config("", root), "mcpq/mcpq.yaml")
            (root / "mcpq.yaml").write_text("x")
            self.assertEqual(resolve_config("", root), "mcpq.yaml")
            self.assertEqual(resolve_config("other.yaml", root), "other.yaml")

    def test_needs_uv(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = Path(d) / "mcpq.yaml"
            cfg.write_text("sources:\n  dbt:\n    generate:\n      dbt_core: 1.9.0\n")
            self.assertTrue(needs_uv(cfg, []))
            self.assertTrue(needs_uv(cfg, ["curated", "dbt"]))
            self.assertFalse(needs_uv(cfg, ["curated"]))
            cfg.write_text("sources:\n  curated: {}\n")
            self.assertFalse(needs_uv(cfg, []))
            self.assertFalse(needs_uv(Path(d) / "missing.yaml", []))
