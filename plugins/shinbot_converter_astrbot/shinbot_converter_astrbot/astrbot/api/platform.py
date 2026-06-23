"""astrbot.api.platform — platform-related types."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class MessageType(StrEnum):
    GROUP_MESSAGE = "group"
    FRIEND_MESSAGE = "private"
    OTHER_MESSAGE = "other"


@dataclass
class MessageMember:
    user_id: str = ""
    nickname: str = ""


@dataclass
class Group:
    id: str = ""
    name: str = ""


@dataclass
class PlatformMetadata:
    name: str = ""
    id: str = ""
