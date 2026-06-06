"""Plain-text board rendering for the ShinBot minesweeper plugin."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal, Protocol

from .parser import cell_label

GameStatus = Literal["active", "won", "lost", "quit"]


class CellView(Protocol):
    """Minimal cell shape consumed by the renderer."""

    @property
    def has_mine(self) -> bool:
        """Return whether the cell contains a mine."""

    @property
    def adjacent_mines(self) -> int:
        """Return adjacent mine count."""

    @property
    def state(self) -> object:
        """Return the visible cell state or enum-like object."""


class BoardView(Protocol):
    """Minimal board shape consumed by the renderer."""

    @property
    def width(self) -> int:
        """Return board width."""

    @property
    def height(self) -> int:
        """Return board height."""

    @property
    def mine_count(self) -> int:
        """Return total mine count."""

    @property
    def cells(self) -> Sequence[CellView]:
        """Return flat board cells in row-major order."""


@dataclass(frozen=True, slots=True)
class RenderSymbols:
    """Symbols used when rendering a board."""

    hidden: str
    flag: str
    empty: str
    mine: str
    exploded: str


UNICODE_SYMBOLS = RenderSymbols(hidden="■", flag="⚑", empty="·", mine="*", exploded="!")
ASCII_SYMBOLS = RenderSymbols(hidden="#", flag="F", empty=".", mine="*", exploded="X")


@dataclass(frozen=True, slots=True)
class RenderOptions:
    """Rendering options for text board output."""

    ascii: bool = False
    show_coordinates: bool = True
    include_hints: bool = True
    reveal_mines_on_loss: bool = True


@dataclass(frozen=True, slots=True)
class RenderContext:
    """Metadata shown above a board."""

    difficulty: str = "custom"
    status: GameStatus = "active"
    moves: int = 0
    last_action: str | None = None
    exploded_cell: tuple[int, int] | None = None


def render_board(
    board: BoardView,
    *,
    context: RenderContext | None = None,
    options: RenderOptions | None = None,
) -> str:
    """Render a minesweeper board as concise Chinese plain text.

    Args:
        board: Board-like object with width, height, mine_count, and flat cells.
        context: Optional game metadata and last-operation text.
        options: Symbol and hint options.

    Raises:
        ValueError: If the board dimensions do not match the cell list.
    """

    active_context = context or RenderContext()
    active_options = options or RenderOptions()
    symbols = ASCII_SYMBOLS if active_options.ascii else UNICODE_SYMBOLS
    _validate_board(board)

    flag_count = sum(1 for cell in board.cells if _state_value(cell) == "flagged")
    summary = (
        f"扫雷 {active_context.difficulty} {board.width}x{board.height} / "
        f"{board.mine_count} 雷 / 步数 {active_context.moves}"
    )
    lines = [summary, f"标记：{flag_count}/{board.mine_count}"]

    status_line = _status_line(active_context)
    if status_line is not None:
        lines.append(status_line)
    if active_context.last_action:
        lines.append(f"本次：{active_context.last_action}")

    lines.extend(
        _render_grid(
            board,
            symbols=symbols,
            context=active_context,
            show_coordinates=active_options.show_coordinates,
            reveal_mines_on_loss=active_options.reveal_mines_on_loss,
        )
    )

    if active_options.include_hints:
        lines.append("操作：,op a1，,flg b2，,ch c3")
        lines.append("其他：/ms status，/ms restart，/ms quit")

    return "\n".join(lines)


def render_help() -> str:
    """Render concise Chinese help text for `/ms`."""

    return "\n".join(
        [
            "扫雷帮助",
            "/ms start easy|normal|hard",
            "/ms start 12 12 20 或 /ms start 12x12 20",
            ",op a1 b1：打开格子",
            ",flg c3：插旗/取消插旗",
            ",ch d4：连开数字格",
            "/ms status 查看，/ms restart 重开，/ms quit 结束",
        ]
    )


def render_error(message: str) -> str:
    """Render a user-facing error line."""

    return message


def _render_grid(
    board: BoardView,
    *,
    symbols: RenderSymbols,
    context: RenderContext,
    show_coordinates: bool,
    reveal_mines_on_loss: bool,
) -> list[str]:
    column_labels = [cell_label(x, 0)[:-1] for x in range(board.width)]
    row_width = max(2, len(str(board.height)))
    cell_width = max(1, *(len(label) for label in column_labels))
    lines: list[str] = []

    if show_coordinates:
        indent = " " * (row_width + 2)
        header = " ".join(label.rjust(cell_width) for label in column_labels)
        lines.append(f"{indent}{header}")

    reveal_all = context.status == "quit" or (
        context.status == "lost" and reveal_mines_on_loss
    )
    for y in range(board.height):
        rendered_cells = [
            _render_cell(
                board.cells[y * board.width + x],
                x=x,
                y=y,
                symbols=symbols,
                context=context,
                reveal_all=reveal_all,
            )
            .rjust(cell_width)
            for x in range(board.width)
        ]
        row = " ".join(rendered_cells)
        if show_coordinates:
            lines.append(f"{str(y + 1).rjust(row_width)}  {row}")
        else:
            lines.append(row)

    return lines


def _render_cell(
    cell: CellView,
    *,
    x: int,
    y: int,
    symbols: RenderSymbols,
    context: RenderContext,
    reveal_all: bool,
) -> str:
    if context.exploded_cell == (x, y):
        return symbols.exploded

    state = _state_value(cell)
    if state == "flagged" and not reveal_all:
        return symbols.flag
    if state == "hidden" and not reveal_all:
        return symbols.hidden
    if cell.has_mine:
        return symbols.mine
    if cell.adjacent_mines <= 0:
        return symbols.empty
    return str(cell.adjacent_mines)


def _status_line(context: RenderContext) -> str | None:
    if context.status == "won":
        return "胜利：已找出全部安全格。"
    if context.status == "lost":
        if context.exploded_cell is not None:
            return f"踩雷：{cell_label(*context.exploded_cell)}，本局结束。"
        return "踩雷：本局结束。"
    if context.status == "quit":
        return "已结束本局。"
    return None


def _validate_board(board: BoardView) -> None:
    expected = board.width * board.height
    if board.width <= 0 or board.height <= 0:
        raise ValueError("board dimensions must be positive")
    if len(board.cells) != expected:
        raise ValueError(
            f"board cell count mismatch: expected {expected}, got {len(board.cells)}"
        )


def _state_value(cell: CellView) -> str:
    state = cell.state
    value = getattr(state, "value", state)
    return str(value)
