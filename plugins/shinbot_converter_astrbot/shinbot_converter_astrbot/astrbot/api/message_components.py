"""astrbot.api.message_components — message component types."""

from __future__ import annotations

import base64
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Plain:
    text: str = ""

    def __init__(self, text: str = "", **kwargs):
        self.text = text


@dataclass
class Image:
    file: str = ""
    url: str = ""
    path: str = ""

    @staticmethod
    def fromURL(url: str) -> Image:
        return Image(url=url)

    @staticmethod
    def fromFileSystem(path: str) -> Image:
        return Image(path=path)

    @staticmethod
    def fromBase64(b64: str) -> Image:
        img = Image()
        img._b64 = b64
        return img

    @staticmethod
    def fromBytes(data: bytes) -> Image:
        b64 = base64.b64encode(data).decode()
        return Image.fromBase64(b64)

    @staticmethod
    def fromIO(io: Any) -> Image:
        data = io.read()
        return Image.fromBytes(data)

    async def convert_to_base64(self) -> str:
        if hasattr(self, "_b64"):
            return self._b64
        return ""

    async def convert_to_file_path(self) -> str:
        return self.path or ""


@dataclass
class At:
    qq: Any = ""
    name: str = ""


@dataclass
class AtAll:
    qq: str = "all"


@dataclass
class Reply:
    id: Any = ""
    chain: Any = None
    sender_id: str = ""
    sender_nickname: str = ""
    message_str: str = ""


@dataclass
class Record:
    file: str = ""
    url: str = ""

    @staticmethod
    def fromURL(url: str) -> Record:
        return Record(url=url)

    @staticmethod
    def fromFileSystem(path: str) -> Record:
        return Record(file=path)


@dataclass
class Video:
    file: str = ""
    cover: str = ""


@dataclass
class File:
    name: str = ""
    file_: str = ""
    url: str = ""

    async def get_file(self) -> bytes:
        return b""


@dataclass
class Node:
    content: list = field(default_factory=list)


@dataclass
class Nodes:
    nodes: list = field(default_factory=list)


@dataclass
class Face:
    id: int = 0


@dataclass
class Share:
    url: str = ""
    title: str = ""
    content: str = ""
    image: str = ""


@dataclass
class Poke:
    _type: str = ""
    id: str = ""
    qq: str = ""


@dataclass
class Json:
    data: dict = field(default_factory=dict)
