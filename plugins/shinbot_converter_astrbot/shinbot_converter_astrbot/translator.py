"""translator.py — converts AstrBot message components to ShinBot MessageElements."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from shinbot.schema.elements import MessageElement


def translate_chain(components: list) -> list[MessageElement]:
    """Translate a list of AstrBot components into ShinBot MessageElements."""

    result: list[MessageElement] = []
    for comp in components:
        el = _translate_one(comp)
        if el is not None:
            result.append(el)
    return result


def _translate_one(comp) -> MessageElement | None:
    from shinbot.schema.elements import MessageElement

    type_name = type(comp).__name__

    match type_name:
        case "Plain":
            text = getattr(comp, "text", "") or ""
            if not text:
                return None
            return MessageElement.text(text)

        case "Image":
            src = _image_src(comp)
            if not src:
                return None
            return MessageElement.img(src)

        case "At":
            qq = str(getattr(comp, "qq", "") or "")
            name = getattr(comp, "name", None)
            if qq in ("all", "everyone"):
                return MessageElement.at(type="all")
            return MessageElement.at(id=qq or None, name=name or None)

        case "AtAll":
            return MessageElement.at(type="all")

        case "Reply":
            msg_id = str(getattr(comp, "id", "") or "")
            if not msg_id:
                return None
            return MessageElement.quote(msg_id)

        case "Record":
            src = getattr(comp, "url", "") or getattr(comp, "file", "") or ""
            if not src:
                return None
            return MessageElement.audio(src)

        case "Video":
            src = getattr(comp, "file", "") or ""
            if not src:
                return None
            return MessageElement.video(src)

        case "File":
            src = (
                getattr(comp, "url", "")
                or getattr(comp, "file_", "")
                or getattr(comp, "file", "")
                or ""
            )
            name = getattr(comp, "name", None)
            if not src:
                return None
            kwargs = {}
            if name:
                kwargs["name"] = name
            return MessageElement.file(src, **kwargs)

        case "Face":
            face_id = str(getattr(comp, "id", "") or "")
            return MessageElement.emoji(id=face_id)

        case _:
            return None


def _image_src(comp) -> str:
    url = getattr(comp, "url", "") or ""
    path = getattr(comp, "path", "") or ""
    b64 = getattr(comp, "_b64", "") or ""

    if url:
        return url
    if path:
        return f"file://{path}"
    if b64:
        return f"data:image/png;base64,{b64}"
    file_val = getattr(comp, "file", "") or ""
    if file_val.startswith("http"):
        return file_val
    if file_val:
        return f"file://{file_val}"
    return ""
