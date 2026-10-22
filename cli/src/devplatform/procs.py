"""Subprocess execution and GitHub Actions annotations.

Every command devctl runs goes through :func:`run`, which records argv, exit code,
duration and a combined stdout/stderr log under ``<reports>/<profile>/``.  The
same log layout is used locally and in CI so a failing CI step can be reproduced
by opening the uploaded artifact.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

STATUS_PASSED = "passed"
STATUS_FAILED = "failed"
STATUS_ERROR = "error"
STATUS_SKIPPED = "skipped"


@dataclass
class Result:
    """Outcome of one executed step."""

    name: str
    argv: list[str]
    exit: int
    duration_s: float
    log: Path
    status: str = STATUS_PASSED
    detail: str = ""
    output: str = ""
    extra: dict[str, Any] = field(default_factory=dict)


def is_ci() -> bool:
    return os.environ.get("GITHUB_ACTIONS", "").lower() == "true"


def display_path(path: Path, root: Path) -> str:
    """Return a repository-relative POSIX path when possible."""
    try:
        return Path(path).resolve().relative_to(Path(root).resolve()).as_posix()
    except ValueError:
        return Path(path).resolve().as_posix()


def _escape_annotation(message: str) -> str:
    return message.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def emit_error(message: str, title: str | None = None) -> None:
    prefix = f"::error title={_escape_annotation(title)}::" if title else "::error::"
    print(f"{prefix}{_escape_annotation(message)}")


def emit_warning(message: str, title: str | None = None) -> None:
    prefix = f"::warning title={_escape_annotation(title)}::" if title else "::warning::"
    print(f"{prefix}{_escape_annotation(message)}")


def emit_notice(message: str) -> None:
    print(f"::notice::{_escape_annotation(message)}")


def _tail(output: str, lines: int = 20) -> str:
    return "\n".join(output.splitlines()[-lines:])


def run(
    name: str,
    argv: list[str],
    cwd: Path,
    log_path: Path,
    env: dict[str, str] | None = None,
    timeout: float | None = None,
) -> Result:
    """Execute ``argv``, tee the result into ``log_path`` and return a :class:`Result`."""
    log_path = Path(log_path)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    argv = [str(item) for item in argv]
    started = time.monotonic()
    child_env = os.environ.copy()
    if env:
        child_env.update(env)

    resolved = shutil.which(argv[0]) if argv else None
    effective = [resolved or argv[0], *argv[1:]] if argv else []

    status = STATUS_PASSED
    detail = ""
    output = ""
    exit_code = 0
    try:
        completed = subprocess.run(
            effective,
            cwd=str(cwd),
            env=child_env,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
        exit_code = completed.returncode
        output = completed.stdout or ""
        if completed.stderr:
            output += completed.stderr
        if exit_code != 0:
            status = STATUS_FAILED
            detail = f"exit {exit_code}"
    except FileNotFoundError:
        exit_code = 127
        status = STATUS_ERROR
        detail = f"command not found: {argv[0] if argv else '<empty>'}"
        output = detail + "\n"
    except subprocess.TimeoutExpired as exc:
        exit_code = 124
        status = STATUS_ERROR
        detail = f"timed out after {timeout}s"
        captured = exc.stdout or ""
        if isinstance(captured, bytes):
            captured = captured.decode("utf-8", "replace")
        output = str(captured) + f"\n{detail}\n"
    except OSError as exc:  # permission denied, invalid executable, ...
        exit_code = 126
        status = STATUS_ERROR
        detail = f"could not execute {argv[0] if argv else '<empty>'}: {exc}"
        output = detail + "\n"

    duration = time.monotonic() - started
    log_path.write_text(
        f"$ {' '.join(argv)}\n{output.rstrip()}\n" if output.strip() else f"$ {' '.join(argv)}\n",
        encoding="utf-8",
    )

    result = Result(
        name=name,
        argv=argv,
        exit=exit_code,
        duration_s=round(duration, 3),
        log=log_path,
        status=status,
        detail=detail,
        output=output,
    )

    if is_ci():
        print(f"::group::{name} (exit {exit_code}, {duration:.1f}s)")
        if output:
            sys.stdout.write(output if output.endswith("\n") else output + "\n")
        print("::endgroup::")
        if exit_code != 0:
            summary = _tail(output) or detail
            emit_error(summary, title=name)
    else:
        marker = "ok" if exit_code == 0 else "FAIL"
        print(f"[{marker}] {name} (exit {exit_code}, {duration:.2f}s)")
        if exit_code != 0 and output:
            print(_tail(output), file=sys.stderr)
    return result
