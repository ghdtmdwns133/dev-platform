"""Pytest fixtures shared by the devctl test suite."""

from __future__ import annotations

from pathlib import Path

import pytest
from support import make_unity_tree


@pytest.fixture
def unity_tree(tmp_path: Path) -> Path:
    return make_unity_tree(tmp_path / "unity")
