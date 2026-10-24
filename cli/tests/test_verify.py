"""The Unity verification step table and failure aggregation."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from support import (
    FakeRunner,
    make_unity_tree,
    write_config,
    write_text,
)

from devplatform import procs, unity, verify
from devplatform.config import load_config
from devplatform.errors import DevctlError


def config_for(root: Path, profile: str = "unity", coverage: dict | None = None):
    write_config(
        root,
        profile=profile,
        coverage=coverage or {"minimum": 0, "enabled": True},
    )
    return load_config(root, cli_profile=profile)


def mock_editor(monkeypatch) -> None:
    monkeypatch.setattr(unity, "require_editor", lambda config, root: Path("Unity.exe"))
    monkeypatch.setattr(unity, "check_editor_version", lambda config, editor: None)
    monkeypatch.setattr(unity, "handle_lock", lambda root: False)


def test_unity_plans(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    config = config_for(root)
    reports = root / "artifacts/reports"
    steps = verify.plan("unity", reports, config)
    assert [step.name for step in steps] == [
        "unity-integrity",
        "unity-editmode",
        "unity-playmode",
        "unity-coverage",
    ]
    steps = verify.plan("unity", reports, config, unity_build=True, upload_coverage=True)
    assert [step.name for step in steps] == [
        "unity-integrity",
        "unity-editmode",
        "unity-playmode",
        "unity-coverage",
        "unity-build",
        "unity-coverage-upload",
    ]
    assets = verify.plan("unity-assets", reports, config)
    assert [step.name for step in assets] == ["unity-integrity"]


def test_coverage_disabled_removes_step(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    config = config_for(root, coverage={"minimum": 0, "enabled": False})
    steps = verify.plan("unity", tmp_path / "reports", config)
    assert [step.name for step in steps] == [
        "unity-integrity",
        "unity-editmode",
        "unity-playmode",
    ]


def test_unity_verify_with_mocked_editor(tmp_path: Path, monkeypatch) -> None:
    root = make_unity_tree(tmp_path / "project")
    config = config_for(root)
    reports = root / "artifacts/reports"
    mock_editor(monkeypatch)

    def fake_run_tests(root, reports, config, platform, editor, runner=None, profile="unity"):
        if platform == "PlayMode":
            write_text(
                reports / "unity/coverage/Report/Summary.xml",
                "<CoverageReport><Summary><Coveredlines>45</Coveredlines>"
                "<Coverablelines>50</Coverablelines></Summary></CoverageReport>",
            )
        return unity.UnityStep(
            f"unity-{platform.lower()}",
            procs.STATUS_PASSED,
            0,
            None,
            "ok",
            {
                "passed": 10,
                "failed": 0,
                "skipped": 1,
                "flaky": ["Tests.Flaky"] if platform == "PlayMode" else [],
            },
        )

    monkeypatch.setattr(unity, "run_tests", fake_run_tests)
    code = verify.run_verify("unity", root, reports, config, 0)
    assert code == 0
    summary = json.loads((reports / "unity/summary.json").read_text(encoding="utf-8"))
    assert summary["coverage"]["line"] == 90.0
    assert summary["tests"] == {
        "passed": 20,
        "failed": 0,
        "skipped": 2,
        "flaky": ["Tests.Flaky"],
    }
    names = [step["name"] for step in summary["steps"]]
    assert names == ["unity-integrity", "unity-editmode", "unity-playmode", "unity-coverage"]


def test_unity_editor_missing_is_precondition(tmp_path: Path, monkeypatch) -> None:
    root = make_unity_tree(tmp_path / "project")
    config = config_for(root)
    reports = root / "artifacts/reports"

    def missing(config, root):
        raise DevctlError(2, "Unity 6000.5.1f1 editor not found; set unity.editorPath")

    monkeypatch.setattr(unity, "require_editor", missing)
    code = verify.run_verify("unity", root, reports, config, 0, runner=FakeRunner())
    assert code == 2
    summary = json.loads((reports / "unity/summary.json").read_text(encoding="utf-8"))
    assert summary["steps"][0]["status"] == "passed"
    assert summary["steps"][1]["status"] == "error"
    assert summary["steps"][1]["exit"] == 2


def test_fail_fast_skips_remaining(tmp_path: Path) -> None:
    root = make_unity_tree(tmp_path / "project")
    scene = root / "Assets/Scenes/SampleScene.unity"
    scene.write_text(
        scene.read_text(encoding="utf-8").replace("m_Name: Main Camera", "m_Name: Renamed"),
        encoding="utf-8",
    )
    config = config_for(root)
    reports = root / "artifacts/reports"
    runner = FakeRunner()
    code = verify.run_verify("unity", root, reports, config, 0, fail_fast=True, runner=runner)
    assert code == 1
    summary = json.loads((reports / "unity/summary.json").read_text(encoding="utf-8"))
    steps = {item["name"]: item for item in summary["steps"]}
    assert steps["unity-integrity"]["status"] == "failed"
    assert steps["unity-editmode"]["status"] == "skipped"
    assert steps["unity-editmode"]["detail"] == "skipped after failure (--fail-fast)"
    assert runner.calls == []


def test_aggregate_exit_precedence() -> None:
    def outcome(status: str, code: int) -> verify.Outcome:
        return verify.Outcome("x", status, code, 0.0, None)

    assert verify.aggregate_exit([outcome("passed", 0)]) == 0
    assert verify.aggregate_exit([outcome("failed", 1)]) == 1
    assert verify.aggregate_exit([outcome("error", 3), outcome("failed", 1)]) == 3
    assert verify.aggregate_exit([outcome("error", 2), outcome("error", 3)]) == 2
    assert verify.aggregate_exit([outcome("error", 4), outcome("error", 3)]) == 4
    assert verify.aggregate_exit([outcome("skipped", 0)]) == 0


def test_verify_clears_previous_reports(tmp_path: Path) -> None:
    root = make_unity_tree(tmp_path / "project")
    config = config_for(root, "unity-assets")
    reports = root / "artifacts/reports"
    stale = reports / "unity-assets/stale.json"
    write_text(stale, "{}")
    code = verify.run_verify("unity-assets", root, reports, config, 0)
    assert code == 0
    assert not stale.exists()
    summary = json.loads((reports / "unity-assets/summary.json").read_text(encoding="utf-8"))
    assert summary["steps"][0]["name"] == "unity-integrity"
    assert summary["steps"][0]["status"] == "passed"
    assert summary["coverage"]["line"] is None
    assert summary["tests"]["passed"] == 0


def test_verify_refuses_reports_outside_root(tmp_path: Path) -> None:
    root = make_unity_tree(tmp_path / "project")
    config = config_for(root, "unity-assets")
    with pytest.raises(DevctlError) as excinfo:
        verify.run_verify(
            "unity-assets",
            root,
            tmp_path / "external-reports",
            config,
            0,
            runner=FakeRunner(),
        )
    assert excinfo.value.code == 2
    assert "outside root" in excinfo.value.message


def test_unity_integrity_does_not_block_tests_but_editmode_blocks_coverage(
    tmp_path: Path, monkeypatch
) -> None:
    root = make_unity_tree(tmp_path / "project")
    scene = root / "Assets/Scenes/SampleScene.unity"
    scene.write_text(
        scene.read_text(encoding="utf-8").replace("m_Name: Main Camera", "m_Name: Renamed"),
        encoding="utf-8",
    )
    config = config_for(root)
    reports = root / "artifacts/reports"
    mock_editor(monkeypatch)
    calls: list[str] = []

    def fake_run_tests(root, reports, config, platform, editor, runner=None, profile="unity"):
        calls.append(platform)
        if platform == "EditMode":
            return unity.UnityStep(
                "unity-editmode",
                procs.STATUS_FAILED,
                1,
                None,
                "1 failed",
                {"passed": 1, "failed": 1, "skipped": 0},
            )
        return unity.UnityStep(
            "unity-playmode",
            procs.STATUS_PASSED,
            0,
            None,
            "passed",
            {"passed": 5, "failed": 0, "skipped": 0},
        )

    monkeypatch.setattr(unity, "run_tests", fake_run_tests)
    code = verify.run_verify("unity", root, reports, config, 0)
    assert code == 1
    assert calls == ["EditMode", "PlayMode"]
    summary = json.loads((reports / "unity/summary.json").read_text(encoding="utf-8"))
    steps = {item["name"]: item for item in summary["steps"]}
    assert steps["unity-integrity"]["status"] == "failed"
    assert steps["unity-editmode"]["status"] == "failed"
    assert steps["unity-playmode"]["status"] == "passed"
    assert steps["unity-coverage"]["status"] == "skipped"
    assert steps["unity-coverage"]["detail"] == "prerequisite unity-editmode failed"


def test_summary_markdown_contains_table(tmp_path: Path, monkeypatch) -> None:
    root = make_unity_tree(tmp_path / "project")
    config = config_for(root)
    reports = root / "artifacts/reports"
    mock_editor(monkeypatch)
    monkeypatch.setattr(
        unity,
        "run_tests",
        lambda *args, **kwargs: unity.UnityStep(
            "unity-test",
            procs.STATUS_PASSED,
            0,
            None,
            "passed",
            {"passed": 3, "failed": 0, "skipped": 0},
        ),
    )
    verify.run_verify("unity", root, reports, config, 0)
    markdown = (reports / "unity/summary.md").read_text(encoding="utf-8")
    assert "| step | status | exit | duration | detail |" in markdown
    assert "Tests: 6 passed" in markdown
