"""Approach 12 gate fixtures: failing repositories must produce exit 1."""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

from support import (
    FakeRunner,
    install_uv_stub,
    write_config,
    write_text,
)

from devplatform import cli, verify
from devplatform.config import load_config

FIXTURES = Path(__file__).parent / "fixtures" / "gates"
PLATFORM_HOME = Path(__file__).resolve().parents[2]


def test_python_bad_fixture_files() -> None:
    source = (FIXTURES / "python-bad/src/python_bad/__init__.py").read_text(encoding="utf-8")
    assert "import os" in source
    assert "noqa" not in source
    test = (FIXTURES / "python-bad/tests/test_fail.py").read_text(encoding="utf-8")
    assert "assert 1 == 2" in test


def test_python_bad_gate_via_subprocess(tmp_path: Path, monkeypatch, capsys) -> None:
    root = tmp_path / "repo"
    shutil.copytree(FIXTURES / "python-bad", root)
    config_path = tmp_path / "python.json"
    config_path.write_text(
        json.dumps(
            {
                "profile": "python",
                "coverage": {"minimum": 0, "enabled": True},
            }
        ),
        encoding="utf-8",
    )
    stub = install_uv_stub(tmp_path / "stubs")
    monkeypatch.setenv("PATH", str(stub.parent) + os.pathsep + os.environ["PATH"])
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    reports = root / "artifacts/reports"

    code = cli.main(
        [
            "--root",
            str(root),
            "--config",
            str(config_path),
            "--reports",
            str(reports),
            "verify",
            "--profile",
            "python",
        ]
    )
    assert code == 1
    summary = json.loads((reports / "python/summary.json").read_text(encoding="utf-8"))
    statuses = {step["name"]: step["status"] for step in summary["steps"]}
    assert statuses["uv-sync"] == "passed"
    assert statuses["ruff-check"] == "failed"
    assert statuses["pytest"] == "failed"
    assert statuses["coverage"] == "skipped"

    output = capsys.readouterr().out
    assert "::error title=ruff-check::" in output
    assert "::error title=pytest::" in output
    assert "F401" in output


def test_typescript_bad_gate(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    shutil.copytree(FIXTURES / "typescript-bad", root)
    source = (root / "src/bad.ts").read_text(encoding="utf-8")
    assert "any" in source
    assert "no-explicit-any" in (root / "eslint.config.js").read_text(encoding="utf-8")
    write_text(
        root / "coverage/coverage-summary.json", json.dumps({"total": {"lines": {"pct": 95}}})
    )
    write_config(root, profile="typescript")
    config = load_config(root, cli_profile="typescript")
    reports = root / "artifacts/reports"

    steps = verify.plan("typescript", root, reports, config, 0)
    names = [step.name for step in steps]
    assert names == ["npm-ci", "tsc", "eslint", "prettier", "vitest", "coverage"]
    runner = FakeRunner({"eslint": 1, "prettier": 1})
    code = verify.run_verify("typescript", root, reports, config, PLATFORM_HOME, 0, runner=runner)
    assert code == 1
    summary = json.loads((reports / "typescript/summary.json").read_text(encoding="utf-8"))
    statuses = {step["name"]: step["status"] for step in summary["steps"]}
    assert statuses["eslint"] == "failed"
    assert statuses["prettier"] == "failed"
    assert statuses["coverage"] == "passed"


def test_dotnet_bad_gate(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    shutil.copytree(FIXTURES / "dotnet-bad", root)
    source = (root / "src/Bad/AsyncWork.cs").read_text(encoding="utf-8")
    assert "await Task.Delay(1);" in source
    assert "CA2007" in (root / ".editorconfig").read_text(encoding="utf-8")
    assert "TreatWarningsAsErrors" in (root / "Directory.Build.props").read_text(encoding="utf-8")
    write_config(root, profile="dotnet")
    config = load_config(root, cli_profile="dotnet")
    reports = root / "artifacts/reports"

    steps = verify.plan("dotnet", root, reports, config, 0)
    build_argv = next(step.argv for step in steps if step.name == "dotnet-build")
    assert "-warnaserror" in build_argv
    format_argv = next(step.argv for step in steps if step.name == "dotnet-format")
    assert "--verify-no-changes" in format_argv

    runner = FakeRunner({"dotnet-build": 1, "dotnet-test": 1})
    code = verify.run_verify("dotnet", root, reports, config, PLATFORM_HOME, 0, runner=runner)
    assert code == 1
    summary = json.loads((reports / "dotnet/summary.json").read_text(encoding="utf-8"))
    statuses = {step["name"]: step["status"] for step in summary["steps"]}
    assert statuses["dotnet-build"] == "failed"
    assert statuses["coverage"] == "skipped"


def test_annotations_only_in_ci(tmp_path: Path, monkeypatch, capsys) -> None:
    root = tmp_path / "repo"
    shutil.copytree(FIXTURES / "python-bad", root)
    config_path = tmp_path / "python.json"
    config_path.write_text(json.dumps({"profile": "python"}), encoding="utf-8")
    stub = install_uv_stub(tmp_path / "stubs")
    monkeypatch.setenv("PATH", str(stub.parent) + os.pathsep + os.environ["PATH"])
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    code = cli.main(
        [
            "--root",
            str(root),
            "--config",
            str(config_path),
            "--reports",
            str(root / "artifacts/reports"),
            "verify",
            "--profile",
            "python",
        ]
    )
    assert code == 1
    output = capsys.readouterr().out
    assert "::error title=ruff-check::" not in output
