"""mcp-query: install mcpq, then build, diff, publish, validate and eval the context.

Subcommands: setup (install, conn file, config), run (the mcpq steps).
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from .installer import ReleaseInstaller
from .runtime import ActionError, Runtime

RELEASE_REPO = "Big-Time-Data/homebrew-tools"
DEFAULT_CONFIGS = ("mcpq.yaml", "mcpq/mcpq.yaml")  # mcpq's own search order


@contextmanager
def group(title: str):
    print(f"::group::{title}", flush=True)
    try:
        yield
    finally:
        print("::endgroup::", flush=True)


@dataclass
class Mcpq:
    bin: str
    config: str
    conn: str

    def env(self, **extra: str) -> dict[str, str]:
        return {**os.environ, "MCPQ_CONN": self.conn, **extra}

    def args(self, *args: str) -> list[str]:
        return [self.bin, *(["--config", self.config] if self.config else []), *args]

    def call(self, *args: str, **extra_env: str) -> None:
        if subprocess.run(self.args(*args), env=self.env(**extra_env)).returncode != 0:
            raise ActionError(f"mcpq {args[0]} failed")

    def build(self, sources: list[str]) -> str:
        """Stream the output and return the path on the 'artifact <path>' line."""
        cmd = self.args("build", "--yes", *(["--source", ",".join(sources)] if sources else []))
        artifact = ""
        with subprocess.Popen(cmd, env=self.env(), stdout=subprocess.PIPE, text=True, bufsize=1) as proc:
            for line in proc.stdout:
                sys.stdout.write(line)
                if line.startswith("artifact "):
                    artifact = line.removeprefix("artifact ").strip()
        if proc.returncode != 0:
            raise ActionError("mcpq build failed")
        if not artifact:
            raise ActionError("mcpq build printed no artifact path")
        return artifact

    def diff(self, artifact: str) -> str:
        out = subprocess.run(self.args("diff", artifact, "current", "--format", "md"), env=self.env(), capture_output=True, text=True)
        if out.returncode != 0:
            raise ActionError(f"mcpq diff failed: {out.stderr.strip()[-500:]}")
        return out.stdout


def resolve_config(config: str, cwd: Path) -> str:
    if config:
        return config
    return next((c for c in DEFAULT_CONFIGS if (cwd / c).is_file()), "")


def needs_uv(config_path: Path, sources: list[str]) -> bool:
    """True when the dbt source runs and mcpq.yaml has a dbt_core version to install."""
    if sources and "dbt" not in sources:
        return False
    if not config_path.is_file():
        return False
    return re.search(r"^\s+dbt_core:", config_path.read_text(encoding="utf-8"), re.MULTILINE) is not None


def install(rt: Runtime) -> Path:
    dest = Path(rt.env.get("RUNNER_TEMP", ".")) / "mcpq-bin"
    local = rt.input("bin")
    if local:
        dest.mkdir(parents=True, exist_ok=True)
        target = dest / "mcpq"
        shutil.copyfile(local, target)
        target.chmod(0o755)
    else:
        installer = ReleaseInstaller(RELEASE_REPO, "mcpq", token=rt.input("github_token"))
        tag = installer.resolve(rt.input("version", "v0"))
        target = installer.install(tag, dest)
    out = subprocess.run([str(target), "version"], capture_output=True, text=True).stdout.strip()
    version = out.splitlines()[0] if out else ""
    print(f"mcpq installed: {target} ({version})")
    path_file = rt.env.get("GITHUB_PATH")
    if path_file:
        with open(path_file, "a", encoding="utf-8") as fh:
            fh.write(f"{dest}\n")
    rt.set_output("bin", str(target))
    rt.set_output("version", version)
    return target


def conn_file(conn: str, tmp: Path) -> str:
    """Return conn when it is a file path, else write the content to a 0600 file in tmp."""
    try:
        if "\n" not in conn and Path(conn).is_file():
            return conn
    except OSError:  # content that is too long for a file name
        pass
    path = tmp / "mcpq-conn.yaml"
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(conn + "\n")
    return str(path)


def setup(rt: Runtime) -> None:
    conn = rt.input("conn") or rt.env.get("MCPQ_CONN", "").strip()
    if not conn:
        raise ActionError("set input 'conn' or env MCPQ_CONN to the conn file content (or a path to it)")

    install(rt)

    conn = conn_file(conn, Path(rt.env.get("RUNNER_TEMP", ".")))

    cwd = Path.cwd()
    config = resolve_config(rt.input("config"), cwd)
    rt.set_output("conn", conn)
    rt.set_output("config", config)
    rt.set_output("need_uv", str(needs_uv(cwd / config, rt.list_input("source")) if config else False).lower())


def run(rt: Runtime) -> None:
    mcpq = Mcpq(bin=rt.input("bin", required=True), config=rt.input("config"), conn=rt.input("conn", required=True))

    with group("mcpq build"):
        artifact = mcpq.build(rt.list_input("source"))
    rt.set_output("artifact", artifact)

    # The diff runs before publish, so it shows what this build changes.
    with group("mcpq diff"):
        try:
            diff = mcpq.diff(artifact)
        except ActionError as exc:
            rt.warning(f"mcp-query: {exc}")
            diff = ""
    if diff:
        diff_file = Path(rt.env.get("RUNNER_TEMP", ".")) / "mcpq-diff.md"
        diff_file.write_text(diff, encoding="utf-8")
        rt.set_output("diff_file", str(diff_file))
        rt.summary(f"## mcpq diff\n\n{diff}")

    if not rt.bool_input("publish", default=True):
        print("publish is false: build and diff only")
        return

    with group("mcpq publish"):
        mcpq.call("publish", "--artifact", artifact)
    with group("mcpq validate"):
        mcpq.call("validate", "--stage", "published")

    tags = rt.input("eval_tags")
    if tags:
        key = rt.input("eval_api_key") or rt.env.get("MCPQ_EVAL", "").strip()
        if not key:
            rt.notice("mcp-query: eval_tags is set, but MCPQ_EVAL is empty; evals skipped")
            return
        with group("mcpq eval"):
            # The claude harness reads its login from ANTHROPIC_API_KEY.
            mcpq.call("eval", "run", "--tags", tags, ANTHROPIC_API_KEY=key)


COMMANDS = {"install": install, "setup": setup, "run": run}

if __name__ == "__main__":
    command = sys.argv[1] if len(sys.argv) > 1 else ""
    if command not in COMMANDS:
        raise SystemExit(f"usage: python3 -m btd_actions.mcp_query {{{','.join(COMMANDS)}}}")
    Runtime().run(COMMANDS[command])
