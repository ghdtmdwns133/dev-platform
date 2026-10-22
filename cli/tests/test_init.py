"""Template rendering tests using a throwaway templates directory."""

from __future__ import annotations

import re
import shutil
from pathlib import Path

import pytest

from devplatform import initcmd
from devplatform.errors import DevctlError
from devplatform.hooks import MARKER


def make_templates(home: Path) -> Path:
    shared = home / "templates" / "_shared"
    shared.mkdir(parents=True)
    (shared / ".gitattributes").write_text("* text=auto eol=lf\n", encoding="utf-8")
    (shared / "README.md").write_text("# __PROJECT_NAME__\n\nowner __OWNER__\n", encoding="utf-8")
    (shared / ".github").mkdir()
    (shared / ".github/dependabot.yml").write_text("version: 2\n", encoding="utf-8")

    python = home / "templates" / "python"
    python.mkdir(parents=True)
    (python / "pyproject.toml").write_text(
        '[project]\nname = "__PROJECT_SLUG__"\n', encoding="utf-8"
    )
    (python / ".github").mkdir()
    (python / ".github/ci.yml").write_text(
        "profile: __PROFILE__\nminimum: __MIN_COVERAGE__\n"
        "codecov: __ENABLE_CODECOV__\nsarif: __UPLOAD_SARIF__\nref: __PLATFORM_REF__\n",
        encoding="utf-8",
    )
    package = python / "src" / "__PACKAGE__"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text(
        'NAME = "__PROJECT_NAME__"\nPROFILE = "__PROFILE__"\n', encoding="utf-8"
    )
    (python / "binary.bin").write_bytes(b"\xff\xfe__PROJECT_NAME__")
    return home / "templates"


def test_python_render(tmp_path: Path) -> None:
    home = tmp_path / "platform"
    make_templates(home)
    dest = tmp_path / "out" / "mine"
    initcmd.init("python", "My Cool App", dest, home)
    assert (dest / "README.md").read_text(encoding="utf-8").startswith("# My Cool App")
    assert (dest / "src" / "my_cool_app" / "__init__.py").read_text(
        encoding="utf-8"
    ) == 'NAME = "My Cool App"\nPROFILE = "python"\n'
    ci = (dest / ".github/ci.yml").read_text(encoding="utf-8")
    assert "minimum: 80" in ci
    assert "codecov: false" in ci
    assert "sarif: true" in ci
    assert "ref: v1" in ci
    assert (dest / "binary.bin").read_bytes() == b"\xff\xfe__PROJECT_NAME__"


def test_tokens_and_options(tmp_path: Path) -> None:
    home = tmp_path / "platform"
    make_templates(home)
    dest = tmp_path / "out" / "mine"
    initcmd.init(
        "python",
        "My Cool App",
        dest,
        home,
        owner="someone",
        ref="v2",
        min_coverage=91,
        enable_codecov=True,
        private=True,
    )
    assert "owner someone" in (dest / "README.md").read_text(encoding="utf-8")
    ci = (dest / ".github/ci.yml").read_text(encoding="utf-8")
    assert "minimum: 91" in ci
    assert "codecov: true" in ci
    assert "sarif: false" in ci
    assert "ref: v2" in ci
    for path in dest.rglob("*"):
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        assert not re.search(r"__[A-Z][A-Z_]*__", text), path


def test_unresolved_token_is_atomic(tmp_path: Path) -> None:
    home = tmp_path / "platform"
    templates = make_templates(home)
    (templates / "python" / "bad.txt").write_text("__UNKNOWN__\n", encoding="utf-8")
    dest = tmp_path / "out" / "mine"
    with pytest.raises(DevctlError) as excinfo:
        initcmd.init("python", "My App", dest, home)
    assert excinfo.value.code == 1
    assert "__UNKNOWN__" in excinfo.value.message
    assert not dest.exists()
    assert not list((tmp_path / "out").glob(".mine.devctl-*"))


def test_non_empty_destination_requires_force(tmp_path: Path) -> None:
    home = tmp_path / "platform"
    make_templates(home)
    dest = tmp_path / "out" / "mine"
    dest.mkdir(parents=True)
    (dest / "keep.txt").write_text("keep", encoding="utf-8")
    with pytest.raises(DevctlError) as excinfo:
        initcmd.init("python", "My App", dest, home)
    assert excinfo.value.code == 1
    assert "not empty" in excinfo.value.message

    initcmd.init("python", "My App", dest, home, force=True)
    assert (dest / "README.md").is_file()
    assert not (dest / "keep.txt").exists()


def test_init_creates_git_repo_and_hook(tmp_path: Path) -> None:
    if shutil.which("git") is None:
        pytest.skip("git is not installed")
    home = tmp_path / "platform"
    make_templates(home)
    dest = tmp_path / "out" / "mine"
    initcmd.init("python", "My App", dest, home)
    assert (dest / ".git").is_dir()
    hook = dest / ".git" / "hooks" / "pre-commit"
    assert hook.is_file()
    content = hook.read_text(encoding="utf-8")
    assert MARKER in content
    assert "/cli" in content.replace("\\", "/")
    assert "hooks pre-commit" in content


def test_unknown_template(tmp_path: Path) -> None:
    home = tmp_path / "platform"
    make_templates(home)
    with pytest.raises(DevctlError) as excinfo:
        initcmd.init("ruby", "My App", tmp_path / "dest", home)
    assert excinfo.value.code == 2


def test_missing_templates(tmp_path: Path) -> None:
    with pytest.raises(DevctlError) as excinfo:
        initcmd.init("python", "My App", tmp_path / "dest", tmp_path / "missing")
    assert excinfo.value.code == 2
