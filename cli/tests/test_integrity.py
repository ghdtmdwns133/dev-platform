"""Unity integrity checks, including the parity wording and baseline handling."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from support import (
    BUILD_SETTINGS_DEFAULT,
    SCENE_DEFAULT,
    SCENE_REL,
    make_unity_tree,
    write_config,
    write_text,
)

from devplatform import integrity
from devplatform.config import load_config
from devplatform.errors import DevctlError

REF_GUID = "0123456789abcdef0123456789abcdef"
PACKAGE_GUID = "fedcba9876543210fedcba9876543210"


def run(root: Path):
    return integrity.check(root, load_config(root))


def test_valid_tree(unity_tree: Path) -> None:
    result = run(unity_tree)
    assert result.errors == []
    assert result.warnings == []
    assert result.guid_count == 2


def test_editorconfig_warning_only(tmp_path: Path) -> None:
    root = make_unity_tree(tmp_path / "unity", editorconfig=False)
    result = run(root)
    assert result.errors == []
    assert result.warnings == ["Missing .editorconfig at repository root"]


def test_required_paths(tmp_path: Path) -> None:
    root = make_unity_tree(tmp_path / "unity")
    (root / "Packages/manifest.json").unlink()
    result = run(root)
    assert "Missing required Unity project path: Packages/manifest.json" in result.errors


def test_version_exact(tmp_path: Path) -> None:
    root = make_unity_tree(tmp_path / "unity", version="6000.5.1f0")
    result = run(root)
    assert "Unity version must be exactly 6000.5.1f1" in result.errors


def test_missing_scene_and_meta(tmp_path: Path) -> None:
    root = make_unity_tree(tmp_path / "unity")
    (root / SCENE_REL).unlink()
    result = run(root)
    assert "Course template SampleScene and its .meta file must be retained" in result.errors


def test_scene_guid_changed(tmp_path: Path) -> None:
    root = make_unity_tree(tmp_path / "unity")
    write_text(root / (SCENE_REL + ".meta"), "fileFormatVersion: 2\nguid: " + "1" * 32 + "\n")
    result = run(root)
    assert "Original course template SampleScene GUID changed" in result.errors


def test_missing_meta_file(tmp_path: Path) -> None:
    root = make_unity_tree(tmp_path / "unity")
    write_text(root / "Assets/MyScripts.meta", "fileFormatVersion: 2\nguid: " + "b" * 32 + "\n")
    write_text(root / "Assets/MyScripts/Example.cs", "public class Example {}\n")
    result = run(root)
    assert "Missing .meta file for Assets/MyScripts/Example.cs" in result.errors


def test_duplicate_guid(tmp_path: Path) -> None:
    root = make_unity_tree(tmp_path / "unity")
    write_text(
        root / "Assets/OtherScripts.meta",
        "fileFormatVersion: 2\nguid: aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\n",
    )
    result = run(root)
    duplicates = [item for item in result.errors if item.startswith("Duplicate GUID:")]
    assert duplicates
    assert "Assets/OtherScripts.meta" in duplicates[0]
    assert "Assets/Scenes.meta" in duplicates[0]


def test_missing_camera_object(tmp_path: Path) -> None:
    root = make_unity_tree(tmp_path / "unity")
    scene = (root / SCENE_REL).read_text(encoding="utf-8")
    scene = re.sub(r"(?ms)^--- !u!1 &330585543\s*\nGameObject:\s*\n.*?(?=^--- !u!)", "", scene)
    write_text(root / SCENE_REL, scene)
    result = run(root)
    assert "Original Main Camera GameObject must be preserved" in result.errors


def test_camera_component_lost(tmp_path: Path) -> None:
    root = make_unity_tree(tmp_path / "unity")
    scene = (root / SCENE_REL).read_text(encoding="utf-8")
    scene = scene.replace("m_GameObject: {fileID: 330585543}", "m_GameObject: {fileID: 1}", 1)
    write_text(root / SCENE_REL, scene)
    result = run(root)
    assert "Original Main Camera lost its Camera component" in result.errors


def test_global_volume_component_lost(tmp_path: Path) -> None:
    root = make_unity_tree(tmp_path / "unity")
    scene = (root / SCENE_REL).read_text(encoding="utf-8").replace("m_IsGlobal: 1", "m_IsGlobal: 0")
    write_text(root / SCENE_REL, scene)
    result = run(root)
    assert "Original Global Volume lost its global Volume component" in result.errors


def test_main_scene_must_be_first(tmp_path: Path) -> None:
    root = make_unity_tree(tmp_path / "unity")
    settings = """%YAML 1.1
--- !u!1045 &1
EditorBuildSettings:
  m_Scenes:
  - enabled: 1
    path: Assets/Scenes/Other.unity
  - enabled: 1
    path: Assets/Scenes/SampleScene.unity
"""
    write_text(root / "ProjectSettings/EditorBuildSettings.asset", settings)
    result = run(root)
    assert "SampleScene must remain the first enabled (main) build scene" in result.errors


def test_missing_build_scene(tmp_path: Path) -> None:
    root = make_unity_tree(tmp_path / "unity")
    settings = BUILD_SETTINGS_DEFAULT.replace(
        "  m_configObjects: {}",
        "  - enabled: 1\n    path: Assets/Scenes/Missing.unity\n  m_configObjects: {}",
    )
    write_text(root / "ProjectSettings/EditorBuildSettings.asset", settings)
    result = run(root)
    assert "Scene in build settings not found: Assets/Scenes/Missing.unity" in result.errors


def test_script_outside_allowed_roots(tmp_path: Path) -> None:
    root = make_unity_tree(tmp_path / "unity")
    write_text(root / "Assets/Rogue.cs", "public class Rogue {}\n")
    write_text(root / "Assets/Rogue.cs.meta", f"fileFormatVersion: 2\nguid: {'c' * 32}\n")
    result = run(root)
    assert "New C# scripts must be in MyScripts or OtherScripts: Assets/Rogue.cs" in result.errors


def test_invalid_json(tmp_path: Path) -> None:
    root = make_unity_tree(tmp_path / "unity")
    write_text(root / "Packages/manifest.json", "{")
    result = run(root)
    assert any(item.startswith("Invalid JSON in Packages/manifest.json:") for item in result.errors)


def test_unresolved_reference_and_baseline(tmp_path: Path) -> None:
    root = make_unity_tree(tmp_path / "unity")
    write_text(
        root / "Assets/Ambient.asset",
        f"m_Texture: {{fileID: 1, guid: {REF_GUID}, type: 2}}\n",
    )
    write_text(root / "Assets/Ambient.asset.meta", f"fileFormatVersion: 2\nguid: {'d' * 32}\n")
    result = run(root)
    assert f"Unresolved asset reference {REF_GUID} in Assets/Ambient.asset" in result.errors

    baseline = tmp_path / "baseline.json"
    baseline.write_text(
        json.dumps({REF_GUID: "Library/PackageCache/x/texture.png"}), encoding="utf-8"
    )
    write_config(root, unity={"externalGuidBaseline": str(baseline)})
    result = run(root)
    assert result.errors == []


def test_write_baseline_indexes_package_cache(tmp_path: Path) -> None:
    root = make_unity_tree(tmp_path / "unity")
    write_text(
        root / "Assets/Ambient.asset",
        f"m_Texture: {{fileID: 1, guid: {PACKAGE_GUID}, type: 2}}\n",
    )
    write_text(root / "Assets/Ambient.asset.meta", f"fileFormatVersion: 2\nguid: {'e' * 32}\n")
    write_text(
        root / "Library/PackageCache/com.unity.pkg/package.meta",
        f"fileFormatVersion: 2\nguid: {PACKAGE_GUID}\n",
    )
    baseline = tmp_path / "external-guids.json"
    write_config(root, unity={"externalGuidBaseline": str(baseline)})
    result = integrity.check(root, load_config(root), write_baseline_requested=True)
    assert result.errors == []
    assert result.baseline_path == baseline
    data = json.loads(baseline.read_text(encoding="utf-8"))
    assert data[PACKAGE_GUID].endswith("package.meta")
    assert data["aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"] == "Assets/Scenes.meta"


def test_write_baseline_freezes_existing_unresolved(tmp_path: Path) -> None:
    root = make_unity_tree(tmp_path / "unity")
    write_text(
        root / "Assets/Ambient.asset",
        f"m_Texture: {{fileID: 1, guid: {REF_GUID}, type: 2}}\n",
    )
    write_text(root / "Assets/Ambient.asset.meta", f"fileFormatVersion: 2\nguid: {'d' * 32}\n")
    (root / "Library/PackageCache/com.unity.pkg").mkdir(parents=True)
    baseline = tmp_path / "external-guids.json"
    write_config(root, unity={"externalGuidBaseline": str(baseline)})
    config = load_config(root)
    result = integrity.check(root, config, write_baseline_requested=True)
    assert result.errors == []
    data = json.loads(baseline.read_text(encoding="utf-8"))
    assert data[REF_GUID] == "unresolved"

    write_text(
        root / "Assets/New.asset",
        "m_Texture: {fileID: 1, guid: " + "9" * 32 + ", type: 2}\n",
    )
    write_text(root / "Assets/New.asset.meta", f"fileFormatVersion: 2\nguid: {'8' * 32}\n")
    result = integrity.check(root, config)
    assert f"Unresolved asset reference {'9' * 32} in Assets/New.asset" in result.errors


def test_write_baseline_requires_package_cache(tmp_path: Path) -> None:
    root = make_unity_tree(tmp_path / "unity")
    with pytest.raises(DevctlError) as excinfo:
        integrity.check(root, load_config(root), write_baseline_requested=True)
    assert excinfo.value.code == 2
    assert "Library/PackageCache" in excinfo.value.message


def test_reference_scan_ignores_builtin_guids(tmp_path: Path) -> None:
    root = make_unity_tree(tmp_path / "unity")
    write_text(
        root / "Assets/Builtin.asset",
        "m_Material: {fileID: 1, guid: 0000000000000000f000000000000000, type: 0}\n",
    )
    write_text(root / "Assets/Builtin.asset.meta", f"fileFormatVersion: 2\nguid: {'f' * 32}\n")
    assert run(root).errors == []


def test_scene_default_fixture_is_valid(tmp_path: Path) -> None:
    # Guard against the fixture drifting away from the real scene shape.
    root = make_unity_tree(tmp_path / "unity")
    assert SCENE_DEFAULT in (root / SCENE_REL).read_text(encoding="utf-8")
