"""astrbot package — stub for AstrBot plugin compatibility."""

from __future__ import annotations

import logging

logger = logging.getLogger("astrbot")


class AstrBotConfig(dict):
    """Stub for AstrBotConfig — behaves like a dict."""

    def save_config(self) -> None:
        """Persist config — no-op in stub, overridden by ShimAstrBotConfig."""
        pass
