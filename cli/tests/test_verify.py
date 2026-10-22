"""The verification step table and failure aggregation."""

from __future__ import annotations

import json
from pathlib import Path

from support import (
    FakeRunner,
    make_unity_tree,
    write_config,
    write_coverage_artifacts,
    write_text,
)

from devplatform import procs, unity, verify
from devplatform.config import load_config
from devplatform.errors import DevctlError

PLATFORM_HOME = Path(__file__).resolve().parents[2]


def config_for(
    root: Path, profile: str, coverage: dict | None = None, unity_extra: dict | None = None
):
    write_config(
        root,
        profile=profile,
        coverage=coverage or {"minimum": 0, "enabled": True},
        unity=unity_extra or {},
    )
    return load_config(root, cli_profile=profile)


def summaries(root: Path):
    return sorted(root.glob("*/summary.json"))


def test_python_plan_argv(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    config = config_for(root, "python")
    reports = tmp_path / "reports"
    steps = verify.plan("python", root, reports, config, 85)
    assert [step.name for step in steps] == [
        "uv-sync",
        "ruff-check",
        "ruff-format",
        "pytest",
        "coverage",
    ]
    assert steps[0].argv == ["uv", "sync", "--frozen"]
    assert steps[1].argv == [
        "uv",
        "run",
        "--frozen",
        "ruff",
        "check",
        "--output-format=github",
        ".",
    ]
    pytest_argv = steps[3].argv
    assert pytest_argv[:4] == ["uv", "run", "--frozen", "pytest"]
    assert f"--junitxml={reports / 'python' / 'junit.xml'}" in pytest_argv
    assert f"--cov-report=xml:{reports / 'python' / 'coverage.xml'}" in pytest_argv
    assert "--cov-fail-under=85" in pytest_argv
    assert steps[4].kind == "coverage"


def test_typescript_plan_argv(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    config = config_for(root, "typescript")
    steps = verify.plan("typescript", root, tmp_path / "reports", config, 70)
    assert [step.name for step in steps] == [
        "npm-ci",
        "tsc",
        "eslint",
        "prettier",
        "vitest",
        "coverage",
    ]
    assert steps[0].argv == ["npm", "ci", "--no-audit", "--no-fund"]
    assert steps[2].argv == ["npx", "eslint", ".", "--max-warnings=0"]
    assert steps[4].argv[-1].startswith("--outputFile.junit=")


def test_dotnet_plan_argv(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    config = config_for(root, "dotnet")
    reports = tmp_path / "reports"
    steps = verify.plan("dotnet", root, reports, config, 60)
    assert [step.name for step in steps] == [
        "dotnet-restore",
        "dotnet-build",
        "dotnet-format",
        "dotnet-test",
        "coverage",
    ]
    assert steps[1].argv == ["dotnet", "build", "--no-restore", "-warnaserror"]
    test_argv = steps[3].argv
    assert "--collect:XPlat Code Coverage" in test_argv
    assert str(reports / "dotnet") in test_argv
    logger = test_argv[test_argv.index("--logger") + 1]
    assert logger.startswith("trx;LogFileName=")
    assert logger.endswith("test.trx")


def test_unity_plans(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    config = config_for(root, "unity")
    reports = tmp_path / "reports"
    steps = verify.plan("unity", root, reports, config, 50)
    assert [step.name for step in steps] == [
        "unity-integrity",
        "unity-editmode",
        "unity-playmode",
        "unity-coverage",
    ]
    steps = verify.plan("unity", root, reports, config, 50, unity_build=True, upload_coverage=True)
    assert [step.name for step in steps] == [
        "unity-integrity",
        "unity-editmode",
        "unity-playmode",
        "unity-coverage",
        "unity-build",
        "unity-coverage-upload",
    ]
    assets = verify.plan("unity-assets", root, reports, config, 0)
    assert [step.name for step in assets] == ["unity-integrity"]


def test_coverage_disabled_removes_step(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    config = config_for(root, "python", coverage={"minimum": 0, "enabled": False})
    steps = verify.plan("python", root, tmp_path / "reports", config, 0)
    assert [step.name for step in steps][-1] == "pytest"


def test_python_success_writes_summary(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    config = config_for(root, "python")
    reports = tmp_path / "reports"
    runner = FakeRunner(
        on_run=lambda name, argv, cwd: write_coverage_artifacts(name, argv, root, reports, "python")
    )
    code = verify.run_verify("python", root, reports, config, PLATFORM_HOME, 80, runner=runner)
    assert code == 0
    summary = json.loads((reports / "python/summary.json").read_text(encoding="utf-8"))
    assert summary["profile"] == "python"
    assert summary["status"] == "passed"
    assert [step["name"] for step in summary["steps"]] == [
        "uv-sync",
        "ruff-check",
        "ruff-format",
        "pytest",
        "coverage",
    ]
    assert summary["coverage"]["line"] == 90.0
    assert summary["coverage"]["minimum"] == 80
    assert summary["tests"] == {"passed": 3, "failed": 0, "skipped": 0}
    assert summary["artifacts"]
    assert (reports / "python/summary.md").is_file()


def test_python_failure_aggregation(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    config = config_for(root, "python")
    reports = tmp_path / "reports"
    runner = FakeRunner({"ruff-check": 1, "pytest": 1})
    code = verify.run_verify("python", root, reports, config, PLATFORM_HOME, 80, runner=runner)
    assert code == 1
    summary = json.loads((reports / "python/summary.json").read_text(encoding="utf-8"))
    statuses = {step["name"]: step["status"] for step in summary["steps"]}
    assert statuses["ruff-check"] == "failed"
    assert statuses["pytest"] == "failed"
    assert statuses["coverage"] == "skipped"


def test_fail_fast_skips_remaining(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    config = config_for(root, "python")
    reports = tmp_path / "reports"
    runner = FakeRunner({"ruff-check": 1})
    code = verify.run_verify(
        "python", root, reports, config, PLATFORM_HOME, 0, fail_fast=True, runner=runner
    )
    assert code == 1
    summary = json.loads((reports / "python/summary.json").read_text(encoding="utf-8"))
    statuses = {step["name"]: step["status"] for step in summary["steps"]}
    assert statuses["uv-sync"] == "passed"
    assert statuses["ruff-check"] == "failed"
    assert statuses["ruff-format"] == "skipped"
    assert statuses["pytest"] == "skipped"
    assert [call["name"] for call in runner.calls] == ["uv-sync", "ruff-check"]


def test_missing_coverage_report_is_execution_error(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    config = config_for(root, "python")
    reports = tmp_path / "reports"
    code = verify.run_verify("python", root, reports, config, PLATFORM_HOME, 0, runner=FakeRunner())
    assert code == 3
    summary = json.loads((reports / "python/summary.json").read_text(encoding="utf-8"))
    step = next(item for item in summary["steps"] if item["name"] == "coverage")
    assert step["status"] == "error"
    assert step["exit"] == 3


def test_coverage_below_minimum_fails(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    config = config_for(root, "python")
    reports = tmp_path / "reports"

    def low(name, argv, cwd):
        if name == "pytest":
            write_text(reports / "python/junit.xml", "<testsuite tests='1' />")
            write_text(reports / "python/coverage.xml", '<coverage line-rate="0.5"></coverage>')

    code = verify.run_verify(
        "python", root, reports, config, PLATFORM_HOME, 80, runner=FakeRunner(on_run=low)
    )
    assert code == 1
    summary = json.loads((reports / "python/summary.json").read_text(encoding="utf-8"))
    assert summary["coverage"]["line"] == 50.0
    step = next(item for item in summary["steps"] if item["name"] == "coverage")
    assert step["status"] == "failed"


def test_typescript_success(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    config = config_for(root, "typescript")
    reports = tmp_path / "reports"
    runner = FakeRunner(
        on_run=lambda name, argv, cwd: write_coverage_artifacts(
            name, argv, root, reports, "typescript"
        )
    )
    code = verify.run_verify("typescript", root, reports, config, PLATFORM_HOME, 80, runner=runner)
    assert code == 0
    summary = json.loads((reports / "typescript/summary.json").read_text(encoding="utf-8"))
    assert summary["coverage"]["line"] == 91.5
    assert summary["tests"]["passed"] == 2


def test_dotnet_success(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    config = config_for(root, "dotnet")
    reports = tmp_path / "reports"
    runner = FakeRunner(
        on_run=lambda name, argv, cwd: write_coverage_artifacts(name, argv, root, reports, "dotnet")
    )
    code = verify.run_verify("dotnet", root, reports, config, PLATFORM_HOME, 60, runner=runner)
    assert code == 0
    summary = json.loads((reports / "dotnet/summary.json").read_text(encoding="utf-8"))
    assert summary["coverage"]["line"] == 88.0
    assert summary["tests"] == {"passed": 4, "failed": 0, "skipped": 0}


def test_unity_verify_with_mocked_editor(tmp_path: Path, monkeypatch) -> None:
    root = make_unity_tree(tmp_path / "project")
    config = config_for(root, "unity")
    reports = tmp_path / "reports"
    for platform in ("editmode", "playmode"):
        write_text(
            reports / f"unity/coverage-{platform}/Report/Summary.xml",
            "<CoverageReport><Summary><Coveredlines>45</Coveredlines>"
            "<Coverablelines>50</Coverablelines></Summary></CoverageReport>",
        )

    monkeypatch.setattr(unity, "require_editor", lambda config, root: Path("Unity.exe"))
    monkeypatch.setattr(unity, "check_editor_version", lambda config, editor: None)
    monkeypatch.setattr(unity, "handle_lock", lambda root: False)

    def fake_run_tests(root, reports, config, platform, editor, runner=None, profile="unity"):
        return unity.UnityStep(
            f"unity-{platform.lower()}",
            procs.STATUS_PASSED,
            0,
            None,
            "ok",
            {"passed": 10, "failed": 0, "skipped": 1},
        )

    monkeypatch.setattr(unity, "run_tests", fake_run_tests)
    code = verify.run_verify("unity", root, reports, config, PLATFORM_HOME, 0)
    assert code == 0
    summary = json.loads((reports / "unity/summary.json").read_text(encoding="utf-8"))
    assert summary["coverage"]["line"] == 90.0
    assert summary["tests"] == {"passed": 20, "failed": 0, "skipped": 2}
    names = [step["name"] for step in summary["steps"]]
    assert names == ["unity-integrity", "unity-editmode", "unity-playmode", "unity-coverage"]


def test_unity_editor_missing_is_precondition(tmp_path: Path, monkeypatch) -> None:
    root = make_unity_tree(tmp_path / "project")
    config = config_for(root, "unity")
    reports = tmp_path / "reports"

    def missing(config, root):
        raise DevctlError(2, "Unity 6000.5.1f1 editor not found; set unity.editorPath")

    monkeypatch.setattr(unity, "require_editor", missing)
    code = verify.run_verify("unity", root, reports, config, PLATFORM_HOME, 0, runner=FakeRunner())
    assert code == 2
    summary = json.loads((reports / "unity/summary.json").read_text(encoding="utf-8"))
    assert summary["steps"][0]["status"] == "passed"
    assert summary["steps"][1]["status"] == "error"
    assert summary["steps"][1]["exit"] == 2


def test_aggregate_exit_precedence() -> None:
    def outcome(status: str, code: int) -> verify.Outcome:
        return verify.Outcome("x", status, code, 0.0, None)

    assert verify.aggregate_exit([outcome("passed", 0)]) == 0
    assert verify.aggregate_exit([outcome("failed", 1)]) == 1
    assert verify.aggregate_exit([outcome("error", 3), outcome("failed", 1)]) == 3
    assert verify.aggregate_exit([outcome("error", 2), outcome("error", 3)]) == 2
    assert verify.aggregate_exit([outcome("error", 4), outcome("error", 3)]) == 4
    assert verify.aggregate_exit([outcome("skipped", 0)]) == 0


def test_summary_markdown_contains_table(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    config = config_for(root, "python")
    reports = tmp_path / "reports"
    runner = FakeRunner(
        on_run=lambda name, argv, cwd: write_coverage_artifacts(name, argv, root, reports, "python")
    )
    verify.run_verify("python", root, reports, config, PLATFORM_HOME, 0, runner=runner)
    markdown = (reports / "python/summary.md").read_text(encoding="utf-8")
    assert "| step | status | exit | duration | detail |" in markdown
    assert "Coverage: 90.0%" in markdown
