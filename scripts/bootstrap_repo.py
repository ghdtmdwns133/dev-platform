#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
"""Create or reconcile a repository generated from the dev-platform Copier template.

This is the single entry point for repository provisioning. It renders the
template with Copier and then applies the GitHub settings that a personal
account cannot share across repositories (secrets, labels and rulesets).

The script is idempotent. ``--dry-run`` prints every planned command and makes
no network calls, no Copier invocation and no filesystem changes.
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

PLATFORM_ROOT = Path(__file__).resolve().parents[1]
COPIER_VERSION = "9.19.1"
PRE_COMMIT_VERSION = "4.7.0"
DOPPLER_PROJECT = "dev-platform-shared"
DOPPLER_CONFIG = "prd"
STACKS = ("python", "typescript", "dotnet", "unity", "other")
LABELS = (
    ("automerge", "0E8A16", "Auto-merge when required checks pass"),
    ("ci-alert", "B60205", "Automated CI failure reports"),
)
SENTRY_PLATFORM = "javascript-react"
PLATFORM_REPOSITORY = "dev-platform"


def log(message: str) -> None:
    print(message)


def notice(message: str) -> None:
    print(f"::notice::{message}")


def slugify(value: str) -> str:
    return value.strip().lower().replace(" ", "-")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Render the dev-platform Copier template and bootstrap the GitHub repository."
    )
    parser.add_argument("--template", choices=STACKS, help="render this stack before bootstrapping")
    parser.add_argument("--dest", help="destination directory for --template rendering")
    parser.add_argument(
        "--template-source",
        default=None,
        help=(
            "Copier source (default: https://github.com/<owner>/dev-platform); "
            "gh:<owner>/<repo> is accepted and normalized to HTTPS"
        ),
    )
    parser.add_argument(
        "--local",
        action="store_true",
        help="render from this checkout instead of the canonical GitHub source (self-test only)",
    )
    parser.add_argument(
        "--template-ref",
        default=None,
        help="Copier template ref (default: latest PEP 440 git tag)",
    )
    parser.add_argument("--root", default=".", help="repository root to bootstrap (default: cwd)")
    parser.add_argument("--name", required=True, help="repository name")
    parser.add_argument("--owner", default="ghdtmdwns133", help="GitHub account")
    parser.add_argument("--visibility", choices=("private", "public"), default="private")
    parser.add_argument("--min-coverage", type=int, default=80)
    parser.add_argument("--platform-ref", default="v1")
    parser.add_argument(
        "--create-repo",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="create the GitHub repository when it does not exist",
    )
    parser.add_argument(
        "--enable-codecov",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="set CODECOV_TOKEN when a value is available",
    )
    parser.add_argument(
        "--enable-sentry",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="create the Sentry project and set its secrets (typescript only)",
    )
    parser.add_argument("--force", action="store_true", help="pass --force to Copier")
    parser.add_argument("--dry-run", action="store_true", help="print the plan; make no changes")
    args = parser.parse_args(argv)
    if args.template and not args.dest:
        parser.error("--template requires --dest")
    if args.template and args.enable_sentry and args.template != "typescript":
        parser.error("--enable-sentry is only supported for the typescript stack")
    return args


class Plan:
    """Execute commands, or print them when running with ``--dry-run``."""

    def __init__(self, dry_run: bool) -> None:
        self.dry_run = dry_run

    def run(
        self,
        argv: list[str],
        *,
        cwd: Path | None = None,
        stdin: str | None = None,
        capture: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        printable = shlex.join(argv)
        if self.dry_run:
            print(f"+ {printable}")
            return subprocess.CompletedProcess(argv, 0, "", "")
        try:
            return subprocess.run(
                argv,
                cwd=str(cwd) if cwd else None,
                input=stdin,
                capture_output=capture,
                text=True,
                check=True,
            )
        except FileNotFoundError as exc:
            raise SystemExit(f"error: {argv[0]} is not installed") from exc
        except subprocess.CalledProcessError as exc:
            detail = (exc.stderr or exc.stdout or "").strip()
            raise SystemExit(f"error: {printable} failed ({exc.returncode})\n{detail}") from exc

    def api(self, method: str, path: str, body: dict[str, Any] | None = None) -> Any:
        argv = ["gh", "api", "--method", method, path]
        stdin = None if body is None else json.dumps(body)
        if body is not None:
            argv.extend(["--input", "-"])
            if self.dry_run:
                prefix = f"+ {shlex.join(argv)} <<< {json.dumps(body, sort_keys=True)}"
                print(prefix)
                return None
        result = self.run(argv, stdin=stdin, capture=True)
        output = (result.stdout or "").strip()
        if self.dry_run or not output:
            return None
        try:
            return json.loads(output)
        except json.JSONDecodeError:
            return output

    def secret(self, repo: str, name: str, value: str) -> None:
        if self.dry_run:
            print(f"+ gh secret set {name} --repo {repo}  # value redacted")
            return
        self.run(["gh", "secret", "set", name, "--repo", repo], stdin=value, capture=True)
        log(f"secret set: {name}")

    def doppler(self, name: str) -> str | None:
        if not shutil.which("doppler"):
            return None
        if self.dry_run:
            print(
                f"+ doppler secrets get {name} --plain --project {DOPPLER_PROJECT} "
                f"--config {DOPPLER_CONFIG}  # value redacted"
            )
            return None
        result = subprocess.run(
            [
                "doppler",
                "secrets",
                "get",
                name,
                "--plain",
                "--project",
                DOPPLER_PROJECT,
                "--config",
                DOPPLER_CONFIG,
            ],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            return None
        value = result.stdout.strip()
        return value or None

    def value(self, name: str) -> str | None:
        value = os.environ.get(name)
        if value:
            return value
        return self.doppler(name)


def canonical_template_source(owner: str) -> str:
    return f"https://github.com/{owner}/{PLATFORM_REPOSITORY}"


def normalize_template_source(source: str) -> str:
    if source.startswith("gh:"):
        return f"https://github.com/{source[len('gh:') :].strip('/')}"
    return source


def template_source(args: argparse.Namespace) -> str:
    if args.template_source:
        return normalize_template_source(args.template_source)
    if args.local:
        return str(PLATFORM_ROOT)
    return canonical_template_source(args.owner)


def answers_source(args: argparse.Namespace) -> str:
    if args.template_source:
        return normalize_template_source(args.template_source)
    return canonical_template_source(args.owner)


def rewrite_answers_source(destination: Path, source: str) -> None:
    answers = destination / ".copier-answers.yml"
    if not answers.is_file():
        raise SystemExit(f"error: Copier did not write {answers.name} in {destination}")
    lines = answers.read_text(encoding="utf-8").splitlines(keepends=True)
    for index, line in enumerate(lines):
        if line.startswith("_src_path:"):
            lines[index] = f"_src_path: {json.dumps(source)}\n"
            break
    else:
        lines.insert(0, f"_src_path: {json.dumps(source)}\n")
    answers.write_text("".join(lines), encoding="utf-8")


def render(args: argparse.Namespace, plan: Plan) -> Path:
    destination = Path(args.dest or "").expanduser().resolve()
    data = {
        "project_name": args.name,
        "stack": args.template,
        "owner": args.owner,
        "visibility": args.visibility,
        "platform_ref": args.platform_ref,
        "min_coverage": str(args.min_coverage),
        "create_github_repo": "true" if args.create_repo else "false",
        "enable_codecov": "true" if args.enable_codecov else "false",
    }
    if args.template == "typescript":
        data["enable_sentry"] = "true" if args.enable_sentry else "false"
    source = template_source(args)
    argv = ["uvx", f"copier@{COPIER_VERSION}", "copy", "--defaults"]
    if args.force:
        argv.append("--force")
    if args.template_ref:
        argv.extend(["--vcs-ref", args.template_ref])
    elif args.local:
        # A local checkout must render its current commit, not whatever tag is newest.
        argv.extend(["--vcs-ref", "HEAD"])
    for key, value in data.items():
        argv.extend(["--data", f"{key}={value}"])
    argv.extend([source, str(destination)])
    plan.run(argv)
    if not plan.dry_run:
        answer_source = answers_source(args)
        if answer_source != source:
            rewrite_answers_source(destination, answer_source)
            log(f"answers source normalized: {answer_source}")
        log(f"rendered {args.template} template: {destination}")
    return destination


def ensure_git_repository(root: Path, plan: Plan) -> None:
    if (root / ".git").exists():
        return
    plan.run(["git", "init", "-b", "main"], cwd=root)
    plan.run(["git", "add", "-A"], cwd=root)
    plan.run(["git", "commit", "-m", "chore: initial commit"], cwd=root)


def mise_task_names(root: Path) -> set[str]:
    result = subprocess.run(
        ["mise", "tasks", "--name-only"],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return set()
    return {line.strip() for line in result.stdout.splitlines() if line.strip()}


def install_pre_commit(root: Path, plan: Plan) -> None:
    if not plan.dry_run and not (root / ".pre-commit-config.yaml").is_file():
        return
    if (root / "mise.toml").is_file() or plan.dry_run:
        plan.run(["mise", "trust"], cwd=root)
        plan.run(["mise", "install"], cwd=root)
        if plan.dry_run:
            print("+ mise run prepare  # when mise.toml defines a prepare task")
        elif "prepare" in mise_task_names(root):
            plan.run(["mise", "run", "prepare"], cwd=root)
            log("stack dependencies prepared: mise run prepare")
        else:
            log("no mise prepare task; no stack dependencies to install before the hook")
        plan.run(["mise", "exec", "--", "pre-commit", "install"], cwd=root)
    else:
        plan.run(["uvx", f"pre-commit@{PRE_COMMIT_VERSION}", "install"], cwd=root)
    if not plan.dry_run:
        log("pre-commit hook installed")


def repository_exists(plan: Plan, repo: str) -> bool:
    if plan.dry_run:
        print(f"+ gh repo view {repo} --json name  # skip creation when this succeeds")
        return False
    result = subprocess.run(
        ["gh", "repo", "view", repo, "--json", "name"],
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def redact_remote(url: str) -> str:
    if "@" in url and "://" in url:
        scheme, rest = url.split("://", 1)
        return f"{scheme}://***@{rest.split('@', 1)[1]}"
    return url


def github_remote_slug(url: str) -> str | None:
    value = url.strip().rstrip("/")
    for prefix in ("https://github.com/", "http://github.com/", "ssh://git@github.com/"):
        if value.startswith(prefix):
            value = value[len(prefix) :]
            break
    else:
        if value.startswith("git@github.com:"):
            value = value[len("git@github.com:") :]
        else:
            return None
    value = value.removesuffix(".git")
    parts = value.split("/")
    if len(parts) != 2 or not all(parts):
        return None
    return f"{parts[0]}/{parts[1]}".lower()


def origin_url(root: Path) -> str | None:
    result = subprocess.run(
        ["git", "remote", "get-url", "origin"],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def ensure_remote_repository(
    args: argparse.Namespace, root: Path, repo: str, plan: Plan
) -> bool:
    if plan.dry_run:
        print(f"+ gh repo view {repo} --json name  # when it exists, require origin == {repo}")
        if not args.create_repo:
            print(f"# assume {repo} exists because --no-create-repo was passed")
            return True
        plan.run(
            [
                "gh",
                "repo",
                "create",
                repo,
                f"--{args.visibility}",
                "--source",
                str(root),
                "--push",
            ]
        )
        return True
    if repository_exists(plan, repo):
        url = origin_url(root)
        slug = github_remote_slug(url) if url else None
        if url is None:
            raise SystemExit(
                f"error: {repo} already exists, but {root} has no git 'origin' remote.\n"
                "Refusing to apply settings to a repository this checkout never pushed.\n"
                "Clone the existing repository or add the matching remote, then re-run:\n"
                f"  git clone https://github.com/{repo}.git {root}\n"
                f"  # or: git -C {root} remote add origin https://github.com/{repo}.git"
            )
        if slug != repo.lower():
            raise SystemExit(
                f"error: {root} has origin {redact_remote(url)!r},"
                f" which does not resolve to {repo}.\n"
                "Refusing to apply repository settings to an unrelated remote.\n"
                f"Clone {repo} or correct 'origin', then re-run."
            )
        log(f"repository exists and origin matches: {repo}")
        return True
    if not args.create_repo:
        notice(f"{repo} does not exist; repository creation disabled")
        return False
    plan.run(
        [
            "gh",
            "repo",
            "create",
            repo,
            f"--{args.visibility}",
            "--source",
            str(root),
            "--push",
        ]
    )
    return True


def apply_settings(repo: str, plan: Plan) -> None:
    plan.api(
        "PUT",
        f"repos/{repo}/actions/permissions/artifact-and-log-retention",
        {"days": 14},
    )
    plan.api(
        "PUT",
        f"repos/{repo}/actions/permissions/workflow",
        {
            "default_workflow_permissions": "read",
            "can_approve_pull_request_reviews": True,
        },
    )
    plan.api(
        "PATCH",
        f"repos/{repo}",
        {"allow_auto_merge": True, "delete_branch_on_merge": True},
    )
    plan.api("PUT", f"repos/{repo}/vulnerability-alerts")


def apply_labels(repo: str, plan: Plan) -> None:
    for name, color, description in LABELS:
        plan.run(
            [
                "gh",
                "label",
                "create",
                name,
                "--color",
                color,
                "--description",
                description,
                "--force",
                "--repo",
                repo,
            ]
        )


def apply_ruleset(root: Path, repo: str, plan: Plan) -> None:
    path = root / ".github" / "rulesets" / "platform-gates.json"
    if not path.is_file():
        if plan.dry_run:
            print(f"+ gh api --method GET repos/{repo}/rulesets  # find platform-gates by name")
            print(
                f"+ gh api --method POST repos/{repo}/rulesets"
                f" <<< <rendered {path.name}>  # when absent"
            )
            print(
                f"+ gh api --method PUT repos/{repo}/rulesets/<id>"
                f" <<< <rendered {path.name}>  # when present"
            )
            return
        notice(f"no ruleset file at {path}; skipping platform-gates")
        return
    payload = json.loads(path.read_text(encoding="utf-8"))
    if plan.dry_run:
        print(f"+ gh api --method GET repos/{repo}/rulesets  # find platform-gates by name")
        print(
            f"+ gh api --method POST repos/{repo}/rulesets <<< <rendered {path.name}>"
            "  # when absent"
        )
        print(
            f"+ gh api --method PUT repos/{repo}/rulesets/<id> <<< <rendered {path.name}>"
            "  # when present"
        )
        return
    result = subprocess.run(
        ["gh", "api", "--paginate", f"repos/{repo}/rulesets"],
        capture_output=True,
        text=True,
    )
    ruleset_id = None
    if result.returncode == 0 and result.stdout.strip():
        for ruleset in json.loads(result.stdout):
            if ruleset.get("name") == payload.get("name"):
                ruleset_id = ruleset.get("id")
                break
    if ruleset_id is None:
        plan.api("POST", f"repos/{repo}/rulesets", payload)
        log("ruleset created: platform-gates")
    else:
        plan.api("PUT", f"repos/{repo}/rulesets/{ruleset_id}", payload)
        log("ruleset updated: platform-gates")


def set_codecov_secret(repo: str, plan: Plan) -> None:
    if plan.dry_run:
        print(
            f"+ gh secret set CODECOV_TOKEN --repo {repo}"
            "  # value from env or Doppler, redacted"
        )
        return
    value = plan.value("CODECOV_TOKEN")
    if not value:
        notice("CODECOV_TOKEN not available; Codecov upload stays disabled")
        return
    plan.secret(repo, "CODECOV_TOKEN", value)


def sentry_request(
    plan: Plan, method: str, url: str, token: str, body: dict[str, Any] | None = None
) -> tuple[int, Any]:
    data = None if body is None else json.dumps(body).encode()
    request = urllib.request.Request(url, data=data, method=method)
    request.add_header("Authorization", f"Bearer {token}")
    request.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = response.read().decode()
            return response.status, json.loads(payload) if payload else None
    except urllib.error.HTTPError as exc:
        payload = exc.read().decode()
        try:
            parsed = json.loads(payload) if payload else None
        except json.JSONDecodeError:
            parsed = payload
        return exc.code, parsed


def provision_sentry(args: argparse.Namespace, repo: str, plan: Plan) -> None:
    if not args.enable_sentry:
        return
    if args.template not in (None, "typescript"):
        notice("Sentry provisioning is only supported for the typescript stack")
        return
    project = slugify(args.name)
    if plan.dry_run:
        print(
            "+ POST https://sentry.io/api/0/teams/<SENTRY_ORG>/<SENTRY_TEAM>/projects/"
            f"  # name={args.name} slug={project} platform={SENTRY_PLATFORM}"
        )
        print(f"+ gh secret set VITE_SENTRY_DSN --repo {repo}  # value redacted")
        print(f"+ gh secret set SENTRY_ORG --repo {repo}")
        print(f"+ gh secret set SENTRY_PROJECT --repo {repo}")
        print(f"+ gh secret set SENTRY_AUTH_TOKEN --repo {repo}  # value redacted")
        return
    org = plan.value("SENTRY_ORG")
    team = plan.value("SENTRY_TEAM")
    token = plan.value("SENTRY_AUTH_TOKEN")
    if not org or not team or not token:
        notice("Sentry credentials missing; project creation skipped")
        return
    status, payload = sentry_request(
        plan,
        "POST",
        f"https://sentry.io/api/0/teams/{org}/{team}/projects/",
        token,
        {"name": args.name, "slug": project, "platform": SENTRY_PLATFORM},
    )
    if status == 409:
        status, payload = sentry_request(
            plan, "GET", f"https://sentry.io/api/0/projects/{org}/{project}/", token
        )
    if status not in (200, 201):
        raise SystemExit(f"error: Sentry project creation failed with status {status}")
    dsn = payload.get("dsn") if isinstance(payload, dict) else None
    if not isinstance(dsn, str) or not dsn.startswith("http"):
        status, keys = sentry_request(
            plan, "GET", f"https://sentry.io/api/0/projects/{org}/{project}/keys/", token
        )
        if status != 200 or not isinstance(keys, list) or not keys:
            raise SystemExit(f"error: Sentry DSN lookup failed with status {status}")
        dsn = (keys[0].get("dsn") or {}).get("public")
    if not isinstance(dsn, str) or not dsn:
        raise SystemExit("error: Sentry returned no public DSN")
    plan.secret(repo, "VITE_SENTRY_DSN", dsn)
    plan.secret(repo, "SENTRY_ORG", org)
    plan.secret(repo, "SENTRY_PROJECT", project)
    plan.secret(repo, "SENTRY_AUTH_TOKEN", token)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    plan = Plan(args.dry_run)
    if args.dry_run:
        print("bootstrap dry run: no network calls, no Copier run, no file changes")
    if args.template:
        root = render(args, plan)
    else:
        root = Path(args.root).expanduser().resolve()
    if not plan.dry_run and not root.is_dir():
        raise SystemExit(f"error: repository root does not exist: {root}")
    ensure_git_repository(root, plan)
    install_pre_commit(root, plan)
    repo = f"{args.owner}/{args.name}"
    exists = ensure_remote_repository(args, root, repo, plan)
    if not exists:
        return 0
    apply_settings(repo, plan)
    apply_labels(repo, plan)
    apply_ruleset(root, repo, plan)
    if args.enable_codecov:
        set_codecov_secret(repo, plan)
    provision_sentry(args, repo, plan)
    log(f"{'bootstrap plan complete' if plan.dry_run else 'bootstrap complete'}: {repo}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
