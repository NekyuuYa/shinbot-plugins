"""ShimAstrMessageEvent — wraps ShinBot MessageContext to present AstrBot's event API."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from shinbot.core.dispatch.message_context import MessageContext


class _MessageObj:
    """Approximates AstrBotMessage."""
    def __init__(self, ctx: MessageContext):
        from astrbot.api.platform import MessageMember, MessageType
        self.sender = MessageMember(
            user_id=ctx.user_id or "",
            nickname=str(getattr(ctx.event, "sender_name", "") or ""),
        )
        self.message_id = ctx.event.message.id if ctx.event.message else ""
        self.type = MessageType.FRIEND_MESSAGE if ctx.is_private else MessageType.GROUP_MESSAGE
        self.session_id = ctx.session_id
        self.self_id = ctx.event.self_id
        self.message: list = []


class ShimAstrMessageEvent:
    """AstrMessageEvent substitute backed by a ShinBot MessageContext."""

    def __init__(self, ctx: MessageContext, full_text: str = ""):
        self._ctx = ctx
        self.message_str = full_text or ctx.text
        self.message_obj = _MessageObj(ctx)
        self.is_wake: bool = True
        self.is_at_or_wake_command: bool = True
        self._extras: dict[str, Any] = {}

    def get_message_str(self) -> str:
        return self.message_str

    def get_messages(self) -> list:
        return self.message_obj.message

    def get_message_type(self):
        return self.message_obj.type

    def get_sender_id(self) -> str:
        return self.message_obj.sender.user_id

    def get_sender_name(self) -> str:
        return self.message_obj.sender.nickname

    def get_group_id(self) -> str:
        return self._ctx.event.channel_id or ""

    def get_self_id(self) -> str:
        return self._ctx.event.self_id or ""

    def get_platform_name(self) -> str:
        return self._ctx.platform

    def get_platform_id(self) -> str:
        return self._ctx.adapter.instance_id if self._ctx.adapter else ""

    def is_private_chat(self) -> bool:
        return self._ctx.is_private

    def is_admin(self) -> bool:
        return self._ctx.has_permission("admin")

    @property
    def role(self) -> str:
        return "admin" if self.is_admin() else "member"

    @property
    def unified_msg_origin(self) -> str:
        return self._ctx.session_id

    @property
    def session(self):
        return self._ctx.session_id

    @property
    def platform_meta(self):
        instance_id = self._ctx.adapter.instance_id if self._ctx.adapter else ""
        return _PlatformMeta(self._ctx.platform, instance_id)

    def set_extra(self, key: str, value) -> None:
        self._extras[key] = value

    def get_extra(self, key: str):
        return self._extras.get(key)

    def stop_event(self) -> None:
        self._ctx.stop()

    def continue_event(self) -> None:
        pass

    def plain_result(self, text: str):
        from astrbot.api.event import MessageEventResult
        r = MessageEventResult()
        r.message(text)
        return r

    def image_result(self, url_or_path: str):
        from astrbot.api.event import MessageEventResult
        r = MessageEventResult()
        if url_or_path.startswith("http"):
            r.url_image(url_or_path)
        else:
            r.file_image(url_or_path)
        return r

    def chain_result(self, chain: list):
        from astrbot.api.event import MessageEventResult
        r = MessageEventResult()
        r.components = list(chain)
        return r

    def make_result(self):
        from astrbot.api.event import MessageEventResult
        return MessageEventResult()

    def set_result(self, result) -> None:
        self._stashed_result = result

    async def send(self, chain) -> None:
        from ..translator import translate_chain
        components = _extract_components(chain)
        elements = translate_chain(components)
        if elements:
            await self._ctx.send(elements)

    async def react(self, emoji: str) -> None:
        pass

    def should_call_llm(self, value: bool) -> None:
        pass  # no-op: ShinBot commands don't go through agent by default

    def request_llm(self, *args, **kwargs):
        return None


class _PlatformMeta:
    def __init__(self, name: str, id: str):
        self.name = name
        self.id = id


def _extract_components(chain) -> list:
    if isinstance(chain, list):
        return chain
    if hasattr(chain, "components"):
        return chain.components
    return [chain]
