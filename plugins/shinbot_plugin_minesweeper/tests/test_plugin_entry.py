"""Tests for minesweeper plugin command wiring helpers."""

from __future__ import annotations

import pytest

from shinbot_plugin_minesweeper import (
    MinesweeperPluginConfig,
    _handle_root_command,
    _handle_shortcut,
)
from shinbot_plugin_minesweeper.models import GameState
from shinbot_plugin_minesweeper.store import GameStore, MemoryGameStore


class _Handle:
    def __init__(self, message_id: str) -> None:
        self.message_id = message_id


class _Logger:
    def debug(self, *_args: object) -> None:
        pass


class _Ctx:
    def __init__(self, *, text: str = "", session_id: str = "s1") -> None:
        self.text = text
        self.session_id = session_id
        self.user_id = "u1"
        self.sent: list[str] = []
        self.deleted: list[str] = []

    async def send(self, content: str) -> _Handle:
        self.sent.append(content)
        return _Handle(f"m{len(self.sent)}")

    async def delete_msg(self, message_id: str) -> None:
        self.deleted.append(message_id)


def _store() -> GameStore[GameState]:
    return MemoryGameStore(updated_at=lambda game: game.updated_at)


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
