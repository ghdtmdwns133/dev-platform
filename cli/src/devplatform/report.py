"""Summary reporting: ``summary.json``, ``summary.md`` and test/coverage parsing."""

from __future__ import annotations

import json
import os
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from .errors import EXIT_EXECUTION, EXIT_PRECONDITION, DevctlError
from .procs import display_path


def _path_text(value: Path | str | None) -> str | None:
    return str(value) if value is not None else None


def render_markdown(data: dict[str, Any]) -> str:
    """Render the human-readable summary used locally and in job summaries."""
    lines = [f"## devctl verify: {data['profile']} ({data['status']})", ""]
    lines.append("| step | status | exit | duration | detail |")
    lines.append("| --- | --- | --- | --- | --- |")
    for step in data["steps"]:
        detail = str(step.get("detail", "")).replace("|", "\\|")
        lines.append(
            f"| {step['name']} | {step['status']} | {step['exit']} "
            f"| {step['duration_s']:.2f}s | {detail} |"
        )
    lines.append("")
    coverage = data.get("coverage") or {}
    if coverage.get("line") is not None:
        minimum = coverage.get("minimum")
        lines.append(f"Coverage: {coverage['line']}% (minimum {minimum}%)")
    tests = data.get("tests") or {}
    lines.append(
        f"Tests: {tests.get('passed', 0)} passed, {tests.get('failed', 0)} failed, "
        f"{tests.get('skipped', 0)} skipped"
    )
    artifacts = data.get("artifacts") or []
    if artifacts:
        lines.append("")
        lines.append("Artifacts:")
        lines.extend(f"- `{item}`" for item in artifacts)
    lines.append("")
    return "\n".join(lines)


def append_step_summary(markdown: str) -> None:
    """Append to ``$GITHUB_STEP_SUMMARY`` when running in Actions."""
    target = os.environ.get("GITHUB_STEP_SUMMARY")
    if not target:
        return
    try:
        with Path(target).open("a", encoding="utf-8") as handle:
            handle.write(markdown)
            if not markdown.endswith("\n"):
                handle.write("\n")
    except OSError:
        # A missing/unwritable summary file must never fail the gate.
        pass


def write_summary(reports_dir: Path, profile: str, data: dict[str, Any]) -> tuple[Path, Path]:
    """Write ``<reports>/<profile>/summary.json`` and ``summary.md``."""
    directory = Path(reports_dir) / profile
    directory.mkdir(parents=True, exist_ok=True)
    json_path = directory / "summary.json"
    markdown_path = directory / "summary.md"
    json_path.write_text(json.dumps(data, indent=2, default=str) + "\n", encoding="utf-8")
    markdown = render_markdown(data)
    markdown_path.write_text(markdown, encoding="utf-8")
    append_step_summary(markdown)
    return json_path, markdown_path


def print_summaries(reports_dir: Path) -> None:
    """Print every profile's ``summary.md`` (``devctl summary``)."""
    reports_dir = Path(reports_dir)
    files = sorted(reports_dir.glob("*/summary.md"))
    if not files:
        raise DevctlError(EXIT_PRECONDITION, f"no summary found under {reports_dir}")
    for index, path in enumerate(files):
        if index:
            print()
        print(f"<!-- {path.parent.name} -->")
        print(path.read_text(encoding="utf-8").rstrip())


def cobertura_line_rate(path: Path) -> float | None:
    """Read ``line-rate`` from a Cobertura coverage file (0..1 scaled to 0..100)."""
    try:
        root = ET.parse(path).getroot()
    except (OSError, ET.ParseError) as exc:
        raise DevctlError(EXIT_EXECUTION, f"could not parse {path}: {exc}") from exc
    raw = root.get("line-rate")
    if raw is None:
        return None
    try:
        return round(float(raw) * 100.0, 2)
    except ValueError:
        return None


def junit_counts(path: Path) -> dict[str, int]:
    """Read aggregate counts from a JUnit XML file."""
    try:
        root = ET.parse(path).getroot()
    except (OSError, ET.ParseError):
        return {"passed": 0, "failed": 0, "skipped": 0}
    suites = [root] if root.tag == "testsuite" else list(root.iter("testsuite"))
    if not suites:
        suites = [root]
    total = failures = errors = skipped = 0
    for suite in suites:
        try:
            total += int(suite.get("tests", "0"))
            failures += int(suite.get("failures", "0"))
            errors += int(suite.get("errors", "0"))
            skipped += int(suite.get("skipped", "0"))
        except ValueError:
            continue
    failed = failures + errors
    return {
        "passed": max(total - failed - skipped, 0),
        "failed": failed,
        "skipped": skipped,
    }


def trx_counts(path: Path) -> dict[str, int]:
    """Read aggregate counts from a VSTest ``.trx`` result file."""
    try:
        root = ET.parse(path).getroot()
    except (OSError, ET.ParseError):
        return {"passed": 0, "failed": 0, "skipped": 0}
    for element in root.iter():
        if not isinstance(element.tag, str):
            continue
        if element.tag.rsplit("}", 1)[-1] != "Counters":
            continue
        try:
            total = int(element.get("total", "0"))
            passed = int(element.get("passed", "0"))
            failed = int(element.get("failed", "0"))
        except ValueError:
            continue
        return {
            "passed": passed,
            "failed": failed,
            "skipped": max(total - passed - failed, 0),
        }
    return {"passed": 0, "failed": 0, "skipped": 0}


def artifact_list(reports_dir: Path, profile: str, root: Path) -> list[str]:
    directory = Path(reports_dir) / profile
    if not directory.is_dir():
        return []
    return sorted(display_path(path, root) for path in directory.rglob("*") if path.is_file())


def step_record(
    name: str,
    status: str,
    exit_code: int,
    duration_s: float,
    log: Path | None,
    root: Path,
    detail: str = "",
) -> dict[str, Any]:
    return {
        "name": name,
        "status": status,
        "exit": exit_code,
        "duration_s": round(duration_s, 3),
        "log": display_path(log, root) if log is not None else None,
        "detail": detail,
    }
