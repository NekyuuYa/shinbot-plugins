"""Virtual plugin registration for AstrBot compat plugins.

Registers each AstrBot compat plugin as a virtual top-level plugin in
ShinBot's WebUI, with a dynamically generated Pydantic config schema
derived from the AstrBot ``_conf_schema.json`` file.
"""

from __future__ import annotations

import json
import logging
import types
from pathlib import Path
from typing import TYPE_CHECKING, Any

from shinbot.core.plugins.types import PluginMeta, PluginRole, PluginState

if TYPE_CHECKING:
    from shinbot.core.plugins.context import Plugin

from .schema_converter import convert_schema_to_pydantic

logger = logging.getLogger(__name__)


def register_virtual_plugins(
    plg: Plugin,
    compat_plugins: dict[str, dict[str, Any]],
) -> None:
    """Register compat plugins as virtual top-level plugins in the WebUI.

    For each compat plugin that has a ``_conf_schema.json``, this creates
    a virtual :class:`PluginMeta` and module entry in the
    :class:`PluginManager` so the plugin appears in the WebUI with an
    editable config form.

    Args:
        plg: The bridge layer's Plugin object.
        compat_plugins: Mapping of ``plugin_id`` → info dict containing:
            - ``plugin_dir``: Path to the compat plugin directory
            - ``config``: The live ShimAstrBotConfig instance
            - ``metadata``: The AstrBot metadata dict (from metadata.yaml)
    """
    plugin_manager = getattr(plg, "_plugin_manager", None)
    if plugin_manager is None:
        logger.warning("astrbot compat: no PluginManager available, skipping virtual registration")
        return

    for plugin_id, info in compat_plugins.items():
        plugin_dir = info["plugin_dir"]
        config = info["config"]
        meta_data = info.get("metadata", {})

        schema_path = plugin_dir / "_conf_schema.json"
        config_path = plugin_dir / "_config.json"

        if not schema_path.exists():
            logger.debug(
                "astrbot compat: no _conf_schema.json for %s, skipping",
                plugin_id,
            )
            continue

        try:
            config_model = convert_schema_to_pydantic(schema_path, plugin_id)
        except Exception:
            logger.exception("astrbot compat: failed to convert schema for %s", plugin_id)
            continue

        _inject_virtual_plugin(
            plugin_manager=plugin_manager,
            plugin_id=plugin_id,
            meta_data=meta_data,
            config_model=config_model,
            config_path=config_path,
            astrbot_config=config,
            boot=plugin_manager._boot if hasattr(plugin_manager, "_boot") else None,
        )


def _inject_virtual_plugin(
    plugin_manager: Any,
    plugin_id: str,
    meta_data: dict[str, Any],
    config_model: type,
    config_path: Path,
    astrbot_config: Any,
    boot: Any = None,
) -> None:
    """Inject a single virtual plugin into the PluginManager."""
    # 1. Create virtual PluginMeta
    virtual_meta = PluginMeta(
        id=plugin_id,
        name=meta_data.get("display_name", meta_data.get("name", plugin_id)),
        version=meta_data.get("version", "0.0.0"),
        description=meta_data.get("desc", ""),
        author=meta_data.get("author", ""),
        role=PluginRole.LOGIC,
        state=PluginState.ACTIVE,
        module_path=f"virtual.compat.{plugin_id}",
    )

    # 2. Create virtual module
    virtual_module = types.ModuleType(f"_virtual_compat_{plugin_id}")
    virtual_module.__plugin_config_class__ = config_model
    virtual_module.__file__ = str(config_path)
    virtual_module.__on_config_updated__ = _create_config_sync_handler(
        plugin_id=plugin_id,
        config_path=config_path,
        astrbot_config=astrbot_config,
    )

    # 3. Inject into PluginManager
    plugin_manager._plugins[plugin_id] = virtual_meta
    plugin_manager._modules[plugin_id] = virtual_module

    # 4. Sync initial config from AstrBot JSON → config.toml
    if boot is not None:
        _sync_astrbot_to_config_toml(boot, plugin_id, config_path)

    logger.info(
        "astrbot compat: registered virtual plugin %s (%s, %d groups)",
        plugin_id,
        virtual_meta.name,
        len(config_model.model_json_schema().get("properties", {})),
    )


def _sync_astrbot_to_config_toml(
    boot: Any,
    plugin_id: str,
    config_path: Path,
) -> None:
    """On first load, copy AstrBot JSON config into config.toml."""
    from shinbot.core.plugins.config import plugin_config_entry, plugin_saved_config

    # Only sync if config.toml has no entry for this plugin yet
    existing = plugin_saved_config(boot, plugin_id)
    if existing:
        return

    if not config_path.exists():
        return

    try:
        astrbot_config = json.loads(config_path.read_text(encoding="utf-8"))
    except Exception:
        return

    if not isinstance(astrbot_config, dict):
        return

    entry = plugin_config_entry(boot.config, plugin_id, create=True)
    if entry is not None:
        entry["config"] = astrbot_config
        logger.info("astrbot compat: synced initial config for %s from _config.json", plugin_id)


def _create_config_sync_handler(
    plugin_id: str,
    config_path: Path,
    astrbot_config: Any,
) -> Any:
    """Create a callback that syncs WebUI config changes to AstrBot JSON.

    When the WebUI saves config via ``PATCH /plugins/{id}/config``,
    this callback is invoked with the normalized Pydantic dict.
    It converts the nested group structure back to AstrBot's flat
    group/item format and writes it to ``_config.json``.
    """

    def handler(normalized_config: dict[str, Any]) -> None:
        # normalized_config is already in group/item structure from Pydantic
        # (e.g. {"basic": {"analysis_days": 1}, "llm": {"llm_retries": 2}})
        # This IS the AstrBot format — just write it directly.
        try:
            config_path.parent.mkdir(parents=True, exist_ok=True)
            config_path.write_text(
                json.dumps(normalized_config, ensure_ascii=False, indent=4),
                encoding="utf-8",
            )
            # Also update the live ShimAstrBotConfig
            if astrbot_config is not None:
                astrbot_config.clear()
                astrbot_config.update(normalized_config)
            logger.info("astrbot compat: synced WebUI config for %s to _config.json", plugin_id)
        except Exception:
            logger.exception("astrbot compat: failed to sync config for %s", plugin_id)

    return handler
