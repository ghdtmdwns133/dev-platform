"""Unity editor discovery, headless test/build execution, and result parsing.

Design notes
------------
* EditMode always runs with ``-nographics``.  PlayMode runs with graphics by
  default (the first supported combination) and only adds ``-nographics`` when
  ``unity.playmodeNographics`` is true, so a repository whose play mode tests need
  a graphics device can opt out.
* Test runs never pass ``-quit``: Unity documents that ``-quit`` is unsupported
  while ``-runTests`` is active; the editor exits on its own when the run ends.
* ``unity.coverageAssemblyFilters`` uses Unity's ``assemblyFilters`` syntax
  (``+Include`` / ``-Exclude``).  The default ``["-*Tests*"]`` keeps everything
  except assemblies whose name contains ``Tests`` in coverage; repositories that
  want a narrow runtime assembly set override it, e.g.
  ``["+ProjectDelta.Runtime", "-ProjectDelta.Tests.*"]``.
* ``unity.playmodeNographics`` (default false) and ``unity.buildOutput``
  (default ``artifacts/unity-build/ProjectDelta.exe``) are the only extra config
  keys beyond the platform plan; both are validated by :mod:`devplatform.config`.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import xml.etree.ElementTree as ET
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import procs
from .config import Config, resolve_path
from .errors import EXIT_EXECUTION, EXIT_PRECONDITION, EXIT_REQUIRED_FEATURE, DevctlError

Runner = Callable[..., procs.Result]
EDITOR_CANDIDATE_ROOTS = ("C:/Program Files/Unity/Hub/Editor",)
MIN_BUILD_BYTES = 1024 * 1024


@dataclass
class UnityStep:
    """A normalized unity execution outcome for summary reporting."""

    name: str
    status: str
    exit: int
    log: Path | None = None
    detail: str = ""
    data: dict[str, Any] = field(default_factory=dict)


def find_editor(config: Config, root: Path | None = None) -> Path | None:
    """Locate the Unity editor using the documented precedence order."""
    version = config.unity["version"]
    candidates: list[Path] = []
    configured = config.unity.get("editorPath")
    if configured:
        configured_path = Path(str(configured))
        candidates.append(
            configured_path
            if configured_path.is_absolute()
            else (Path(root) / configured_path if root is not None else configured_path)
        )
    env_path = os.environ.get("UNITY_EDITOR_PATH")
    if env_path:
        candidates.append(Path(env_path))
    hub_roots = [Path(item) for item in EDITOR_CANDIDATE_ROOTS]
    for variable in ("ProgramFiles", "ProgramFiles(x86)"):
        value = os.environ.get(variable)
        if value:
            hub_roots.append(Path(value) / "Unity/Hub/Editor")
    for base in hub_roots:
        candidates.append(base / version / "Editor/Unity.exe")
        candidates.append(base / version / "Editor/Unity")
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def require_editor(config: Config, root: Path | None = None) -> Path:
    editor = find_editor(config, root)
    if editor is None:
        raise DevctlError(
            EXIT_PRECONDITION,
            f"Unity {config.unity['version']} editor not found; set unity.editorPath",
        )
    return editor


def probe_editor_version(editor: Path, timeout: float = 180.0) -> tuple[str | None, str]:
    """Run ``Unity -version`` and return (version, captured output)."""
    try:
        completed = subprocess.run(
            [str(editor), "-version"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
        text = (completed.stdout or "") + (completed.stderr or "")
    except (OSError, subprocess.TimeoutExpired) as exc:
        return None, str(exc)
    match = re.search(r"\b(\d+\.\d+\.\d+[abfp]\d+)\b", text)
    return (match.group(1) if match else None), text.strip()


def check_editor_version(config: Config, editor: Path) -> None:
    actual, output = probe_editor_version(editor)
    expected = config.unity["version"]
    if actual is None:
        raise DevctlError(
            EXIT_PRECONDITION,
            f"could not determine Unity editor version from {editor}",
            detail=output[-2000:] if output else None,
        )
    if actual != expected:
        raise DevctlError(
            EXIT_PRECONDITION,
            f"Unity editor version mismatch: expected {expected}, found {actual}",
        )


def _process_alive(pid: int) -> bool:
    if os.name == "nt":
        try:
            completed = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=30,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return False
        return re.search(rf"\b{pid}\b", completed.stdout or "") is not None
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def handle_lock(root: Path) -> bool:
    """Remove a stale ``Temp/UnityLockfile`` or refuse when an editor is alive."""
    lockfile = Path(root) / "Temp/UnityLockfile"
    if not lockfile.exists():
        return False
    pid: int | None = None
    instance = Path(root) / "Library/EditorInstance.json"
    if instance.is_file():
        try:
            data = json.loads(instance.read_text(encoding="utf-8-sig"))
            if isinstance(data, dict) and isinstance(data.get("process_id"), int):
                pid = int(data["process_id"])
        except (OSError, UnicodeError, ValueError, TypeError):
            pid = None
    if pid is not None and _process_alive(pid):
        raise DevctlError(
            EXIT_PRECONDITION,
            f"Unity editor is running (pid {pid}); close it before headless verification",
        )
    try:
        lockfile.unlink()
    except FileNotFoundError:
        return False
    except OSError as exc:
        raise DevctlError(EXIT_EXECUTION, f"could not remove stale Unity lockfile: {exc}") from exc
    procs.emit_notice("Removed stale Unity lockfile")
    return True


def coverage_options(config: Config) -> str:
    options = ["generateAdditionalMetrics", "generateHtmlReport", "generateBadgeReport"]
    filters = config.unity["coverageAssemblyFilters"]
    if filters:
        options.append("assemblyFilters:" + ";".join(filters))
    return ";".join(options)


def test_argv(
    root: Path, reports_dir: Path, config: Config, platform: str, editor: Path
) -> list[str]:
    """Build the exact headless test argv (never includes ``-quit``)."""
    unity_dir = Path(reports_dir) / "unity"
    argv = [str(editor), "-batchmode"]
    if platform == "EditMode" or config.unity["playmodeNographics"]:
        argv.append("-nographics")
    argv.extend(
        [
            "-runTests",
            "-projectPath",
            str(root),
            "-testPlatform",
            platform,
            "-testResults",
            str(unity_dir / f"{platform.lower()}.xml"),
            "-logFile",
            str(unity_dir / f"{platform.lower()}.log"),
        ]
    )
    if config.coverage_enabled:
        argv.extend(
            [
                "-enableCodeCoverage",
                "-coverageResultsPath",
                str(unity_dir / f"coverage-{platform.lower()}"),
                "-coverageOptions",
                coverage_options(config),
            ]
        )
    return argv


def parse_nunit(path: Path) -> dict[str, Any]:
    """Parse a Unity NUnit3 ``<test-run>`` result file."""
    try:
        root = ET.parse(path).getroot()
    except (OSError, ET.ParseError) as exc:
        raise DevctlError(
            EXIT_EXECUTION, f"could not parse Unity test results {path}: {exc}"
        ) from exc
    run = root if root.tag == "test-run" else root.find(".//test-run")
    if run is None:
        raise DevctlError(EXIT_EXECUTION, f"no <test-run> element in {path}")
    if run.get("failed") is None:
        raise DevctlError(EXIT_EXECUTION, f"test-run element has no failed attribute in {path}")

    def _int(attribute: str) -> int:
        try:
            return int(run.get(attribute, "0"))
        except (TypeError, ValueError):
            return 0

    return {
        "passed": _int("passed"),
        "failed": _int("failed"),
        "skipped": _int("skipped") + _int("inconclusive"),
        "total": _int("total") or _int("testcasecount"),
        "result": run.get("result", ""),
    }


def parse_summary_xml(path: Path) -> dict[str, Any]:
    """Parse a Unity Code Coverage ``Report/Summary.xml`` line coverage report."""
    try:
        root = ET.parse(path).getroot()
    except (OSError, ET.ParseError) as exc:
        raise DevctlError(EXIT_EXECUTION, f"could not parse coverage report {path}: {exc}") from exc
    summary = root.find(".//Summary")
    if summary is None:
        summary = root
    values: dict[str, str] = {}
    for child in summary.iter():
        if isinstance(child.tag, str) and child.text:
            values[child.tag.lower()] = child.text.strip()

    def number(*names: str) -> float | None:
        for name in names:
            raw = values.get(name)
            if raw is None:
                continue
            cleaned = raw.replace("%", "").strip()
            try:
                return float(cleaned)
            except ValueError:
                continue
        return None

    covered = number("coveredlines")
    coverable = number("coverablelines")
    line = number("linecoverage", "totalpercentage")
    if line is None and coverable:
        line = (covered or 0.0) / coverable * 100.0
    if line is None:
        raise DevctlError(EXIT_EXECUTION, f"no line coverage value in {path}")
    return {
        "line": round(line, 2),
        "covered": int(covered) if covered is not None else None,
        "coverable": int(coverable) if coverable is not None else None,
    }


def run_tests(
    root: Path,
    reports_dir: Path,
    config: Config,
    platform: str,
    editor: Path,
    runner: Runner = procs.run,
    profile: str = "unity",
) -> UnityStep:
    """Run one Unity test platform and validate its NUnit3 result file."""
    unity_dir = Path(reports_dir) / "unity"
    unity_dir.mkdir(parents=True, exist_ok=True)
    handle_lock(Path(root))
    name = f"unity-{platform.lower()}"
    argv = test_argv(Path(root), Path(reports_dir), config, platform, editor)
    result = runner(
        name,
        argv,
        Path(root),
        Path(reports_dir) / profile / f"{name}.log",
    )
    result_file = unity_dir / f"{platform.lower()}.xml"
    if result.status == procs.STATUS_ERROR:
        return UnityStep(name, procs.STATUS_ERROR, result.exit, result.log, result.detail)
    if not result_file.is_file():
        return UnityStep(
            name,
            procs.STATUS_ERROR,
            EXIT_EXECUTION,
            result.log,
            f"Unity test result file missing: {result_file}",
        )
    try:
        counts = parse_nunit(result_file)
    except DevctlError as exc:
        return UnityStep(name, procs.STATUS_ERROR, EXIT_EXECUTION, result.log, exc.message)

    failed = counts["failed"] > 0 or counts["result"] != "Passed"
    status = procs.STATUS_FAILED if failed or result.exit != 0 else procs.STATUS_PASSED
    exit_code = 0 if status == procs.STATUS_PASSED else 1
    detail = f"{counts['passed']} passed, {counts['failed']} failed, {counts['skipped']} skipped"
    if result.exit != 0 and not failed:
        detail += f" (Unity exit {result.exit})"
    return UnityStep(name, status, exit_code, result.log, detail, counts)


def build_project(
    root: Path,
    reports_dir: Path,
    config: Config,
    editor: Path,
    runner: Runner = procs.run,
    profile: str = "unity",
) -> UnityStep:
    """Build the standalone Windows player and verify the produced executable."""
    root = Path(root)
    reports_dir = Path(reports_dir)
    unity_dir = reports_dir / "unity"
    unity_dir.mkdir(parents=True, exist_ok=True)
    handle_lock(root)
    output = resolve_path(root, config.unity["buildOutput"])
    argv = [
        str(editor),
        "-batchmode",
        "-quit",
        "-projectPath",
        str(root),
        "-buildWindows64Player",
        str(output),
        "-logFile",
        str(unity_dir / "build.log"),
    ]
    result = runner("unity-build", argv, root, reports_dir / profile / "unity-build.log")
    if result.status == procs.STATUS_ERROR:
        return UnityStep("unity-build", procs.STATUS_ERROR, result.exit, result.log, result.detail)
    if result.exit != 0:
        return UnityStep(
            "unity-build", procs.STATUS_FAILED, result.exit, result.log, f"exit {result.exit}"
        )
    if not output.is_file():
        return UnityStep(
            "unity-build",
            procs.STATUS_ERROR,
            EXIT_EXECUTION,
            result.log,
            f"build output missing: {output}",
        )
    size = output.stat().st_size
    if size <= MIN_BUILD_BYTES:
        return UnityStep(
            "unity-build",
            procs.STATUS_ERROR,
            EXIT_EXECUTION,
            result.log,
            f"build output too small: {size} bytes",
        )
    return UnityStep("unity-build", procs.STATUS_PASSED, 0, result.log, f"{size} bytes")


def run_odin(
    root: Path,
    reports_dir: Path,
    config: Config,
    editor: Path,
    runner: Runner = procs.run,
    profile: str = "unity",
    require_odin: bool = False,
) -> UnityStep:
    """Invoke the Odin validator bridge and interpret its JSON report."""
    root = Path(root)
    reports_dir = Path(reports_dir)
    unity_dir = reports_dir / "unity"
    unity_dir.mkdir(parents=True, exist_ok=True)
    handle_lock(root)
    entry = config.unity["odinEntryPoint"]
    argv = [
        str(editor),
        "-batchmode",
        "-projectPath",
        str(root),
        "-executeMethod",
        entry,
        "-logFile",
        str(unity_dir / "odin.log"),
    ]
    result = runner("unity-odin", argv, root, reports_dir / profile / "unity-odin.log")
    report_path = unity_dir / "odin.json"
    if not report_path.is_file():
        return UnityStep(
            "unity-odin",
            procs.STATUS_ERROR,
            EXIT_EXECUTION,
            result.log,
            f"Odin report missing: {report_path}",
        )
    try:
        report = json.loads(report_path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, ValueError) as exc:
        return UnityStep(
            "unity-odin",
            procs.STATUS_ERROR,
            EXIT_EXECUTION,
            result.log,
            f"invalid Odin report: {exc}",
        )
    status = report.get("status") if isinstance(report, dict) else None
    if status == "skipped":
        if require_odin:
            raise DevctlError(
                EXIT_REQUIRED_FEATURE,
                "Odin Validator required but the bridge reported skipped",
                detail=str(report.get("reason", "")),
            )
        return UnityStep("unity-odin", procs.STATUS_PASSED, 0, result.log, "odin: skipped")
    if status == "passed":
        return UnityStep("unity-odin", procs.STATUS_PASSED, 0, result.log, "odin: passed")
    if status == "failed":
        detail = json.dumps(report, sort_keys=True)
        return UnityStep("unity-odin", procs.STATUS_FAILED, 1, result.log, detail[:500])
    return UnityStep(
        "unity-odin",
        procs.STATUS_ERROR,
        EXIT_EXECUTION,
        result.log,
        f"unexpected Odin report status: {status!r}",
    )


def collect_coverage(
    reports_dir: Path, config: Config, platforms: list[str] | None = None
) -> dict[str, dict[str, Any]]:
    """Parse ``coverage-<platform>/Report/Summary.xml`` for each test platform."""
    reports_dir = Path(reports_dir)
    wanted = platforms if platforms is not None else list(config.unity["testPlatforms"])
    results: dict[str, dict[str, Any]] = {}
    for platform in wanted:
        path = reports_dir / "unity" / f"coverage-{platform.lower()}" / "Report" / "Summary.xml"
        if not path.is_file():
            procs.emit_warning("code coverage report not produced")
            results[platform] = {"line": None, "report": None}
            continue
        parsed = parse_summary_xml(path)
        parsed["report"] = path
        results[platform] = parsed
    return results


def aggregate_coverage(results: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Combine per-platform coverage into one summary record."""
    rows = [row for row in results.values() if row.get("line") is not None]
    if not rows:
        return {"line": None, "minimum": None, "report": None}
    covered = sum(row["covered"] for row in rows if row.get("covered") is not None)
    coverable = sum(row["coverable"] for row in rows if row.get("coverable") is not None)
    if coverable:
        line = round(covered / coverable * 100.0, 2)
    else:
        line = round(sum(row["line"] for row in rows) / len(rows), 2)
    report = rows[0].get("report")
    return {
        "line": line,
        "report": Path(report).as_posix() if report else None,
        "platforms": {name: row.get("line") for name, row in results.items()},
    }


def nunit_to_junit(source: Path, out: Path) -> dict[str, int]:
    """Convert Unity's NUnit3 XML (file or directory) into JUnit XML."""
    source = Path(source)
    out = Path(out)
    if source.is_file():
        files = [source]
    elif source.is_dir():
        files = sorted(source.rglob("*.xml"))
    else:
        raise DevctlError(EXIT_PRECONDITION, f"test results not found: {source}")

    cases: list[dict[str, Any]] = []
    for path in files:
        try:
            root = ET.parse(path).getroot()
        except (OSError, ET.ParseError):
            continue
        run = root if root.tag == "test-run" else root.find(".//test-run")
        if run is None:
            continue
        for case in run.iter("test-case"):
            fullname = case.get("fullname") or case.get("name") or "unnamed"
            classname = fullname.rpartition(".")[0] or "Unity"
            result = case.get("result", "")
            failure = case.find("failure")
            message = ""
            stack = ""
            if failure is not None:
                message_node = failure.find("message")
                stack_node = failure.find("stack-trace")
                message = (message_node.text or "").strip() if message_node is not None else ""
                stack = (stack_node.text or "").strip() if stack_node is not None else ""
            reason = case.find("reason")
            skipped_message = ""
            if reason is not None:
                reason_message = reason.find("message")
                if reason_message is not None and reason_message.text:
                    skipped_message = reason_message.text.strip()
            try:
                duration = float(case.get("duration", "0") or 0)
            except ValueError:
                duration = 0.0
            cases.append(
                {
                    "name": case.get("name") or fullname,
                    "classname": classname,
                    "time": duration,
                    "result": result,
                    "message": message or skipped_message,
                    "stack": stack,
                }
            )
    if not cases:
        raise DevctlError(EXIT_EXECUTION, f"no NUnit3 test cases found in {source}")

    failures = sum(1 for case in cases if case["result"] in {"Failed", "Error"})
    skipped = sum(1 for case in cases if case["result"] in {"Skipped", "Inconclusive"})
    total_time = sum(case["time"] for case in cases)
    suites = ET.Element(
        "testsuites",
        {
            "name": "unity",
            "tests": str(len(cases)),
            "failures": str(failures),
            "errors": "0",
            "skipped": str(skipped),
            "time": f"{total_time:.3f}",
        },
    )
    suite = ET.SubElement(
        suites,
        "testsuite",
        {
            "name": "unity",
            "tests": str(len(cases)),
            "failures": str(failures),
            "errors": "0",
            "skipped": str(skipped),
            "time": f"{total_time:.3f}",
        },
    )
    for case in cases:
        element = ET.SubElement(
            suite,
            "testcase",
            {
                "classname": str(case["classname"]),
                "name": str(case["name"]),
                "time": f"{case['time']:.3f}",
            },
        )
        if case["result"] in {"Failed", "Error"}:
            failure = ET.SubElement(element, "failure", {"message": str(case["message"])[:1000]})
            failure.text = str(case["stack"]) or str(case["message"])
        elif case["result"] in {"Skipped", "Inconclusive"}:
            ET.SubElement(element, "skipped", {"message": str(case["message"])[:1000]})
    out.parent.mkdir(parents=True, exist_ok=True)
    ET.ElementTree(suites).write(out, encoding="utf-8", xml_declaration=True)
    return {"tests": len(cases), "failures": failures, "skipped": skipped}


def _git(root: Path, *args: str) -> tuple[int, str, str]:
    completed = subprocess.run(
        ["git", "-C", str(root), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    return completed.returncode, (completed.stdout or "").strip(), (completed.stderr or "").strip()


def opencover_reports(reports_dir: Path) -> list[Path]:
    unity_dir = Path(reports_dir) / "unity"
    if not unity_dir.is_dir():
        return []
    return sorted(unity_dir.glob("coverage-*/**/TestCoverageResults_*.xml"))


def github_slug(root: Path) -> str:
    code, remote, _ = _git(Path(root), "remote", "get-url", "origin")
    if code != 0 or not remote:
        raise DevctlError(
            EXIT_PRECONDITION, "cannot determine GitHub slug: no origin remote configured"
        )
    match = re.search(r"github\.com[:/]([^/]+)/([^/]+?)(?:\.git)?/?$", remote)
    if not match:
        raise DevctlError(
            EXIT_PRECONDITION, f"cannot determine GitHub slug from origin remote: {remote}"
        )
    return f"{match.group(1)}/{match.group(2)}"


def _platform_from_report(report: Path, unity_dir: Path) -> str:
    for part in report.relative_to(unity_dir).parts:
        if part.startswith("coverage-"):
            return part[len("coverage-") :] or "unity"
    return "unity"


def coverage_upload(
    root: Path,
    reports_dir: Path,
    platform_home: Path,
    runner: Runner = procs.run,
    profile: str = "unity",
    token: str | None = None,
) -> UnityStep:
    """Upload Unity OpenCover reports to Codecov for each test platform flag."""
    from .versions import load_versions

    root = Path(root)
    reports_dir = Path(reports_dir)
    unity_dir = reports_dir / "unity"
    reports = opencover_reports(reports_dir)
    if not reports:
        raise DevctlError(EXIT_PRECONDITION, "no Unity OpenCover report found")
    token = token if token is not None else os.environ.get("CODECOV_TOKEN", "")
    if not token:
        raise DevctlError(EXIT_PRECONDITION, "CODECOV_TOKEN not set (run via 'doppler run --')")
    code, status, _ = _git(root, "status", "--porcelain")
    if code != 0:
        raise DevctlError(
            EXIT_EXECUTION, "git status failed; coverage upload requires a git checkout"
        )
    if status:
        raise DevctlError(EXIT_PRECONDITION, "commit must be pushed before coverage upload")
    code, sha, _ = _git(root, "rev-parse", "HEAD")
    if code != 0 or not sha:
        raise DevctlError(EXIT_EXECUTION, "could not read HEAD for coverage upload")
    code, contains, _ = _git(root, "branch", "-r", "--contains", "HEAD")
    if code != 0 or not contains:
        raise DevctlError(EXIT_PRECONDITION, "commit must be pushed before coverage upload")
    code, branch, _ = _git(root, "rev-parse", "--abbrev-ref", "HEAD")
    if code != 0 or not branch or branch == "HEAD":
        raise DevctlError(
            EXIT_PRECONDITION, "coverage upload requires a checked-out branch (detached HEAD)"
        )
    slug = github_slug(root)
    version = load_versions(Path(platform_home)).get("tools", {}).get("codecovCli")
    if not version:
        raise DevctlError(EXIT_PRECONDITION, "tools.codecovCli missing from versions.json")

    grouped: dict[str, list[Path]] = {}
    for report in reports:
        grouped.setdefault(_platform_from_report(report, unity_dir), []).append(report)

    logs: list[Path] = []
    statuses: list[UnityStep] = []
    for platform, files in sorted(grouped.items()):
        flag = f"unity-{platform}"
        argv = [
            "uvx",
            "--python",
            "3.12",
            "--from",
            f"codecov-cli=={version}",
            "codecovcli",
            "upload-process",
            "--git-service",
            "github",
            "--slug",
            slug,
            "--sha",
            sha,
            "--branch",
            branch,
            "--flag",
            flag,
            "--fail-on-error",
        ]
        for file in files:
            argv.extend(["--file", str(file)])
        log = reports_dir / profile / f"unity-coverage-upload-{flag}.log"
        result = runner(
            f"unity-coverage-upload-{flag}",
            argv,
            root,
            log,
            env={"CODECOV_TOKEN": token},
        )
        logs.append(log)
        statuses.append(
            UnityStep(
                f"unity-coverage-upload-{flag}",
                result.status,
                0
                if result.status == procs.STATUS_PASSED
                else (1 if result.exit == 0 else result.exit),
                log,
                f"flag {flag}: {len(files)} file(s)",
            )
        )
    combined_log = reports_dir / profile / "unity-coverage-upload.log"
    combined_log.parent.mkdir(parents=True, exist_ok=True)
    combined_log.write_text(
        "".join(path.read_text(encoding="utf-8") for path in logs if path.is_file()),
        encoding="utf-8",
    )
    if any(step.status == procs.STATUS_ERROR for step in statuses):
        return UnityStep(
            "unity-coverage-upload",
            procs.STATUS_ERROR,
            EXIT_EXECUTION,
            combined_log,
            "; ".join(step.detail for step in statuses),
        )
    if any(step.status == procs.STATUS_FAILED for step in statuses):
        return UnityStep(
            "unity-coverage-upload",
            procs.STATUS_FAILED,
            1,
            combined_log,
            "; ".join(step.detail for step in statuses),
        )
    return UnityStep(
        "unity-coverage-upload",
        procs.STATUS_PASSED,
        0,
        combined_log,
        "; ".join(step.detail for step in statuses),
    )
