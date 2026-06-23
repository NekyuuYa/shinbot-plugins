"""astrbot.api.provider — LLM response types."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class LLMResponse:
    """Stub for AstrBot's LLM response object."""

    role: str = "assistant"
    completion_text: str = ""
    usage: Any = None
    raw_completion: Any = None
    is_chunk: bool = False
