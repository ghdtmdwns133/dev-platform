"""Toolchain version contract (``devctl versions``).

Semantics fixed by the shared contract:

* python: the interpreter running devctl must be 3.12.x -> FAIL otherwise.
* node: installed major < pinned -> FAIL; installed major > pinned -> WARNING.
  Missing node is a FAIL only for the ``typescript`` profile.
* dotnet: an SDK in the pinned feature band with patch >= pinned -> ok; otherwise
  FAIL only for the ``dotnet`` profile, WARNING elsewhere.
* unity: when an editor for the pinned version is located, the project version
  file must match exactly; no editor is a WARNING unless the profile is ``unity``.
* uv/npm/security tools: mismatches are WARNINGs only.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from . import procs
from .config import Config
from .errors import EXIT_PRECONDITION, DevctlError
from .unity import find_editor

LEVEL_OK = "ok"
LEVEL_WARN = "warn"
LEVEL_FAIL = "fail"

Probe = Callable[[list[str]], "str | None"]


@dataclass
class Check:
    tool: str
    level: str
    expected: str
    found: str

    def render(self) -> str:
        return f"{self.level} {self.tool} expected={self.expected} found={self.found}"


def load_versions(platform_home: Path) -> dict:
    path = Path(platform_home) / "versions.json"
    if not path.is_file():
        raise DevctlError(EXIT_PRECONDITION, f"versions.json not found in {platform_home}")
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, ValueError) as exc:
        raise DevctlError(EXIT_PRECONDITION, f"invalid versions.json: {exc}") from exc
    if not isinstance(data, dict):
        raise DevctlError(EXIT_PRECONDITION, "versions.json must contain an object")
    return data


def _probe(argv: list[str]) -> str | None:
    try:
        completed = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    text = ((completed.stdout or "") + (completed.stderr or "")).strip()
    return text or None


def _extract(text: str | None) -> str | None:
    if not text:
        return None
    match = re.search(r"(\d+)\.(\d+)\.(\d+)", text)
    return match.group(0) if match else None


def _parts(version: str) -> tuple[int, int, int]:
    match = re.search(r"(\d+)\.(\d+)(?:\.(\d+))?", version)
    if not match:
        raise DevctlError(EXIT_PRECONDITION, f"cannot parse version: {version!r}")
    return int(match.group(1)), int(match.group(2)), int(match.group(3) or 0)


def _simple(tool: str, expected: str, raw: str | None) -> Check:
    found = _extract(raw)
    if found is None:
        return Check(tool, LEVEL_WARN, expected, "not found")
    level = LEVEL_OK if found == expected else LEVEL_WARN
    return Check(tool, level, expected, found)


def _check_python(expected: str, version: tuple[int, int, int]) -> Check:
    major, minor, _ = version
    pinned_major, pinned_minor, _ = _parts(expected)
    found = ".".join(str(part) for part in version)
    level = LEVEL_OK if (major, minor) == (pinned_major, pinned_minor) else LEVEL_FAIL
    return Check("python", level, expected, found)


def _check_node(expected: str, profile: str | None, raw: str | None) -> Check:
    pinned_match = re.search(r"\d+", expected)
    if pinned_match is None:
        raise DevctlError(EXIT_PRECONDITION, f"cannot parse node version: {expected!r}")
    pinned = int(pinned_match.group(0))
    found_version = _extract(raw)
    if found_version is None:
        level = LEVEL_FAIL if profile == "typescript" else LEVEL_WARN
        return Check("node", level, expected, "not found")
    installed = _parts(found_version)[0]
    if installed < pinned:
        level = LEVEL_FAIL
    elif installed > pinned:
        level = LEVEL_WARN
    else:
        level = LEVEL_OK
    return Check("node", level, expected, found_version)


def _check_dotnet(expected: str, profile: str | None, raw: str | None) -> Check:
    pinned = _parts(expected)
    installed: list[tuple[int, int, int]] = []
    if raw:
        for match in re.finditer(r"(?m)^\s*(\d+)\.(\d+)\.(\d+)\s", raw):
            installed.append((int(match.group(1)), int(match.group(2)), int(match.group(3))))
    matching = [
        value
        for value in installed
        if value[:2] == pinned[:2] and value[2] // 100 == pinned[2] // 100 and value[2] >= pinned[2]
    ]
    required = profile == "dotnet"
    if matching:
        best = max(matching)
        return Check("dotnet", LEVEL_OK, expected, ".".join(str(part) for part in best))
    found = ", ".join(".".join(str(part) for part in value) for value in installed) or "not found"
    return Check("dotnet", LEVEL_FAIL if required else LEVEL_WARN, expected, found)


def _check_unity(config: Config, profile: str | None, root: Path) -> Check:
    expected = str(config.unity["version"])
    editor = find_editor(config, root)
    required = profile == "unity"
    if editor is None:
        return Check("unity", LEVEL_FAIL if required else LEVEL_WARN, expected, "not found")
    version_file = Path(root) / "ProjectSettings/ProjectVersion.txt"
    if not version_file.is_file():
        return Check("unity", LEVEL_OK, expected, f"editor found ({expected})")
    match = re.search(
        r"(?m)^m_EditorVersion:\s*(\S+)\s*$",
        version_file.read_text(encoding="utf-8", errors="replace"),
    )
    found = match.group(1) if match else "unreadable ProjectVersion.txt"
    level = LEVEL_OK if found == expected else LEVEL_FAIL
    return Check("unity", level, expected, found)


def check_versions(
    config: Config,
    profile: str | None,
    root: Path,
    platform_home: Path,
    probe: Probe | None = None,
    python_version: tuple[int, int, int] | None = None,
) -> list[Check]:
    versions = load_versions(Path(platform_home))
    probe = probe or _probe
    python_pin = str(versions.get("python", {}).get("version", "3.12"))
    node_pin = str(versions.get("node", {}).get("version", "22"))
    dotnet_pin = str(versions.get("dotnet", {}).get("sdk", ""))
    security = versions.get("security", {})
    if not isinstance(security, dict):
        security = {}

    current = python_version or (
        sys.version_info.major,
        sys.version_info.minor,
        sys.version_info.micro,
    )
    return [
        _check_python(python_pin, current),
        _check_node(node_pin, profile, probe(["node", "--version"])),
        _check_dotnet(dotnet_pin, profile, probe(["dotnet", "--list-sdks"])),
        _check_unity(config, profile, Path(root)),
        _simple("uv", str(versions.get("python", {}).get("uv", "")), probe(["uv", "--version"])),
        _simple("npm", str(versions.get("node", {}).get("npm", "")), probe(["npm", "--version"])),
        _simple("trivy", str(security.get("trivy", "")), probe(["trivy", "--version"])),
        _simple("gitleaks", str(security.get("gitleaks", "")), probe(["gitleaks", "version"])),
        _check_zizmor(str(security.get("zizmor", "")), probe),
        _simple(
            "actionlint", str(security.get("actionlint", "")), probe(["actionlint", "--version"])
        ),
    ]


def _check_zizmor(expected: str, probe: Probe) -> Check:
    raw = probe(["zizmor", "--version"])
    if raw is None:
        raw = probe(["uvx", f"zizmor=={expected}", "--version"])
    return _simple("zizmor", expected, raw)


def report_checks(checks: list[Check]) -> int:
    """Print ``ok|warn|fail <tool> ...`` lines (plus CI annotations)."""
    failed = False
    for check in checks:
        print(check.render())
        if check.level == LEVEL_WARN and procs.is_ci():
            procs.emit_warning(check.render()[len(LEVEL_WARN) + 1 :])
        elif check.level == LEVEL_FAIL:
            failed = True
            if procs.is_ci():
                procs.emit_error(check.render()[len(LEVEL_FAIL) + 1 :])
    return 1 if failed else 0


def print_table(checks: list[Check]) -> int:
    print(f"{'tool':<12} {'expected':<14} {'found':<40} state")
    for check in checks:
        print(f"{check.tool:<12} {check.expected:<14} {check.found:<40} {check.level}")
    return 0
