"""Regression tests for the repository bootstrap safety contract.

The bootstrap is a standalone script, so it is imported by path.  Tests use
real temporary directories and disposable Git repositories, and intercept
process execution only at the boundary.  Rejection paths may run read-only Git
but must never reach Copier, GitHub, mise, Doppler or Git writes.  The local
setup regression additionally permits only git init/add/commit and local
tooling; every other process is still recorded as a mutation.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "bootstrap_repo.py"
REAL_RUN = subprocess.run

GIT_WRITE_COMMANDS = {
    "add",
    "checkout",
    "clean",
    "commit",
    "fetch",
    "init",
    "merge",
    "mv",
    "pull",
    "push",
    "rebase",
    "reset",
    "restore",
    "rm",
    "stash",
    "switch",
    "tag",
}


@pytest.fixture(scope="module")
def bootstrap():
    spec = importlib.util.spec_from_file_location("devplatform_bootstrap_repo", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    yield module
    sys.modules.pop(spec.name, None)


class BoundaryRecorder:
    """Run permitted Git/tooling; record every other process as a mutation."""

    def __init__(
        self,
        *,
        allow_repo_view: bool = True,
        repo_exists: bool = True,
        allow_git_writes: bool = False,
        allow_local_tools: bool = False,
    ) -> None:
        self.allow_repo_view = allow_repo_view
        self.repo_exists = repo_exists
        self.allow_git_writes = allow_git_writes
        self.allow_local_tools = allow_local_tools
        self.hook_install_attempted = False
        self.mutations: list[list[str]] = []

    def __call__(self, argv, *args, **kwargs):
        command = [str(part) for part in argv]
        executable = Path(command[0]).stem.lower()
        if executable == "git":
            if _git_is_read_only(command[1:]):
                return REAL_RUN(argv, *args, **kwargs)
            if self.allow_git_writes and _git_subcommand(command[1:]) in ("add", "commit", "init"):
                return REAL_RUN(argv, *args, **kwargs)
            self.mutations.append(command)
            return subprocess.CompletedProcess(argv, 1, "", "blocked")
        if self.allow_repo_view and executable == "gh" and command[1:3] == ["repo", "view"]:
            if self.repo_exists:
                return subprocess.CompletedProcess(argv, 0, '{"name": "widget"}', "")
            return subprocess.CompletedProcess(argv, 1, "", "not found")
        if self.allow_local_tools and executable in {"mise", "pre-commit"}:
            if "pre-commit" in command and "install" in command:
                self.hook_install_attempted = True
            return subprocess.CompletedProcess(argv, 0, "", "")
        self.mutations.append(command)
        return subprocess.CompletedProcess(argv, 0, "", "")


def _git_subcommand(arguments: list[str]) -> str | None:
    index = 0
    while index < len(arguments):
        token = arguments[index]
        if token in {"-C", "-c", "--git-dir", "--work-tree"}:
            index += 2
            continue
        if token.startswith("-"):
            index += 1
            continue
        return token
    return None


def _git_is_read_only(arguments: list[str]) -> bool:
    index = 0
    while index < len(arguments):
        token = arguments[index]
        if token in {"-C", "-c", "--git-dir", "--work-tree"}:
            index += 2
            continue
        if token.startswith("-"):
            index += 1
            continue
        break
    if index >= len(arguments):
        return True
    subcommand = arguments[index]
    rest = arguments[index + 1 :]
    if subcommand in GIT_WRITE_COMMANDS:
        return False
    if subcommand == "remote":
        return not any(
            token in {"add", "remove", "rename", "set-url", "prune", "update"} for token in rest
        )
    if subcommand == "branch":
        return not any(
            token in {"-d", "-D", "--delete", "-m", "--move", "-c", "--copy"} for token in rest
        )
    if subcommand == "config":
        write_flags = {
            "--add",
            "--edit",
            "--remove-section",
            "--rename-section",
            "--replace-all",
            "--unset",
            "--unset-all",
        }
        if any(token in write_flags for token in rest):
            return False
        positionals = [token for token in rest if not token.startswith("-")]
        return len(positionals) <= 1
    if subcommand == "worktree":
        return not rest or rest[0] == "list"
    return subcommand in {
        "cat-file",
        "check-ignore",
        "describe",
        "diff",
        "for-each-ref",
        "log",
        "ls-files",
        "merge-base",
        "name-rev",
        "rev-list",
        "rev-parse",
        "show",
        "show-ref",
        "status",
        "symbolic-ref",
        "var",
    }


def _use_recorder(
    monkeypatch,
    bootstrap,
    *,
    allow_repo_view: bool = True,
    repo_exists: bool = True,
    allow_git_writes: bool = False,
    allow_local_tools: bool = False,
) -> BoundaryRecorder:
    recorder = BoundaryRecorder(
        allow_repo_view=allow_repo_view,
        repo_exists=repo_exists,
        allow_git_writes=allow_git_writes,
        allow_local_tools=allow_local_tools,
    )
    monkeypatch.setattr(bootstrap.subprocess, "run", recorder)
    return recorder


def _forbid_processes(monkeypatch, bootstrap) -> None:
    def fail(argv, *args, **kwargs):
        raise AssertionError(f"unexpected process: {argv}")

    monkeypatch.setattr(bootstrap.subprocess, "run", fail)


def _block_network(monkeypatch, bootstrap) -> None:
    def fail(*args, **kwargs):
        raise AssertionError("unexpected network call")

    monkeypatch.setattr(bootstrap.urllib.request, "urlopen", fail)


def _exit_code(module, argv: list[str]) -> int:
    try:
        result = module.main(argv)
    except SystemExit as exc:
        if exc.code is None:
            return 0
        return exc.code if isinstance(exc.code, int) else 1
    return 0 if result is None else int(result)


def _git(root: Path, *arguments: str) -> str:
    completed = REAL_RUN(
        ["git", *arguments],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout


def _make_repo(root: Path, origin: str | None = None) -> Path:
    root.mkdir(parents=True)
    _git(root, "init", "-b", "main")
    _git(root, "config", "user.email", "bootstrap-tests@example.invalid")
    _git(root, "config", "user.name", "Bootstrap Tests")
    _git(root, "config", "commit.gpgsign", "false")
    _git(root, "config", "core.hooksPath", ".git/hooks")
    (root / "README.md").write_text("baseline\n", encoding="utf-8")
    _git(root, "add", "README.md")
    _git(root, "commit", "-m", "initial")
    if origin is not None:
        _git(root, "remote", "add", "origin", origin)
    return root


def _make_unborn_repo(root: Path) -> Path:
    root.mkdir(parents=True)
    _git(root, "init", "-b", "main")
    _git(root, "config", "user.email", "bootstrap-tests@example.invalid")
    _git(root, "config", "user.name", "Bootstrap Tests")
    (root / "README.md").write_text("staged\n", encoding="utf-8")
    _git(root, "add", "README.md")
    return root


def _isolate_git_config(monkeypatch, tmp_path: Path) -> None:
    config = tmp_path / "gitconfig"
    config.write_text(
        "[user]\n"
        "\tname = Bootstrap Tests\n"
        "\temail = bootstrap-tests@example.invalid\n"
        "[commit]\n"
        "\tgpgsign = false\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(config))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))
    monkeypatch.setenv("GIT_AUTHOR_NAME", "Bootstrap Tests")
    monkeypatch.setenv("GIT_AUTHOR_EMAIL", "bootstrap-tests@example.invalid")
    monkeypatch.setenv("GIT_COMMITTER_NAME", "Bootstrap Tests")
    monkeypatch.setenv("GIT_COMMITTER_EMAIL", "bootstrap-tests@example.invalid")


def _head(root: Path) -> str:
    return _git(root, "rev-parse", "HEAD").strip()


def _has_head(root: Path) -> bool:
    completed = REAL_RUN(
        ["git", "rev-parse", "--verify", "HEAD"],
        cwd=root,
        capture_output=True,
        text=True,
    )
    return completed.returncode == 0


def _status(root: Path) -> str:
    return _git(root, "status", "--porcelain")


def _snapshot(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file() and ".git" not in path.relative_to(root).parts
    }


def _assert_no_install_or_commit(root: Path, head: str, status: str) -> None:
    assert not (root / ".git" / "hooks" / "pre-commit").exists()
    assert _head(root) == head
    assert _status(root) == status


@pytest.mark.parametrize("force", [False, True], ids=["plain", "force"])
def test_normal_render_refuses_nonempty_destination(
    bootstrap, monkeypatch, tmp_path: Path, force: bool
) -> None:
    destination = tmp_path / "service"
    destination.mkdir()
    (destination / "keep.txt").write_text("original\n", encoding="utf-8")
    before = _snapshot(destination)
    recorder = _use_recorder(monkeypatch, bootstrap)
    _block_network(monkeypatch, bootstrap)

    argv = [
        "--template",
        "other",
        "--dest",
        str(destination),
        "--name",
        "widget",
        "--owner",
        "acme",
    ]
    if force:
        argv.append("--force")

    assert _exit_code(bootstrap, argv) != 0
    assert _snapshot(destination) == before
    assert sorted(path.name for path in destination.iterdir()) == ["keep.txt"]
    assert recorder.mutations == []


@pytest.mark.parametrize(
    ("extra", "create_destination"),
    [
        (["--template", "other"], True),
        (["--render-only", "--template", "python"], True),
        (["--render-only", "--template", "other", "--force"], True),
        (["--render-only", "--template", "other"], False),
    ],
    ids=["missing-render-only", "unsupported-template", "force", "missing-destination"],
)
def test_adoption_rejects_unsafe_invocations(
    bootstrap,
    monkeypatch,
    tmp_path: Path,
    extra: list[str],
    create_destination: bool,
) -> None:
    destination = tmp_path / "service"
    if create_destination:
        destination.mkdir()
        (destination / "keep.txt").write_text("original\n", encoding="utf-8")
    before = _snapshot(destination) if create_destination else None
    recorder = _use_recorder(monkeypatch, bootstrap)
    _block_network(monkeypatch, bootstrap)

    argv = ["--adopt", "--dest", str(destination), "--name", "widget", "--owner", "acme", *extra]

    assert _exit_code(bootstrap, argv) != 0
    if create_destination:
        assert _snapshot(destination) == before
        assert not (destination / ".git").exists()
    else:
        assert not destination.exists()
    assert recorder.mutations == []


def test_adoption_refuses_existing_copier_provenance(
    bootstrap, monkeypatch, tmp_path: Path
) -> None:
    destination = tmp_path / "service"
    destination.mkdir()
    (destination / ".copier-answers.yml").write_text(
        "_src_path: https://github.com/acme/dev-platform\n", encoding="utf-8"
    )
    (destination / "keep.txt").write_text("original\n", encoding="utf-8")
    before = _snapshot(destination)
    recorder = _use_recorder(monkeypatch, bootstrap)
    _block_network(monkeypatch, bootstrap)

    argv = [
        "--adopt",
        "--render-only",
        "--template",
        "other",
        "--dest",
        str(destination),
        "--name",
        "widget",
        "--owner",
        "acme",
    ]

    assert _exit_code(bootstrap, argv) != 0
    assert _snapshot(destination) == before
    assert not (destination / ".git").exists()
    assert recorder.mutations == []


def test_render_only_stops_before_git_remote_and_secret_operations(
    bootstrap, monkeypatch, tmp_path: Path
) -> None:
    destination = tmp_path / "service"

    def fake_render(args, plan):
        destination.mkdir()
        (destination / "rendered.txt").write_bytes(b"rendered\n")
        return destination

    monkeypatch.setattr(bootstrap, "render", fake_render)
    recorder = _use_recorder(monkeypatch, bootstrap, allow_repo_view=False)
    _block_network(monkeypatch, bootstrap)

    argv = [
        "--render-only",
        "--template",
        "other",
        "--dest",
        str(destination),
        "--name",
        "widget",
        "--owner",
        "acme",
        "--enable-codecov",
    ]

    assert _exit_code(bootstrap, argv) == 0
    assert _snapshot(destination) == {"rendered.txt": b"rendered\n"}
    assert not (destination / ".git").exists()
    assert recorder.mutations == []


def test_dry_run_makes_no_changes(bootstrap, monkeypatch, tmp_path: Path) -> None:
    repository = _make_repo(
        tmp_path / "widget",
        origin="https://github.com/acme/widget.git",
    )
    before = _snapshot(repository)
    head = _head(repository)
    status = _status(repository)
    recorder = _use_recorder(monkeypatch, bootstrap, allow_repo_view=False)
    _block_network(monkeypatch, bootstrap)

    argv = [
        "--dry-run",
        "--root",
        str(repository),
        "--name",
        "widget",
        "--owner",
        "acme",
        "--enable-codecov",
    ]

    assert _exit_code(bootstrap, argv) == 0
    assert _snapshot(repository) == before
    assert _status(repository) == status
    _assert_no_install_or_commit(repository, head, status)
    assert recorder.mutations == []


def test_template_dry_run_does_not_render_or_leak_tokens(
    bootstrap, monkeypatch, tmp_path: Path, capsys
) -> None:
    destination = tmp_path / "service"
    token = "sentinel-codecov-token-4f1c"
    monkeypatch.setenv("CODECOV_TOKEN", token)
    _forbid_processes(monkeypatch, bootstrap)
    _block_network(monkeypatch, bootstrap)

    argv = [
        "--dry-run",
        "--template",
        "other",
        "--dest",
        str(destination),
        "--name",
        "widget",
        "--owner",
        "acme",
        "--enable-codecov",
    ]

    assert _exit_code(bootstrap, argv) == 0
    captured = capsys.readouterr()
    assert not destination.exists()
    assert token not in captured.out
    assert token not in captured.err


def test_root_requires_a_real_git_checkout(bootstrap, monkeypatch, tmp_path: Path) -> None:
    root = tmp_path / "plain"
    root.mkdir()
    (root / "keep.txt").write_text("original\n", encoding="utf-8")
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))
    before = _snapshot(root)
    with pytest.raises(SystemExit):
        bootstrap.require_git_checkout(root)
    recorder = _use_recorder(monkeypatch, bootstrap, allow_repo_view=False)
    _block_network(monkeypatch, bootstrap)

    argv = ["--root", str(root), "--name", "widget", "--owner", "acme"]

    with pytest.raises(SystemExit):
        bootstrap.main(argv)
    assert not (root / ".git").exists()
    assert _snapshot(root) == before
    assert recorder.mutations == []


def test_root_requires_the_checkout_top_level(bootstrap, monkeypatch, tmp_path: Path) -> None:
    repository = _make_repo(tmp_path / "widget")
    nested = repository / "nested"
    nested.mkdir()
    (nested / "keep.txt").write_text("original\n", encoding="utf-8")
    before = _snapshot(nested)
    with pytest.raises(SystemExit):
        bootstrap.require_git_checkout(nested)
    recorder = _use_recorder(monkeypatch, bootstrap, allow_repo_view=False)
    _block_network(monkeypatch, bootstrap)

    argv = ["--root", str(nested), "--name", "widget", "--owner", "acme"]

    with pytest.raises(SystemExit):
        bootstrap.main(argv)
    assert not (nested / ".git").exists()
    assert _snapshot(nested) == before
    assert recorder.mutations == []


@pytest.mark.parametrize(
    "origin",
    [None, "https://github.com/acme/other.git"],
    ids=["missing-origin", "mismatched-origin"],
)
def test_root_refuses_missing_or_mismatched_origin(
    bootstrap, monkeypatch, tmp_path: Path, origin: str | None
) -> None:
    repository = _make_repo(tmp_path / "widget", origin=origin)
    before = _snapshot(repository)
    head = _head(repository)
    status = _status(repository)
    recorder = _use_recorder(monkeypatch, bootstrap)
    _block_network(monkeypatch, bootstrap)

    argv = ["--root", str(repository), "--name", "widget", "--owner", "acme"]

    assert _exit_code(bootstrap, argv) != 0
    assert _snapshot(repository) == before
    _assert_no_install_or_commit(repository, head, status)
    assert recorder.mutations == []


def test_root_refuses_dirty_checkout_before_remote_or_install(
    bootstrap, monkeypatch, tmp_path: Path
) -> None:
    repository = _make_repo(
        tmp_path / "widget",
        origin="https://github.com/acme/widget.git",
    )
    (repository / "uncommitted.txt").write_text("draft\n", encoding="utf-8")
    before = _snapshot(repository)
    head = _head(repository)
    status = _status(repository)
    recorder = _use_recorder(monkeypatch, bootstrap, allow_repo_view=False)
    _block_network(monkeypatch, bootstrap)

    argv = ["--root", str(repository), "--name", "widget", "--owner", "acme"]

    with pytest.raises(SystemExit):
        bootstrap.main(argv)
    assert _snapshot(repository) == before
    _assert_no_install_or_commit(repository, head, status)
    assert recorder.mutations == []


def test_root_refuses_unborn_checkout_without_touching_the_index(
    bootstrap, monkeypatch, tmp_path: Path
) -> None:
    repository = _make_unborn_repo(tmp_path / "widget")
    before = _snapshot(repository)
    index = _git(repository, "ls-files", "--stage")
    status = _status(repository)
    with pytest.raises(SystemExit):
        bootstrap.require_git_checkout(repository)
    recorder = _use_recorder(monkeypatch, bootstrap, allow_repo_view=False)
    _block_network(monkeypatch, bootstrap)

    argv = ["--root", str(repository), "--name", "widget", "--owner", "acme"]

    with pytest.raises(SystemExit):
        bootstrap.main(argv)
    assert not _has_head(repository)
    assert _git(repository, "ls-files", "--stage") == index
    assert _status(repository) == status
    assert _snapshot(repository) == before
    assert not (repository / ".git" / "hooks" / "pre-commit").exists()
    assert recorder.mutations == []


def test_no_create_repo_without_remote_prepares_the_local_checkout(
    bootstrap, monkeypatch, tmp_path: Path
) -> None:
    destination = tmp_path / "service"

    def fake_render(args, plan):
        destination.mkdir()
        (destination / "README.md").write_text("original\n", encoding="utf-8")
        (destination / "mise.toml").write_text("[tools]\n", encoding="utf-8")
        (destination / ".pre-commit-config.yaml").write_text("repos: []\n", encoding="utf-8")
        return destination

    monkeypatch.setattr(bootstrap, "render", fake_render)
    _isolate_git_config(monkeypatch, tmp_path)
    recorder = _use_recorder(
        monkeypatch,
        bootstrap,
        repo_exists=False,
        allow_git_writes=True,
        allow_local_tools=True,
    )
    _block_network(monkeypatch, bootstrap)

    argv = [
        "--template",
        "other",
        "--dest",
        str(destination),
        "--name",
        "widget",
        "--owner",
        "acme",
        "--no-create-repo",
    ]

    assert _exit_code(bootstrap, argv) == 0
    assert _has_head(destination)
    assert _status(destination) == ""
    assert (destination / "README.md").read_text(encoding="utf-8") == "original\n"
    assert recorder.hook_install_attempted
    assert recorder.mutations == []


@pytest.mark.parametrize(
    "argv",
    [
        ["--template", "other", "--dest", "out", "--name", "widget", "--min-coverage", "-1"],
        ["--template", "other", "--dest", "out", "--name", "widget", "--min-coverage", "101"],
        [
            "--template",
            "unity",
            "--dest",
            "out",
            "--name",
            "widget",
            "--visibility",
            "public",
            "--unity-runner",
            "self-hosted",
        ],
        [
            "--template",
            "other",
            "--dest",
            "out",
            "--name",
            "widget",
            "--unity-runner",
            "self-hosted",
        ],
        ["--template", "python", "--dest", "out", "--name", "widget", "--run-tests"],
        ["--render-only", "--name", "widget"],
    ],
    ids=[
        "coverage-below-zero",
        "coverage-above-hundred",
        "public-self-hosted-runner",
        "runner-on-other-stack",
        "run-tests-on-python",
        "render-only-without-template",
    ],
)
def test_unsafe_cli_options_are_rejected(bootstrap, argv: list[str]) -> None:
    with pytest.raises(SystemExit) as excinfo:
        bootstrap.parse_args(argv)
    assert excinfo.value.code == 2
