"""Security gate fixtures generated at runtime (no secrets in the repository)."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

ZIZMOR_VERSION = "1.31.1"


def _run(argv: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        argv,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


@pytest.mark.skipif(shutil.which("gitleaks") is None, reason="gitleaks is not on PATH")
def test_gitleaks_detects_fake_aws_key(tmp_path: Path) -> None:
    key = "AKIA" + "ABCDEFGHIJKLMNOP"
    (tmp_path / "leak.txt").write_text(f"aws_access_key_id = {key}\n", encoding="utf-8")
    completed = _run(
        [
            "gitleaks",
            "dir",
            str(tmp_path),
            "--redact",
            "--no-banner",
            "--exit-code",
            "1",
            "-v",
        ],
        tmp_path,
    )
    output = completed.stdout + completed.stderr
    assert completed.returncode != 0
    assert "aws-access-token" in output
    assert "leak.txt" in output


@pytest.mark.skipif(shutil.which("trivy") is None, reason="trivy is not on PATH")
def test_trivy_detects_vulnerable_lockfile(tmp_path: Path) -> None:
    lock = {
        "name": "security-bad",
        "version": "1.0.0",
        "lockfileVersion": 3,
        "requires": True,
        "packages": {
            "": {
                "name": "security-bad",
                "version": "1.0.0",
                "dependencies": {"lodash": "4.17.15"},
            },
            "node_modules/lodash": {
                "version": "4.17.15",
                "resolved": "https://registry.npmjs.org/lodash/-/lodash-4.17.15.tgz",
            },
        },
    }
    (tmp_path / "package-lock.json").write_text(json.dumps(lock), encoding="utf-8")
    report = tmp_path / "trivy.json"
    completed = _run(
        [
            "trivy",
            "fs",
            "--scanners",
            "vuln",
            "--severity",
            "HIGH,CRITICAL",
            "--ignore-unfixed",
            "--format",
            "json",
            "--output",
            str(report),
            "--exit-code",
            "1",
            str(tmp_path),
        ],
        tmp_path,
    )
    assert completed.returncode != 0, completed.stdout + completed.stderr
    data = json.loads(report.read_text(encoding="utf-8"))
    findings = [
        (vuln.get("PkgName"), vuln.get("VulnerabilityID"), vuln.get("Severity"))
        for result in data.get("Results", [])
        for vuln in result.get("Vulnerabilities", [])
    ]
    assert any(pkg == "lodash" for pkg, _, _ in findings), findings
    assert any(vuln_id and vuln_id.startswith("CVE-") for _, vuln_id, _ in findings)


@pytest.fixture(scope="session")
def zizmor_available() -> None:
    if shutil.which("uvx") is None:
        pytest.skip("uvx is not on PATH (needed for zizmor)")
    completed = subprocess.run(
        ["uvx", f"zizmor=={ZIZMOR_VERSION}", "--version"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if completed.returncode != 0:
        pytest.skip(f"zizmor unavailable: {(completed.stdout + completed.stderr)[:300]}")


def test_zizmor_detects_unpinned_action(tmp_path: Path, zizmor_available: None) -> None:
    workflows = tmp_path / ".github" / "workflows"
    workflows.mkdir(parents=True)
    (workflows / "bad.yml").write_text(
        "name: bad\n"
        "on: push\n"
        "jobs:\n"
        "  x:\n"
        "    runs-on: ubuntu-latest\n"
        "    steps:\n"
        "      - uses: actions/checkout@main\n",
        encoding="utf-8",
    )
    completed = _run(
        [
            "uvx",
            f"zizmor=={ZIZMOR_VERSION}",
            "--format",
            "plain",
            "--no-progress",
            "--min-severity",
            "high",
            str(workflows),
        ],
        tmp_path,
    )
    output = completed.stdout + completed.stderr
    assert completed.returncode != 0
    assert "unpinned-uses" in output
