"""Unity Build Automation client: mocked HTTP server success and failure paths."""

from __future__ import annotations

import hashlib
import json
import threading
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest
from support import write_config

from devplatform import cli, cloudbuild
from devplatform.config import load_config
from devplatform.errors import DevctlError

COMMIT = "0123456789abcdef0123456789abcdef01234567"
BUILD_PATH = "/api/v1/orgs/org/projects/project/buildtargets/windows/builds/7"
LINKS = {
    "self": {"href": BUILD_PATH, "method": "GET"},
    "log": {"href": BUILD_PATH + "/log", "method": "GET"},
    "download_primary": {"href": BUILD_PATH + "/download/build.zip", "redirect": True},
}

Responder = Callable[[str, str, dict[str, str], bytes, str], tuple[int, dict[str, str], Any]]


class MockUba:
    """Minimal Build Automation API mock (bearer auth, 303 artifact redirect)."""

    def __init__(self, responder: Responder) -> None:
        self.responder = responder
        self.requests: list[dict[str, Any]] = []
        outer = self
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), self._handler_type())
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.origin = f"http://127.0.0.1:{self.httpd.server_address[1]}"
        self.base = self.origin + "/api/v1"
        outer.origin = self.origin

    def _handler_type(self):
        outer = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def do_GET(self) -> None:
                outer._handle(self)

            def do_POST(self) -> None:
                outer._handle(self)

            def log_message(self, *_args: Any) -> None:
                return

        return Handler

    def _handle(self, handler: BaseHTTPRequestHandler) -> None:
        length = int(handler.headers.get("Content-Length") or 0)
        body = handler.rfile.read(length)
        headers = {key.lower(): value for key, value in handler.headers.items()}
        self.requests.append(
            {"method": handler.command, "path": handler.path, "headers": headers, "body": body}
        )
        status, extra, payload = self.responder(
            handler.command, handler.path, headers, body, self.origin
        )
        if not isinstance(payload, bytes):
            payload = str(payload).encode("utf-8")
        handler.send_response(status)
        for key, value in extra.items():
            handler.send_header(key, value)
        handler.send_header("Content-Length", str(len(payload)))
        handler.end_headers()
        handler.wfile.write(payload)

    def __enter__(self) -> MockUba:
        self.thread.start()
        return self

    def __exit__(self, *_exc: Any) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=5)


def _config(root: Path, target: str | None = "windows"):
    unity: dict[str, Any] = {"cloudBuild": {"target": target}} if target else {}
    write_config(root, profile="unity", unity=unity)
    return load_config(root)


def _env(server: MockUba) -> dict[str, str]:
    return {
        "UNITY_BUILD_API_KEY": "test-key",
        "UNITY_BUILD_ORG_ID": "org",
        "UNITY_BUILD_PROJECT_ID": "project",
        "UNITY_BUILD_API_BASE": server.base,
        "UNITY_BUILD_POLL_SECONDS": "0.01",
    }


def _success_responder(state: dict[str, int]) -> Responder:
    def responder(method, path, headers, body, origin):
        if method == "POST":
            assert path == "/api/v1/orgs/org/projects/project/buildtargets/windows/builds"
            assert headers["authorization"] == "Bearer test-key"
            assert json.loads(body) == {"clean": False, "commit": COMMIT}
            return (
                202,
                {"Content-Type": "application/json"},
                json.dumps([{"build": 7, "buildStatus": "queued", "lastBuiltRevision": COMMIT}]),
            )
        if path == BUILD_PATH:
            state["status"] += 1
            if state["status"] == 1:
                return (
                    200,
                    {"Content-Type": "application/json"},
                    json.dumps({"build": 7, "buildStatus": "queued", "links": LINKS}),
                )
            return (
                200,
                {"Content-Type": "application/json"},
                json.dumps(
                    {
                        "build": 7,
                        "buildStatus": "success",
                        "totalTimeInSeconds": 42.5,
                        "lastBuiltRevision": COMMIT,
                        "links": LINKS,
                    }
                ),
            )
        if path == BUILD_PATH + "/download/build.zip":
            signed = origin + "/files/Project.zip"
            return 303, {"Content-Type": "application/json"}, json.dumps(signed)
        if path == "/files/Project.zip":
            return (
                200,
                {
                    "Content-Type": "application/zip",
                    "Content-Disposition": 'attachment; filename="Project.zip"',
                },
                b"PK\x03\x04fake-build",
            )
        return 404, {"Content-Type": "application/json"}, b'{"error":"not found"}'

    return responder


def test_cloud_build_success_downloads_and_reports(tmp_path: Path, capsys) -> None:
    state = {"status": 0}
    with MockUba(_success_responder(state)) as server:
        payload = cloudbuild.run_cloud_build(
            tmp_path,
            tmp_path / "artifacts/reports",
            _config(tmp_path),
            commit=COMMIT,
            env=_env(server),
        )

    artifact = tmp_path / "artifacts/reports/unity/cloud-build/Project.zip"
    assert artifact.read_bytes() == b"PK\x03\x04fake-build"
    assert payload == {
        "buildNumber": 7,
        "status": "success",
        "commit": COMMIT,
        "durationSeconds": 42.5,
        "artifact": "artifacts/reports/unity/cloud-build/Project.zip",
        "sha256": hashlib.sha256(b"PK\x03\x04fake-build").hexdigest(),
        "buildUrl": server.origin + BUILD_PATH,
    }
    report = json.loads((tmp_path / "artifacts/reports/unity/cloud-build.json").read_text())
    assert report == payload
    signed = [item for item in server.requests if item["path"] == "/files/Project.zip"]
    assert len(signed) == 1
    assert "authorization" not in signed[0]["headers"]
    notices = capsys.readouterr().out
    assert "build 7: queued" in notices
    assert "build 7: success" in notices


def test_cloud_build_failure_includes_log_url(tmp_path: Path) -> None:
    def responder(method, path, headers, body, origin):
        if method == "POST":
            return 202, {}, json.dumps([{"build": 9, "buildStatus": "created"}])
        return (
            200,
            {"Content-Type": "application/json"},
            json.dumps(
                {
                    "build": 9,
                    "buildStatus": "failure",
                    "failureDetails": [{"displayName": "Build failed"}],
                    "links": {"log": {"href": "/api/v1/logs/9", "method": "GET"}},
                }
            ),
        )

    with MockUba(responder) as server:
        with pytest.raises(DevctlError) as excinfo:
            cloudbuild.run_cloud_build(
                tmp_path,
                tmp_path / "artifacts/reports",
                _config(tmp_path),
                commit=COMMIT,
                env=_env(server),
            )

    assert excinfo.value.code == 1
    assert server.origin + "/api/v1/logs/9" in excinfo.value.message
    assert "failure" in excinfo.value.message
    assert not (tmp_path / "artifacts/reports/unity/cloud-build.json").exists()


def test_cloud_build_honors_retry_after(tmp_path: Path) -> None:
    state = {"status": 0}
    sleeps: list[float] = []

    def responder(method, path, headers, body, origin):
        if method == "POST":
            return 202, {}, json.dumps([{"build": 11, "buildStatus": "queued"}])
        state["status"] += 1
        if state["status"] == 1:
            return 429, {"Retry-After": "7"}, b'{"error":"Rate limit exceeded, retry in 7 seconds"}'
        return (
            200,
            {"Content-Type": "application/json"},
            json.dumps({"build": 11, "buildStatus": "success", "links": LINKS}),
        )

    with MockUba(responder) as server:
        payload = cloudbuild.run_cloud_build(
            tmp_path,
            tmp_path / "artifacts/reports",
            _config(tmp_path),
            commit=COMMIT,
            env=_env(server),
            sleep=sleeps.append,
        )

    assert payload["buildNumber"] == 11
    assert sleeps == [7.0]


def test_cloud_build_timeout_exits_3(tmp_path: Path) -> None:
    now = [0.0]

    def responder(method, path, headers, body, origin):
        if method == "POST":
            return 202, {}, json.dumps([{"build": 12, "buildStatus": "queued"}])
        return (
            200,
            {"Content-Type": "application/json"},
            json.dumps({"build": 12, "buildStatus": "queued", "links": LINKS}),
        )

    def sleep(seconds: float) -> None:
        now[0] += seconds

    with MockUba(responder) as server:
        with pytest.raises(DevctlError) as excinfo:
            cloudbuild.run_cloud_build(
                tmp_path,
                tmp_path / "artifacts/reports",
                _config(tmp_path),
                commit=COMMIT,
                timeout_min=1,
                env=_env(server),
                sleep=sleep,
                clock=lambda: now[0],
                poll_seconds=30,
            )

    assert excinfo.value.code == 3
    assert "timed out after 1 minute" in excinfo.value.message


def test_cloud_build_requires_target(tmp_path: Path) -> None:
    with pytest.raises(DevctlError) as excinfo:
        cloudbuild.run_cloud_build(
            tmp_path,
            tmp_path / "artifacts/reports",
            _config(tmp_path, target=None),
            commit=COMMIT,
            env={
                "UNITY_BUILD_API_KEY": "k",
                "UNITY_BUILD_ORG_ID": "o",
                "UNITY_BUILD_PROJECT_ID": "p",
            },
        )
    assert excinfo.value.code == 2
    assert "unity.cloudBuild.target" in excinfo.value.message


def test_missing_credentials_names_variables(tmp_path: Path, monkeypatch, capsys) -> None:
    for name in (
        "UNITY_BUILD_API_KEY",
        "UNITY_BUILD_ORG_ID",
        "UNITY_BUILD_PROJECT_ID",
        "UNITY_BUILD_API_BASE",
        "UNITY_BUILD_POLL_SECONDS",
    ):
        monkeypatch.delenv(name, raising=False)
    _config(tmp_path)
    code = cli.main(["--root", str(tmp_path), "unity", "cloud-build", "--commit", COMMIT])
    captured = capsys.readouterr()
    assert code == 2
    assert "::error::" in captured.out
    assert "UNITY_BUILD_API_KEY" in captured.out
    assert "UNITY_BUILD_ORG_ID" in captured.out
    assert "UNITY_BUILD_PROJECT_ID" in captured.out


def test_cli_cloud_build_runs_without_editor(tmp_path: Path, monkeypatch, capsys) -> None:
    state = {"status": 0}
    with MockUba(_success_responder(state)) as server:
        for key, value in _env(server).items():
            monkeypatch.setenv(key, value)
        _config(tmp_path)
        code = cli.main(["--root", str(tmp_path), "unity", "cloud-build", "--commit", COMMIT])
    assert code == 0
    report = tmp_path / "artifacts/reports/unity/cloud-build.json"
    assert json.loads(report.read_text())["buildNumber"] == 7
    assert "Unity Build Automation" in capsys.readouterr().out
