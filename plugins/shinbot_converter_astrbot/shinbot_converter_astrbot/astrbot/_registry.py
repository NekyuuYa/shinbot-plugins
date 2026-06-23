"""Central mutable state shared across all stub modules."""

from __future__ import annotations

import inspect
from dataclasses import dataclass
from typing import Any


class GreedyStr(str):
    """Consume all remaining tokens as a single string."""

    __greedy__ = True


@dataclass
class HandlerMeta:
    func: Any
    event_type: str  # "command" | "regex" | "ignored"
    group_path: list[str]  # [] for flat; [group, *aliases] for grouped
    names: list[str]  # name + aliases (or sub-command names for grouped)
    description: str
    param_specs: list[tuple[str, type]]  # [(param_name, param_type), ...]
    priority: int = 0
    msg_type_filter: str | None = None  # "group" | "private" | None
    permission: str = ""  # e.g. "admin", "member"


# Pending registrations — cleared before each plugin module import
pending_stars: list[type] = []
pending_handlers: list[HandlerMeta] = []


def clear() -> None:
    pending_stars.clear()
    pending_handlers.clear()


def extract_params(func: Any) -> list[tuple[str, type]]:
    """Inspect handler signature and return [(name, type)] skipping self and event."""
    try:
        sig = inspect.signature(func)
        params = []
        for i, (pname, param) in enumerate(sig.parameters.items()):
            if i < 2:  # skip self, event
                continue
            ann = param.annotation
            if ann is inspect.Parameter.empty:
                ann = str
            params.append((pname, ann))
        return params
    except (ValueError, TypeError):
        return []
