"""ShinBot plugin: general-purpose HTML/CSS and SVG image rendering."""

from __future__ import annotations

import sys
import tomllib
from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field, ValidationError

from .api import (
    close_default_backend,
    close_default_svg_backend,
    configure_default_backend,
    configure_default_svg_backend,
    render_html_to_bytes,
    render_html_to_file,
    render_svg_template_to_bytes,
    render_svg_template_to_file,
    render_svg_to_bytes,
    render_svg_to_file,
    render_template_to_bytes,
    render_template_to_file,
)
from .backends import CairoSvgRenderBackend, PlaywrightRenderBackend
from .models import ImageFormat, RenderOptions, RenderResult, SvgRenderOptions
from .template import render_template_text

if TYPE_CHECKING:
    from shinbot.core.plugins.context import Plugin

__plugin_name__ = "RenderKit"
__plugin_description__ = "General-purpose HTML/CSS and SVG template rendering for ShinBot plugins."


class RenderKitPluginConfig(BaseModel):
    """Configuration for RenderKit."""

    default_width: int = Field(default=800, ge=1, le=4096)
    default_height: int = Field(default=480, ge=1, le=4096)
    default_device_scale_factor: float = Field(default=1.0, gt=0, le=4)
    default_timeout_ms: int = Field(default=30_000, ge=1000, le=120_000)
    max_concurrency: int = Field(default=2, ge=1, le=16)
    chromium_executable_path: str | None = None
    cache_files: bool = True
    tool_enabled: bool = True


__plugin_config_class__ = RenderKitPluginConfig


def setup(plg: Plugin) -> None:
    """Register optional RenderKit tool integrations."""
    config = _load_plugin_config(plg.plugin_id)
    configure_default_backend(
        PlaywrightRenderBackend(
            executable_path=config.chromium_executable_path,
            max_concurrency=config.max_concurrency,
        )
    )
    configure_default_svg_backend(CairoSvgRenderBackend(max_concurrency=config.max_concurrency))
    if not config.tool_enabled:
        plg.logger.info("RenderKit plugin loaded without tool registration")
        return

    try:
        _register_render_tool(plg, config)
    except RuntimeError:
        plg.logger.info("RenderKit plugin loaded as Python API only")
        return

    plg.logger.info("RenderKit plugin loaded")


async def on_disable(_plg: Plugin) -> None:
    """Close RenderKit browser resources when the plugin is disabled."""
    await close_default_backend()
    await close_default_svg_backend()


def _register_render_tool(
    plg: Plugin,
    config: RenderKitPluginConfig,
    *,
    public_visibility: Any | None = None,
) -> None:
    if public_visibility is None:
        try:
            from shinbot.core.tools import ToolVisibility
        except ImportError as exc:
            raise RuntimeError("ShinBot ToolRegistry types are not available.") from exc
        public_visibility = ToolVisibility.PUBLIC

    @plg.tool(
        name="render_html_image",
        display_name="Render HTML Image",
        description="Render a standard HTML/CSS document or fragment to an image file.",
        input_schema={
            "type": "object",
            "properties": {
                "html": {"type": "string"},
                "width": {"type": "integer", "minimum": 1, "maximum": 4096},
                "height": {"type": "integer", "minimum": 1, "maximum": 4096},
                "format": {"type": "string", "enum": ["png", "jpeg"]},
            },
            "required": ["html"],
            "additionalProperties": False,
        },
        output_schema={
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "mime_type": {"type": "string"},
                "width": {"type": "integer"},
                "height": {"type": "integer"},
                "cached": {"type": "boolean"},
            },
            "required": ["path", "mime_type", "width", "height", "cached"],
            "additionalProperties": False,
        },
        visibility=public_visibility,
        timeout_seconds=120.0,
        tags=["render", "html", "image"],
    )
    async def render_html_image(
        html: str,
        width: int | None = None,
        height: int | None = None,
        format: str = "png",
    ) -> dict[str, object]:
        options = RenderOptions(
            width=width if width is not None else config.default_width,
            height=height if height is not None else config.default_height,
            image_format=_image_format(format),
            device_scale_factor=config.default_device_scale_factor,
            timeout_ms=config.default_timeout_ms,
        )
        result = await render_html_to_file(
            html,
            output_dir=Path(plg.data_dir) / "renders",
            options=options,
            cache=config.cache_files,
        )
        return result.to_dict()

    @plg.tool(
        name="render_svg_image",
        display_name="Render SVG Image",
        description="Render a standard SVG document or fragment to a PNG image file.",
        input_schema={
            "type": "object",
            "properties": {
                "svg": {"type": "string"},
                "width": {"type": "integer", "minimum": 1, "maximum": 4096},
                "height": {"type": "integer", "minimum": 1, "maximum": 4096},
                "scale": {"type": "number", "exclusiveMinimum": 0, "maximum": 4},
                "background_color": {"type": "string"},
            },
            "required": ["svg"],
            "additionalProperties": False,
        },
        output_schema={
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "mime_type": {"type": "string"},
                "width": {"type": "integer"},
                "height": {"type": "integer"},
                "cached": {"type": "boolean"},
            },
            "required": ["path", "mime_type", "width", "height", "cached"],
            "additionalProperties": False,
        },
        visibility=public_visibility,
        timeout_seconds=120.0,
        tags=["render", "svg", "image"],
    )
    async def render_svg_image(
        svg: str,
        width: int | None = None,
        height: int | None = None,
        scale: float = 1.0,
        background_color: str | None = None,
    ) -> dict[str, object]:
        options = SvgRenderOptions(
            width=width if width is not None else config.default_width,
            height=height if height is not None else config.default_height,
            scale=scale,
            timeout_ms=config.default_timeout_ms,
            background_color=background_color,
        )
        result = await render_svg_to_file(
            svg,
            output_dir=Path(plg.data_dir) / "renders",
            options=options,
            cache=config.cache_files,
        )
        return result.to_dict()


def _image_format(value: str) -> ImageFormat:
    formats: dict[str, ImageFormat] = {"png": "png", "jpeg": "jpeg"}
    image_format = formats.get(value)
    if image_format is None:
        raise ValueError("format must be 'png' or 'jpeg'.")
    return image_format


def _resolve_config_path(argv: Sequence[str] | None = None) -> Path:
    from shinbot.core.application.paths import DEFAULT_CONFIG_PATH

    args = list(sys.argv[1:] if argv is None else argv)
    for index, value in enumerate(args):
        if value == "--config" and index + 1 < len(args):
            return Path(args[index + 1])
        if value.startswith("--config="):
            return Path(value.split("=", 1)[1])
    return DEFAULT_CONFIG_PATH


def _load_plugin_config(plugin_id: str) -> RenderKitPluginConfig:
    from shinbot.core.plugins.config import plugin_config_block

    path = _resolve_config_path()
    raw: dict[str, Any] = {}
    try:
        if path.exists():
            with path.open("rb") as file_obj:
                payload = tomllib.load(file_obj)
            raw = plugin_config_block(payload, plugin_id)
    except Exception:
        raw = {}
    try:
        return RenderKitPluginConfig.model_validate(raw)
    except ValidationError:
        return RenderKitPluginConfig()


__all__ = [
    "RenderKitPluginConfig",
    "RenderOptions",
    "RenderResult",
    "SvgRenderOptions",
    "close_default_backend",
    "close_default_svg_backend",
    "configure_default_backend",
    "configure_default_svg_backend",
    "render_html_to_bytes",
    "render_html_to_file",
    "render_svg_template_to_bytes",
    "render_svg_template_to_file",
    "render_svg_to_bytes",
    "render_svg_to_file",
    "render_template_text",
    "render_template_to_bytes",
    "render_template_to_file",
]
