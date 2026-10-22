"""Config schema validation and defaults."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from devplatform.config import load_config, reports_directory
from devplatform.errors import DevctlError


def test_defaults_without_file(tmp_path: Path) -> None:
    config = load_config(tmp_path)
    assert config.profile is None
    assert config.reports == "artifacts/reports"
    assert config.coverage_minimum == 0
    assert config.coverage_enabled is True
    assert config.unity["version"] == "6000.5.1f1"
    assert config.unity["playmodeNographics"] is False
    assert config.unity["coverageAssemblyFilters"] == ["-*Tests*"]
    assert reports_directory(tmp_path, config) == tmp_path / "artifacts/reports"


def test_reports_override_and_absolute(tmp_path: Path) -> None:
    config = load_config(tmp_path)
    absolute = tmp_path / "elsewhere"
    assert reports_directory(tmp_path, config, str(absolute)) == absolute
    assert reports_directory(tmp_path, config, "custom/reports") == tmp_path / "custom/reports"


def _write(tmp_path: Path, data: dict) -> Path:
    path = tmp_path / ".devplatform/config.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_unknown_top_level_key_rejected(tmp_path: Path) -> None:
    _write(tmp_path, {"profile": "python", "profiles": "typo"})
    with pytest.raises(DevctlError) as excinfo:
        load_config(tmp_path)
    assert excinfo.value.code == 2
    assert "unknown key" in excinfo.value.message


def test_unknown_nested_key_rejected(tmp_path: Path) -> None:
    _write(tmp_path, {"profile": "unity", "unity": {"scenes": "typo"}})
    with pytest.raises(DevctlError) as excinfo:
        load_config(tmp_path)
    assert "unknown key(s) in unity" in excinfo.value.message


def test_invalid_profile_rejected(tmp_path: Path) -> None:
    _write(tmp_path, {"profile": "ruby"})
    with pytest.raises(DevctlError) as excinfo:
        load_config(tmp_path)
    assert "profile must be one of" in excinfo.value.message


def test_missing_profile_when_file_exists(tmp_path: Path) -> None:
    _write(tmp_path, {"reports": "out"})
    with pytest.raises(DevctlError) as excinfo:
        load_config(tmp_path)
    assert "profile is required" in excinfo.value.message


def test_profile_mismatch(tmp_path: Path) -> None:
    _write(tmp_path, {"profile": "python"})
    with pytest.raises(DevctlError) as excinfo:
        load_config(tmp_path, cli_profile="typescript")
    assert excinfo.value.code == 2
    assert "profile mismatch" in excinfo.value.message


def test_unity_assets_is_compatible_with_unity_config(tmp_path: Path) -> None:
    _write(tmp_path, {"profile": "unity"})
    config = load_config(tmp_path, cli_profile="unity-assets")
    assert config.profile == "unity"

    with pytest.raises(DevctlError) as excinfo:
        load_config(tmp_path, cli_profile="python")
    assert excinfo.value.code == 2
    assert "profile mismatch" in excinfo.value.message


def test_unity_is_not_compatible_with_unity_assets_config(tmp_path: Path) -> None:
    _write(tmp_path, {"profile": "unity-assets"})
    with pytest.raises(DevctlError) as excinfo:
        load_config(tmp_path, cli_profile="unity")
    assert excinfo.value.code == 2


def test_explicit_config_missing(tmp_path: Path) -> None:
    with pytest.raises(DevctlError) as excinfo:
        load_config(tmp_path, config_path="nope.json")
    assert "config file not found" in excinfo.value.message


def test_absolute_external_guid_baseline(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline.json"
    _write(tmp_path, {"profile": "unity", "unity": {"externalGuidBaseline": str(baseline)}})
    config = load_config(tmp_path)
    assert config.unity["externalGuidBaseline"] == str(baseline)


def test_required_objects_validation(tmp_path: Path) -> None:
    _write(
        tmp_path,
        {
            "profile": "unity",
            "unity": {"requiredObjects": [{"fileId": "1", "name": "Cam", "componentClassId": 20}]},
        },
    )
    config = load_config(tmp_path)
    assert config.unity["requiredObjects"][0]["requireGlobalVolume"] is False

    _write(tmp_path, {"profile": "unity", "unity": {"requiredObjects": [{"fileId": "1"}]}})
    with pytest.raises(DevctlError):
        load_config(tmp_path)


def test_coverage_bounds(tmp_path: Path) -> None:
    _write(tmp_path, {"profile": "python", "coverage": {"minimum": 101}})
    with pytest.raises(DevctlError):
        load_config(tmp_path)


def test_playmode_nographics_flag(tmp_path: Path) -> None:
    _write(tmp_path, {"profile": "unity", "unity": {"playmodeNographics": True}})
    config = load_config(tmp_path)
    assert config.unity["playmodeNographics"] is True
