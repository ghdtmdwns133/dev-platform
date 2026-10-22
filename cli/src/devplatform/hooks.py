"""Git hooks: installation and the fast staged-file pre-commit gate.

The hook script is POSIX ``sh`` so it works under Git for Windows as well as on
Linux/macOS.  It embeds the absolute platform-home path, but prefers a vendored
``<repo>/.dev-platform/cli`` checkout when the consumer repository has one.

``devctl hooks pre-commit`` only looks at staged files and never launches Unity;
``unity``/``unity-assets`` profiles run the (fast, editor-free) integrity checks.
"""

from __future__ import annotations

import contextlib
import os
import subprocess
from pathlib import Path

from . import integrity, procs
from .config import Config
from .errors import EXIT_GATE, EXIT_PRECONDITION, DevctlError

MARKER = "# devctl pre-commit hook"

HOOK_TEMPLATE = """#!/bin/sh
# devctl pre-commit hook (managed by `devctl hooks install`; do not edit)
set -u
repo="$(git rev-parse --show-toplevel)" || exit 1
platform="__PLATFORM__"
if [ -f "$repo/.dev-platform/cli/pyproject.toml" ]; then
\tplatform="$repo/.dev-platform/cli"
fi
exec uv run --project "$platform" devctl --root "$repo" hooks pre-commit
"""

TS_ESLINT_SUFFIXES = {".ts", ".tsx", ".js", ".jsx"}
TS_PRETTIER_SUFFIXES = TS_ESLINT_SUFFIXES | {".json", ".css", ".md"}
UNITY_RELEVANT_PREFIXES = ("Assets/", "Packages/", "ProjectSettings/")


def _git(root: Path, *args: str, strip: bool = True) -> tuple[int, str, str]:
    completed = subprocess.run(
        ["git", "-C", str(root), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    stdout = completed.stdout or ""
    stderr = completed.stderr or ""
    if strip:
        stdout = stdout.strip()
        stderr = stderr.strip()
    return completed.returncode, stdout, stderr


def hook_directory(root: Path) -> Path:
    code, output, error = _git(Path(root), "rev-parse", "--git-path", "hooks")
    if code != 0:
        raise DevctlError(EXIT_PRECONDITION, f"not a git repository: {root}", detail=error or None)
    path = Path(output)
    return path if path.is_absolute() else Path(root) / path


def render_hook(platform_home: Path) -> str:
    platform = (Path(platform_home) / "cli").resolve().as_posix()
    return HOOK_TEMPLATE.replace("__PLATFORM__", platform)


def install_hooks(root: Path, platform_home: Path, force: bool = False) -> Path:
    """Install (or refresh) the managed pre-commit hook."""
    root = Path(root)
    hook = hook_directory(root) / "pre-commit"
    hook.parent.mkdir(parents=True, exist_ok=True)
    content = render_hook(platform_home)
    if hook.exists():
        try:
            existing = hook.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            raise DevctlError(EXIT_PRECONDITION, f"could not read {hook}: {exc}") from exc
        if MARKER not in existing and not force:
            raise DevctlError(
                EXIT_GATE,
                f"refusing to overwrite non-devctl hook: {hook} (use --force)",
            )
        if existing == content:
            _make_executable(hook)
            procs.emit_notice(f"devctl pre-commit hook already installed: {hook}")
            return hook
    try:
        hook.write_bytes(content.encode("utf-8"))
    except OSError as exc:
        raise DevctlError(EXIT_PRECONDITION, f"could not write {hook}: {exc}") from exc
    _make_executable(hook)
    procs.emit_notice(f"Installed devctl pre-commit hook: {hook}")
    return hook


def _make_executable(path: Path) -> None:
    # Windows ignores the execute bit; Git for Windows runs sh hooks anyway.
    with contextlib.suppress(OSError):
        os.chmod(path, 0o755)


def staged_files(root: Path) -> list[str]:
    code, output, error = _git(
        Path(root), "diff", "--cached", "--name-only", "--diff-filter=ACMR", "-z", strip=False
    )
    if code != 0:
        raise DevctlError(
            EXIT_PRECONDITION, "could not list staged files", detail=error.strip() or None
        )
    return [item for item in output.split("\0") if item]


def _existing(root: Path, files: list[str]) -> list[str]:
    return [name for name in files if (Path(root) / name).is_file()]


def _plan(
    root: Path, config: Config, staged: list[str]
) -> tuple[list[tuple[str, list[str]]], bool]:
    """Return (commands, run_integrity) for the configured profile."""
    profile = config.profile
    commands: list[tuple[str, list[str]]] = []
    if profile == "python":
        files = _existing(root, [name for name in staged if name.endswith(".py")])
        if files:
            commands.append(
                ("hooks-ruff-check", ["uv", "run", "--frozen", "ruff", "check", *files])
            )
            commands.append(
                (
                    "hooks-ruff-format",
                    ["uv", "run", "--frozen", "ruff", "format", "--check", *files],
                )
            )
    elif profile == "typescript":
        eslint = _existing(
            root, [name for name in staged if Path(name).suffix in TS_ESLINT_SUFFIXES]
        )
        prettier = _existing(
            root, [name for name in staged if Path(name).suffix in TS_PRETTIER_SUFFIXES]
        )
        if eslint:
            commands.append(("hooks-eslint", ["npx", "eslint", "--max-warnings=0", *eslint]))
        if prettier:
            commands.append(("hooks-prettier", ["npx", "prettier", "--check", *prettier]))
    elif profile == "dotnet":
        files = _existing(root, [name for name in staged if name.endswith(".cs")])
        if files:
            commands.append(
                (
                    "hooks-dotnet-format",
                    ["dotnet", "format", "--verify-no-changes", "--include", *files],
                )
            )
    elif profile in {"unity", "unity-assets"}:
        relevant = [
            name
            for name in staged
            if name == ".editorconfig" or name.startswith(UNITY_RELEVANT_PREFIXES)
        ]
        if relevant:
            return commands, True
    return commands, False


def pre_commit(
    root: Path,
    config: Config,
    reports_dir: Path,
    runner=procs.run,
) -> int:
    """Run the staged-file gate.  Returns a process exit code."""
    root = Path(root)
    profile = config.profile
    if profile is None:
        procs.emit_notice("devctl pre-commit: no profile configured; skipping")
        return 0
    staged = staged_files(root)
    commands, run_integrity = _plan(root, config, staged)
    if run_integrity:
        result = integrity.check(root, config)
        integrity.print_result(result)
        return 0 if not result.errors else 1
    if not commands:
        return 0
    exit_code = 0
    for name, argv in commands:
        result = runner(name, argv, root, Path(reports_dir) / profile / f"{name}.log")
        if result.exit != 0:
            exit_code = 1
    return exit_code
