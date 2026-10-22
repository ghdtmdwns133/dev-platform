"""Unity Build Automation (UBA) REST client for ``devctl unity cloud-build``.

Verified endpoints (Build Automation API 2.0.0, 2026-10-22):

* Interactive reference and OpenAPI schema:
  <https://build-api.cloud.unity3d.com/docs/>
* OpenAPI JSON: <https://build-api.cloud.unity3d.com/api/v1/api.json>
* Product documentation:
  <https://docs.unity.com/en-us/build-automation/build-automation-api>

Base URL: ``https://build-api.cloud.unity3d.com/api/v1``.

* Start a build:
  ``POST /orgs/{orgid}/projects/{projectid}/buildtargets/{buildtargetid}/builds``
  with ``{"commit": "<sha>"}``. The response is ``202`` and a JSON array whose
  first element is the build attempt; the ``build`` field is the build number.
* Build status: ``GET .../builds/{number}``. ``buildStatus`` is one of
  ``created``, ``queued``, ``sentToBuilder``, ``started``, ``restarted``,
  ``processing``, ``success``, ``failure``, ``canceled`` or ``unknown``.
* Artifact: ``build["links"]["download_primary"]["href"]``. A relative href is
  resolved against the API host. Requesting an internal href returns ``303``
  with the signed storage URL as a JSON string in the body (no ``Location``
  header), so the client parses the body and downloads that URL directly.
  ``links["log"]["href"]`` is the build log used in failure messages.

Authentication is ``Authorization: Bearer <UNITY_BUILD_API_KEY>`` per the
OpenAPI security scheme. Older documentation shows
``Authorization: Basic <api key>`` with the key verbatim; set
``UNITY_BUILD_API_AUTH=basic`` for that legacy form.

Environment variables: ``UNITY_BUILD_API_KEY``, ``UNITY_BUILD_ORG_ID``,
``UNITY_BUILD_PROJECT_ID``; optional ``UNITY_BUILD_API_BASE`` (tests) and
``UNITY_BUILD_POLL_SECONDS`` (poll interval override, default 30).
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import procs
from .config import Config
from .errors import EXIT_EXECUTION, EXIT_GATE, EXIT_PRECONDITION, DevctlError

DEFAULT_API_BASE = "https://build-api.cloud.unity3d.com/api/v1"
DEFAULT_POLL_SECONDS = 30.0
MAX_POLL_SECONDS = 300.0
HTTP_TIMEOUT_SECONDS = 60.0

IN_PROGRESS = frozenset(
    {"created", "queued", "sentToBuilder", "started", "restarted", "processing"}
)
FAILED = frozenset({"failure", "canceled", "unknown"})

CREDENTIAL_VARIABLES = (
    "UNITY_BUILD_API_KEY",
    "UNITY_BUILD_ORG_ID",
    "UNITY_BUILD_PROJECT_ID",
)


@dataclass(frozen=True)
class Response:
    """A non-redirect-following HTTP response."""

    status: int
    headers: Mapping[str, str]
    body: bytes


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Surface ``303`` responses instead of silently following them."""

    def redirect_request(
        self,
        req: urllib.request.Request,
        fp: Any,
        code: int,
        msg: str,
        headers: Any,
        newurl: str,
    ) -> None:
        return None


class Client:
    """Minimal Build Automation HTTP client with bearer/basic API-key auth."""

    def __init__(
        self,
        api_base: str,
        api_key: str,
        *,
        auth: str = "bearer",
        timeout: float = HTTP_TIMEOUT_SECONDS,
    ) -> None:
        self.api_base = api_base.rstrip("/")
        self.api_key = api_key
        self.auth = auth
        self.timeout = timeout
        self._opener = urllib.request.build_opener(_NoRedirect)

    def authorization(self) -> str:
        prefix = "Basic" if self.auth == "basic" else "Bearer"
        return f"{prefix} {self.api_key}"

    def request(
        self,
        method: str,
        url: str,
        *,
        payload: dict[str, Any] | None = None,
        authenticated: bool = True,
    ) -> Response:
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        request = urllib.request.Request(url, data=data, method=method)
        request.add_header("Accept", "application/json")
        request.add_header("User-Agent", "devctl-uba/1")
        if data is not None:
            request.add_header("Content-Type", "application/json")
        if authenticated:
            request.add_header("Authorization", self.authorization())
        try:
            with self._opener.open(request, timeout=self.timeout) as response:
                return Response(response.status, dict(response.headers), response.read())
        except urllib.error.HTTPError as exc:
            headers = dict(exc.headers or {})
            try:
                body = exc.read()
            except OSError:  # pragma: no cover - defensive
                body = b""
            return Response(exc.code, headers, body)
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            reason = getattr(exc, "reason", exc)
            raise DevctlError(
                EXIT_EXECUTION, f"Unity Build Automation request failed: {reason}"
            ) from exc


def _header(headers: Mapping[str, str], name: str) -> str:
    wanted = name.lower()
    for key, value in headers.items():
        if key.lower() == wanted:
            return value
    return ""


def _quote(value: str) -> str:
    return urllib.parse.quote(value, safe="")


def build_url(api_base: str, org: str, project: str, target: str, number: Any = None) -> str:
    base = (
        f"{api_base.rstrip('/')}/orgs/{_quote(org)}/projects/{_quote(project)}"
        f"/buildtargets/{_quote(target)}/builds"
    )
    return f"{base}/{number}" if number is not None else base


def _link_href(build: Mapping[str, Any], name: str) -> str | None:
    links = build.get("links")
    if not isinstance(links, Mapping):
        return None
    link = links.get(name)
    if not isinstance(link, Mapping):
        return None
    href = link.get("href")
    return href if isinstance(href, str) and href else None


def absolute_url(base: str, href: str) -> str:
    """Resolve an API href (absolute or relative) against the API base."""
    if href.startswith(("http://", "https://")):
        return href
    parts = urllib.parse.urlsplit(base)
    origin = f"{parts.scheme}://{parts.netloc}"
    if href.startswith("/"):
        return origin + href
    return urllib.parse.urljoin(base.rstrip("/") + "/", href)


def _same_origin(left: str, right: str) -> bool:
    a = urllib.parse.urlsplit(left)
    b = urllib.parse.urlsplit(right)
    return (a.scheme, a.netloc) == (b.scheme, b.netloc)


def _json(response: Response, what: str) -> Any:
    try:
        return json.loads(response.body.decode("utf-8"))
    except (UnicodeError, ValueError) as exc:
        raise DevctlError(
            EXIT_EXECUTION, f"invalid JSON from Unity Build Automation ({what}): {exc}"
        ) from exc


def _retry_after(response: Response, fallback: float) -> float:
    header = _header(response.headers, "retry-after").strip()
    if header.isdigit():
        return float(header)
    match = re.search(rb"retry in (\d+)", response.body)
    if match:
        return float(match.group(1))
    return fallback


def start_build(
    client: Client, org: str, project: str, target: str, commit: str
) -> tuple[int, dict[str, Any]]:
    """Start a build for ``commit`` and return ``(build number, attempt)``."""
    url = build_url(client.api_base, org, project, target)
    response = client.request("POST", url, payload={"clean": False, "commit": commit})
    if response.status == 409:
        raise DevctlError(
            EXIT_PRECONDITION,
            f"Unity Build Automation already has a pending build for target {target!r}",
        )
    if response.status == 422:
        raise DevctlError(
            EXIT_PRECONDITION,
            f"Unity Build Automation rejected the build request for target {target!r}: "
            f"{response.body.decode('utf-8', 'replace')[:500]}",
        )
    if response.status not in (200, 201, 202):
        raise DevctlError(
            EXIT_EXECUTION,
            f"Unity Build Automation start failed: HTTP {response.status}",
            detail=response.body.decode("utf-8", "replace")[:2000],
        )
    data = _json(response, "start build")
    entry = data[0] if isinstance(data, list) and data else data
    if not isinstance(entry, dict):
        raise DevctlError(
            EXIT_EXECUTION, "Unity Build Automation start response did not contain a build"
        )
    number = entry.get("build", entry.get("buildNumber"))
    if isinstance(number, bool) or not isinstance(number, (int, float)):
        raise DevctlError(
            EXIT_EXECUTION, "Unity Build Automation start response did not contain a build number"
        )
    return int(number), entry


def build_status(attempt: Mapping[str, Any]) -> str:
    value = attempt.get("buildStatus") or attempt.get("status") or ""
    return str(value)


def build_log_url(api_base: str, attempt: Mapping[str, Any], fallback: str) -> str:
    href = _link_href(attempt, "log")
    return absolute_url(api_base, href) if href else fallback


def wait_for_build(
    client: Client,
    org: str,
    project: str,
    target: str,
    number: int,
    *,
    timeout_minutes: float,
    poll_seconds: float,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
    initial_status: str | None = None,
) -> dict[str, Any]:
    """Poll until the build finishes; exit 1 on failure, 3 on timeout."""
    deadline = clock() + timeout_minutes * 60.0
    url = build_url(client.api_base, org, project, target, number)
    delay = poll_seconds
    last_status: str | None = initial_status
    last_attempt: dict[str, Any] = {}

    def timed_out() -> None:
        log = build_log_url(client.api_base, last_attempt, url)
        raise DevctlError(
            EXIT_EXECUTION,
            f"Unity Build Automation build {number} timed out after "
            f"{timeout_minutes:g} minute(s): {log}",
        )

    while True:
        if clock() >= deadline:
            timed_out()
        response = client.request("GET", url)
        if response.status in (429, 503):
            wait = _retry_after(response, delay)
            remaining = deadline - clock()
            if remaining <= 0:
                timed_out()
            sleep(min(max(wait, 0.0), remaining))
            delay = min(delay * 2 if delay else DEFAULT_POLL_SECONDS, MAX_POLL_SECONDS)
            continue
        if response.status == 404:
            raise DevctlError(EXIT_EXECUTION, f"Unity Build Automation build {number} not found")
        if response.status >= 400:
            raise DevctlError(
                EXIT_EXECUTION,
                f"Unity Build Automation status request failed: HTTP {response.status}",
                detail=response.body.decode("utf-8", "replace")[:2000],
            )
        attempt = _json(response, "build status")
        if not isinstance(attempt, dict):
            raise DevctlError(EXIT_EXECUTION, "invalid Unity Build Automation status payload")
        last_attempt = attempt
        status = build_status(attempt)
        if status != last_status:
            procs.emit_notice(f"Unity Build Automation build {number}: {status or 'unknown'}")
            last_status = status
        if status == "success":
            return attempt
        if status in FAILED:
            log = build_log_url(client.api_base, attempt, url)
            raise DevctlError(
                EXIT_GATE,
                f"Unity Build Automation build {number} {status}: {log}",
                detail=json.dumps(attempt.get("failureDetails", []), sort_keys=True)[:2000],
            )
        remaining = deadline - clock()
        if remaining <= 0:
            timed_out()
        sleep(min(delay, remaining))
        delay = min(delay * 2 if delay else DEFAULT_POLL_SECONDS, MAX_POLL_SECONDS)


def _filename(response: Response, url: str, number: int) -> str:
    disposition = _header(response.headers, "content-disposition")
    match = re.search(r"filename\*?=(?:UTF-8''|\")?([^\";]+)", disposition, re.IGNORECASE)
    if match:
        name = urllib.parse.unquote(match.group(1).strip())
    else:
        name = urllib.parse.unquote(Path(urllib.parse.urlsplit(url).path).name)
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("._")
    if not name:
        name = f"build-{number}.zip"
    return name


def download_artifact(
    client: Client, attempt: Mapping[str, Any], number: int, directory: Path
) -> tuple[Path, str, int]:
    """Download the primary artifact and return ``(path, sha256, size)``."""
    href = _link_href(attempt, "download_primary")
    if not href:
        raise DevctlError(
            EXIT_EXECUTION, f"Unity Build Automation build {number} has no primary artifact"
        )
    url = absolute_url(client.api_base, href)
    response = client.request("GET", url, authenticated=_same_origin(url, client.api_base))
    if response.status in (301, 302, 303, 307, 308):
        location = _header(response.headers, "location")
        signed: str | None = location or None
        if not signed:
            try:
                value = json.loads(response.body.decode("utf-8"))
            except (UnicodeError, ValueError):
                value = None
            signed = value if isinstance(value, str) and value else None
        if not signed:
            raise DevctlError(EXIT_EXECUTION, "Unity Build Automation artifact redirect had no URL")
        url = absolute_url(url, signed)
        response = client.request("GET", url, authenticated=False)
    if response.status != 200:
        raise DevctlError(
            EXIT_EXECUTION,
            f"Unity Build Automation artifact download failed: HTTP {response.status}",
            detail=response.body.decode("utf-8", "replace")[:1000],
        )
    if not response.body:
        raise DevctlError(EXIT_EXECUTION, "Unity Build Automation artifact is empty")

    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / _filename(response, url, number)
    temporary = path.with_name(path.name + ".part")
    temporary.write_bytes(response.body)
    temporary.replace(path)
    digest = hashlib.sha256(response.body).hexdigest()
    return path, digest, len(response.body)


def _head_commit(root: Path) -> str:
    completed = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    sha = (completed.stdout or "").strip()
    if completed.returncode != 0 or not re.fullmatch(r"[0-9a-f]{40}", sha):
        raise DevctlError(
            EXIT_PRECONDITION,
            "commit not specified and HEAD could not be read; pass --commit",
        )
    return sha


def _poll_interval(env: Mapping[str, str]) -> float:
    raw = env.get("UNITY_BUILD_POLL_SECONDS")
    if not raw:
        return DEFAULT_POLL_SECONDS
    try:
        value = float(raw)
    except ValueError as exc:
        raise DevctlError(EXIT_PRECONDITION, "UNITY_BUILD_POLL_SECONDS must be a number") from exc
    if value < 0:
        raise DevctlError(EXIT_PRECONDITION, "UNITY_BUILD_POLL_SECONDS must be zero or greater")
    return value


def run_cloud_build(
    root: Path,
    reports_dir: Path,
    config: Config,
    *,
    target: str | None = None,
    commit: str | None = None,
    timeout_min: int | None = None,
    download: str | None = None,
    env: Mapping[str, str] | None = None,
    client: Client | None = None,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
    poll_seconds: float | None = None,
) -> dict[str, Any]:
    """Start a Build Automation build, wait for it, and download its artifact."""
    root = Path(root)
    reports_dir = Path(reports_dir)
    environment = os.environ if env is None else env
    cloud = config.unity.get("cloudBuild") or {}
    if not isinstance(cloud, Mapping):  # pragma: no cover - config validation guarantees this
        cloud = {}
    target = target or cloud.get("target")
    if not target:
        raise DevctlError(
            EXIT_PRECONDITION,
            "no Unity Build Automation target configured; pass --target or set "
            "unity.cloudBuild.target",
        )
    missing = [name for name in CREDENTIAL_VARIABLES if not environment.get(name)]
    if missing:
        raise DevctlError(
            EXIT_PRECONDITION,
            "missing Unity Build Automation credential(s): " + ", ".join(missing),
        )
    commit = commit or _head_commit(root)
    if timeout_min is None:
        timeout_min = int(cloud.get("timeoutMinutes", 90))
    if timeout_min <= 0:
        raise DevctlError(EXIT_PRECONDITION, "cloud build timeout must be at least one minute")
    if poll_seconds is None:
        poll_seconds = _poll_interval(environment)
    auth = environment.get("UNITY_BUILD_API_AUTH", "bearer").lower()
    if auth not in {"bearer", "basic"}:
        raise DevctlError(EXIT_PRECONDITION, "UNITY_BUILD_API_AUTH must be bearer or basic")

    api_base = environment.get("UNITY_BUILD_API_BASE") or DEFAULT_API_BASE
    client = client or Client(api_base, environment["UNITY_BUILD_API_KEY"], auth=auth)
    org = environment["UNITY_BUILD_ORG_ID"]
    project = environment["UNITY_BUILD_PROJECT_ID"]
    started = clock()

    procs.emit_notice(f"Unity Build Automation: starting {target} at {commit[:12]}")
    number, attempt = start_build(client, org, project, target, commit)
    procs.emit_notice(
        f"Unity Build Automation build {number}: {build_status(attempt) or 'created'}"
    )
    attempt = wait_for_build(
        client,
        org,
        project,
        target,
        number,
        timeout_minutes=timeout_min,
        poll_seconds=poll_seconds,
        sleep=sleep,
        clock=clock,
        initial_status=build_status(attempt) or None,
    )

    destination = Path(download) if download else reports_dir / "unity" / "cloud-build"
    if not destination.is_absolute():
        destination = root / destination
    artifact, digest, size = download_artifact(client, attempt, number, destination)

    elapsed = round(clock() - started, 1)
    duration = attempt.get("totalTimeInSeconds")
    if isinstance(duration, bool) or not isinstance(duration, (int, float)):
        duration = elapsed
    self_href = _link_href(attempt, "self")
    build_url_value = (
        absolute_url(client.api_base, self_href)
        if self_href
        else build_url(client.api_base, org, project, target, number)
    )
    built_revision = attempt.get("lastBuiltRevision")
    payload: dict[str, Any] = {
        "buildNumber": number,
        "status": build_status(attempt),
        "commit": built_revision if isinstance(built_revision, str) and built_revision else commit,
        "durationSeconds": round(float(duration), 1),
        "artifact": procs.display_path(artifact, root),
        "sha256": digest,
        "buildUrl": build_url_value,
    }
    report = reports_dir / "unity" / "cloud-build.json"
    report.parent.mkdir(parents=True, exist_ok=True)
    temporary = report.with_name(report.name + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(report)
    procs.emit_notice(
        f"Unity Build Automation build {number} artifact: {payload['artifact']} "
        f"({size} bytes, sha256 {digest})"
    )
    return payload
