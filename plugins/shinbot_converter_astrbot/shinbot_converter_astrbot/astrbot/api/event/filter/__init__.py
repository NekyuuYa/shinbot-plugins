"""astrbot.api.event.filter — decorator stubs for AstrBot plugins."""

from __future__ import annotations

from astrbot._registry import (
    GreedyStr,  # noqa: F401
    HandlerMeta,
    extract_params,
    pending_handlers,
    pending_stars,  # noqa: F401
)

# ── Enums ─────────────────────────────────────────────────────────────────────


class EventMessageType:
    GROUP_MESSAGE = "group"
    PRIVATE_MESSAGE = "private"
    OTHER_MESSAGE = "other"
    ALL = "all"


class PermissionType:
    ADMIN = "admin"
    MEMBER = "member"
    WHITE_LIST = "whitelist"
    BLACK_LIST = "blacklist"


class PlatformAdapterType:
    TELEGRAM = "telegram"
    ONEBOT = "onebot"
    DISCORD = "discord"
    LARK = "lark"


# ── Command group proxy ───────────────────────────────────────────────────────


class _GroupProxy:
    """Represents a registered command group; supports .command() chaining."""

    def __init__(self, group_path: list[str]):
        self._group_path = group_path

    def __call__(self, func):
        return self

    def command(self, sub_name: str = "", alias: set[str] | None = None):
        names = ([sub_name] if sub_name else []) + list(alias or [])

        def decorator(func):
            pending_handlers.append(
                HandlerMeta(
                    func=func,
                    event_type="command",
                    group_path=list(self._group_path),
                    names=names,
                    description=func.__doc__ or "",
                    param_specs=extract_params(func),
                )
            )
            return func

        return decorator

    def group(self, sub_name: str, alias: set[str] | None = None) -> _GroupProxy:
        new_path = self._group_path + [sub_name] + list(alias or [])
        return _GroupProxy(new_path)

    def custom_filter(self, *args, **kwargs):
        def decorator(func):
            return func

        return decorator


# ── Core decorators ───────────────────────────────────────────────────────────


def command(name: str, alias: set[str] | None = None):
    names = [name] + list(alias or [])

    def decorator(func):
        meta = HandlerMeta(
            func=func,
            event_type="command",
            group_path=[],
            names=names,
            description=func.__doc__ or "",
            param_specs=extract_params(func),
        )
        # Pick up msg_type_filter if set by a decorator applied before @command
        compat_msg_type = getattr(func, "__compat_msg_type__", None)
        if compat_msg_type is not None:
            meta.msg_type_filter = (
                getattr(compat_msg_type, "value", str(compat_msg_type))
                if hasattr(compat_msg_type, "value")
                else str(compat_msg_type)
            )
        # Pick up permission if set by @permission_type before @command
        compat_perm = getattr(func, "__compat_permission__", None)
        if compat_perm is not None:
            meta.permission = compat_perm
        pending_handlers.append(meta)
        return func

    return decorator


def command_group(name: str, alias: set[str] | None = None) -> _GroupProxy:
    group_path = [name] + list(alias or [])
    return _GroupProxy(group_path)


def regex(pattern: str):
    def decorator(func):
        pending_handlers.append(
            HandlerMeta(
                func=func,
                event_type="regex",
                group_path=[],
                names=[pattern],
                description=func.__doc__ or "",
                param_specs=[],
            )
        )
        return func

    return decorator


def event_message_type(msg_type):
    """Filter by message type (GROUP_MESSAGE / PRIVATE_MESSAGE / ALL)."""

    def decorator(func):
        for meta in reversed(pending_handlers):
            if meta.func is func:
                meta.msg_type_filter = (
                    getattr(msg_type, "value", str(msg_type))
                    if hasattr(msg_type, "value")
                    else str(msg_type)
                )
                break
        else:
            func.__compat_msg_type__ = msg_type
        return func

    return decorator


# ── No-op decorators ──────────────────────────────────────────────────────────


def _noop(*args, **kwargs):
    def decorator(func):
        return func

    return decorator


def permission_type(perm):
    """Attach permission requirement to handler for bridge-layer extraction."""

    def decorator(func):
        perm_value = getattr(perm, "value", str(perm))
        func.__compat_permission__ = perm_value
        # Also update the most recently registered handler
        for meta in reversed(pending_handlers):
            if meta.func is func:
                meta.permission = perm_value
                break
        return func

    return decorator
platform_adapter_type = _noop
on_llm_request = _noop
on_llm_response = _noop
on_agent_begin = _noop
on_agent_done = _noop
on_astrbot_loaded = _noop
on_platform_loaded = _noop
on_decorating_result = _noop
after_message_sent = _noop
llm_tool = _noop
on_using_llm_tool = _noop
on_llm_tool_respond = _noop
on_plugin_error = _noop
on_plugin_loaded = _noop
on_plugin_unloaded = _noop
on_waiting_llm_request = _noop
custom_filter = _noop
