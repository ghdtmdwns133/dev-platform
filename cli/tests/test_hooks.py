"""Git hook installation and the staged-file pre-commit gate."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest
from support import FakeRunner, install_uv_ruff_proxy, make_unity_tree, write_config

from devplatform import hooks
from devplatform.config import load_config
from devplatform.errors import DevctlError
from devplatform.hooks import MARKER


def git(repo: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    return completed.stdout.strip()


def init_repo(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    git(path, "init", "-b", "main")
    git(path, "config", "user.email", "devctl@example.com")
    git(path, "config", "user.name", "devctl tests")
    return path


def test_install_and_idempotent(tmp_path: Path) -> None:
    repo = init_repo(tmp_path / "repo")
    platform = tmp_path / "platform"
    (platform / "cli").mkdir(parents=True)
    first = hooks.install_hooks(repo, platform)
    content = first.read_text(encoding="utf-8")
    assert MARKER in content
    assert (platform / "cli").as_posix() in content.replace("\\", "/")
    assert "hooks pre-commit" in content
    assert "\r\n" not in content
    second = hooks.install_hooks(repo, platform)
    assert first == second
    assert second.read_text(encoding="utf-8") == content


def test_refuses_foreign_hook(tmp_path: Path) -> None:
    repo = init_repo(tmp_path / "repo")
    platform = tmp_path / "platform"
    (platform / "cli").mkdir(parents=True)
    hook = repo / ".git" / "hooks" / "pre-commit"
    hook.parent.mkdir(parents=True, exist_ok=True)
    hook.write_text("#!/bin/sh\necho foreign\n", encoding="utf-8")
    with pytest.raises(DevctlError) as excinfo:
        hooks.install_hooks(repo, platform)
    assert excinfo.value.code == 1
    assert "refusing to overwrite" in excinfo.value.message
    hooks.install_hooks(repo, platform, force=True)
    assert MARKER in hook.read_text(encoding="utf-8")


def test_install_outside_git_repo(tmp_path: Path) -> None:
    platform = tmp_path / "platform"
    (platform / "cli").mkdir(parents=True)
    with pytest.raises(DevctlError) as excinfo:
        hooks.install_hooks(tmp_path / "plain", platform)
    assert excinfo.value.code == 2


def _python_repo(tmp_path: Path) -> Path:
    repo = init_repo(tmp_path / "repo")
    write_config(repo, profile="python")
    return repo


def test_pre_commit_good_and_bad_python(tmp_path: Path, monkeypatch) -> None:
    if shutil.which("ruff") is None:
        pytest.skip("ruff is not on PATH")
    repo = _python_repo(tmp_path)
    stub = install_uv_ruff_proxy(tmp_path / "stubs")
    monkeypatch.setenv("PATH", str(stub.parent) + os.pathsep + os.environ["PATH"])
    config = load_config(repo)
    reports = repo / "artifacts/reports"

    good = repo / "good.py"
    good.write_text("x = 1\n", encoding="utf-8")
    git(repo, "add", "good.py")
    assert hooks.pre_commit(repo, config, reports) == 0

    good.write_text("import os\n", encoding="utf-8")
    git(repo, "add", "good.py")
    assert hooks.pre_commit(repo, config, reports) == 1


def test_pre_commit_no_relevant_files(tmp_path: Path) -> None:
    repo = _python_repo(tmp_path)
    config = load_config(repo)
    runner = FakeRunner()
    (repo / "notes.txt").write_text("hi", encoding="utf-8")
    git(repo, "add", "notes.txt")
    assert hooks.pre_commit(repo, config, repo / "artifacts", runner=runner) == 0
    assert runner.calls == []


def test_pre_commit_skips_without_profile(tmp_path: Path) -> None:
    repo = init_repo(tmp_path / "repo")
    config = load_config(repo)
    assert config.profile is None
    assert hooks.pre_commit(repo, config, repo / "artifacts", runner=FakeRunner()) == 0


def test_pre_commit_unity_runs_integrity(tmp_path: Path) -> None:
    repo = init_repo(tmp_path / "repo")
    make_unity_tree(repo)
    write_config(repo, profile="unity")
    config = load_config(repo)
    git(repo, "add", "Assets/Scenes/SampleScene.unity")
    assert hooks.pre_commit(repo, config, repo / "artifacts") == 0

    scene = repo / "Assets/Scenes/SampleScene.unity"
    scene.write_text(
        scene.read_text(encoding="utf-8").replace("Main Camera", "Renamed Camera"),
        encoding="utf-8",
    )
    git(repo, "add", "Assets/Scenes/SampleScene.unity")
    assert hooks.pre_commit(repo, config, repo / "artifacts") == 1


def test_typescript_and_dotnet_plans(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "src").mkdir()
    (repo / "src/a.ts").write_text("export const a = 1;\n", encoding="utf-8")
    (repo / "README.md").write_text("# readme\n", encoding="utf-8")
    (repo / "src/App.cs").write_text("class App {}\n", encoding="utf-8")

    write_config(repo, profile="typescript")
    config = load_config(repo)
    commands, integrity = hooks._plan(repo, config, ["src/a.ts", "README.md", "src/App.cs"])
    assert integrity is False
    assert [name for name, _ in commands] == ["hooks-eslint", "hooks-prettier"]
    assert commands[0][1] == ["npx", "eslint", "--max-warnings=0", "src/a.ts"]
    assert commands[1][1] == ["npx", "prettier", "--check", "src/a.ts", "README.md"]

    write_config(repo, profile="dotnet")
    config = load_config(repo)
    commands, _ = hooks._plan(repo, config, ["src/App.cs", "README.md"])
    assert commands == [
        (
            "hooks-dotnet-format",
            ["dotnet", "format", "--verify-no-changes", "--include", "src/App.cs"],
        )
    ]
