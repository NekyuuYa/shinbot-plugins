"""Stub for astrbot.core.utils.astrbot_path."""

from __future__ import annotations

from pathlib import Path

_DATA_DIR: Path | None = None


def get_astrbot_data_path() -> str:
    """Return the AstrBot data directory path."""
    if _DATA_DIR is not None:
        return str(_DATA_DIR)
    return str(Path("data"))


def _set_data_dir(path: Path) -> None:
    """Set the data directory (called by the bridge loader)."""
    global _DATA_DIR
    _DATA_DIR = path
