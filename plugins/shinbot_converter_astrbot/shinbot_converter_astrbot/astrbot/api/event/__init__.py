"""astrbot.api.event — AstrMessageEvent and filter namespace."""

from __future__ import annotations

import astrbot.api.event.filter as filter  # noqa: F401
from astrbot.api.event.filter import (  # noqa: F401
    EventMessageType,
    PermissionType,
    PlatformAdapterType,
    command,
    command_group,
    custom_filter,
    event_message_type,
    permission_type,
    regex,
)


class MessageChain:
    """Builder for message component chains."""

    def __init__(self):
        self.components: list = []
        self._stop = False

    def message(self, text: str) -> MessageChain:
        from astrbot.api.message_components import Plain

        self.components.append(Plain(text=text))
        return self

    def url_image(self, url: str) -> MessageChain:
        from astrbot.api.message_components import Image

        self.components.append(Image.fromURL(url))
        return self

    def file_image(self, path: str) -> MessageChain:
        from astrbot.api.message_components import Image

        self.components.append(Image.fromFileSystem(path))
        return self

    def base64_image(self, b64: str) -> MessageChain:
        from astrbot.api.message_components import Image

        self.components.append(Image.fromBase64(b64))
        return self

    def at(self, name: str = "", qq: str = "") -> MessageChain:
        from astrbot.api.message_components import At

        self.components.append(At(qq=qq, name=name))
        return self

    def at_all(self) -> MessageChain:
        from astrbot.api.message_components import AtAll

        self.components.append(AtAll())
        return self

    def use_t2i(self, enabled: bool) -> MessageChain:
        return self  # no-op

    def stop_event(self) -> MessageChain:
        self._stop = True
        return self

    def continue_event(self) -> MessageChain:
        self._stop = False
        return self

    def get_plain_text(self, with_other_comps_mark: bool = False) -> str:
        from astrbot.api.message_components import Plain

        parts = [c.text for c in self.components if isinstance(c, Plain)]
        return "".join(parts)


class MessageEventResult(MessageChain):
    """Result of a handler — a MessageChain with stop/continue semantics."""


CommandResult = MessageEventResult


class AstrMessageEvent:
    """Stub — actual instances are ShimAstrMessageEvent from shim/event.py."""
