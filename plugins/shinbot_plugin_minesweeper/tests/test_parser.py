from __future__ import annotations

import pytest

from shinbot_plugin_minesweeper.parser import (
    CustomLimits,
    GameSize,
    ParseError,
    RootCommand,
    ShortcutCommand,
    cell_label,
    parse_cell,
    parse_game_size,
    parse_root_command,
    parse_shortcut_message,
)


def test_parse_empty_root_command_as_help() -> None:
    assert parse_root_command("") == RootCommand(action="help")
    assert parse_root_command("   ") == RootCommand(action="help")


def test_parse_root_operation_aliases_with_multi_cells() -> None:
    command = parse_root_command("o a1 AA12", board_width=27, board_height=12)

    assert command.action == "open"
    assert [(cell.x, cell.y, cell.label) for cell in command.cells] == [
        (0, 0, "A1"),
        (26, 11, "AA12"),
    ]


def test_parse_start_named_and_empty_default() -> None:
    assert parse_root_command("start").size == GameSize(
        kind="default",
        difficulty="easy",
        width=9,
        height=9,
        mines=10,
    )
    assert parse_root_command("start hard").size == GameSize(
        kind="difficulty",
        difficulty="hard",
        width=30,
        height=16,
        mines=99,
    )


def test_parse_restart_empty_reuses_current() -> None:
    assert parse_root_command("restart").size == GameSize(kind="current")


def test_parse_theme_command() -> None:
    assert parse_root_command("theme") == RootCommand(action="theme")
    assert parse_root_command("theme dark") == RootCommand(
        action="theme",
        theme="dark",
    )
    assert parse_root_command("主题 classic") == RootCommand(
        action="theme",
        theme="classic",
    )

    with pytest.raises(ParseError, match="未知主题"):
        parse_root_command("theme neon")

    with pytest.raises(ParseError, match="用法：/ms theme"):
        parse_root_command("theme dark light")


@pytest.mark.parametrize(
    ("args", "expected"),
    [
        ("custom 12 12 20", GameSize(kind="custom", width=12, height=12, mines=20)),
        ("12 12 20", GameSize(kind="custom", width=12, height=12, mines=20)),
        ("12x12 20", GameSize(kind="custom", width=12, height=12, mines=20)),
        ("12X12 20", GameSize(kind="custom", width=12, height=12, mines=20)),
    ],
)
def test_parse_custom_size_forms(args: str, expected: GameSize) -> None:
    assert parse_game_size(args.split()) == expected


def test_custom_limits_are_enforced() -> None:
    limits = CustomLimits(max_width=10, max_height=10, max_mines=20)

    with pytest.raises(ParseError, match="宽度超出范围"):
        parse_game_size("11 10 20".split(), limits=limits)

    with pytest.raises(ParseError, match="雷数太多"):
        parse_game_size("5 5 17".split(), limits=limits)


def test_parse_cell_is_case_insensitive_and_validates_bounds() -> None:
    assert parse_cell("aa12", width=27, height=12).label == "AA12"
    assert cell_label(26, 11) == "AA12"

    with pytest.raises(ParseError, match="坐标超出棋盘"):
        parse_cell("j1", width=9, height=9)


def test_parse_duplicate_cells_rejected_after_normalization() -> None:
    with pytest.raises(ParseError, match="重复坐标"):
        parse_root_command("open a1 A1", board_width=9, board_height=9)


def test_parse_comma_shortcuts_with_multi_cells() -> None:
    assert parse_shortcut_message("hello") is None

    command = parse_shortcut_message("  ,OP a1 b2 AA12", board_width=27, board_height=12)

    assert command == ShortcutCommand(
        action="open",
        cells=(
            parse_cell("a1", width=27, height=12),
            parse_cell("b2", width=27, height=12),
            parse_cell("aa12", width=27, height=12),
        ),
    )


def test_parse_configured_shortcut_prefix() -> None:
    assert parse_shortcut_message(",op a1", shortcut_prefix=".") is None

    command = parse_shortcut_message(".OP a1", shortcut_prefix=".")

    assert command == ShortcutCommand(action="open", cells=(parse_cell("a1"),))

    with pytest.raises(ParseError, match=r"用法：\.flg a1"):
        parse_shortcut_message(".flg", shortcut_prefix=".")


def test_parse_shortcut_missing_cells_reports_usage() -> None:
    with pytest.raises(ParseError, match="用法：,flg a1"):
        parse_shortcut_message(",flg")
