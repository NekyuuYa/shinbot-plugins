"""Convert AstrBot _conf_schema.json to dynamic Pydantic BaseModel classes.

This module reads an AstrBot plugin's ``_conf_schema.json`` file and generates
a Pydantic ``BaseModel`` subclass whose fields correspond to the schema groups
and items.  The resulting model can be set as ``__plugin_config_class__`` on a
virtual plugin module so that ShinBot's WebUI renders an editable config form.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, create_model


def convert_schema_to_pydantic(
    schema_path: Path,
    plugin_id: str,
) -> type[BaseModel]:
    """Convert an AstrBot ``_conf_schema.json`` to a Pydantic model class.

    Each top-level group in the schema becomes a nested BaseModel field.
    Each item within a group becomes a typed field on the group model.

    Args:
        schema_path: Path to the ``_conf_schema.json`` file.
        plugin_id:   Plugin identifier (used for the model class name).

    Returns:
        A Pydantic BaseModel subclass ready to be used as
        ``__plugin_config_class__``.
    """
    schema = json.loads(schema_path.read_text(encoding="utf-8"))

    group_models: dict[str, type[BaseModel]] = {}

    for group_key, group_def in schema.items():
        if not isinstance(group_def, dict):
            continue
        if group_def.get("type") != "object":
            continue

        items = group_def.get("items", {})
        if not items:
            continue

        fields: dict[str, Any] = {}
        annotations: dict[str, type] = {}

        for item_key, item_def in items.items():
            if not isinstance(item_def, dict):
                continue
            py_type, field_obj = _convert_field(group_key, item_def)
            annotations[item_key] = py_type
            fields[item_key] = field_obj

        # Build the group model dynamically
        namespace = {"__annotations__": annotations}
        namespace.update(fields)
        group_model = create_model(
            f"{_pascal_case(group_key)}GroupConfig",
            **{k: (t, fields[k]) for k, t in annotations.items()},
        )
        group_models[group_key] = group_model

    # Build the top-level config model
    top_fields: dict[str, Any] = {}
    for group_key, group_model in group_models.items():
        group_desc = schema.get(group_key, {}).get("description", group_key)
        top_fields[group_key] = (
            group_model,
            Field(default_factory=group_model, description=group_desc),
        )

    plugin_name = _pascal_case(plugin_id)
    ConfigModel = create_model(
        f"{plugin_name}Config",
        **top_fields,
    )

    return ConfigModel


# ── Field type conversion ─────────────────────────────────────────────────


def _convert_field(group_key: str, item_def: dict[str, Any]) -> tuple[type, Any]:
    """Convert a single AstrBot field definition to (py_type, Field).

    Args:
        group_key: The group name (used for ui_group metadata).
        item_def:  The field definition dict from ``_conf_schema.json``.

    Returns:
        A tuple of (Python type, Pydantic Field instance).
    """
    astrbot_type = item_def.get("type", "string")
    options = item_def.get("options")
    default = item_def.get("default")
    description = item_def.get("description", "")
    hint = item_def.get("hint", "")
    slider = item_def.get("slider")
    special = item_def.get("_special", "")
    editor_mode = item_def.get("editor_mode", False)

    # Build json_schema_extra
    extra: dict[str, Any] = {"ui_group": group_key}
    if hint:
        extra["hint"] = hint
    if slider and isinstance(slider, dict):
        extra["x-slider"] = slider
    if special:
        extra["x-special"] = special
    if editor_mode:
        extra["x-ui-component"] = "code_editor"

    # Determine Python type and default
    if options and isinstance(options, list):
        # Enum field — use Literal
        literal_type = Literal[tuple(options)]  # type: ignore[valid-type]
        py_type: type = literal_type
        field_default = default if default in options else options[0]
        return py_type, Field(
            default=field_default,
            description=description,
            json_schema_extra=extra,
        )

    match astrbot_type:
        case "string" | "text":
            py_type = str
            field_default = default if isinstance(default, str) else ""

        case "int":
            py_type = int
            field_default = default if isinstance(default, int) else 0
            if slider and isinstance(slider, dict):
                extra["minimum"] = slider.get("min")
                extra["maximum"] = slider.get("max")

        case "float":
            py_type = float
            field_default = default if isinstance(default, (int, float)) else 0.0
            if slider and isinstance(slider, dict):
                extra["minimum"] = slider.get("min")
                extra["maximum"] = slider.get("max")

        case "bool":
            py_type = bool
            field_default = default if isinstance(default, bool) else False

        case "list":
            py_type = list[str]  # type: ignore[assignment]
            field_default = default if isinstance(default, list) else []

        case _:
            py_type = str
            field_default = default if isinstance(default, str) else ""

    return py_type, Field(
        default=field_default,
        description=description,
        json_schema_extra=extra,
    )


# ── Helpers ────────────────────────────────────────────────────────────────


_PASCAL_RE = re.compile(r"[^a-zA-Z0-9]+")


def _pascal_case(s: str) -> str:
    """Convert a snake_case or kebab-case string to PascalCase."""
    parts = _PASCAL_RE.split(s)
    return "".join(p.capitalize() for p in parts if p)
