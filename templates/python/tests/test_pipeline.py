from __future__ import annotations

import pytest

from __PACKAGE__.pipeline import (
    Stage,
    StageGraphError,
    critical_path_length,
    topological_order,
)


def test_critical_path_uses_longest_chain() -> None:
    stages = [
        Stage("build", 4),
        Stage("test", 3, ("build",)),
        Stage("package", 2, ("test",)),
        Stage("lint", 1, ("build",)),
    ]

    assert critical_path_length(stages) == 9
    assert topological_order(stages) == ["build", "lint", "test", "package"]


def test_cycle_is_rejected() -> None:
    stages = [Stage("a", 1, ("b",)), Stage("b", 1, ("a",))]

    with pytest.raises(StageGraphError, match="cycle"):
        critical_path_length(stages)


def test_empty_graph_returns_zero() -> None:
    assert critical_path_length([]) == 0
