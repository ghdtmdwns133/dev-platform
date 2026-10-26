"""Loading and validation of ``.devplatform/config.json``.

The config is intentionally strict: unknown keys are rejected so that a typo in a
consumer repository fails immediately instead of silently falling back to a
default.  Only ``profile`` is required when the file exists; every other value has
a documented default.  When the file does not exist at all, defaults are used and
the profile is ``None`` (useful for platform repositories such as dev-platform
itself, which only run ``devctl summary``).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .errors import EXIT_PRECONDITION, DevctlError

PROFILES = ("unity", "unity-assets")

#: Defaults documented in the platform specification.  Consumer repositories
#: override these through ``.devplatform/config.json``.
DEFAULT_UNITY: dict[str, Any] = {
    "version": "6000.5.1f1",
    "editorPath": None,
    "scene": "Assets/Scenes/SampleScene.unity",
    "sceneGuid": "99c9720ab356a0642a771bea13969a05",
    "mainScene": "Assets/Scenes/SampleScene.unity",
    "requiredObjects": [
        {"fileId": "330585543", "name": "Main Camera", "componentClassId": 20},
        {
            "fileId": "832575517",
            "name": "Global Volume",
            "componentClassId": 114,
            "requireGlobalVolume": True,
        },
    ],
    "allowedScriptRoots": ["Assets/MyScripts/", "Assets/OtherScripts/"],
    "templateScripts": [
        "Assets/Settings/GlobalVolumeSettings.cs",
        "Assets/TutorialInfo/Scripts/Readme.cs",
        "Assets/TutorialInfo/Scripts/Editor/ReadmeEditor.cs",
    ],
    "externalGuidBaseline": ".devplatform/external-guids.json",
    "testPlatforms": ["EditMode", "PlayMode"],
    "buildTarget": "StandaloneWindows64",
    "odinEntryPoint": "ProjectDelta.Editor.DevPlatform.OdinValidatorEntryPoint.Run",
    "playmodeMode": "gui",
    "retryFailed": 1,
    "coverageAssemblyFilters": ["-*Tests*"],
    "buildOutput": "artifacts/unity-build/ProjectDelta.exe",
    "cloudBuild": {"target": None, "timeoutMinutes": 90},
}

TOP_LEVEL_KEYS = {"profile", "reports", "coverage", "unity"}
COVERAGE_KEYS = {"minimum", "enabled"}
UNITY_KEYS = set(DEFAULT_UNITY)
REQUIRED_OBJECT_KEYS = {"fileId", "name", "componentClassId", "requireGlobalVolume"}


@dataclass(frozen=True)
class Config:
    """Validated configuration plus its source path."""

    profile: str | None
    reports: str
    coverage_minimum: int
    coverage_enabled: bool
    unity: dict[str, Any]
    raw: dict[str, Any]
    source: Path | None

    def unity_path(self, root: Path, key: str) -> Path:
        """Resolve a unity path-valued key relative to ``root`` (absolute allowed)."""
        value = self.unity.get(key)
        if not isinstance(value, str) or not value:
            raise DevctlError(EXIT_PRECONDITION, f"unity.{key} must be a non-empty string")
        path = Path(value)
        return path if path.is_absolute() else root / path


def _error(message: str) -> DevctlError:
    return DevctlError(EXIT_PRECONDITION, message)


def _expect_bool(value: Any, name: str) -> bool:
    if not isinstance(value, bool):
        raise _error(f"{name} must be true or false")
    return value


def _expect_int(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise _error(f"{name} must be an integer")
    return value


def _expect_str(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value:
        raise _error(f"{name} must be a non-empty string")
    return value


def _expect_str_list(value: Any, name: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise _error(f"{name} must be a list of strings")
    return list(value)


def _validate_required_objects(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise _error("unity.requiredObjects must be a list")
    result: list[dict[str, Any]] = []
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            raise _error(f"unity.requiredObjects[{index}] must be an object")
        unknown = set(item) - REQUIRED_OBJECT_KEYS
        if unknown:
            raise _error(f"unknown key(s) in unity.requiredObjects[{index}]: {sorted(unknown)}")
        if "fileId" not in item or "name" not in item or "componentClassId" not in item:
            raise _error(f"unity.requiredObjects[{index}] needs fileId, name and componentClassId")
        result.append(
            {
                "fileId": str(item["fileId"]),
                "name": _expect_str(item["name"], f"unity.requiredObjects[{index}].name"),
                "componentClassId": _expect_int(
                    item["componentClassId"], f"unity.requiredObjects[{index}].componentClassId"
                ),
                "requireGlobalVolume": _expect_bool(
                    item.get("requireGlobalVolume", False),
                    f"unity.requiredObjects[{index}].requireGlobalVolume",
                ),
            }
        )
    return result


CLOUD_BUILD_KEYS = {"target", "timeoutMinutes"}


def _validate_cloud_build(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise _error("unity.cloudBuild must be an object")
    unknown = set(value) - CLOUD_BUILD_KEYS
    if unknown:
        raise _error(f"unknown key(s) in unity.cloudBuild: {sorted(unknown)}")
    target = value.get("target")
    if target is not None:
        target = _expect_str(target, "unity.cloudBuild.target")
    timeout = _expect_int(value.get("timeoutMinutes", 90), "unity.cloudBuild.timeoutMinutes")
    if timeout < 1 or timeout > 1440:
        raise _error("unity.cloudBuild.timeoutMinutes must be between 1 and 1440")
    return {"target": target, "timeoutMinutes": timeout}


def _validate_unity(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise _error("unity must be an object")
    unknown = set(value) - UNITY_KEYS
    if unknown:
        raise _error(f"unknown key(s) in unity: {sorted(unknown)}")
    unity = dict(DEFAULT_UNITY)
    unity.update(value)

    for key in (
        "version",
        "scene",
        "sceneGuid",
        "mainScene",
        "externalGuidBaseline",
        "buildTarget",
        "odinEntryPoint",
        "buildOutput",
    ):
        unity[key] = _expect_str(unity[key], f"unity.{key}")
    if unity["editorPath"] is not None:
        unity["editorPath"] = _expect_str(unity["editorPath"], "unity.editorPath")
    unity["requiredObjects"] = _validate_required_objects(unity["requiredObjects"])
    unity["allowedScriptRoots"] = _expect_str_list(
        unity["allowedScriptRoots"], "unity.allowedScriptRoots"
    )
    unity["templateScripts"] = _expect_str_list(unity["templateScripts"], "unity.templateScripts")
    unity["testPlatforms"] = _expect_str_list(unity["testPlatforms"], "unity.testPlatforms")
    if not unity["testPlatforms"] or len(set(unity["testPlatforms"])) != len(
        unity["testPlatforms"]
    ):
        raise _error("unity.testPlatforms must be a non-empty list without duplicates")
    if any(platform not in {"EditMode", "PlayMode"} for platform in unity["testPlatforms"]):
        raise _error("unity.testPlatforms must contain only EditMode and/or PlayMode")
    unity["coverageAssemblyFilters"] = _expect_str_list(
        unity["coverageAssemblyFilters"], "unity.coverageAssemblyFilters"
    )
    unity["playmodeMode"] = _expect_str(unity["playmodeMode"], "unity.playmodeMode")
    if unity["playmodeMode"] not in {"gui", "batch"}:
        raise _error('unity.playmodeMode must be "gui" or "batch"')
    unity["retryFailed"] = _expect_int(unity["retryFailed"], "unity.retryFailed")
    if unity["retryFailed"] < 0:
        raise _error("unity.retryFailed must be zero or greater")
    unity["cloudBuild"] = _validate_cloud_build(unity["cloudBuild"])
    return unity


def load_config(
    root: Path, config_path: Path | str | None = None, cli_profile: str | None = None
) -> Config:
    """Load and validate the configuration for ``root``.

    ``cli_profile`` is compared against ``profile`` when both are present; a
    mismatch is a precondition error (exit 2).
    """
    root = Path(root)
    explicit = config_path is not None
    path = Path(config_path) if config_path is not None else root / ".devplatform" / "config.json"
    if not path.is_absolute():
        path = root / path

    data: dict[str, Any] = {}
    exists = path.is_file()
    if explicit and not exists:
        raise _error(f"config file not found: {path}")
    if exists:
        try:
            loaded = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, UnicodeError, ValueError) as exc:
            raise _error(f"invalid JSON in {path}: {exc}") from exc
        if not isinstance(loaded, dict):
            raise _error(f"config root must be an object in {path}")
        data = loaded
        unknown = set(data) - TOP_LEVEL_KEYS
        if unknown:
            raise _error(f"unknown key(s) in {path}: {sorted(unknown)}")

    profile = data.get("profile")
    if profile is None:
        if exists:
            raise _error(f"profile is required in {path}")
    else:
        profile = _expect_str(profile, "profile")
        if profile not in PROFILES:
            raise _error(f"profile must be one of {list(PROFILES)}, got {profile!r}")
    if cli_profile is not None and profile is not None and cli_profile != profile:
        compatible = cli_profile == "unity-assets" and profile == "unity"
        if not compatible:
            raise _error(
                f"profile mismatch: CLI requested {cli_profile!r} but {path} declares {profile!r}"
            )

    reports = _expect_str(data.get("reports", "artifacts/reports"), "reports")

    coverage = data.get("coverage", {})
    if not isinstance(coverage, dict):
        raise _error("coverage must be an object")
    unknown = set(coverage) - COVERAGE_KEYS
    if unknown:
        raise _error(f"unknown key(s) in coverage: {sorted(unknown)}")
    minimum = _expect_int(coverage.get("minimum", 0), "coverage.minimum")
    if minimum < 0 or minimum > 100:
        raise _error("coverage.minimum must be between 0 and 100")
    enabled = _expect_bool(coverage.get("enabled", True), "coverage.enabled")

    unity = _validate_unity(data.get("unity", {}))

    return Config(
        profile=profile,
        reports=reports,
        coverage_minimum=minimum,
        coverage_enabled=enabled,
        unity=unity,
        raw=data,
        source=path if exists else None,
    )


def reports_directory(root: Path, config: Config, override: str | None = None) -> Path:
    """Return the absolute reports directory (``--reports`` wins over config)."""
    value = override if override is not None else config.reports
    path = Path(value)
    return path if path.is_absolute() else Path(root) / path


def resolve_path(root: Path, value: str) -> Path:
    """Resolve a config path, honouring absolute paths."""
    path = Path(value)
    return path if path.is_absolute() else Path(root) / path
