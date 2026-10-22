"""Version contract semantics with mocked tool probes."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from devplatform import versions
from devplatform.config import load_config
from devplatform.errors import DevctlError


def platform_home(tmp_path: Path, *, node: str = "22", sdk: str = "10.0.401") -> Path:
    home = tmp_path / "platform"
    home.mkdir()
    (home / "versions.json").write_text(
        json.dumps(
            {
                "schema": 1,
                "python": {"version": "3.12", "uv": "0.12.21"},
                "node": {"version": node, "npm": "11.20.0"},
                "dotnet": {"sdk": sdk, "targetFramework": "net10.0"},
                "unity": {"version": "6000.5.1f1"},
                "security": {
                    "trivy": "0.74.0",
                    "gitleaks": "8.30.1",
                    "zizmor": "1.31.1",
                    "actionlint": "1.7.7",
                },
            }
        ),
        encoding="utf-8",
    )
    return home


def probe_from(outputs: dict[str, str | None]):
    def probe(argv: list[str]) -> str | None:
        return outputs.get(" ".join(argv))

    return probe


BASE_OUTPUTS = {
    "node --version": "v26.12.0",
    "dotnet --list-sdks": "10.0.401 [C:\\Program Files\\dotnet\\sdk]",
    "uv --version": "uv 0.12.21 (abcdef)",
    "npm --version": "11.20.0",
    "trivy --version": "Version: 0.74.0",
    "gitleaks version": "8.30.1",
    "zizmor --version": "zizmor 1.31.1",
    "actionlint --version": "1.7.7",
}


def checks(
    tmp_path: Path, home: Path, outputs: dict, profile: str | None = None, python=(3, 12, 14)
):
    config = load_config(tmp_path)
    return versions.check_versions(
        config,
        profile,
        tmp_path,
        home,
        probe=probe_from(outputs),
        python_version=python,
    )


def by_tool(items):
    return {item.tool: item for item in items}


def test_node_newer_is_warning(tmp_path: Path) -> None:
    home = platform_home(tmp_path)
    items = by_tool(checks(tmp_path, home, BASE_OUTPUTS))
    assert items["node"].level == "warn"
    assert items["node"].found == "26.12.0"


def test_node_older_fails(tmp_path: Path) -> None:
    home = platform_home(tmp_path)
    outputs = dict(BASE_OUTPUTS, **{"node --version": "v20.9.0"})
    assert by_tool(checks(tmp_path, home, outputs))["node"].level == "fail"


def test_node_missing_profile_rules(tmp_path: Path) -> None:
    home = platform_home(tmp_path)
    outputs = dict(BASE_OUTPUTS, **{"node --version": None})
    assert by_tool(checks(tmp_path, home, outputs))["node"].level == "warn"
    assert by_tool(checks(tmp_path, home, outputs, profile="typescript"))["node"].level == "fail"


def test_node_pin_99_fails(tmp_path: Path) -> None:
    home = platform_home(tmp_path, node="99")
    items = checks(tmp_path, home, BASE_OUTPUTS)
    assert by_tool(items)["node"].level == "fail"
    assert versions.report_checks(items) == 1


def test_dotnet_feature_band(tmp_path: Path) -> None:
    home = platform_home(tmp_path)
    outputs = dict(BASE_OUTPUTS, **{"dotnet --list-sdks": "10.0.402 [x]"})
    assert by_tool(checks(tmp_path, home, outputs))["dotnet"].level == "ok"

    outputs = dict(BASE_OUTPUTS, **{"dotnet --list-sdks": "10.0.500 [x]"})
    assert by_tool(checks(tmp_path, home, outputs))["dotnet"].level == "warn"
    assert by_tool(checks(tmp_path, home, outputs, profile="dotnet"))["dotnet"].level == "fail"

    outputs = dict(BASE_OUTPUTS, **{"dotnet --list-sdks": "9.0.100 [x]"})
    assert by_tool(checks(tmp_path, home, outputs))["dotnet"].level == "warn"


def test_python_interpreter_mismatch(tmp_path: Path) -> None:
    home = platform_home(tmp_path)
    items = checks(tmp_path, home, BASE_OUTPUTS, python=(3, 11, 9))
    assert by_tool(items)["python"].level == "fail"
    assert versions.report_checks(items) == 1


def test_unity_missing_editor_rules(tmp_path: Path, monkeypatch) -> None:
    home = platform_home(tmp_path)
    monkeypatch.setattr(versions, "find_editor", lambda config, root: None)
    assert by_tool(checks(tmp_path, home, BASE_OUTPUTS))["unity"].level == "warn"
    assert by_tool(checks(tmp_path, home, BASE_OUTPUTS, profile="unity"))["unity"].level == "fail"


def test_unity_project_version_mismatch(tmp_path: Path, monkeypatch) -> None:
    home = platform_home(tmp_path)
    editor = tmp_path / "Unity.exe"
    editor.write_text("", encoding="utf-8")
    monkeypatch.setattr(versions, "find_editor", lambda config, root: editor)
    settings = tmp_path / "ProjectSettings"
    settings.mkdir()
    (settings / "ProjectVersion.txt").write_text("m_EditorVersion: 6000.5.1f0\n", encoding="utf-8")
    assert by_tool(checks(tmp_path, home, BASE_OUTPUTS))["unity"].level == "fail"


def test_tool_mismatches_are_warnings_only(tmp_path: Path) -> None:
    home = platform_home(tmp_path)
    outputs = dict(
        BASE_OUTPUTS,
        **{
            "uv --version": "uv 0.11.0",
            "npm --version": "11.0.0",
            "trivy --version": "Version: 0.70.0",
            "gitleaks version": "8.0.0",
            "zizmor --version": "zizmor 1.0.0",
            "actionlint --version": "1.6.0",
        },
    )
    items = checks(tmp_path, home, outputs)
    for tool in ("uv", "npm", "trivy", "gitleaks", "zizmor", "actionlint"):
        assert by_tool(items)[tool].level == "warn"
    assert versions.report_checks(items) == 0


def test_zizmor_uvx_fallback(tmp_path: Path) -> None:
    home = platform_home(tmp_path)
    outputs = dict(
        BASE_OUTPUTS, **{"zizmor --version": None, "uvx zizmor==1.31.1 --version": "zizmor 1.31.1"}
    )
    assert by_tool(checks(tmp_path, home, outputs))["zizmor"].level == "ok"


def test_table_prints(tmp_path: Path, capsys) -> None:
    home = platform_home(tmp_path)
    items = checks(tmp_path, home, BASE_OUTPUTS)
    assert versions.print_table(items) == 0
    output = capsys.readouterr().out
    assert "expected" in output
    assert "python" in output


def test_missing_versions_file(tmp_path: Path) -> None:
    with pytest.raises(DevctlError) as excinfo:
        versions.load_versions(tmp_path / "missing")
    assert excinfo.value.code == 2


def test_report_output_format(tmp_path: Path, capsys) -> None:
    home = platform_home(tmp_path)
    items = checks(tmp_path, home, BASE_OUTPUTS)
    assert versions.report_checks(items) == 0
    lines = capsys.readouterr().out.splitlines()
    assert any(line.startswith("ok python expected=3.12 found=3.12.14") for line in lines)
    assert any(line.startswith("warn node expected=22 found=26.12.0") for line in lines)
