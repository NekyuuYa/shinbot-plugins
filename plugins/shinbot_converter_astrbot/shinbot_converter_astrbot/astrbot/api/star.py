"""astrbot.api.star — Star base class, Context stub, and StarTools."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from astrbot._registry import pending_stars


class Context:
    """Stub — actual instances are ShimContext from shim/context.py."""


class StarTools:
    """Plugin utility class with a configurable data directory."""

    _data_dir: Path | None = None

    @staticmethod
    def get_data_dir() -> Path:
        """Return the plugin data directory. Set by the bridge loader."""
        if StarTools._data_dir is not None:
            return StarTools._data_dir
        raise RuntimeError("StarTools.get_data_dir() not configured by bridge loader")


class Star:
    """Base class for AstrBot plugins."""

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        pending_stars.append(cls)

    def __init__(self, context: Context, config=None):
        self.context = context
        self.config = config or {}

    async def initialize(self) -> None:
        pass

    async def terminate(self) -> None:
        pass

    # KV storage — delegated to _kv_store injected by the bridge loader
    async def put_kv_data(self, key: str, value: Any) -> None:
        if hasattr(self, "_kv_store") and self._kv_store is not None:
            await self._kv_store.put_kv_data(key, value)

    async def get_kv_data(self, key: str, default=None):
        if hasattr(self, "_kv_store") and self._kv_store is not None:
            return await self._kv_store.get_kv_data(key, default)
        return default

    # HTML rendering — injected by the bridge loader
    async def html_render(
        self,
        tmpl: str,
        data: dict,
        return_url: bool = True,
        options: dict | None = None,
    ) -> str | bytes:
        """Render HTML to image. Injected with real implementation by the bridge."""
        raise NotImplementedError(
            "html_render not available — install shinbot_plugin_renderkit"
        )


def register(
    name: str = "",
    author: str = "",
    desc: str = "",
    version: str = "",
    repo: str = "",
):
    """Legacy @register(...) class decorator — just passes through."""

    def decorator(cls):
        return cls

    return decorator
