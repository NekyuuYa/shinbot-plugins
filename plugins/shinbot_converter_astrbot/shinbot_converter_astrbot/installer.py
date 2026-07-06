"""AstrBot plugin installer for ShinBot converter."""

from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

ASTRBOT_PLUGIN_METADATA_REQUIRED_FIELDS = ("name", "desc", "version", "author")


async def install_astrbot_plugin(
    plugin_path: Path,
    *,
    target_dir: Path,
    source_info: dict[str, Any] | None = None,
) -> bool:
    """Install an AstrBot plugin to the compat_plugins directory.

    Args:
        plugin_path: Path to the extracted plugin directory.
        target_dir:  Target directory (compat_plugins).
        source_info: Optional source metadata.

    Returns:
        True if installation succeeded.
    """
    metadata = _load_metadata(plugin_path)
    if not metadata:
        logger.error("astrbot installer: no valid metadata found in %s", plugin_path)
        return False

    plugin_name = metadata.get("name") or plugin_path.name
    dest = target_dir / plugin_name

    if dest.exists():
        logger.info("astrbot installer: removing existing plugin at %s", dest)
        shutil.rmtree(dest)

    shutil.copytree(plugin_path, dest)
    logger.info("astrbot installer: installed %s to %s", plugin_name, dest)
    return True


async def uninstall_astrbot_plugin(
    plugin_name: str,
    *,
    target_dir: Path,
) -> bool:
    """Uninstall an AstrBot plugin from compat_plugins.

    Args:
        plugin_name: Name of the plugin to uninstall.
        target_dir:  Target directory (compat_plugins).

    Returns:
        True if uninstallation succeeded.
    """
    plugin_dir = target_dir / plugin_name
    if not plugin_dir.exists():
        logger.warning("astrbot installer: plugin %s not found at %s", plugin_name, plugin_dir)
        return False

    shutil.rmtree(plugin_dir)
    logger.info("astrbot installer: uninstalled %s", plugin_name)
    return True


def validate_astrbot_metadata(plugin_path: Path) -> dict[str, Any] | None:
    """Validate AstrBot plugin metadata.

    Args:
        plugin_path: Path to the plugin directory.

    Returns:
        Metadata dict if valid, None otherwise.
    """
    return _load_metadata(plugin_path)


def _load_metadata(plugin_path: Path) -> dict[str, Any] | None:
    """Load and validate AstrBot plugin metadata from metadata.yaml or metadata.json."""
    # Try metadata.yaml first
    yaml_path = plugin_path / "metadata.yaml"
    if yaml_path.exists():
        try:
            data = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
            if _validate_metadata_fields(data):
                return data
        except Exception:
            logger.debug("astrbot installer: failed to parse %s", yaml_path)

    # Try metadata.json as fallback
    json_path = plugin_path / "metadata.json"
    if json_path.exists():
        try:
            import json

            data = json.loads(json_path.read_text(encoding="utf-8"))
            if _validate_metadata_fields(data):
                return data
        except Exception:
            logger.debug("astrbot installer: failed to parse %s", json_path)

    return None


def _validate_metadata_fields(data: Any) -> bool:
    """Validate that metadata contains required fields."""
    if not isinstance(data, dict):
        return False
    return all(field in data for field in ASTRBOT_PLUGIN_METADATA_REQUIRED_FIELDS)
