"""AstrBot plugin installer for ShinBot converter."""

from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

ASTRBOT_PLUGIN_METADATA_REQUIRED_FIELDS = ("name",)


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

    target_dir.mkdir(parents=True, exist_ok=True)
    plugin_name = _plugin_id_from_metadata(metadata, plugin_path)
    dest = _target_plugin_dir(target_dir, plugin_name)

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
    plugin_dir = _target_plugin_dir(target_dir, plugin_name)
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
    metadata = _load_metadata(plugin_path)
    if metadata is None:
        return None
    plugin_id = _plugin_id_from_metadata(metadata, plugin_path)
    normalized = dict(metadata)
    normalized["id"] = plugin_id
    normalized.setdefault("display_name", str(metadata.get("name") or plugin_id))
    normalized["name"] = plugin_id
    normalized.setdefault("version", "0.0.0")
    normalized.setdefault("author", "")
    normalized.setdefault("desc", "")
    return normalized


def _load_metadata(plugin_path: Path) -> dict[str, Any] | None:
    """Load and validate AstrBot plugin metadata from metadata.yaml or metadata.json."""
    # Try metadata.yaml first
    yaml_path = plugin_path / "metadata.yaml"
    if yaml_path.exists():
        try:
            import yaml

            data = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
            if _validate_metadata_fields(data):
                return _normalize_metadata(data, plugin_path)
        except Exception:
            logger.debug("astrbot installer: failed to parse %s", yaml_path)

    # Try metadata.json as fallback
    json_path = plugin_path / "metadata.json"
    if json_path.exists():
        try:
            import json

            data = json.loads(json_path.read_text(encoding="utf-8"))
            if _validate_metadata_fields(data):
                return _normalize_metadata(data, plugin_path)
        except Exception:
            logger.debug("astrbot installer: failed to parse %s", json_path)

    return None


def _validate_metadata_fields(data: Any) -> bool:
    """Validate that metadata contains required fields."""
    if not isinstance(data, dict):
        return False
    return all(
        str(data.get(field) or "").strip()
        for field in ASTRBOT_PLUGIN_METADATA_REQUIRED_FIELDS
    )


def _normalize_metadata(data: dict[str, Any], plugin_path: Path) -> dict[str, Any]:
    """Return AstrBot metadata with safe ShinBot marketplace fields attached."""
    plugin_id = _plugin_id_from_metadata(data, plugin_path)
    normalized = dict(data)
    normalized["id"] = plugin_id
    normalized.setdefault("display_name", str(data.get("name") or plugin_id))
    normalized["name"] = plugin_id
    normalized.setdefault("version", "0.0.0")
    normalized.setdefault("author", "")
    normalized.setdefault("desc", "")
    return normalized


def _plugin_id_from_metadata(metadata: dict[str, Any], plugin_path: Path) -> str:
    raw = str(metadata.get("id") or metadata.get("name") or plugin_path.name).strip()
    plugin_id = raw or plugin_path.name
    if (
        not plugin_id
        or "/" in plugin_id
        or "\\" in plugin_id
        or plugin_id in {".", ".."}
        or ".." in Path(plugin_id).parts
    ):
        plugin_id = plugin_path.name
    if (
        not plugin_id
        or "/" in plugin_id
        or "\\" in plugin_id
        or plugin_id in {".", ".."}
        or ".." in Path(plugin_id).parts
    ):
        raise ValueError(f"invalid AstrBot plugin name: {raw!r}")
    return plugin_id


def _target_plugin_dir(target_dir: Path, plugin_name: str) -> Path:
    """Resolve a plugin target and ensure it stays inside target_dir."""
    root = target_dir.resolve()
    target = (root / plugin_name).resolve()
    if target == root or not target.is_relative_to(root):
        raise ValueError(f"invalid AstrBot plugin target: {plugin_name!r}")
    return target
