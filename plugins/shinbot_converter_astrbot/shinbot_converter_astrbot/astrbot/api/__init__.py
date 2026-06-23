"""astrbot.api — top-level API exports."""

from __future__ import annotations

import logging

logger = logging.getLogger("astrbot")


class AstrBotConfig(dict):
    """Stub for AstrBotConfig — behaves like a dict."""

    def save_config(self) -> None:
        pass


class _SharedPreferences:
    """Stub for AstrBot SharedPreferences."""

    async def get_async(self, scope="", scope_id="", key="", default=None):
        return default


sp = _SharedPreferences()
