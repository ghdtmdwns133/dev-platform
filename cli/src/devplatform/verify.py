"""The single verification pipeline shared by local development and CI.

``plan()`` is the authoritative step/argv table; ``run_verify()`` executes it,
aggregates failures (all steps run by default), and writes ``summary.json`` /
``summary.md``.  Exit codes follow the shared contract: 0 success, 1 gate failure,
2 precondition missing, 3 execution failure, 4 required feature absent.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from . import integrity, procs, report, unity
from .config import Config
from .errors import EXIT_EXECUTION, EXIT_GATE, DevctlError

Runner = Callable[..., procs.Result]

COVERAGE_PRODUCERS = {
    "python": "pytest",
    "typescript": "vitest",
    "dotnet": "dotnet-test",
}


@dataclass
class Step:
    name: str
    kind: str
    argv: list[str] = field(default_factory=list)
    platform: str | None = None
    coverage_kind: str | None = None


@dataclass
class Outcome:
    name: str
    status: str
    exit: int
    duration_s: float
    log: Path | None
    detail: str = ""


def _reports_step(reports_dir: Path, profile: str, name: str) -> Path:
    return Path(reports_dir) / profile / f"{name}.log"


def plan(
    profile: str,
    root: Path,
    reports_dir: Path,
    config: Config,
    min_coverage: int,
    unity_build: bool = False,
    upload_coverage: bool = False,
) -> list[Step]:
    """Return the fixed step table for ``profile`` with resolved argv."""
    profile_dir = Path(reports_dir) / profile
    profile_dir.mkdir(parents=True, exist_ok=True)
    steps: list[Step] = []
    if profile == "python":
        steps = [
            Step("uv-sync", "run", ["uv", "sync", "--frozen"]),
            Step(
                "ruff-check",
                "run",
                ["uv", "run", "--frozen", "ruff", "check", "--output-format=github", "."],
            ),
            Step("ruff-format", "run", ["uv", "run", "--frozen", "ruff", "format", "--check", "."]),
            Step(
                "pytest",
                "run",
                [
                    "uv",
                    "run",
                    "--frozen",
                    "pytest",
                    "-q",
                    f"--junitxml={profile_dir / 'junit.xml'}",
                    "--cov",
                    f"--cov-report=xml:{profile_dir / 'coverage.xml'}",
                    "--cov-report=term-missing",
                    f"--cov-fail-under={min_coverage}",
                ],
            ),
        ]
        if config.coverage_enabled:
            steps.append(Step("coverage", "coverage", coverage_kind="python"))
    elif profile == "typescript":
        steps = [
            Step("npm-ci", "run", ["npm", "ci", "--no-audit", "--no-fund"]),
            Step("tsc", "run", ["npx", "tsc", "--noEmit"]),
            Step("eslint", "run", ["npx", "eslint", ".", "--max-warnings=0"]),
            Step("prettier", "run", ["npx", "prettier", "--check", "."]),
            Step(
                "vitest",
                "run",
                [
                    "npx",
                    "vitest",
                    "run",
                    "--coverage",
                    "--reporter=default",
                    "--reporter=junit",
                    f"--outputFile.junit={profile_dir / 'junit.xml'}",
                ],
            ),
        ]
        if config.coverage_enabled:
            steps.append(Step("coverage", "coverage", coverage_kind="typescript"))
    elif profile == "dotnet":
        steps = [
            Step("dotnet-restore", "run", ["dotnet", "restore"]),
            Step("dotnet-build", "run", ["dotnet", "build", "--no-restore", "-warnaserror"]),
            Step(
                "dotnet-format",
                "run",
                ["dotnet", "format", "--verify-no-changes", "--severity", "warn"],
            ),
            Step(
                "dotnet-test",
                "run",
                [
                    "dotnet",
                    "test",
                    "--no-build",
                    "--collect:XPlat Code Coverage",
                    "--results-directory",
                    str(profile_dir),
                    "--logger",
                    f"trx;LogFileName={profile_dir / 'test.trx'}",
                ],
            ),
        ]
        if config.coverage_enabled:
            steps.append(Step("coverage", "coverage", coverage_kind="dotnet"))
    elif profile == "unity":
        steps = [Step("unity-integrity", "integrity")]
        for platform in config.unity["testPlatforms"]:
            steps.append(
                Step(
                    f"unity-{platform.lower()}",
                    "unity-test",
                    platform=platform,
                )
            )
        if config.coverage_enabled:
            steps.append(Step("unity-coverage", "unity-coverage"))
        if unity_build:
            steps.append(Step("unity-build", "unity-build"))
        if upload_coverage:
            steps.append(Step("unity-coverage-upload", "unity-coverage-upload"))
    elif profile == "unity-assets":
        steps = [Step("unity-integrity", "integrity")]
    else:  # pragma: no cover - argparse restricts profiles
        raise DevctlError(EXIT_EXECUTION, f"unknown profile: {profile}")

    for step in steps:
        if step.kind == "run":
            step.argv = [str(item) for item in step.argv]
    return steps


def _write_log(path: Path, lines: list[str]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _record(
    step: Step,
    status: str,
    exit_code: int,
    duration: float,
    log: Path | None,
    root: Path,
    detail: str = "",
) -> Outcome:
    return Outcome(step.name, status, exit_code, round(duration, 3), log, detail)


def _coverage_value(
    profile: str, root: Path, reports_dir: Path, kind: str
) -> tuple[float | None, Path | None]:
    if kind == "python":
        path = Path(reports_dir) / "python" / "coverage.xml"
    elif kind == "typescript":
        path = Path(root) / "coverage" / "coverage-summary.json"
    elif kind == "dotnet":
        candidates = sorted((Path(reports_dir) / "dotnet").rglob("coverage.cobertura.xml"))
        path = candidates[0] if candidates else None
    else:  # pragma: no cover - defensive
        return None, None
    if path is None or not Path(path).is_file():
        return None, None
    if kind == "typescript":
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8-sig"))
            value = data["total"]["lines"]["pct"]
            return float(value), Path(path)
        except (OSError, UnicodeError, ValueError, KeyError, TypeError):
            return None, Path(path)
    return report.cobertura_line_rate(Path(path)), Path(path)


def _coverage_detail(profile: str, value: float, minimum: int) -> str:
    return f"coverage {value}% (minimum {minimum}%)"


def _run_test_counts(profile: str, root: Path, reports_dir: Path) -> dict[str, int]:
    profile_dir = Path(reports_dir) / profile
    counts = {"passed": 0, "failed": 0, "skipped": 0}
    if profile in {"python", "typescript"}:
        path = profile_dir / "junit.xml"
        if path.is_file():
            counts = report.junit_counts(path)
    elif profile == "dotnet":
        path = profile_dir / "test.trx"
        if path.is_file():
            counts = report.trx_counts(path)
    return counts


def run_verify(
    profile: str,
    root: Path,
    reports_dir: Path,
    config: Config,
    platform_home: Path,
    min_coverage: int,
    unity_build: bool = False,
    upload_coverage: bool = False,
    fail_fast: bool = False,
    runner: Runner = procs.run,
) -> int:
    root = Path(root)
    reports_dir = Path(reports_dir)
    started_at = datetime.now(UTC).isoformat(timespec="seconds")
    started = time.monotonic()
    steps = plan(profile, root, reports_dir, config, min_coverage, unity_build, upload_coverage)
    outcomes: list[Outcome] = []
    coverage_record: dict[str, Any] = {
        "line": None,
        "minimum": min_coverage,
        "report": None,
    }
    tests = {"passed": 0, "failed": 0, "skipped": 0}
    aborted = False
    editor: Path | None = None

    def ensure_editor() -> Path:
        nonlocal editor
        if editor is None:
            editor = unity.require_editor(config, root)
            unity.check_editor_version(config, editor)
            unity.handle_lock(root)
        return editor

    def mark_failure() -> None:
        nonlocal aborted
        if fail_fast:
            aborted = True

    for step in steps:
        log = _reports_step(reports_dir, profile, step.name)
        if aborted:
            outcomes.append(
                _record(
                    step,
                    procs.STATUS_SKIPPED,
                    0,
                    0.0,
                    log,
                    root,
                    "skipped after failure (--fail-fast)",
                )
            )
            continue
        step_started = time.monotonic()
        try:
            if step.kind == "run":
                result = runner(step.name, step.argv, root, log)
                outcome = _record(
                    step,
                    result.status,
                    result.exit,
                    result.duration_s,
                    result.log,
                    root,
                    result.detail,
                )
            elif step.kind == "integrity":
                result = integrity.check(root, config)
                integrity.print_result(result)
                lines = [*[f"::warning::{item}" for item in result.warnings], *result.errors]
                _write_log(log, lines or ["Unity repository structure valid"])
                status = procs.STATUS_FAILED if result.errors else procs.STATUS_PASSED
                outcome = _record(
                    step,
                    status,
                    1 if result.errors else 0,
                    time.monotonic() - step_started,
                    log,
                    root,
                    f"{len(result.errors)} violation(s)",
                )
            elif step.kind == "unity-test":
                assert step.platform is not None
                result = unity.run_tests(
                    root, reports_dir, config, step.platform, ensure_editor(), runner, profile
                )
                outcome = _record(
                    step,
                    result.status,
                    result.exit,
                    time.monotonic() - step_started,
                    result.log,
                    root,
                    result.detail,
                )
                for key in ("passed", "failed", "skipped"):
                    tests[key] += int(result.data.get(key, 0))
            elif step.kind == "unity-coverage":
                results = unity.collect_coverage(reports_dir, config)
                aggregate = unity.aggregate_coverage(results)
                platforms = {name: row.get("line") for name, row in results.items()}
                coverage_record = {
                    "line": aggregate["line"],
                    "minimum": min_coverage,
                    "report": aggregate.get("report"),
                    "platforms": platforms,
                }
                _write_log(log, [json.dumps(coverage_record, indent=2)])
                if aggregate["line"] is None:
                    outcome = _record(
                        step,
                        procs.STATUS_PASSED,
                        0,
                        time.monotonic() - step_started,
                        log,
                        root,
                        "coverage report not produced",
                    )
                elif aggregate["line"] < min_coverage:
                    outcome = _record(
                        step,
                        procs.STATUS_FAILED,
                        1,
                        time.monotonic() - step_started,
                        log,
                        root,
                        _coverage_detail(profile, aggregate["line"], min_coverage),
                    )
                else:
                    outcome = _record(
                        step,
                        procs.STATUS_PASSED,
                        0,
                        time.monotonic() - step_started,
                        log,
                        root,
                        _coverage_detail(profile, aggregate["line"], min_coverage),
                    )
            elif step.kind == "coverage":
                producer = COVERAGE_PRODUCERS.get(step.coverage_kind or "")
                producer_outcome = next((item for item in outcomes if item.name == producer), None)
                if producer_outcome is not None and producer_outcome.status != procs.STATUS_PASSED:
                    outcome = _record(
                        step,
                        procs.STATUS_SKIPPED,
                        0,
                        time.monotonic() - step_started,
                        log,
                        root,
                        f"{producer} did not pass",
                    )
                    outcomes.append(outcome)
                    mark_failure()
                    continue
                value, path = _coverage_value(profile, root, reports_dir, step.coverage_kind or "")
                if value is None:
                    message = f"coverage report missing for {profile}"
                    _write_log(log, [message])
                    outcome = _record(
                        step,
                        procs.STATUS_ERROR,
                        EXIT_EXECUTION,
                        time.monotonic() - step_started,
                        log,
                        root,
                        message,
                    )
                else:
                    coverage_record = {
                        "line": round(value, 2),
                        "minimum": min_coverage,
                        "report": report.display_path(path, root) if path else None,
                    }
                    status = procs.STATUS_PASSED if value >= min_coverage else procs.STATUS_FAILED
                    _write_log(log, [json.dumps(coverage_record, indent=2)])
                    outcome = _record(
                        step,
                        status,
                        0 if status == procs.STATUS_PASSED else 1,
                        time.monotonic() - step_started,
                        log,
                        root,
                        _coverage_detail(profile, round(value, 2), min_coverage),
                    )
            elif step.kind == "unity-build":
                result = unity.build_project(
                    root, reports_dir, config, ensure_editor(), runner, profile
                )
                outcome = _record(
                    step,
                    result.status,
                    result.exit,
                    time.monotonic() - step_started,
                    result.log,
                    root,
                    result.detail,
                )
            elif step.kind == "unity-coverage-upload":
                result = unity.coverage_upload(root, reports_dir, platform_home, runner, profile)
                outcome = _record(
                    step,
                    result.status,
                    result.exit,
                    time.monotonic() - step_started,
                    result.log,
                    root,
                    result.detail,
                )
            else:  # pragma: no cover - defensive
                outcome = _record(
                    step,
                    procs.STATUS_ERROR,
                    EXIT_EXECUTION,
                    0.0,
                    log,
                    root,
                    f"unknown step kind: {step.kind}",
                )
        except DevctlError as exc:
            _write_log(log, [f"::error title={step.name}::{exc.message}"])
            outcome = _record(
                step,
                procs.STATUS_ERROR,
                exc.code,
                time.monotonic() - step_started,
                log,
                root,
                exc.message,
            )
            procs.emit_error(exc.message, title=step.name)
        except Exception as exc:
            message = f"{type(exc).__name__}: {exc}"
            _write_log(log, [message])
            outcome = _record(
                step,
                procs.STATUS_ERROR,
                EXIT_EXECUTION,
                time.monotonic() - step_started,
                log,
                root,
                message,
            )
            procs.emit_error(message, title=step.name)

        outcomes.append(outcome)
        if outcome.status in {procs.STATUS_FAILED, procs.STATUS_ERROR}:
            mark_failure()

    if profile in {"python", "typescript", "dotnet"}:
        tests = _run_test_counts(profile, root, reports_dir)

    exit_code = aggregate_exit(outcomes)
    status = (
        procs.STATUS_PASSED
        if exit_code == 0
        else (
            procs.STATUS_ERROR
            if any(o.status == procs.STATUS_ERROR for o in outcomes)
            else procs.STATUS_FAILED
        )
    )
    duration = time.monotonic() - started
    data = {
        "schema": 1,
        "profile": profile,
        "status": status,
        "exit": exit_code,
        "started": started_at,
        "duration_s": round(duration, 3),
        "root": root.resolve().as_posix(),
        "steps": [
            report.step_record(
                outcome.name,
                outcome.status,
                outcome.exit,
                outcome.duration_s,
                outcome.log,
                root,
                outcome.detail,
            )
            for outcome in outcomes
        ],
        "coverage": coverage_record,
        "tests": tests,
        "artifacts": report.artifact_list(reports_dir, profile, root),
    }
    json_path, markdown_path = report.write_summary(reports_dir, profile, data)
    if procs.is_ci():
        procs.emit_notice(f"devctl verify {profile}: {status} (exit {exit_code})")
    else:
        print(f"summary: {json_path}")
        print(markdown_path.read_text(encoding="utf-8").rstrip())
    return exit_code


def aggregate_exit(outcomes: list[Outcome]) -> int:
    errors = [item for item in outcomes if item.status == procs.STATUS_ERROR]
    if errors:
        for preferred in (2, 4, 3):
            if any(item.exit == preferred for item in errors):
                return preferred
        return EXIT_EXECUTION
    if any(item.status == procs.STATUS_FAILED for item in outcomes):
        return EXIT_GATE
    return 0
