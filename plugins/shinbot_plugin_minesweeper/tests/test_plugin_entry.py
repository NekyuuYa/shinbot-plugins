"""Tests for minesweeper plugin command wiring helpers."""

from __future__ import annotations

import sys
import types
from pathlib import Path
from typing import Any

import pytest

from shinbot_plugin_minesweeper import (
    MinesweeperPluginConfig,
    __plugin_locales__,
    _handle_root_command,
    _handle_shortcut,
)
from shinbot_plugin_minesweeper.models import GameState
from shinbot_plugin_minesweeper.renderer import DARK_THEME
from shinbot_plugin_minesweeper.store import GameStore, MemoryGameStore


class _Handle:
    def __init__(self, message_id: str) -> None:
        self.message_id = message_id


class _Logger:
    def __init__(self) -> None:
        self.debug_messages: list[tuple[object, ...]] = []

    def debug(self, *_args: object) -> None:
        self.debug_messages.append(_args)


class _Ctx:
    def __init__(
        self,
        *,
        text: str = "",
        session_id: str = "s1",
        fail_image_send: bool = False,
    ) -> None:
        self.text = text
        self.session_id = session_id
        self.user_id = "u1"
        self.sent: list[Any] = []
        self.deleted: list[str] = []
        self.fail_image_send = fail_image_send

    async def send(self, content: Any) -> _Handle:
        if self.fail_image_send and _is_image_content(content):
            self.fail_image_send = False
            raise RuntimeError("image upload failed")
        self.sent.append(content)
        return _Handle(f"m{len(self.sent)}")

    async def delete_msg(self, message_id: str) -> None:
        self.deleted.append(message_id)


def _store() -> GameStore[GameState]:
    return MemoryGameStore(updated_at=lambda game: game.updated_at)


def _is_image_content(content: Any) -> bool:
    return isinstance(content, list) and any(
        isinstance(item, dict) and item.get("type") == "img" for item in content
    )


def _install_fake_image_modules(
    monkeypatch: pytest.MonkeyPatch,
    *,
    available: bool = True,
    fail_render: bool = False,
) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []
    shinbot_module = types.ModuleType("shinbot")
    schema_module = types.ModuleType("shinbot.schema")
    elements_module = types.ModuleType("shinbot.schema.elements")

    class MessageElement:
        @classmethod
        def img(cls, src: str, **kwargs: Any) -> dict[str, Any]:
            return {"type": "img", "attrs": {"src": src, **kwargs}}

    elements_module.__dict__["MessageElement"] = MessageElement

    renderkit_module = types.ModuleType("shinbot_plugin_renderkit")

    class Capabilities:
        svg = available

    class SvgRenderOptions:
        def __init__(self, **kwargs: Any) -> None:
            self.kwargs = kwargs

    async def render_svg_template_to_file(*args: Any, **kwargs: Any) -> Any:
        calls.append({"args": args, **kwargs})
        if fail_render:
            raise RuntimeError("render failed")

        class Result:
            path = Path("/tmp/minesweeper.png")
            width = 320
            height = 180

        return Result()

    renderkit_module.__dict__["SvgRenderOptions"] = SvgRenderOptions
    renderkit_module.__dict__["probe_renderkit_capabilities"] = lambda: Capabilities()
    renderkit_module.__dict__["render_svg_template_to_file"] = render_svg_template_to_file

    monkeypatch.setitem(sys.modules, "shinbot", shinbot_module)
    monkeypatch.setitem(sys.modules, "shinbot.schema", schema_module)
    monkeypatch.setitem(sys.modules, "shinbot.schema.elements", elements_module)
    monkeypatch.setitem(sys.modules, "shinbot_plugin_renderkit", renderkit_module)
    return calls


def test_plugin_locales_cover_config_schema() -> None:
    zh = __plugin_locales__["zh-CN"]
    en = __plugin_locales__["en-US"]

    for field_name in MinesweeperPluginConfig.model_fields:
        assert f"config.fields.{field_name}.label" in zh
        assert f"config.fields.{field_name}.label" in en
        assert f"config.fields.{field_name}.description" in zh
        assert f"config.fields.{field_name}.description" in en

    assert zh["config.title"] == "扫雷设置"
    assert zh["config.fields.shortcut_prefix.label"] == "快捷指令前缀"
    assert zh["config.fields.theme.options.dark"] == "深色"
    assert en["config.fields.render_mode.options.image"] == "Image"


@pytest.mark.asyncio
async def test_empty_root_command_returns_help() -> None:
    ctx = _Ctx()

    await _handle_root_command(
        ctx,
        "",
        store=_store(),
        config=MinesweeperPluginConfig(persist_games=False),
        logger=_Logger(),
    )

    assert "扫雷帮助" in ctx.sent[-1]


@pytest.mark.asyncio
async def test_start_and_shortcut_batch_updates_board() -> None:
    ctx = _Ctx()
    store = _store()
    config = MinesweeperPluginConfig(
        persist_games=False,
        recall_old_boards=False,
    )

    await _handle_root_command(ctx, "start easy", store=store, config=config, logger=_Logger())
    ctx.text = ",op a1 b1"
    await _handle_shortcut(ctx, store=store, config=config, logger=_Logger())

    assert "扫雷 easy 9x9" in ctx.sent[-1]
    assert "本次：打开 a1 b1" in ctx.sent[-1]
    assert store.load(ctx.session_id) is not None


@pytest.mark.asyncio
async def test_configured_shortcut_prefix_updates_board() -> None:
    ctx = _Ctx()
    store = _store()
    config = MinesweeperPluginConfig(
        persist_games=False,
        recall_old_boards=False,
        shortcut_prefix=".",
    )

    await _handle_root_command(ctx, "start easy", store=store, config=config, logger=_Logger())
    ctx.text = ",op a1"
    await _handle_shortcut(ctx, store=store, config=config, logger=_Logger())
    ctx.text = ".op a1"
    await _handle_shortcut(ctx, store=store, config=config, logger=_Logger())

    assert "本次：打开 a1" in ctx.sent[-1]
    assert "操作：.op a1，.flg b2，.ch c3" in ctx.sent[-1]


@pytest.mark.asyncio
async def test_image_render_mode_sends_renderkit_image(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = _install_fake_image_modules(monkeypatch)
    ctx = _Ctx()
    store = _store()
    config = MinesweeperPluginConfig(
        persist_games=False,
        recall_old_boards=False,
        render_mode="auto",
    )

    await _handle_root_command(
        ctx,
        "start easy",
        store=store,
        config=config,
        logger=_Logger(),
        render_dir=tmp_path,
    )

    sent = ctx.sent[-1]
    assert isinstance(sent, list)
    assert sent[0]["type"] == "img"
    assert sent[0]["attrs"]["src"] == "/tmp/minesweeper.png"
    assert calls[0]["args"][0] == "board.svg.j2"
    assert calls[0]["data"]["title"].startswith("扫雷 easy")
    assert calls[0]["output_dir"] == tmp_path
    assert calls[0]["template_dirs"][0].name == "templates"


@pytest.mark.asyncio
async def test_theme_command_updates_game_theme_and_rerenders_image(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = _install_fake_image_modules(monkeypatch)
    ctx = _Ctx()
    store = _store()
    config = MinesweeperPluginConfig(
        persist_games=False,
        recall_old_boards=False,
        render_mode="auto",
        theme="light",
    )

    await _handle_root_command(
        ctx,
        "start easy",
        store=store,
        config=config,
        logger=_Logger(),
        render_dir=tmp_path,
    )
    await _handle_root_command(
        ctx,
        "theme dark",
        store=store,
        config=config,
        logger=_Logger(),
        render_dir=tmp_path,
    )

    game = store.load(ctx.session_id)
    assert game is not None
    assert game.theme == "dark"
    assert "已切换扫雷主题：dark" in ctx.sent[-2]
    assert calls[-1]["data"]["background"] == DARK_THEME.background


@pytest.mark.asyncio
async def test_theme_status_reports_current_theme() -> None:
    ctx = _Ctx()

    await _handle_root_command(
        ctx,
        "theme",
        store=_store(),
        config=MinesweeperPluginConfig(persist_games=False, theme="classic"),
        logger=_Logger(),
    )

    assert "当前扫雷主题：classic" in ctx.sent[-1]
    assert "light、dark、classic" in ctx.sent[-1]


@pytest.mark.asyncio
async def test_image_render_mode_falls_back_to_text_when_renderkit_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fake_image_modules(monkeypatch, fail_render=True)
    ctx = _Ctx()
    store = _store()
    config = MinesweeperPluginConfig(
        persist_games=False,
        recall_old_boards=False,
        render_mode="auto",
    )

    await _handle_root_command(
        ctx,
        "start easy",
        store=store,
        config=config,
        logger=_Logger(),
        render_dir=tmp_path,
    )

    assert isinstance(ctx.sent[-1], str)
    assert "扫雷 easy 9x9" in ctx.sent[-1]


@pytest.mark.asyncio
async def test_image_render_mode_falls_back_to_text_when_image_send_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fake_image_modules(monkeypatch)
    ctx = _Ctx(fail_image_send=True)
    store = _store()
    logger = _Logger()
    config = MinesweeperPluginConfig(
        persist_games=False,
        recall_old_boards=False,
        render_mode="auto",
    )

    await _handle_root_command(
        ctx,
        "start easy",
        store=store,
        config=config,
        logger=logger,
        render_dir=tmp_path,
    )

    game = store.load(ctx.session_id)
    assert game is not None
    assert isinstance(ctx.sent[-1], str)
    assert "扫雷 easy 9x9" in ctx.sent[-1]
    assert game.board_message_ids == ["m1"]
    assert logger.debug_messages


@pytest.mark.asyncio
async def test_board_retention_recalls_old_board_messages() -> None:
    ctx = _Ctx()
    store = _store()
    config = MinesweeperPluginConfig(
        persist_games=False,
        recall_old_boards=True,
        keep_recent_board_messages=1,
    )

    await _handle_root_command(ctx, "start easy", store=store, config=config, logger=_Logger())
    ctx.text = ",op a1"
    await _handle_shortcut(ctx, store=store, config=config, logger=_Logger())

    assert ctx.deleted == ["m1"]


@pytest.mark.asyncio
async def test_status_does_not_update_board_retention() -> None:
    ctx = _Ctx()
    store = _store()
    config = MinesweeperPluginConfig(
        persist_games=False,
        recall_old_boards=True,
        keep_recent_board_messages=1,
    )

    await _handle_root_command(ctx, "start easy", store=store, config=config, logger=_Logger())
    game = store.load(ctx.session_id)
    assert game is not None
    before_ids = list(game.board_message_ids)

    await _handle_root_command(ctx, "status", store=store, config=config, logger=_Logger())

    after = store.load(ctx.session_id)
    assert after is not None
    assert after.board_message_ids == before_ids
    assert ctx.deleted == []


@pytest.mark.asyncio
async def test_restart_reuses_named_difficulty_when_custom_is_disabled() -> None:
    ctx = _Ctx()
    store = _store()
    config = MinesweeperPluginConfig(
        persist_games=False,
        allow_custom=False,
        recall_old_boards=False,
    )

    await _handle_root_command(ctx, "start easy", store=store, config=config, logger=_Logger())
    await _handle_root_command(ctx, "restart", store=store, config=config, logger=_Logger())

    game = store.load(ctx.session_id)
    assert game is not None
    assert game.difficulty == "easy"
    assert game.board.width == 9
    assert "当前配置不允许自定义棋盘" not in ctx.sent[-1]


@pytest.mark.asyncio
async def test_restart_current_revalidates_persisted_custom_size_limits() -> None:
    ctx = _Ctx()
    store = _store()
    config = MinesweeperPluginConfig(
        persist_games=False,
        max_width=30,
        recall_old_boards=False,
    )

    await _handle_root_command(ctx, "start 30 5 10", store=store, config=config, logger=_Logger())
    game = store.load(ctx.session_id)
    assert game is not None
    game.difficulty = "custom"
    game.board.width = 31

    await _handle_root_command(ctx, "restart", store=store, config=config, logger=_Logger())

    assert "宽度必须在 5-30 之间" in ctx.sent[-1]
