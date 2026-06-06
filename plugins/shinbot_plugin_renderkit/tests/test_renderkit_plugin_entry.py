"""Tests for RenderKit plugin setup helpers."""

from __future__ import annotations

import sys
import types
from pathlib import Path
from typing import Any

import pytest

import shinbot_plugin_renderkit
from shinbot_plugin_renderkit import (
    RenderKitPluginConfig,
    _load_plugin_config,
    _register_render_tool,
)


class _Logger:
    def info(self, *_args: object) -> None:
        pass


class _FakePlugin:
    def __init__(self, data_dir: Path) -> None:
        self.plugin_id = "shinbot_plugin_renderkit"
        self.data_dir = data_dir
        self.logger = _Logger()
        self.tools: list[dict[str, Any]] = []

    def tool(self, **kwargs: Any) -> Any:
        self.tools.append(kwargs)

        def decorator(func: Any) -> Any:
            self.tools[-1]["handler"] = func
            return func

        return decorator


def test_register_render_tool_declares_public_html_tool(tmp_path: Path) -> None:
    plugin = _FakePlugin(tmp_path)

    _register_render_tool(plugin, RenderKitPluginConfig(), public_visibility="public")

    assert plugin.tools[0]["name"] == "render_html_image"
    assert "html" in plugin.tools[0]["tags"]
    assert plugin.tools[0]["input_schema"]["required"] == ["html"]
    assert plugin.tools[1]["name"] == "render_svg_image"
    assert "svg" in plugin.tools[1]["tags"]
    assert plugin.tools[1]["input_schema"]["required"] == ["svg"]
    assert plugin.tools[2]["name"] == "render_typst_image"
    assert "typst" in plugin.tools[2]["tags"]
    assert plugin.tools[2]["input_schema"]["required"] == ["source"]


@pytest.mark.asyncio
async def test_render_tool_rejects_invalid_format(tmp_path: Path) -> None:
    plugin = _FakePlugin(tmp_path)

    _register_render_tool(plugin, RenderKitPluginConfig(), public_visibility="public")
    handler = plugin.tools[0]["handler"]

    with pytest.raises(ValueError, match="format"):
        await handler("<main>Hello</main>", format="webp")


@pytest.mark.asyncio
async def test_render_tool_rejects_zero_dimensions(tmp_path: Path) -> None:
    plugin = _FakePlugin(tmp_path)

    _register_render_tool(plugin, RenderKitPluginConfig(), public_visibility="public")
    handler = plugin.tools[0]["handler"]

    with pytest.raises(ValueError, match="width"):
        await handler("<main>Hello</main>", width=0)
    with pytest.raises(ValueError, match="height"):
        await handler("<main>Hello</main>", height=0)


@pytest.mark.asyncio
async def test_svg_render_tool_rejects_zero_dimensions(tmp_path: Path) -> None:
    plugin = _FakePlugin(tmp_path)

    _register_render_tool(plugin, RenderKitPluginConfig(), public_visibility="public")
    handler = plugin.tools[1]["handler"]

    with pytest.raises(ValueError, match="width"):
        await handler("<svg />", width=0)
    with pytest.raises(ValueError, match="height"):
        await handler("<svg />", height=0)


@pytest.mark.asyncio
async def test_svg_render_tool_rejects_zero_scale(tmp_path: Path) -> None:
    plugin = _FakePlugin(tmp_path)

    _register_render_tool(plugin, RenderKitPluginConfig(), public_visibility="public")
    handler = plugin.tools[1]["handler"]

    with pytest.raises(ValueError, match="scale"):
        await handler("<svg />", scale=0)


@pytest.mark.asyncio
async def test_typst_render_tool_rejects_invalid_page_and_ppi(tmp_path: Path) -> None:
    plugin = _FakePlugin(tmp_path)

    _register_render_tool(plugin, RenderKitPluginConfig(), public_visibility="public")
    handler = plugin.tools[2]["handler"]

    with pytest.raises(ValueError, match="page"):
        await handler("Hello", page=0)
    with pytest.raises(ValueError, match="PPI"):
        await handler("Hello", ppi=0)
    with pytest.raises(ValueError, match="PPI"):
        await handler("Hello", ppi=1201)


@pytest.mark.asyncio
async def test_typst_render_tool_uses_restricted_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plugin = _FakePlugin(tmp_path)
    calls: list[dict[str, Any]] = []

    async def fake_render_typst_to_file(*_args: Any, **kwargs: Any) -> Any:
        calls.append(kwargs)

        class Result:
            def to_dict(self) -> dict[str, object]:
                return {
                    "path": str(tmp_path / "renders" / "typst.png"),
                    "mime_type": "image/png",
                    "width": 100,
                    "height": 50,
                    "cached": False,
                }

        return Result()

    monkeypatch.setattr(shinbot_plugin_renderkit, "render_typst_to_file", fake_render_typst_to_file)
    _register_render_tool(plugin, RenderKitPluginConfig(), public_visibility="public")
    handler = plugin.tools[2]["handler"]

    result = await handler("Hello")

    options = calls[0]["options"]
    assert result["mime_type"] == "image/png"
    assert options.root == tmp_path / "typst-root"
    assert options.root.is_dir()


def test_load_plugin_config_reads_shinbot_config_block(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        """
[[plugins]]
id = "shinbot_plugin_renderkit"
enabled = true

[plugins.config]
default_width = 1024
default_height = 768
max_concurrency = 4
tool_enabled = false
""",
        encoding="utf-8",
    )
    _install_fake_shinbot_modules(config_path, monkeypatch)
    monkeypatch.setattr(sys, "argv", ["main.py", "--config", str(config_path)])

    config = _load_plugin_config("shinbot_plugin_renderkit")

    assert config.default_width == 1024
    assert config.default_height == 768
    assert config.max_concurrency == 4
    assert config.tool_enabled is False


def _install_fake_shinbot_modules(
    config_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    shinbot_module = types.ModuleType("shinbot")
    core_module = types.ModuleType("shinbot.core")
    application_module = types.ModuleType("shinbot.core.application")
    paths_module = types.ModuleType("shinbot.core.application.paths")
    paths_module.__dict__["DEFAULT_CONFIG_PATH"] = config_path
    plugins_module = types.ModuleType("shinbot.core.plugins")
    config_module = types.ModuleType("shinbot.core.plugins.config")

    def plugin_config_block(payload: dict[str, Any], plugin_id: str) -> dict[str, Any]:
        for item in payload.get("plugins", []):
            if isinstance(item, dict) and item.get("id") == plugin_id:
                config = item.get("config", {})
                return dict(config) if isinstance(config, dict) else {}
        return {}

    config_module.__dict__["plugin_config_block"] = plugin_config_block
    modules = {
        "shinbot": shinbot_module,
        "shinbot.core": core_module,
        "shinbot.core.application": application_module,
        "shinbot.core.application.paths": paths_module,
        "shinbot.core.plugins": plugins_module,
        "shinbot.core.plugins.config": config_module,
    }
    for name, module in modules.items():
        monkeypatch.setitem(sys.modules, name, module)
