"""Unity repository integrity checks.

This module is the single implementation of the invariants that used to live as an
inline Python heredoc in ``project-delta/.github/workflows/ci.yml``.  The existing
wording is preserved verbatim for every overlapping check because it is the parity
baseline (see ``docs/ADOPTION.md`` and the platform plan, Approach 4).

Checks run in a fixed order:

1. required Unity project paths
2. ``ProjectSettings/ProjectVersion.txt`` matches ``unity.version``
3. the retained course scene and its original GUID
4. the required template GameObjects and their components
5. ``EditorBuildSettings.asset`` main scene and referenced scene paths
6. C# script locations
7. valid JSON in ``Packages`` manifests
8. ``.meta`` presence, GUID validity and duplicate GUIDs
9. unresolved ``guid:`` references against Assets + the external baseline
10. ``.editorconfig`` presence (warning only)
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from .config import Config, resolve_path
from .errors import EXIT_PRECONDITION, DevctlError

REQUIRED_PATHS = (
    "Assets",
    "Packages/manifest.json",
    "Packages/packages-lock.json",
    "ProjectSettings/ProjectVersion.txt",
    "ProjectSettings/EditorBuildSettings.asset",
)

REFERENCE_SUFFIXES = {
    ".unity",
    ".prefab",
    ".asset",
    ".mat",
    ".controller",
    ".overrideController",
    ".inputactions",
    ".playable",
    ".anim",
    ".physicsMaterial2D",
}

COMPONENT_TYPE_NAMES = {20: "Camera", 114: "MonoBehaviour"}


@dataclass
class IntegrityResult:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    guid_count: int = 0
    baseline_path: Path | None = None
    baseline_entries: int = 0


def _rel(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _check_required_paths(root: Path, errors: list[str]) -> None:
    for required in REQUIRED_PATHS:
        if not (root / required).exists():
            errors.append(f"Missing required Unity project path: {required}")


def _check_version(root: Path, config: Config, errors: list[str]) -> None:
    version_file = root / "ProjectSettings/ProjectVersion.txt"
    if not version_file.is_file():
        return
    match = re.search(r"(?m)^m_EditorVersion:\s*(\S+)\s*$", _read(version_file))
    expected = config.unity["version"]
    if not match or match.group(1) != expected:
        errors.append(f"Unity version must be exactly {expected}")


def _check_scene(root: Path, config: Config, errors: list[str]) -> str | None:
    scene_rel = config.unity["scene"]
    scene_file = root / scene_rel
    scene_meta_file = root / (scene_rel + ".meta")
    if not scene_file.is_file() or not scene_meta_file.is_file():
        errors.append("Course template SampleScene and its .meta file must be retained")
        return None

    meta = _read(scene_meta_file)
    expected_guid = config.unity["sceneGuid"]
    if not re.search(rf"(?m)^guid:\s*{re.escape(expected_guid)}\s*$", meta):
        errors.append("Original course template SampleScene GUID changed")
    return _read(scene_file)


def _check_required_objects(scene: str, config: Config, errors: list[str]) -> None:
    for obj in config.unity["requiredObjects"]:
        file_id = str(obj["fileId"])
        name = obj["name"]
        class_id = int(obj["componentClassId"])
        block = re.search(
            rf"(?ms)^--- !u!1 &{re.escape(file_id)}\s*\nGameObject:\s*\n(.*?)(?=^--- !u!|\Z)",
            scene,
        )
        if not block or not re.search(rf"(?m)^\s*m_Name:\s*{re.escape(name)}\s*$", block.group(1)):
            errors.append(f"Original {name} GameObject must be preserved")

        type_name = COMPONENT_TYPE_NAMES.get(class_id, r"[A-Za-z]+")
        pattern = (
            rf"(?ms)^--- !u!{class_id} &\d+\s*\n{type_name}:\s*\n"
            rf"(?:(?!^--- !u!).)*?^\s*m_GameObject:\s*\{{fileID:\s*{re.escape(file_id)}\}}"
        )
        if obj.get("requireGlobalVolume"):
            pattern += r"\s*\n(?:(?!^--- !u!).)*?^\s*m_IsGlobal:\s*1\s*$"
        if not re.search(pattern, scene):
            if obj.get("requireGlobalVolume"):
                errors.append(f"Original {name} lost its global Volume component")
            elif class_id == 20:
                errors.append(f"Original {name} lost its Camera component")
            else:
                errors.append(f"Original {name} lost its component (class {class_id})")


def _check_build_settings(root: Path, config: Config, errors: list[str]) -> None:
    settings = root / "ProjectSettings/EditorBuildSettings.asset"
    if not settings.is_file():
        return
    text = _read(settings)
    main_scene = config.unity["mainScene"]
    entries = re.findall(r"(?m)^\s*-\s+enabled:\s*(0|1)\s*\n\s*path:\s*(Assets/[^\r\n]+)", text)
    enabled_scenes = [path.strip() for enabled, path in entries if enabled == "1"]
    if not enabled_scenes or enabled_scenes[0] != main_scene:
        errors.append("SampleScene must remain the first enabled (main) build scene")

    for scene in re.findall(r"(?m)^\s*path:\s*(Assets/[^\r\n]+)", text):
        if not (root / scene).is_file():
            errors.append(f"Scene in build settings not found: {scene}")


def _check_scripts(root: Path, config: Config, errors: list[str]) -> None:
    asset_dir = root / "Assets"
    if not asset_dir.is_dir():
        return
    template_scripts = set(config.unity["templateScripts"])
    allowed_roots = tuple(config.unity["allowedScriptRoots"])
    for source in sorted(asset_dir.rglob("*.cs")):
        relative = _rel(root, source)
        if relative in template_scripts or relative.startswith(allowed_roots):
            continue
        errors.append(f"New C# scripts must be in MyScripts or OtherScripts: {relative}")


def _check_json(root: Path, errors: list[str]) -> None:
    for filename in ("Packages/manifest.json", "Packages/packages-lock.json"):
        path = root / filename
        if not path.is_file():
            continue
        try:
            json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, UnicodeError, ValueError) as exc:
            errors.append(f"Invalid JSON in {filename}: {exc}")


def _check_metas(root: Path, errors: list[str]) -> tuple[set[str], int]:
    asset_dir = root / "Assets"
    guid_locations: dict[str, str] = {}
    if not asset_dir.is_dir():
        return set(), 0
    for path in sorted(asset_dir.rglob("*")):
        if path.name.endswith(".meta"):
            content = _read(path)
            match = re.search(r"(?m)^guid:\s*([0-9a-fA-F]{32})\s*$", content)
            if not match:
                errors.append(f"Missing or invalid GUID in {_rel(root, path)}")
                continue
            guid = match.group(1).lower()
            if guid in guid_locations:
                errors.append(f"Duplicate GUID: {_rel(root, path)} and {guid_locations[guid]}")
            else:
                guid_locations[guid] = _rel(root, path)
        elif (
            path.name != ".gitkeep"
            and (path.is_file() or any(path.iterdir()))
            and not (path.parent / (path.name + ".meta")).is_file()
        ):
            errors.append(f"Missing .meta file for {_rel(root, path)}")
    return set(guid_locations), len(guid_locations)


def baseline_file(root: Path, config: Config) -> Path:
    return resolve_path(root, config.unity["externalGuidBaseline"])


def load_baseline(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    try:
        loaded = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, ValueError) as exc:
        raise DevctlError(EXIT_PRECONDITION, f"invalid JSON in {path}: {exc}") from exc
    if not isinstance(loaded, dict):
        raise DevctlError(EXIT_PRECONDITION, f"baseline must be an object: {path}")
    clean: dict[str, str] = {}
    for key, value in loaded.items():
        if not isinstance(key, str) or not isinstance(value, str):
            raise DevctlError(EXIT_PRECONDITION, f"baseline entries must map GUID to path: {path}")
        clean[key.lower()] = value
    return clean


def _iter_references(root: Path):
    """Yield (relative file, lower-case GUID) for asset references, once per GUID/file."""
    asset_dir = root / "Assets"
    if not asset_dir.is_dir():
        return
    for path in sorted(asset_dir.rglob("*")):
        if not path.is_file() or path.suffix not in REFERENCE_SUFFIXES:
            continue
        text = _read(path)
        seen: set[str] = set()
        for match in re.finditer(r"guid: ([0-9a-fA-F]{32})", text):
            guid = match.group(1).lower()
            if guid in seen:
                continue
            seen.add(guid)
            yield _rel(root, path), guid


def write_baseline(root: Path, config: Config) -> tuple[Path, int]:
    """Index Assets/Packages/Library metas and write the external GUID baseline.

    ``Library/PackageCache`` is required: without it the baseline would silently
    omit every package GUID and the subsequent integrity run would report false
    unresolved references, so refusing (exit 2) is safer than writing a bad file.

    References that are already unresolved at baseline time are recorded with the
    sentinel value ``"unresolved"``.  Unity templates ship a few dangling GUIDs
    (for example URP test volume components that are not in the installed
    package); freezing those keeps ``--write-baseline`` honest about the current
    state while still failing on any *new* broken reference.
    """
    package_cache = root / "Library/PackageCache"
    if not package_cache.is_dir():
        raise DevctlError(
            EXIT_PRECONDITION,
            "Library/PackageCache not found; cannot write the external GUID baseline "
            "(open the project once so Unity resolves packages)",
        )
    entries: dict[str, str] = {}
    for base in ("Assets", "Packages", "Library/PackageCache"):
        directory = root / base
        if not directory.is_dir():
            continue
        for meta in sorted(directory.rglob("*.meta")):
            match = re.search(r"(?m)^guid:\s*([0-9a-fA-F]{32})\s*$", _read(meta))
            if not match:
                continue
            entries.setdefault(match.group(1).lower(), _rel(root, meta))
    known = set(entries)
    for _relative, guid in _iter_references(root):
        if guid not in known and not guid.startswith("0" * 16):
            entries.setdefault(guid, "unresolved")
    path = baseline_file(root, config)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(sorted(entries.items())), indent=2) + "\n", encoding="utf-8")
    return path, len(entries)


def _check_references(root: Path, config: Config, asset_guids: set[str], errors: list[str]) -> None:
    baseline = load_baseline(baseline_file(root, config))
    known = asset_guids | set(baseline)
    for relative, guid in _iter_references(root):
        if guid in known or guid.startswith("0" * 16):
            continue
        errors.append(f"Unresolved asset reference {guid} in {relative}")


def check(root: Path, config: Config, write_baseline_requested: bool = False) -> IntegrityResult:
    """Run every integrity check against ``root`` without writing anything else."""
    root = Path(root)
    result = IntegrityResult()
    baseline_path: Path | None = None
    baseline_entries = 0
    if write_baseline_requested:
        baseline_path, baseline_entries = write_baseline(root, config)

    _check_required_paths(root, result.errors)
    _check_version(root, config, result.errors)
    scene = _check_scene(root, config, result.errors)
    if scene is not None:
        _check_required_objects(scene, config, result.errors)
    _check_build_settings(root, config, result.errors)
    _check_scripts(root, config, result.errors)
    _check_json(root, result.errors)
    asset_guids, guid_count = _check_metas(root, result.errors)
    _check_references(root, config, asset_guids, result.errors)
    if not (root / ".editorconfig").is_file():
        result.warnings.append("Missing .editorconfig at repository root")

    result.guid_count = guid_count
    result.baseline_path = baseline_path
    result.baseline_entries = baseline_entries
    return result


def print_result(result: IntegrityResult) -> None:
    """Print violations with the stable wording consumed by CI annotations."""
    for warning in result.warnings:
        print(f"::warning::{warning}")
    for error in result.errors:
        print(f"::error::{error}")
    if result.baseline_path is not None:
        print(
            f"::notice::Wrote external GUID baseline: {result.baseline_path} "
            f"({result.baseline_entries} entries)"
        )
    if not result.errors:
        print(f"Unity repository structure valid; {result.guid_count} unique asset GUIDs")
