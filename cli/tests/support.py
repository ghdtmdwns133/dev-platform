"""Shared helpers for the devctl test suite."""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Callable
from pathlib import Path

from devplatform import procs

SCENE_REL = "Assets/Scenes/SampleScene.unity"
SCENE_GUID = "99c9720ab356a0642a771bea13969a05"

SCENE_DEFAULT = """%YAML 1.1
%TAG !u! tag:unity3d.com,2011:
--- !u!1 &330585543
GameObject:
  m_ObjectHideFlags: 0
  m_Name: Main Camera
  m_IsActive: 1
--- !u!20 &330585545
Camera:
  m_ObjectHideFlags: 0
  m_GameObject: {fileID: 330585543}
  m_Enabled: 1
--- !u!1 &832575517
GameObject:
  m_ObjectHideFlags: 0
  m_Name: Global Volume
  m_IsActive: 1
--- !u!114 &832575519
MonoBehaviour:
  m_ObjectHideFlags: 0
  m_GameObject: {fileID: 832575517}
  m_Enabled: 1
  m_IsGlobal: 1
  priority: 0
"""

BUILD_SETTINGS_DEFAULT = """%YAML 1.1
%TAG !u! tag:unity3d.com,2011:
--- !u!1045 &1
EditorBuildSettings:
  m_ObjectHideFlags: 0
  serializedVersion: 2
  m_Scenes:
  - enabled: 1
    path: Assets/Scenes/SampleScene.unity
    guid: 99c9720ab356a0642a771bea13969a05
  m_configObjects: {}
"""


def write_text(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")
    return path


def write_meta(path: Path, guid: str | None = None) -> Path:
    import hashlib

    if guid is None:
        digest = hashlib.md5(path.as_posix().encode(), usedforsecurity=False).hexdigest()
        guid = digest
    return write_text(path.with_name(path.name + ".meta"), f"fileFormatVersion: 2\nguid: {guid}\n")


def make_unity_tree(
    root: Path,
    *,
    scene: str | None = None,
    build_settings: str | None = None,
    editorconfig: bool = True,
    version: str = "6000.5.1f1",
) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    write_text(root / SCENE_REL, scene if scene is not None else SCENE_DEFAULT)
    write_text(root / (SCENE_REL + ".meta"), f"fileFormatVersion: 2\nguid: {SCENE_GUID}\n")
    write_text(
        root / "Assets/Scenes.meta",
        "fileFormatVersion: 2\nguid: aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\n",
    )
    (root / "Assets/MyScripts").mkdir(parents=True, exist_ok=True)
    write_text(root / "Packages/manifest.json", json.dumps({"dependencies": {}}) + "\n")
    write_text(root / "Packages/packages-lock.json", json.dumps({"dependencies": {}}) + "\n")
    write_text(
        root / "ProjectSettings/ProjectVersion.txt",
        f"m_EditorVersion: {version}\nm_EditorVersionWithRevision: {version} (deadbeef)\n",
    )
    write_text(
        root / "ProjectSettings/EditorBuildSettings.asset",
        build_settings if build_settings is not None else BUILD_SETTINGS_DEFAULT,
    )
    if editorconfig:
        write_text(root / ".editorconfig", "root = true\n")
    return root


def write_config(root: Path, profile: str = "unity", unity: dict | None = None, **extra) -> Path:
    data: dict = {
        "profile": profile,
        "reports": "artifacts/reports",
        "coverage": {"minimum": 0, "enabled": True},
        "unity": unity or {},
    }
    data.update(extra)
    path = root / ".devplatform/config.json"
    write_text(path, json.dumps(data, indent=2) + "\n")
    return path


class FakeRunner:
    """Records argv and returns scripted exit codes; optional per-step hooks."""

    def __init__(
        self,
        exits: dict[str, int] | None = None,
        on_run: Callable[[str, list[str], Path], None] | None = None,
    ) -> None:
        self.exits = exits or {}
        self.on_run = on_run
        self.calls: list[dict] = []

    def __call__(self, name, argv, cwd, log_path, env=None, **kwargs):
        log_path = Path(log_path)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        self.calls.append(
            {"name": name, "argv": list(argv), "env": env, "cwd": Path(cwd), "log": log_path}
        )
        if self.on_run is not None:
            self.on_run(name, list(argv), Path(cwd))
        code = int(self.exits.get(name, 0))
        log_path.write_text(f"$ {' '.join(map(str, argv))}\n", encoding="utf-8")
        return procs.Result(
            name=name,
            argv=list(argv),
            exit=code,
            duration_s=0.02,
            log=log_path,
            status=procs.STATUS_PASSED if code == 0 else procs.STATUS_FAILED,
        )


def write_coverage_artifacts(
    name: str, argv: list[str], root: Path, reports: Path, profile: str
) -> None:
    """Simulate the artifacts a passing tool would produce."""
    profile_dir = reports / profile
    if name == "pytest":
        write_text(
            profile_dir / "junit.xml",
            '<testsuite tests="3" failures="0" errors="0" skipped="0"></testsuite>',
        )
        write_text(profile_dir / "coverage.xml", '<coverage line-rate="0.9"></coverage>')
    elif name == "vitest":
        write_text(
            profile_dir / "junit.xml",
            '<testsuite tests="2" failures="0" errors="0" skipped="0"></testsuite>',
        )
        write_text(
            root / "coverage/coverage-summary.json",
            json.dumps({"total": {"lines": {"pct": 91.5}}}),
        )
    elif name == "dotnet-test":
        write_text(
            profile_dir / "test.trx",
            '<TestRun><ResultSummary><Counters total="6" passed="4" failed="1" '
            'notExecuted="1" inconclusive="0"/></ResultSummary></TestRun>',
        )
        write_text(
            profile_dir / "abc123/coverage.cobertura.xml",
            '<coverage line-rate="0.88"></coverage>',
        )


def install_uv_stub(directory: Path) -> Path:
    """Put a fake ``uv`` first on PATH that reports lint/pytest failures."""
    directory.mkdir(parents=True, exist_ok=True)
    script = directory / "uv_stub.py"
    script.write_text(
        "import subprocess, sys\n"
        "args = sys.argv[1:]\n"
        "if not args:\n"
        "    sys.exit(0)\n"
        "if args[0] == 'sync':\n"
        "    sys.exit(0)\n"
        "if args[0] == 'run':\n"
        "    rest = args[1:]\n"
        "    while rest and rest[0] in {'--frozen', '--project'}:\n"
        "        rest = rest[2:] if rest[0] == '--project' else rest[1:]\n"
        "    if rest and rest[0] == 'ruff' and 'check' in rest:\n"
        "        sys.stderr.write('src/bad.py:1:1: F401 `os` imported but unused\\n')\n"
        "        sys.exit(1)\n"
        "    if rest and rest[0] == 'ruff':\n"
        "        sys.exit(0)\n"
        "    if rest and rest[0] == 'pytest':\n"
        "        sys.stderr.write('1 failed, 0 passed\\n')\n"
        "        sys.exit(1)\n"
        "sys.exit(0)\n",
        encoding="utf-8",
    )
    if os.name == "nt":
        shim = directory / "uv.cmd"
        shim.write_text(
            f'@echo off\r\n"{sys.executable}" "{script}" %*\r\n', encoding="utf-8", newline=""
        )
    else:
        shim = directory / "uv"
        shim.write_text(
            f'#!/bin/sh\nexec "{sys.executable}" "{script}" "$@"\n',
            encoding="utf-8",
            newline="\n",
        )
        shim.chmod(0o755)
    return shim


def install_uv_ruff_proxy(directory: Path) -> Path:
    """A fake ``uv`` that forwards ``run --frozen ruff ...`` to the real ruff."""
    directory.mkdir(parents=True, exist_ok=True)
    script = directory / "uv_proxy.py"
    script.write_text(
        "import shutil, subprocess, sys\n"
        "args = sys.argv[1:]\n"
        "if not args or args[0] != 'run':\n"
        "    sys.exit(0)\n"
        "rest = args[1:]\n"
        "while rest and rest[0] in {'--frozen', '--project'}:\n"
        "    rest = rest[2:] if rest[0] == '--project' else rest[1:]\n"
        "ruff = shutil.which('ruff')\n"
        "if rest and rest[0] == 'ruff' and ruff:\n"
        "    sys.exit(subprocess.call([ruff, *rest[1:]]))\n"
        "sys.exit(0)\n",
        encoding="utf-8",
    )
    if os.name == "nt":
        shim = directory / "uv.cmd"
        shim.write_text(
            f'@echo off\r\n"{sys.executable}" "{script}" %*\r\n', encoding="utf-8", newline=""
        )
    else:
        shim = directory / "uv"
        shim.write_text(
            f'#!/bin/sh\nexec "{sys.executable}" "{script}" "$@"\n',
            encoding="utf-8",
            newline="\n",
        )
        shim.chmod(0o755)
    return shim
