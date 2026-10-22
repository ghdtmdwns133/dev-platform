"""Template rendering for ``devctl init``.

Rendering is atomic: the template is copied and substituted into a temporary
directory next to the destination, every leftover ``__TOKEN__`` is rejected, and
only then is the directory renamed into place.  The shared template is copied
first, then the selected template overrides files with the same path.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from . import hooks, procs
from .errors import EXIT_GATE, EXIT_PRECONDITION, DevctlError

TEMPLATE_PROFILES = {
    "python": ("python", 80),
    "typescript": ("typescript", 80),
    "dotnet": ("dotnet", 70),
    "unity": ("unity", 0),
}

TOKEN_PATTERN = re.compile(r"__[A-Z][A-Z_]*__")
TOKEN_VALUE_PATTERN = re.compile(r"__[A-Z][A-Z_]*__")


def _slug(value: str, separator: str) -> str:
    cleaned = re.sub(r"[^0-9A-Za-z]+", separator, value).strip(separator)
    cleaned = re.sub(re.escape(separator) * 2, separator, cleaned)
    if not cleaned:
        raise DevctlError(EXIT_PRECONDITION, f"cannot derive a name from {value!r}")
    if cleaned[0].isdigit():
        cleaned = f"{separator}{cleaned}"
    return cleaned.lower()


def _replace(text: str, values: dict[str, str]) -> str:
    for key in sorted(values, key=len, reverse=True):
        text = text.replace(f"__{key}__", values[key])
    return text


def _copy_tree(source: Path, target: Path, values: dict[str, str], rendered: list[Path]) -> None:
    for item in sorted(source.rglob("*")):
        relative = item.relative_to(source)
        parts = [_replace(part, values) for part in relative.parts]
        destination = target.joinpath(*parts)
        if item.is_dir():
            destination.mkdir(parents=True, exist_ok=True)
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        raw = item.read_bytes()
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            destination.write_bytes(raw)
        else:
            destination.write_bytes(_replace(text, values).encode("utf-8"))
        rendered.append(destination)


def _unresolved(root: Path) -> list[str]:
    problems: list[str] = []
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        for part in Path(relative).parts:
            for token in TOKEN_VALUE_PATTERN.findall(part):
                problems.append(f"{relative}: {token} (path)")
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            continue
        for token in TOKEN_VALUE_PATTERN.findall(text):
            problems.append(f"{relative}: {token}")
    return problems


def _git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(root), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


def _prepare_git(destination: Path, platform_home: Path) -> None:
    """Initialise a repository and install the hook when safe to do so."""
    if shutil.which("git") is None:
        procs.emit_notice("git not found; skipped repository init and hook installation")
        return
    top = _git(destination, "rev-parse", "--show-toplevel")
    if top.returncode != 0:
        init = _git(destination, "init", "-b", "main")
        if init.returncode != 0:
            procs.emit_warning(f"git init failed: {init.stderr.strip()}")
            return
        hooks.install_hooks(destination, platform_home)
        return
    repository_root = Path(top.stdout.strip())
    if repository_root.resolve() == destination.resolve():
        hooks.install_hooks(destination, platform_home)
    else:
        procs.emit_notice(
            f"destination is inside the existing repository {repository_root}; "
            "skipped git init and hook installation"
        )


def init(
    template: str,
    name: str,
    dest: Path,
    platform_home: Path,
    owner: str = "ghdtmdwns133",
    ref: str = "v1",
    min_coverage: int | None = None,
    enable_codecov: bool = False,
    private: bool = False,
    force: bool = False,
) -> Path:
    if template not in TEMPLATE_PROFILES:
        raise DevctlError(
            EXIT_PRECONDITION,
            f"unknown template {template!r}; choose from {sorted(TEMPLATE_PROFILES)}",
        )
    profile, default_minimum = TEMPLATE_PROFILES[template]
    templates_root = Path(platform_home) / "templates"
    if not (templates_root / template).is_dir():
        raise DevctlError(
            EXIT_PRECONDITION, f"template directory not found: {templates_root / template}"
        )
    destination = Path(dest).expanduser()
    if not destination.is_absolute():
        destination = Path.cwd() / destination
    destination = destination.resolve()

    if destination.exists() and not destination.is_dir():
        raise DevctlError(EXIT_GATE, f"destination is not a directory: {destination}")
    if destination.is_dir() and any(destination.iterdir()) and not force:
        raise DevctlError(
            EXIT_GATE, f"destination is not empty: {destination} (use --force to replace it)"
        )

    values = {
        "PROJECT_NAME": name,
        "PROJECT_SLUG": _slug(name, "-"),
        "PACKAGE": _slug(name, "_"),
        "OWNER": owner,
        "PLATFORM_REF": ref,
        "PROFILE": profile,
        "MIN_COVERAGE": str(min_coverage if min_coverage is not None else default_minimum),
        "ENABLE_CODECOV": "true" if enable_codecov else "false",
        "UPLOAD_SARIF": "false" if private else "true",
    }

    destination.parent.mkdir(parents=True, exist_ok=True)
    temp = Path(tempfile.mkdtemp(prefix=f".{destination.name}.devctl-", dir=destination.parent))
    rendered: list[Path] = []
    backup: Path | None = None
    try:
        _copy_tree(templates_root / "_shared", temp, values, rendered)
        _copy_tree(templates_root / template, temp, values, rendered)
        unresolved = _unresolved(temp)
        if unresolved:
            listing = "\n".join(unresolved)
            raise DevctlError(EXIT_GATE, f"unresolved template tokens:\n{listing}")
        if destination.exists():
            if not force:
                destination.rmdir()
            else:
                backup = destination.parent / f".{destination.name}.bak-{os.getpid()}"
                if backup.exists():
                    shutil.rmtree(backup)
                destination.rename(backup)
        temp.rename(destination)
        temp = None
    except Exception:
        if backup is not None and backup.exists() and not destination.exists():
            backup.rename(destination)
        raise
    finally:
        if temp is not None and temp.exists():
            shutil.rmtree(temp, ignore_errors=True)
        if backup is not None and backup.exists():
            shutil.rmtree(backup, ignore_errors=True)

    _prepare_git(destination, platform_home)

    print(f"Created {destination} from template {template!r}.")
    print("Next steps:")
    print("  1. git init && git add -A && git commit -m 'Initial commit'")
    print(f"  2. devctl verify --profile {profile}")
    print(f"  3. https://github.com/{owner}/dev-platform/blob/{ref}/docs/SECRETS.md")
    print(
        "  Hooks: `devctl hooks install` runs automatically for a new repository; "
        "run it again after cloning elsewhere."
    )
    return destination
