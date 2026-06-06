from __future__ import annotations

from dataclasses import dataclass

from shinbot_plugin_minesweeper.renderer import (
    RenderContext,
    RenderOptions,
    render_board,
    render_help,
)


@dataclass(slots=True)
class FakeCell:
    has_mine: bool = False
    adjacent_mines: int = 0
    state: str = "hidden"


@dataclass(slots=True)
class FakeBoard:
    width: int
    height: int
    mine_count: int
    cells: list[FakeCell]


def test_render_unicode_board() -> None:
    board = FakeBoard(
        width=3,
        height=2,
        mine_count=1,
        cells=[
            FakeCell(state="revealed"),
            FakeCell(adjacent_mines=1, state="revealed"),
            FakeCell(state="hidden"),
            FakeCell(state="flagged"),
            FakeCell(state="hidden"),
            FakeCell(has_mine=True, state="hidden"),
        ],
    )

    rendered = render_board(
        board,
        context=RenderContext(difficulty="easy", moves=3, last_action="打开 a1 b1"),
    )

    assert "扫雷 easy 3x2 / 1 雷 / 步数 3" in rendered
    assert "标记：1/1" in rendered
    assert "本次：打开 a1 b1" in rendered
    assert "    A B C" in rendered
    assert "1  · 1 ■" in rendered
    assert "2  ⚑ ■ ■" in rendered
    assert "操作：,op a1，,flg b2，,ch c3" in rendered


def test_render_ascii_fallback_and_loss_reveals_mines() -> None:
    board = FakeBoard(
        width=2,
        height=2,
        mine_count=1,
        cells=[
            FakeCell(state="revealed"),
            FakeCell(has_mine=True, state="hidden"),
            FakeCell(adjacent_mines=1, state="revealed"),
            FakeCell(state="flagged"),
        ],
    )

    rendered = render_board(
        board,
        context=RenderContext(status="lost", moves=2, exploded_cell=(1, 0)),
        options=RenderOptions(ascii=True),
    )

    assert "踩雷：B1，本局结束。" in rendered
    assert "1  . X" in rendered
    assert "2  1 ." in rendered
    assert "#" not in rendered


def test_loss_can_hide_non_exploded_mines() -> None:
    board = FakeBoard(
        width=2,
        height=2,
        mine_count=1,
        cells=[
            FakeCell(state="revealed"),
            FakeCell(has_mine=True, state="hidden"),
            FakeCell(adjacent_mines=1, state="revealed"),
            FakeCell(state="hidden"),
        ],
    )

    rendered = render_board(
        board,
        context=RenderContext(status="lost", moves=2, exploded_cell=(1, 0)),
        options=RenderOptions(ascii=True, reveal_mines_on_loss=False),
    )

    assert "1  . X" in rendered
    assert "2  1 #" in rendered


def test_render_without_coordinates_or_hints() -> None:
    board = FakeBoard(
        width=2,
        height=1,
        mine_count=1,
        cells=[FakeCell(), FakeCell(adjacent_mines=1, state="revealed")],
    )

    rendered = render_board(
        board,
        options=RenderOptions(show_coordinates=False, include_hints=False),
    )

    assert rendered.splitlines()[-1] == "■ 1"
    assert "操作：" not in rendered
    assert "A B" not in rendered


def test_render_help_mentions_empty_ms_usage() -> None:
    rendered = render_help()

    assert "扫雷帮助" in rendered
    assert "/ms start easy|normal|hard" in rendered
    assert ",op a1 b1" in rendered
