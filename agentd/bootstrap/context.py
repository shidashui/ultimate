"""Per-session container access via contextvars.

Each AgentRunner.run_turn() sets the current container at entry
and clears it on exit. Tool functions call get_current_container()
to reach their dependencies without importing a global singleton.
"""
from __future__ import annotations

import contextvars
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agentd.bootstrap.container import Container

_current_container: contextvars.ContextVar[Container | None] = (
    contextvars.ContextVar("current_container", default=None)
)


def set_current_container(container: Container | None) -> None:
    """Set the container for the current async context."""
    _current_container.set(container)


def get_current_container() -> Container:
    """Return the current session's container.

    Raises RuntimeError if called outside AgentRunner.run_turn().
    """
    c = _current_container.get()
    if c is None:
        raise RuntimeError(
            "No container set — must be called within AgentRunner.run_turn()"
        )
    return c
