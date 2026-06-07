from __future__ import annotations

from dataclasses import dataclass
from typing import cast

from shinbot_plugin_minesweeper.renderer import (
    DARK_THEME,
    LIGHT_THEME,
    THEMES,
    RenderContext,
    RenderOptions,
    get_theme,
    render_board,
    render_board_svg,
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


def test_render_svg_returns_template_data() -> None:
    board = FakeBoard(
        width=2,
        height=1,
        mine_count=1,
        cells=[FakeCell(state="flagged"), FakeCell(adjacent_mines=1, state="revealed")],
    )

    svg = render_board_svg(
        board,
        context=RenderContext(difficulty="easy", moves=2, last_action="标记 a1"),
    )

    assert svg.template == "board.svg.j2"
    assert svg.template_dirs[0].name == "templates"
    assert svg.width > 0
    assert svg.height > 0
    assert svg.data["title"] == "Minesweeper easy 2x1 / mines 1 / moves 2"
    assert "last: flag a1" in str(svg.data["subtitle"])
    cells = cast(list[dict[str, object]], svg.data["cells"])
    assert len(cells) == 2


def test_render_svg_uses_ascii_only_text() -> None:
    board = FakeBoard(
        width=2,
        height=1,
        mine_count=1,
        cells=[FakeCell(state="flagged"), FakeCell(has_mine=True, state="hidden")],
    )

    svg = render_board_svg(
        board,
        context=RenderContext(
            difficulty="easy",
            status="lost",
            moves=2,
            last_action="踩雷 b1",
            exploded_cell=(1, 0),
        ),
    )

    visible_text = " ".join(
        [
            str(svg.data["title"]),
            str(svg.data["subtitle"]),
            " ".join(
                str(cell["text"])
                for cell in cast(list[dict[str, object]], svg.data["cells"])
            ),
        ]
    )

    assert visible_text.isascii()
    assert "lost: B1" in visible_text
    assert "last: mine b1" in visible_text


def test_render_help_mentions_empty_ms_usage() -> None:
    rendered = render_help()

    assert "扫雷帮助" in rendered
    assert "/ms start easy|normal|hard" in rendered
    assert ",op a1 b1" in rendered


def test_render_board_uses_configured_shortcut_prefix_in_hints() -> None:
    board = FakeBoard(width=1, height=1, mine_count=0, cells=[FakeCell()])

    rendered = render_board(board, options=RenderOptions(shortcut_prefix="."))

    assert "操作：.op a1，.flg b2，.ch c3" in rendered


def test_theme_registry_and_fallback() -> None:
    assert set(THEMES) == {"light", "dark", "classic"}
    assert get_theme(None) is LIGHT_THEME
    assert get_theme("DARK") is DARK_THEME
    assert get_theme("does-not-exist") is LIGHT_THEME


def test_render_svg_defaults_to_light_theme() -> None:
    board = FakeBoard(
        width=1,
        height=1,
        mine_count=0,
        cells=[FakeCell(state="hidden")],
    )

    svg = render_board_svg(board)

    assert svg.data["background"] == LIGHT_THEME.background
    cells = cast(list[dict[str, object]], svg.data["cells"])
    assert cells[0]["fill"] == LIGHT_THEME.hidden.fill
    assert cells[0]["radius"] == 2
    assert cells[0]["stroke_width"] == 0.75


def test_render_svg_expands_width_for_header_text() -> None:
    board = FakeBoard(
        width=1,
        height=1,
        mine_count=0,
        cells=[FakeCell(state="hidden")],
    )

    svg = render_board_svg(
        board,
        context=RenderContext(
            difficulty="custom-super-long-name",
            moves=123,
            last_action="打开 a1 b1 c1 d1 e1 f1",
        ),
    )

    assert svg.width > 500
    assert str(svg.data["title"]).isascii()
    assert str(svg.data["subtitle"]).isascii()


def test_render_svg_applies_dark_theme() -> None:
    board = FakeBoard(
        width=2,
        height=1,
        mine_count=0,
        cells=[FakeCell(state="hidden"), FakeCell(adjacent_mines=1, state="revealed")],
    )

    svg = render_board_svg(board, theme=DARK_THEME)

    assert svg.data["background"] == DARK_THEME.background
    assert svg.data["title_fill"] == DARK_THEME.title_fill
    cells = cast(list[dict[str, object]], svg.data["cells"])
    assert cells[0]["fill"] == DARK_THEME.hidden.fill
    assert cells[1]["text_fill"] == DARK_THEME.number_color(1)


def test_render_svg_classic_theme_uses_square_cells() -> None:
    board = FakeBoard(
        width=1,
        height=1,
        mine_count=0,
        cells=[FakeCell(state="hidden")],
    )

    svg = render_board_svg(board, theme=THEMES["classic"])

    cells = cast(list[dict[str, object]], svg.data["cells"])
    assert cells[0]["radius"] == 0
    assert cells[0]["stroke_width"] == 0.75
