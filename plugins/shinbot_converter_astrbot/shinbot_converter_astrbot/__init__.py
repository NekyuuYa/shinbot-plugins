"""shinbot_converter_astrbot — AstrBot plugin compatibility layer for ShinBot.

Compat plugins (AstrBot-style) should be placed in:
    data/plugin_data/shinbot_converter_astrbot/compat_plugins/<plugin_name>/
Each subdirectory must contain a main.py with a Star subclass.

Supported:
  - @filter.command / @filter.command_group / @filter.regex
  - @filter.event_message_type / @filter.permission_type
  - yield event.plain_result() / image_result() / chain_result() / make_result()
  - event.stop_event() / should_call_llm()
  - context.llm_generate() via plg.llm_call()
  - context.get_provider_by_id() / get_all_providers()
  - context.cron_manager.scheduler (direct APScheduler access)
  - Star.put_kv_data() / get_kv_data()
  - Star.html_render() (requires shinbot_plugin_renderkit)
  - AstrBotConfig save_config() / dict-based config
  - StarTools.get_data_dir()

Partially supported (degraded):
  - context.persona_manager → returns None (no persona injection)
  - context.conversation_manager → returns None
  - astrbot.api.sp (SharedPreferences) → returns defaults
  - Streaming LLM calls → not yet supported (use non-streaming mode)
"""
from __future__ import annotations

import inspect
import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from shinbot.core.dispatch.message_context import MessageContext
    from shinbot.core.plugins.context import Plugin

logger = logging.getLogger(__name__)

_loaded_plugins: list = []


async def setup(plg: Plugin) -> None:
    from .loader import inject_stub, load_compat_plugin

    # First inject the stub to make astrbot package available
    inject_stub()

    # Now we can import from astrbot
    from astrbot.api.star import StarTools
    from astrbot.core.utils.astrbot_path import _set_data_dir

    from .installer import (
        install_astrbot_plugin,
        uninstall_astrbot_plugin,
        validate_astrbot_metadata,
    )
    from .shim.config import ShimAstrBotConfig
    from .shim.context import ShimContext
    from .shim.kv import ShimKVStore

    # Configure path stubs
    _set_data_dir(plg.data_dir.parent)
    StarTools._data_dir = plg.data_dir

    # Register AstrBot plugin installer
    compat_dir = plg.data_dir / "compat_plugins"
    plg.register_plugin_installer(
        "astrbot",
        install_fn=install_astrbot_plugin,
        uninstall_fn=uninstall_astrbot_plugin,
        validate_fn=validate_astrbot_metadata,
        target_dir=compat_dir,
    )

    # Register AstrBot plugin marketplace source
    plg.register_marketplace_source(
        source_id="astrbot-official",
        name="AstrBot Official Plugins",
        source_type="github_index",
        repository_url="https://github.com/AstrBotDevs/AstrBot_Plugins_Collection",
        ref="main",
        plugin_root="plugins.json",
        installer_type="astrbot",
    )

    compat_dir.mkdir(parents=True, exist_ok=True)

    # Shared KV store (all compat plugins share one file)
    kv_store = ShimKVStore(plg.data_dir / "_kv_store.json")

    subdirs = sorted(p for p in compat_dir.iterdir() if p.is_dir())
    if not subdirs:
        logger.info("astrbot compat: no compat plugins found in %s", compat_dir)
        return

    compat_info: dict[str, dict] = {}

    for plugin_subdir in subdirs:
        loaded = load_compat_plugin(plugin_subdir)
        if loaded is None:
            continue

        # Load config
        config_path = plugin_subdir / "_config.json"
        schema_path = plugin_subdir / "_conf_schema.json"
        config = ShimAstrBotConfig(config_path, schema_path)

        # Build shim context
        shim_ctx = ShimContext(plg, config, kv_store, plugin_subdir)

        # Inject KV store and html_render onto Star instance
        loaded.instance._kv_store = kv_store
        loaded.instance.html_render = shim_ctx.html_render

        await loaded.initialize(shim_ctx)
        _register_handlers(plg, loaded)
        _loaded_plugins.append(loaded)

        # Collect info for virtual plugin registration
        plugin_id = plugin_subdir.name
        compat_info[plugin_id] = {
            "plugin_dir": plugin_subdir,
            "config": config,
            "metadata": _load_astrbot_metadata(plugin_subdir),
        }

    logger.info("astrbot compat: registered %d plugin(s)", len(_loaded_plugins))

    # Register virtual plugins in the WebUI
    if compat_info:
        from .shim.virtual_plugin import register_virtual_plugins

        register_virtual_plugins(plg, compat_info)


def _load_astrbot_metadata(plugin_dir: Path) -> dict[str, Any]:
    """Load AstrBot plugin metadata from metadata.yaml."""
    import yaml

    meta_path = plugin_dir / "metadata.yaml"
    if not meta_path.exists():
        # Try metadata.json as fallback
        json_path = plugin_dir / "metadata.json"
        if json_path.exists():
            try:
                return json.loads(json_path.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {}

    try:
        return yaml.safe_load(meta_path.read_text(encoding="utf-8")) or {}
    except Exception:
        logger.debug("astrbot compat: failed to load metadata from %s", meta_path)
        return {}


async def teardown() -> None:
    for loaded in _loaded_plugins:
        await loaded.terminate()
    _loaded_plugins.clear()


# ── Handler registration ──────────────────────────────────────────────────────


def _register_handlers(plg: Plugin, loaded) -> None:
    from shinbot.core.message_routes import CommandPriority

    flat: list = []
    groups: dict[tuple, list] = {}
    regexes: list = []

    for meta in loaded.handlers:
        if meta.event_type == "regex":
            regexes.append(meta)
        elif meta.group_path:
            groups.setdefault(tuple(meta.group_path), []).append(meta)
        else:
            flat.append(meta)

    # Flat commands
    for meta in flat:
        if not meta.names:
            continue
        name, *aliases = meta.names
        permission = _extract_permission(meta)

        @plg.on_command(
            name, aliases=aliases, description=meta.description, permission=permission
        )
        async def _flat_handler(
            ctx: MessageContext,
            args: str,
            _meta=meta,
            _loaded=loaded,
        ) -> None:
            await _invoke(ctx, args, _meta, _loaded)

    # Grouped commands — one ShinBot command per group, sub-command in args
    for group_path, sub_handlers in groups.items():
        group_name, *group_aliases = group_path
        desc = f"AstrBot command group: {group_name}"

        @plg.on_command(group_name, aliases=group_aliases, description=desc)
        async def _group_handler(
            ctx: MessageContext,
            args: str,
            _subs=sub_handlers,
            _loaded=loaded,
        ) -> None:
            tokens = args.split(None, 1)
            if not tokens:
                return
            sub_token, rest = tokens[0], (tokens[1] if len(tokens) > 1 else "")
            for meta in _subs:
                if sub_token in meta.names:
                    await _invoke(ctx, rest, meta, _loaded)
                    return

    # Regex handlers
    for meta in regexes:
        pattern = meta.names[0] if meta.names else ""
        if not pattern:
            continue

        @plg.on_command(
            pattern,
            priority=CommandPriority.P2_REGEX,
            pattern=pattern,
            description=meta.description,
        )
        async def _regex_handler(
            ctx: MessageContext,
            args: str,
            _meta=meta,
            _loaded=loaded,
        ) -> None:
            await _invoke(ctx, ctx.text, _meta, _loaded, full_text=ctx.text)


def _extract_permission(meta) -> str:
    """Extract permission from HandlerMeta if permission_type was applied."""
    # Check meta.permission (set by @permission_type decorator chain)
    if hasattr(meta, "permission") and meta.permission:
        return meta.permission
    # Check function attribute (fallback)
    perm = getattr(meta.func, "__compat_permission__", None)
    if perm:
        return perm
    return ""


# ── Invocation ────────────────────────────────────────────────────────────────


async def _invoke(
    ctx: MessageContext,
    args: str,
    meta,
    loaded,
    *,
    full_text: str = "",
) -> None:
    from .shim.event import ShimAstrMessageEvent
    from .translator import translate_chain

    # Message type filter (group / private)
    if meta.msg_type_filter == "group" and ctx.is_private:
        return
    if meta.msg_type_filter == "private" and not ctx.is_private:
        return

    event = ShimAstrMessageEvent(ctx, full_text=full_text or args)
    params = _parse_params(args, meta.param_specs)

    handler = meta.func.__get__(loaded.instance, type(loaded.instance))

    try:
        result = handler(event, **params)
        if inspect.isasyncgen(result):
            async for item in result:
                if item is not None:
                    await _send_result(ctx, item, translate_chain)
                    if getattr(item, "_stop", False):
                        break
        elif inspect.isawaitable(result):
            item = await result
            if item is not None:
                await _send_result(ctx, item, translate_chain)
        # Check if plugin used set_result()
        stashed = getattr(event, "_stashed_result", None)
        if stashed is not None:
            await _send_result(ctx, stashed, translate_chain)
    except Exception:
        logger.exception(
            "astrbot compat: error in handler %s.%s",
            loaded.plugin_dir.name,
            meta.func.__name__,
        )


async def _send_result(ctx: MessageContext, result, translate_fn) -> None:
    components = getattr(result, "components", None)
    if not components:
        return

    elements = translate_fn(components)
    if elements:
        await ctx.send(elements)

    if getattr(result, "_stop", False):
        ctx.stop()


# ── Parameter parsing ─────────────────────────────────────────────────────────


def _parse_params(args: str, param_specs: list) -> dict:
    if not param_specs:
        return {}

    tokens = args.split() if args.strip() else []
    result: dict = {}

    for i, (name, typ) in enumerate(param_specs):
        is_greedy = getattr(typ, "__greedy__", False) or (
            hasattr(typ, "__name__") and typ.__name__ == "GreedyStr"
        )
        if is_greedy:
            result[name] = args.strip()
            break

        if i < len(tokens):
            try:
                result[name] = typ(tokens[i])
            except (ValueError, TypeError):
                result[name] = tokens[i]
        else:
            if typ is str or (hasattr(typ, "__name__") and typ.__name__ == "str"):
                result[name] = ""
            elif typ is int or (hasattr(typ, "__name__") and typ.__name__ == "int"):
                result[name] = 0
            else:
                result[name] = None

    return result
