"""Critical-path planning for a stage dependency graph."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass


class StageGraphError(ValueError):
    """Raised when a stage graph is not a directed acyclic graph."""


@dataclass(frozen=True)
class Stage:
    """A single pipeline stage with a duration and its direct dependencies."""

    name: str
    duration: int
    needs: tuple[str, ...] = ()


def topological_order(stages: Iterable[Stage]) -> list[str]:
    """Return stage names in dependency order, breaking ties alphabetically."""
    stage_list = list(stages)
    graph = {stage.name: stage.needs for stage in stage_list}
    pending = {name: len(needs) for name, needs in graph.items()}
    for needs in graph.values():
        for need in needs:
            if need not in graph:
                raise StageGraphError(f"unknown stage dependency: {need}")
    ready = sorted(name for name, count in pending.items() if count == 0)
    order: list[str] = []
    while ready:
        name = ready.pop(0)
        order.append(name)
        for candidate, needs in graph.items():
            if name in needs:
                pending[candidate] -= 1
                if pending[candidate] == 0:
                    ready.append(candidate)
        ready.sort()
    if len(order) != len(graph):
        raise StageGraphError("stage graph contains a cycle")
    return order


def critical_path_length(stages: Iterable[Stage]) -> int:
    """Return the earliest possible completion time of the whole graph."""
    stage_list = list(stages)
    order = topological_order(stage_list)
    durations = {stage.name: stage.duration for stage in stage_list}
    needs = {stage.name: stage.needs for stage in stage_list}
    finish: dict[str, int] = {}
    for name in order:
        longest = max((finish[need] for need in needs[name]), default=0)
        finish[name] = longest + durations[name]
    return max(finish.values(), default=0)
