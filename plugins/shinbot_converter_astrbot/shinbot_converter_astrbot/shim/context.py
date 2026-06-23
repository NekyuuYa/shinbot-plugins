"""ShimContext — the core shim that maps AstrBot Context API to ShinBot Plugin capabilities."""

from __future__ import annotations

import base64
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from shinbot.core.plugins.context import Plugin

    from .config import ShimAstrBotConfig
    from .kv import ShimKVStore

logger = logging.getLogger(__name__)


# ── Unsupported stub ──────────────────────────────────────────────────────────


class _Unsupported:
    """Placeholder for context attributes not available in compat mode.

    Silently no-ops on attribute access and calls so plugins that merely
    import but don't invoke unsupported APIs won't crash.
    """

    def __init__(self, path: str):
        self._path = path

    def __call__(self, *args, **kwargs):
        logger.debug("astrbot compat: unsupported context.%s() called", self._path)
        return None

    def __getattr__(self, name: str) -> _Unsupported:
        return _Unsupported(f"{self._path}.{name}")

    def __bool__(self) -> bool:
        return False


# ── Shim cron manager ─────────────────────────────────────────────────────────


class _ShimCronManager:
    """Wraps PluginCronManager so auto_scheduler can access .scheduler directly."""

    def __init__(self, cron_manager: Any):
        self._cron_manager = cron_manager

    @property
    def scheduler(self):
        """Expose the raw APScheduler scheduler for direct add_job/remove_job."""
        if self._cron_manager is None:
            return None
        # Ensure the scheduler is lazily started
        self._cron_manager._ensure_scheduler()
        return self._cron_manager._scheduler


# ── Shim platform manager ─────────────────────────────────────────────────────


class _ShimPlatformManager:
    """Wraps AdapterManager to provide platform_manager.get_insts()."""

    def __init__(self, adapter_manager: Any):
        self._adapter_manager = adapter_manager

    def get_insts(self) -> list:
        """Return adapter instances wrapped in shim objects."""
        if self._adapter_manager is None:
            return []
        instances = []
        for inst_id, adapter in self._adapter_manager._instances.items():
            instances.append(_ShimPlatformInstance(inst_id, adapter))
        return instances


class _ShimPlatformInstance:
    """Wraps a ShinBot adapter to present AstrBot's platform instance interface."""

    def __init__(self, instance_id: str, adapter: Any):
        self._id = instance_id
        self._adapter = adapter

    @property
    def metadata(self):
        return _ShimPlatformMetadata(self._id)

    @property
    def meta(self):
        return self.metadata

    def get_client(self):
        return self._adapter


class _ShimPlatformMetadata:
    def __init__(self, instance_id: str):
        self.id = instance_id
        self.name = "onebot"
        self.type = "onebot"


# ── Shim message history manager ──────────────────────────────────────────────


class _ShimMessageHistoryManager:
    """Stub for context.message_history_manager.

    Currently returns empty results — the plugin's core analysis uses
    bot.call_action("get_group_msg_history") directly, not this manager.
    """

    def __init__(self, database: Any):
        self._db = database

    async def insert(self, *args, **kwargs) -> None:
        pass  # no-op: message logging handled by ShinBot's message_logs

    async def get_messages(self, *args, **kwargs) -> list:
        return []  # no-op: plugin fetches via OneBot API


# ── ShimContext ───────────────────────────────────────────────────────────────


class ShimContext:
    """Maps AstrBot Context API calls to ShinBot Plugin capabilities.

    This is the bridge between AstrBot plugins and ShinBot's runtime.
    Every method/property that an AstrBot plugin accesses on `self.context`
    routes through here.
    """

    def __init__(
        self,
        plg: Plugin,
        config: ShimAstrBotConfig,
        kv_store: ShimKVStore,
        plugin_dir: Path,
    ):
        self._plg = plg
        self._config = config
        self._kv_store = kv_store
        self._plugin_dir = plugin_dir

    # ── Config ────────────────────────────────────────────────────────

    def get_config(self, umo: Any = None) -> dict:
        return dict(self._config)

    # ── LLM generation ────────────────────────────────────────────────

    async def llm_generate(self, **kwargs) -> Any:
        """Bridge to plg.llm_call().

        Maps AstrBot's llm_generate kwargs to plg.llm_call parameters.
        """
        from astrbot.api.provider import LLMResponse

        prompt = kwargs.get("prompt", "")
        system_prompt = kwargs.get("system_prompt")
        provider_id = kwargs.get("chat_provider_id")
        response_format = kwargs.get("response_format")

        # Extract extra params
        temperature = kwargs.get("temperature")
        max_tokens = kwargs.get("max_tokens")

        try:
            result = await self._plg.llm_call(
                prompt=prompt,
                system_prompt=system_prompt,
                model_id=provider_id,
                response_format=response_format,
                temperature=temperature,
                max_tokens=max_tokens,
                purpose=f"astrbot_compat.{self._plg.plugin_id}",
            )

            return LLMResponse(
                role="assistant",
                completion_text=result.text,
                usage=_ShimUsage(result.usage),
                raw_completion=result.raw_response,
            )
        except Exception as e:
            logger.error("ShimContext.llm_generate failed: %s", e)
            return None

    # ── Provider management ────────────────────────────────────────────

    def get_provider_by_id(self, provider_id: str = "", **kwargs) -> Any:
        """Return a ShimProvider wrapping the provider definition dict."""
        from .provider import ShimProvider

        pid = provider_id or kwargs.get("provider_id", "")
        if not pid:
            return None
        data = self._plg.get_provider(pid)
        if data is None:
            return None
        return ShimProvider(data)

    def get_all_providers(self) -> list:
        """Return all configured providers as ShimProvider objects."""
        from .provider import ShimProvider

        return [ShimProvider(p) for p in self._plg.list_providers()]

    async def get_current_chat_provider_id(self, umo: str | None = None) -> str | None:
        """Get the provider ID for the current chat session.

        Falls back to the plugin's configured llm_provider_id.
        """
        llm_config = self._config.get("llm", {})
        return llm_config.get("llm_provider_id") or None

    # ── Cron scheduling ───────────────────────────────────────────────

    @property
    def cron_manager(self):
        """Expose the cron manager for direct scheduler access."""
        return _ShimCronManager(self._plg._cron_manager)

    # ── Platform management ───────────────────────────────────────────

    @property
    def platform_manager(self):
        """Expose adapter instances as AstrBot platform instances."""
        return _ShimPlatformManager(self._plg._adapter_manager)

    # ── Persona (degraded) ────────────────────────────────────────────

    @property
    def persona_manager(self):
        """Not available — persona injection is degraded."""
        return None

    @property
    def conversation_manager(self):
        """Not available — conversation management is degraded."""
        return None

    @property
    def message_history_manager(self):
        """Stub message history manager."""
        return _ShimMessageHistoryManager(self._plg.database)

    # ── Other context attributes ──────────────────────────────────────

    @property
    def provider_manager(self) -> _Unsupported:
        return _Unsupported("provider_manager")

    @property
    def kb_manager(self) -> _Unsupported:
        return _Unsupported("kb_manager")

    def get_using_provider(self, *args, **kwargs) -> None:
        return None

    def get_platform_inst(self, *args, **kwargs) -> None:
        return None

    def get_all_stars(self) -> list:
        return []

    def add_llm_tools(self, *args, **kwargs) -> None:
        pass

    def get_llm_tool_manager(self) -> _Unsupported:
        return _Unsupported("llm_tool_manager")

    def get_db(self) -> _Unsupported:
        return _Unsupported("db")

    def register_web_api(self, *args, **kwargs) -> None:
        logger.debug("astrbot compat: register_web_api() not supported")

    # ── HTML rendering ────────────────────────────────────────────────

    async def html_render(self, html: str, **kwargs) -> str:
        """Render HTML to base64 image using renderkit (optional dependency)."""
        try:
            from shinbot_plugin_renderkit.api import render_html_to_bytes
        except ImportError as err:
            raise RuntimeError(
                "shinbot_plugin_renderkit is required for HTML-to-image rendering. "
                "Install it or set output_format to 'text'."
            ) from err

        image_bytes = await render_html_to_bytes(html)
        return f"base64://{base64.b64encode(image_bytes).decode()}"

    # ── Proactive messaging ───────────────────────────────────────────

    async def send_message(self, session_id: str, chain: Any) -> None:
        """Send a message proactively (outside a command context)."""
        from ..translator import translate_chain

        components = _extract_components(chain)
        elements = translate_chain(components)
        if elements:
            await self._plg.send_to(session_id, elements)


# ── Usage shim ────────────────────────────────────────────────────────────────


class _ShimUsage:
    """Wraps a usage dict to expose .input, .output, .total properties (AstrBot TokenUsage)."""

    def __init__(self, usage: dict[str, Any]):
        self._usage = usage or {}

    @property
    def input(self) -> int:
        return self._usage.get("prompt_tokens", 0)

    @property
    def output(self) -> int:
        return self._usage.get("completion_tokens", 0)

    @property
    def total(self) -> int:
        return self._usage.get("total_tokens", 0)


# ── Helpers ───────────────────────────────────────────────────────────────────


def _extract_components(chain: Any) -> list:
    if isinstance(chain, list):
        return chain
    if hasattr(chain, "components"):
        return chain.components
    return [chain]
