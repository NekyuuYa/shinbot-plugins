"""ShimProvider — wraps a provider dict from ModelRegistry as an AstrBot Provider object."""
from __future__ import annotations

from typing import Any


class _ShimMeta:
    def __init__(self, provider_id: str, display_name: str = ""):
        self.id = provider_id
        self.name = display_name


class ShimProvider:
    """Wraps a provider definition dict to match AstrBot's Provider interface."""

    def __init__(self, data: dict[str, Any]):
        self._data = data

    def meta(self):
        return _ShimMeta(
            self._data.get("id", ""),
            self._data.get("display_name", self._data.get("id", "")),
        )

    @property
    def provider_config(self) -> dict[str, Any]:
        return self._data

    async def text_chat_stream(self, **kwargs):
        raise NotImplementedError(
            "Streaming LLM calls are not yet supported in bridge mode. "
            "Set enable_streaming_llm_call to false in the plugin config."
        )
