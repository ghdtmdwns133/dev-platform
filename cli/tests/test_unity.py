"""Unity execution layer: argv assembly, parsing, lock handling and upload."""

from __future__ import annotations

import hashlib
import json
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
from support import FakeRunner, write_config, write_text

from devplatform import procs, unity
from devplatform.config import load_config
from devplatform.errors import DevctlError

PLATFORM_HOME = Path(__file__).resolve().parents[2]


def config_for(root: Path, **unity_overrides):
    write_config(root, profile="unity", unity=unity_overrides)
    return load_config(root)


def test_procs_run_uses_devnull_stdin(tmp_path: Path, monkeypatch) -> None:
    captured: dict = {}

    class Completed:
        returncode = 0
        stdout = ""
        stderr = ""

    def fake_run(*args, **kwargs):
        captured.update(kwargs)
        return Completed()

    monkeypatch.setattr(procs.subprocess, "run", fake_run)
    procs.run("tool", ["python", "-c", "pass"], tmp_path, tmp_path / "log.txt")
    assert captured["stdin"] is procs.subprocess.DEVNULL


def test_parse_nunit(tmp_path: Path) -> None:
    path = tmp_path / "editmode.xml"
    path.write_text(
        '<test-run result="Failed" passed="3" failed="1" skipped="2" '
        'inconclusive="0" total="6" testcasecount="6" />',
        encoding="utf-8",
    )
    counts = unity.parse_nunit(path)
    assert counts == {
        "passed": 3,
        "failed": 1,
        "skipped": 2,
        "total": 6,
        "result": "Failed",
    }


def test_parse_nunit_requires_failed_attribute(tmp_path: Path) -> None:
    path = tmp_path / "editmode.xml"
    path.write_text('<test-run result="Passed" />', encoding="utf-8")
    with pytest.raises(DevctlError) as excinfo:
        unity.parse_nunit(path)
    assert excinfo.value.code == 3


def test_parse_nunit_invalid_xml(tmp_path: Path) -> None:
    path = tmp_path / "broken.xml"
    path.write_text("<test-run", encoding="utf-8")
    with pytest.raises(DevctlError):
        unity.parse_nunit(path)


def test_parse_summary_xml_variants(tmp_path: Path) -> None:
    path = tmp_path / "Summary.xml"
    path.write_text(
        "<CoverageReport><Summary><Coveredlines>80</Coveredlines>"
        "<Coverablelines>100</Coverablelines><Linecoverage>80.0</Linecoverage>"
        "</Summary></CoverageReport>",
        encoding="utf-8",
    )
    parsed = unity.parse_summary_xml(path)
    assert parsed["line"] == 80.0
    assert parsed["covered"] == 80

    path.write_text(
        "<CoverageReport><Summary><Coveredlines>1</Coveredlines>"
        "<Coverablelines>8</Coverablelines></Summary></CoverageReport>",
        encoding="utf-8",
    )
    assert unity.parse_summary_xml(path)["line"] == 12.5

    path.write_text(
        "<CoverageReport><Summary><Totalpercentage>66.5%</Totalpercentage>"
        "</Summary></CoverageReport>",
        encoding="utf-8",
    )
    assert unity.parse_summary_xml(path)["line"] == 66.5

    path.write_text("<CoverageReport><Summary></Summary></CoverageReport>", encoding="utf-8")
    with pytest.raises(DevctlError):
        unity.parse_summary_xml(path)


def test_editmode_argv_includes_nographics_and_shared_coverage(tmp_path: Path) -> None:
    root = tmp_path / "project"
    root.mkdir()
    config = config_for(root)
    argv = unity.test_argv(root, tmp_path / "reports", config, "EditMode", Path("Unity.exe"))
    assert argv[0] == "Unity.exe"
    assert "-batchmode" in argv
    assert "-nographics" in argv
    assert "-runTests" in argv
    assert "-quit" not in argv
    assert argv[argv.index("-testPlatform") + 1] == "EditMode"
    assert argv[argv.index("-testResults") + 1].endswith("unity\\editmode.xml") or argv[
        argv.index("-testResults") + 1
    ].endswith("unity/editmode.xml")
    coverage_path = argv[argv.index("-coverageResultsPath") + 1].replace("\\", "/")
    assert coverage_path.endswith("unity/coverage")
    options = argv[argv.index("-coverageOptions") + 1]
    assert options.startswith("generateAdditionalMetrics;generateHtmlReport")
    assert "assemblyFilters:-*Tests*" in options


def test_playmode_mode_gui_and_batch(tmp_path: Path) -> None:
    root = tmp_path / "project"
    root.mkdir()
    config = config_for(root)
    argv = unity.test_argv(root, tmp_path / "reports", config, "PlayMode", Path("Unity.exe"))
    assert "-batchmode" not in argv
    assert "-nographics" not in argv
    assert "-runTests" in argv
    assert "-quit" not in argv
    assert (
        argv[argv.index("-coverageResultsPath") + 1].replace("\\", "/").endswith("unity/coverage")
    )

    config = config_for(root, playmodeMode="batch")
    argv = unity.test_argv(root, tmp_path / "reports", config, "PlayMode", Path("Unity.exe"))
    assert "-batchmode" in argv
    assert "-nographics" not in argv


def test_coverage_disabled_omits_flags(tmp_path: Path) -> None:
    root = tmp_path / "project"
    root.mkdir()
    write_config(root, profile="unity", coverage={"minimum": 0, "enabled": False})
    config = load_config(root)
    argv = unity.test_argv(root, tmp_path / "reports", config, "EditMode", Path("Unity.exe"))
    assert "-enableCodeCoverage" not in argv
    assert "-coverageOptions" not in argv


def test_handle_lock_removes_stale(tmp_path: Path, monkeypatch, capsys) -> None:
    write_text(tmp_path / "Temp/UnityLockfile", "")
    write_text(tmp_path / "Library/EditorInstance.json", '{"process_id": 999999}')
    monkeypatch.setattr(unity, "_process_alive", lambda pid: False)
    assert unity.handle_lock(tmp_path) is True
    assert not (tmp_path / "Temp/UnityLockfile").exists()
    assert "Removed stale Unity lockfile" in capsys.readouterr().out


def test_handle_lock_refuses_running_editor(tmp_path: Path, monkeypatch) -> None:
    write_text(tmp_path / "Temp/UnityLockfile", "")
    write_text(tmp_path / "Library/EditorInstance.json", '{"process_id": 1234}')
    monkeypatch.setattr(unity, "_process_alive", lambda pid: True)
    with pytest.raises(DevctlError) as excinfo:
        unity.handle_lock(tmp_path)
    assert excinfo.value.code == 2
    assert "pid 1234" in excinfo.value.message


def test_handle_lock_without_lock(tmp_path: Path) -> None:
    assert unity.handle_lock(tmp_path) is False


def test_editor_discovery_precedence(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "project"
    root.mkdir()
    editor = tmp_path / "Unity.exe"
    editor.write_text("", encoding="utf-8")
    config = config_for(root, editorPath=str(editor))
    assert unity.find_editor(config, root) == editor

    monkeypatch.setattr(unity, "EDITOR_CANDIDATE_ROOTS", ())
    for variable in ("UNITY_EDITOR_PATH", "ProgramFiles", "ProgramFiles(x86)"):
        monkeypatch.delenv(variable, raising=False)
    config = config_for(root)
    assert unity.find_editor(config, root) is None
    with pytest.raises(DevctlError) as excinfo:
        unity.require_editor(config, root)
    assert excinfo.value.code == 2


def test_editor_version_env_override(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "project"
    root.mkdir()
    editor = tmp_path / "Unity.exe"
    editor.write_text("", encoding="utf-8")
    monkeypatch.setenv("UNITY_EDITOR_PATH", str(editor))
    monkeypatch.setattr(unity, "EDITOR_CANDIDATE_ROOTS", ())
    config = config_for(root)
    assert unity.find_editor(config, root) == editor


def test_editor_version_mismatch(tmp_path: Path, monkeypatch) -> None:
    config = config_for(tmp_path)
    monkeypatch.setattr(unity, "probe_editor_version", lambda editor: ("6000.5.1f0", ""))
    with pytest.raises(DevctlError) as excinfo:
        unity.check_editor_version(config, Path("Unity.exe"))
    assert excinfo.value.code == 2
    assert "expected 6000.5.1f1" in excinfo.value.message

    monkeypatch.setattr(unity, "probe_editor_version", lambda editor: ("6000.5.1f1", ""))
    unity.check_editor_version(config, Path("Unity.exe"))


def test_run_tests_passes_and_parses(tmp_path: Path) -> None:
    root = tmp_path / "project"
    root.mkdir()
    config = config_for(root)
    reports = tmp_path / "reports"
    write_text(
        reports / "unity/editmode.xml",
        '<test-run failed="0" result="Passed" passed="7" skipped="1" total="8" />',
    )
    runner = FakeRunner()
    step = unity.run_tests(root, reports, config, "EditMode", Path("Unity.exe"), runner)
    assert step.status == "passed"
    assert step.data["passed"] == 7
    assert step.data["skipped"] == 1
    argv = runner.calls[0]["argv"]
    assert "-nographics" in argv
    assert "-quit" not in argv
    assert runner.calls[0]["log"].name == "unity-editmode.log"


def test_run_tests_missing_result_is_execution_error(tmp_path: Path) -> None:
    root = tmp_path / "project"
    root.mkdir()
    config = config_for(root)
    step = unity.run_tests(
        root, tmp_path / "reports", config, "EditMode", Path("Unity.exe"), FakeRunner()
    )
    assert step.status == "error"
    assert step.exit == 3
    assert "missing" in step.detail


def test_run_tests_failed_result(tmp_path: Path) -> None:
    root = tmp_path / "project"
    root.mkdir()
    config = config_for(root, retryFailed=0)
    reports = tmp_path / "reports"
    write_text(
        reports / "unity/playmode.xml",
        '<test-run failed="1" result="Failed" passed="2" skipped="0" total="3" />',
    )
    step = unity.run_tests(root, reports, config, "PlayMode", Path("Unity.exe"), FakeRunner())
    assert step.status == "failed"
    assert step.exit == 1


def _nunit_xml(cases, passed: int, failed: int, skipped: int, result: str) -> str:
    body = "".join(
        f'<test-case name="{name.rsplit(".", 1)[-1]}" fullname="{name}" result="{status}" />'
        for name, status in cases
    )
    return (
        f'<test-run failed="{failed}" result="{result}" passed="{passed}" '
        f'skipped="{skipped}" total="{len(cases)}"><test-suite>{body}</test-suite></test-run>'
    )


FLAKE_A = (
    "ProjectDelta.Tests.PlayMode.MissionAcceptanceTests."
    "ActiveInterceptBot_ReachesRealSuccess_WithinMissionBudget"
)
FLAKE_B = "ProjectDelta.Tests.PlayMode.ViewRigTests.FreeLook_FreezesTheAim_WhileDragging"


def test_retry_marks_flaky_and_passes(tmp_path: Path, capsys) -> None:
    root = tmp_path / "project"
    root.mkdir()
    config = config_for(root)
    reports = tmp_path / "reports"
    write_text(
        reports / "unity/playmode.xml",
        _nunit_xml(
            [(FLAKE_A, "Failed"), (FLAKE_B, "Failed")],
            passed=5,
            failed=2,
            skipped=1,
            result="Failed",
        ),
    )

    def on_run(name, argv, cwd):
        if name == "unity-playmode-retry":
            write_text(
                reports / "unity/playmode-retry.xml",
                _nunit_xml(
                    [(FLAKE_A, "Passed"), (FLAKE_B, "Passed")],
                    passed=2,
                    failed=0,
                    skipped=0,
                    result="Passed",
                ),
            )

    runner = FakeRunner(on_run=on_run)
    step = unity.run_tests(root, reports, config, "PlayMode", Path("Unity.exe"), runner)
    assert step.status == "passed"
    assert step.exit == 0
    assert step.data["failed"] == 0
    assert step.data["passed"] == 7
    assert sorted(step.data["flaky"]) == sorted([FLAKE_A, FLAKE_B])
    assert step.detail == "flaky: 2"

    retry_call = runner.calls[1]
    assert retry_call["name"] == "unity-playmode-retry"
    retry_argv = retry_call["argv"]
    assert "-enableCodeCoverage" not in retry_argv
    assert "-coverageOptions" not in retry_argv
    results_arg = retry_argv[retry_argv.index("-testResults") + 1].replace("\\", "/")
    assert results_arg.endswith("unity/playmode-retry.xml")
    filter_value = retry_argv[retry_argv.index("-testFilter") + 1]
    assert "|" in filter_value
    assert "MissionAcceptanceTests\\.ActiveInterceptBot" in filter_value
    assert "ViewRigTests\\.FreeLook" in filter_value

    output = capsys.readouterr().out
    assert f"::warning title=flaky test::{FLAKE_A}" in output
    assert f"::warning title=flaky test::{FLAKE_B}" in output


def test_retry_partial_failure_still_fails(tmp_path: Path) -> None:
    root = tmp_path / "project"
    root.mkdir()
    config = config_for(root)
    reports = tmp_path / "reports"
    write_text(
        reports / "unity/playmode.xml",
        _nunit_xml(
            [(FLAKE_A, "Failed"), (FLAKE_B, "Failed")],
            passed=1,
            failed=2,
            skipped=0,
            result="Failed",
        ),
    )

    def on_run(name, argv, cwd):
        if name == "unity-playmode-retry":
            write_text(
                reports / "unity/playmode-retry.xml",
                _nunit_xml(
                    [(FLAKE_A, "Passed"), (FLAKE_B, "Failed")],
                    passed=1,
                    failed=1,
                    skipped=0,
                    result="Failed",
                ),
            )

    step = unity.run_tests(
        root, reports, config, "PlayMode", Path("Unity.exe"), FakeRunner(on_run=on_run)
    )
    assert step.status == "failed"
    assert step.exit == 1
    assert step.data["flaky"] == [FLAKE_A]
    assert step.data["failed"] == 1
    assert "flaky: 1" in step.detail


def test_retry_disabled_does_not_rerun(tmp_path: Path) -> None:
    root = tmp_path / "project"
    root.mkdir()
    config = config_for(root, retryFailed=0)
    reports = tmp_path / "reports"
    write_text(
        reports / "unity/playmode.xml",
        _nunit_xml([(FLAKE_A, "Failed")], passed=1, failed=1, skipped=0, result="Failed"),
    )
    runner = FakeRunner()
    step = unity.run_tests(root, reports, config, "PlayMode", Path("Unity.exe"), runner)
    assert step.status == "failed"
    assert len(runner.calls) == 1


def test_retry_missing_result_is_execution_error(tmp_path: Path) -> None:
    root = tmp_path / "project"
    root.mkdir()
    config = config_for(root)
    reports = tmp_path / "reports"
    write_text(
        reports / "unity/playmode.xml",
        _nunit_xml([(FLAKE_A, "Failed")], passed=1, failed=1, skipped=0, result="Failed"),
    )
    step = unity.run_tests(root, reports, config, "PlayMode", Path("Unity.exe"), FakeRunner())
    assert step.status == "error"
    assert step.exit == 3
    assert "retry result file missing" in step.detail


def test_build_project_success(tmp_path: Path) -> None:
    root = tmp_path / "project"
    root.mkdir()
    config = config_for(root)
    output = root / "artifacts/unity-build/ProjectDelta.exe"
    output.parent.mkdir(parents=True)
    payload = b"\0" * 667_648
    output.write_bytes(payload)
    (output.parent / "UnityPlayer.dll").write_bytes(b"\0" * (2 * 1024 * 1024))
    runner = FakeRunner()
    step = unity.build_project(root, tmp_path / "reports", config, Path("Unity.exe"), runner)
    assert step.status == "passed"
    assert "bytes total" in step.detail
    assert "UnityPlayer.dll" not in step.detail
    expected_hash = hashlib.sha256(payload).hexdigest()
    assert f"sha256 {expected_hash}" in step.detail
    assert "exe 667648 bytes" in step.detail
    argv = runner.calls[0]["argv"]
    assert "-buildWindows64Player" in argv
    assert "-quit" in argv
    assert str(output) in argv


def test_build_project_missing_and_small(tmp_path: Path) -> None:
    root = tmp_path / "project"
    root.mkdir()
    config = config_for(root)
    step = unity.build_project(root, tmp_path / "reports", config, Path("Unity.exe"), FakeRunner())
    assert step.status == "error"
    assert step.exit == 3

    output = root / "artifacts/unity-build/ProjectDelta.exe"
    output.parent.mkdir(parents=True)
    output.write_bytes(b"\0")
    step = unity.build_project(root, tmp_path / "reports", config, Path("Unity.exe"), FakeRunner())
    assert step.status == "error"
    assert "directory too small" in step.detail


def test_build_project_tool_failure(tmp_path: Path) -> None:
    root = tmp_path / "project"
    root.mkdir()
    config = config_for(root)
    step = unity.build_project(
        root,
        tmp_path / "reports",
        config,
        Path("Unity.exe"),
        FakeRunner({"unity-build": 7}),
    )
    assert step.status == "failed"
    assert step.exit == 7


def test_odin_skipped_and_required(tmp_path: Path) -> None:
    root = tmp_path / "project"
    root.mkdir()
    config = config_for(root)
    reports = tmp_path / "reports"
    write_text(reports / "unity/odin.json", json.dumps({"status": "skipped", "reason": "absent"}))
    step = unity.run_odin(root, reports, config, Path("Unity.exe"), FakeRunner())
    assert step.status == "passed"
    assert step.detail == "odin: skipped"

    with pytest.raises(DevctlError) as excinfo:
        unity.run_odin(root, reports, config, Path("Unity.exe"), FakeRunner(), require_odin=True)
    assert excinfo.value.code == 4


def test_odin_failed_and_missing_report(tmp_path: Path) -> None:
    root = tmp_path / "project"
    root.mkdir()
    config = config_for(root)
    reports = tmp_path / "reports"
    write_text(reports / "unity/odin.json", json.dumps({"status": "failed", "errors": 2}))
    step = unity.run_odin(root, reports, config, Path("Unity.exe"), FakeRunner())
    assert step.status == "failed"
    assert step.exit == 1

    (reports / "unity/odin.json").unlink()
    step = unity.run_odin(root, reports, config, Path("Unity.exe"), FakeRunner())
    assert step.status == "error"
    assert step.exit == 3


def test_nunit_to_junit_conversion(tmp_path: Path) -> None:
    source = tmp_path / "results"
    write_text(
        source / "editmode.xml",
        """<test-run>
  <test-suite name="Suite">
    <test-case name="Passes" fullname="Tests.Passes" duration="0.25" result="Passed" />
    <test-case name="Fails" fullname="Tests.Fails" duration="0.5" result="Failed">
      <failure><message>boom</message><stack-trace>at Tests.Fails()</stack-trace></failure>
    </test-case>
    <test-case name="Skips" fullname="Tests.Skips" result="Skipped">
      <reason><message>not now</message></reason>
    </test-case>
  </test-suite>
</test-run>""",
    )
    out = tmp_path / "junit.xml"
    counts = unity.nunit_to_junit(source, out)
    assert counts == {"tests": 3, "failures": 1, "skipped": 1}
    root = ET.parse(out).getroot()
    assert root.tag == "testsuites"
    cases = {case.get("name"): case for case in root.iter("testcase")}
    assert cases["Passes"].get("classname") == "Tests"
    failure = cases["Fails"].find("failure")
    assert failure is not None
    assert "boom" in (failure.get("message") or "")
    assert cases["Skips"].find("skipped") is not None


def test_nunit_to_junit_no_cases(tmp_path: Path) -> None:
    source = tmp_path / "empty"
    write_text(source / "x.xml", "<test-run />")
    with pytest.raises(DevctlError) as excinfo:
        unity.nunit_to_junit(source, tmp_path / "junit.xml")
    assert excinfo.value.code == 3


def _fake_git(mapping):
    def fake(root: Path, *args: str):
        return mapping.get(tuple(args), (1, "", "unexpected arg"))

    return fake


GIT_OK = {
    ("status", "--porcelain"): (0, "", ""),
    ("rev-parse", "HEAD"): (0, "abc123", ""),
    ("branch", "-r", "--contains", "HEAD"): (0, "origin/main", ""),
    ("rev-parse", "--abbrev-ref", "HEAD"): (0, "main", ""),
    ("remote", "get-url", "origin"): (0, "https://github.com/octo/repo.git", ""),
}


def _upload_tree(tmp_path: Path) -> Path:
    reports = tmp_path / "reports"
    write_text(
        reports / "unity/coverage/project-delta-opencov/EditMode/TestCoverageResults_0000.xml",
        "<x />",
    )
    write_text(
        reports / "unity/coverage/project-delta-opencov/PlayMode/TestCoverageResults_0000.xml",
        "<x />",
    )
    return reports


def test_coverage_upload_builds_codecov_argv(tmp_path: Path, monkeypatch) -> None:
    reports = _upload_tree(tmp_path)
    monkeypatch.setattr(unity, "_git", _fake_git(GIT_OK))
    runner = FakeRunner()
    step = unity.coverage_upload(
        tmp_path, reports, PLATFORM_HOME, runner=runner, token="secret-token"
    )
    assert step.status == "passed"
    assert len(runner.calls) == 1
    argv = runner.calls[0]["argv"]
    assert argv[:5] == ["uvx", "--python", "3.12", "--from", "codecov-cli==11.3.1"]
    assert argv[argv.index("--flag") + 1] == "unity"
    assert "--slug" in argv and "octo/repo" in argv
    assert "--sha" in argv and "abc123" in argv
    assert "--branch" in argv and "main" in argv
    assert argv.count("--file") == 2
    assert runner.calls[0]["env"] == {"CODECOV_TOKEN": "secret-token"}
    assert (reports / "unity/unity-coverage-upload.log").is_file()


def test_coverage_upload_preconditions(tmp_path: Path, monkeypatch) -> None:
    reports = _upload_tree(tmp_path)
    monkeypatch.setattr(unity, "_git", _fake_git(GIT_OK))
    with pytest.raises(DevctlError) as excinfo:
        unity.coverage_upload(tmp_path, reports, PLATFORM_HOME, runner=FakeRunner(), token="")
    assert excinfo.value.code == 2
    assert "CODECOV_TOKEN" in excinfo.value.message

    empty = tmp_path / "empty-reports"
    with pytest.raises(DevctlError) as excinfo:
        unity.coverage_upload(tmp_path, empty, PLATFORM_HOME, runner=FakeRunner(), token="t")
    assert "no Unity OpenCover report found" in excinfo.value.message

    dirty = dict(GIT_OK)
    dirty[("status", "--porcelain")] = (0, " M file.txt", "")
    monkeypatch.setattr(unity, "_git", _fake_git(dirty))
    with pytest.raises(DevctlError) as excinfo:
        unity.coverage_upload(tmp_path, reports, PLATFORM_HOME, runner=FakeRunner(), token="t")
    assert excinfo.value.code == 2
    assert "commit must be pushed" in excinfo.value.message


def test_github_slug_formats(tmp_path: Path, monkeypatch) -> None:
    for remote in (
        "https://github.com/owner/repo.git",
        "git@github.com:owner/repo.git",
        "ssh://git@github.com/owner/repo.git",
    ):
        mapping = dict(GIT_OK)
        mapping[("remote", "get-url", "origin")] = (0, remote, "")
        monkeypatch.setattr(unity, "_git", _fake_git(mapping))
        assert unity.github_slug(tmp_path) == "owner/repo"


def test_collect_combined_coverage(tmp_path: Path) -> None:
    reports = tmp_path / "reports"
    write_text(
        reports / "unity/coverage/Report/Summary.xml",
        "<CoverageReport><Summary><Coveredlines>80</Coveredlines>"
        "<Coverablelines>100</Coverablelines></Summary></CoverageReport>",
    )
    measured = unity.collect_coverage(reports)
    assert measured["line"] == 80.0
    assert measured["report"] == reports / "unity/coverage/Report/Summary.xml"


def test_collect_coverage_missing_warns(tmp_path: Path, capsys) -> None:
    measured = unity.collect_coverage(tmp_path / "reports")
    assert measured["line"] is None
    assert "code coverage report not produced" in capsys.readouterr().out
