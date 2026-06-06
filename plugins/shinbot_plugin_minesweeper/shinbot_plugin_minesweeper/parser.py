"""Command parsing helpers for the ShinBot minesweeper plugin."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

DifficultyName = Literal["easy", "normal", "hard"]
ThemeName = Literal["light", "dark", "classic"]
RootAction = Literal[
    "help",
    "start",
    "restart",
    "open",
    "flag",
    "chord",
    "status",
    "theme",
    "quit",
]
ShortcutAction = Literal["open", "flag", "chord"]
GameSizeKind = Literal["default", "current", "difficulty", "custom"]

DIFFICULTIES: dict[DifficultyName, tuple[int, int, int]] = {
    "easy": (9, 9, 10),
    "normal": (16, 16, 40),
    "hard": (30, 16, 99),
}
THEME_NAMES: tuple[ThemeName, ...] = ("light", "dark", "classic")

DEFAULT_MIN_WIDTH = 5
DEFAULT_MIN_HEIGHT = 5
DEFAULT_MAX_WIDTH = 30
DEFAULT_MAX_HEIGHT = 24
DEFAULT_MIN_MINES = 1
DEFAULT_MAX_MINES = 200

_CELL_PATTERN = re.compile(r"^([A-Za-z]+)([1-9][0-9]*)$")
_SIZE_PATTERN = re.compile(r"^([1-9][0-9]*)x([1-9][0-9]*)$", re.IGNORECASE)
_ACTION_ALIASES: dict[str, RootAction] = {
    "help": "help",
    "h": "help",
    "start": "start",
    "new": "start",
    "open": "open",
    "o": "open",
    "flag": "flag",
    "f": "flag",
    "chord": "chord",
    "c": "chord",
    "status": "status",
    "board": "status",
    "b": "status",
    "theme": "theme",
    "themes": "theme",
    "t": "theme",
    "主题": "theme",
    "restart": "restart",
    "r": "restart",
    "quit": "quit",
    "stop": "quit",
}

_SHORTCUT_ACTIONS: dict[str, ShortcutAction] = {
    "op": "open",
    "flg": "flag",
    "ch": "chord",
}


class ParseError(ValueError):
    """Raised when a minesweeper command cannot be parsed."""


@dataclass(frozen=True, slots=True)
class CellCoord:
    """A parsed zero-based board coordinate."""

    x: int
    y: int
    label: str


@dataclass(frozen=True, slots=True)
class CustomLimits:
    """Bounds used when parsing custom board sizes."""

    min_width: int = DEFAULT_MIN_WIDTH
    min_height: int = DEFAULT_MIN_HEIGHT
    max_width: int = DEFAULT_MAX_WIDTH
    max_height: int = DEFAULT_MAX_HEIGHT
    min_mines: int = DEFAULT_MIN_MINES
    max_mines: int = DEFAULT_MAX_MINES


@dataclass(frozen=True, slots=True)
class GameSize:
    """Parsed start/restart size selection."""

    kind: GameSizeKind
    difficulty: DifficultyName | None = None
    width: int | None = None
    height: int | None = None
    mines: int | None = None


@dataclass(frozen=True, slots=True)
class RootCommand:
    """Parsed `/minesweeper` or `/ms` command arguments."""

    action: RootAction
    cells: tuple[CellCoord, ...] = ()
    size: GameSize | None = None
    theme: ThemeName | None = None


@dataclass(frozen=True, slots=True)
class ShortcutCommand:
    """Parsed shortcut command such as `,op a1 b1`."""

    action: ShortcutAction
    cells: tuple[CellCoord, ...]


def parse_cell(value: str, *, width: int | None = None, height: int | None = None) -> CellCoord:
    """Parse a user-facing cell coordinate into zero-based coordinates.

    Args:
        value: Input coordinate such as `A1`, `a1`, or `AA12`.
        width: Optional board width used for range validation.
        height: Optional board height used for range validation.

    Raises:
        ParseError: If the coordinate is malformed or outside the given bounds.
    """

    raw = value.strip()
    match = _CELL_PATTERN.fullmatch(raw)
    if match is None:
        raise ParseError(f"坐标无效：{value}。示例：A1、C7。")

    column_text, row_text = match.groups()
    x = _column_to_index(column_text)
    y = int(row_text) - 1
    label = f"{_index_to_column(x)}{y + 1}"

    if width is not None and x >= width:
        raise ParseError(f"坐标超出棋盘：{value}。")
    if height is not None and y >= height:
        raise ParseError(f"坐标超出棋盘：{value}。")

    return CellCoord(x=x, y=y, label=label)


def parse_cells(
    values: list[str] | tuple[str, ...],
    *,
    width: int | None = None,
    height: int | None = None,
) -> tuple[CellCoord, ...]:
    """Parse and de-duplicate a list of cell coordinates.

    Args:
        values: Raw coordinate tokens.
        width: Optional board width used for range validation.
        height: Optional board height used for range validation.

    Raises:
        ParseError: If any coordinate is invalid, out of range, or duplicated.
    """

    cells: list[CellCoord] = []
    seen: set[tuple[int, int]] = set()
    for value in values:
        cell = parse_cell(value, width=width, height=height)
        key = (cell.x, cell.y)
        if key in seen:
            raise ParseError(f"重复坐标：{value}。")
        seen.add(key)
        cells.append(cell)
    return tuple(cells)


def parse_root_command(
    args: str,
    *,
    default_difficulty: DifficultyName = "easy",
    limits: CustomLimits | None = None,
    board_width: int | None = None,
    board_height: int | None = None,
) -> RootCommand:
    """Parse raw arguments passed to the root minesweeper command.

    Args:
        args: Raw argument string after ShinBot strips `/minesweeper` or `/ms`.
        default_difficulty: Difficulty used by bare `start`.
        limits: Bounds for custom start/restart sizes.
        board_width: Optional active board width for operation range checks.
        board_height: Optional active board height for operation range checks.

    Raises:
        ParseError: If the command action or arguments are invalid.
    """

    tokens = args.split()
    if not tokens:
        return RootCommand(action="help")

    action_token = tokens[0].lower()
    action = _ACTION_ALIASES.get(action_token)
    if action is None:
        raise ParseError(f"未知扫雷命令：{tokens[0]}。使用 /ms 查看帮助。")

    rest = tokens[1:]
    if action in {"help", "status", "quit"}:
        if rest:
            raise ParseError(f"{tokens[0]} 不需要额外参数。")
        return RootCommand(action=action)

    if action == "theme":
        theme = parse_theme_name(rest)
        return RootCommand(action=action, theme=theme)

    if action == "start":
        size = parse_game_size(
            rest,
            default_difficulty=default_difficulty,
            empty_kind="default",
            limits=limits,
        )
        return RootCommand(action=action, size=size)

    if action == "restart":
        size = parse_game_size(
            rest,
            default_difficulty=default_difficulty,
            empty_kind="current",
            limits=limits,
        )
        return RootCommand(action=action, size=size)

    if not rest:
        usage = {
            "open": "用法：/ms open a1",
            "flag": "用法：/ms flag a1",
            "chord": "用法：/ms chord a1",
        }[action]
        raise ParseError(usage)

    cells = parse_cells(rest, width=board_width, height=board_height)
    return RootCommand(action=action, cells=cells)


def parse_theme_name(tokens: list[str] | tuple[str, ...]) -> ThemeName | None:
    """Parse an optional theme name for `/ms theme`."""

    if not tokens:
        return None
    if len(tokens) != 1:
        raise ParseError("用法：/ms theme light|dark|classic")
    candidate = tokens[0].lower()
    if candidate not in THEME_NAMES:
        choices = "、".join(THEME_NAMES)
        raise ParseError(f"未知主题：{tokens[0]}。可选：{choices}。")
    return candidate


def parse_game_size(
    tokens: list[str] | tuple[str, ...],
    *,
    default_difficulty: DifficultyName = "easy",
    empty_kind: Literal["default", "current"] = "default",
    limits: CustomLimits | None = None,
) -> GameSize:
    """Parse start/restart size selection.

    Args:
        tokens: Size tokens after `start` or `restart`.
        default_difficulty: Difficulty selected by bare `start`.
        empty_kind: Whether empty input means default difficulty or current game.
        limits: Custom board bounds.

    Raises:
        ParseError: If the size form is malformed or outside configured limits.
    """

    active_limits = limits or CustomLimits()
    if not tokens:
        if empty_kind == "current":
            return GameSize(kind="current")
        width, height, mines = DIFFICULTIES[default_difficulty]
        return GameSize(
            kind="default",
            difficulty=default_difficulty,
            width=width,
            height=height,
            mines=mines,
        )

    first = tokens[0].lower()
    if first in DIFFICULTIES:
        if len(tokens) != 1:
            raise ParseError(f"难度 {tokens[0]} 不需要额外参数。")
        difficulty = _as_difficulty(first)
        width, height, mines = DIFFICULTIES[difficulty]
        return GameSize(
            kind="difficulty",
            difficulty=difficulty,
            width=width,
            height=height,
            mines=mines,
        )

    if first == "custom":
        if len(tokens) != 4:
            raise ParseError("用法：/ms start custom 12 12 20")
        width, height, mines = _parse_three_ints(tokens[1:])
        return _custom_size(width, height, mines, limits=active_limits)

    if len(tokens) == 3:
        width, height, mines = _parse_three_ints(tokens)
        return _custom_size(width, height, mines, limits=active_limits)

    if len(tokens) == 2:
        size_match = _SIZE_PATTERN.fullmatch(tokens[0])
        if size_match is not None:
            width = int(size_match.group(1))
            height = int(size_match.group(2))
            mines = _parse_int(tokens[1], "雷数")
            return _custom_size(width, height, mines, limits=active_limits)

    raise ParseError("用法：/ms start easy 或 /ms start 12 12 20")


def parse_shortcut_message(
    text: str,
    *,
    shortcut_prefix: str = ",",
    board_width: int | None = None,
    board_height: int | None = None,
) -> ShortcutCommand | None:
    """Parse a shortcut message.

    Args:
        text: Full message text.
        shortcut_prefix: Prefix expected before `op`, `flg`, or `ch`.
        board_width: Optional active board width for range checks.
        board_height: Optional active board height for range checks.

    Returns:
        The parsed shortcut, or `None` if the message is not a supported shortcut.

    Raises:
        ParseError: If the shortcut is supported but its cell list is invalid.
    """

    match = shortcut_pattern(shortcut_prefix).match(text)
    if match is None:
        return None

    verb, rest = match.groups()
    action = _SHORTCUT_ACTIONS[verb.lower()]
    tokens = rest.split()
    if not tokens:
        example = {
            "open": f"{shortcut_prefix}op a1",
            "flag": f"{shortcut_prefix}flg a1",
            "chord": f"{shortcut_prefix}ch a1",
        }[action]
        raise ParseError(f"用法：{example}")

    cells = parse_cells(tokens, width=board_width, height=board_height)
    return ShortcutCommand(action=action, cells=cells)


def shortcut_pattern(shortcut_prefix: str = ",") -> re.Pattern[str]:
    """Build a regex that matches configured shortcut messages."""

    return re.compile(
        rf"^\s*{re.escape(shortcut_prefix)}\s*(op|flg|ch)\b(.*)$",
        re.IGNORECASE,
    )


def cell_label(x: int, y: int) -> str:
    """Return a user-facing label for zero-based coordinates."""

    if x < 0 or y < 0:
        raise ValueError("coordinates must be non-negative")
    return f"{_index_to_column(x)}{y + 1}"


def _column_to_index(column_text: str) -> int:
    index = 0
    for character in column_text.upper():
        index = index * 26 + (ord(character) - ord("A") + 1)
    return index - 1


def _index_to_column(index: int) -> str:
    if index < 0:
        raise ValueError("column index must be non-negative")

    chars: list[str] = []
    current = index
    while True:
        current, remainder = divmod(current, 26)
        chars.append(chr(ord("A") + remainder))
        if current == 0:
            break
        current -= 1
    return "".join(reversed(chars))


def _as_difficulty(value: str) -> DifficultyName:
    if value not in DIFFICULTIES:
        raise ParseError(f"未知难度：{value}。")
    return value


def _parse_three_ints(tokens: list[str] | tuple[str, ...]) -> tuple[int, int, int]:
    return (
        _parse_int(tokens[0], "宽度"),
        _parse_int(tokens[1], "高度"),
        _parse_int(tokens[2], "雷数"),
    )


def _parse_int(value: str, label: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise ParseError(f"{label}必须是整数：{value}。") from exc
    return parsed


def _custom_size(width: int, height: int, mines: int, *, limits: CustomLimits) -> GameSize:
    if not limits.min_width <= width <= limits.max_width:
        raise ParseError(f"宽度超出范围：{width}。允许 {limits.min_width}..{limits.max_width}。")
    if not limits.min_height <= height <= limits.max_height:
        raise ParseError(f"高度超出范围：{height}。允许 {limits.min_height}..{limits.max_height}。")
    if not limits.min_mines <= mines <= limits.max_mines:
        raise ParseError(f"雷数超出范围：{mines}。允许 {limits.min_mines}..{limits.max_mines}。")
    if mines >= width * height:
        raise ParseError("雷数必须小于格子总数。")
    if width > 3 and height > 3 and mines > width * height - 9:
        raise ParseError("雷数太多，无法保证首开安全。")
    return GameSize(kind="custom", width=width, height=height, mines=mines)
