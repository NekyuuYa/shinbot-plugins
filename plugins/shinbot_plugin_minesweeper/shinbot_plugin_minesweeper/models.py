"""Pure data models for the ShinBot minesweeper plugin."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Literal, cast

GameStatus = Literal["active", "won", "lost", "quit"]


class CellState(Enum):
    """Visible state of a minesweeper cell."""

    HIDDEN = "hidden"
    REVEALED = "revealed"
    FLAGGED = "flagged"


@dataclass(slots=True)
class Cell:
    """A single minesweeper board cell."""

    has_mine: bool = False
    adjacent_mines: int = 0
    state: CellState = CellState.HIDDEN
    exploded: bool = False

    def to_dict(self) -> dict[str, object]:
        """Serialize the cell into JSON-compatible data."""
        return {
            "has_mine": self.has_mine,
            "adjacent_mines": self.adjacent_mines,
            "state": self.state.value,
            "exploded": self.exploded,
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> Cell:
        """Deserialize a cell from JSON-compatible data."""
        return cls(
            has_mine=bool(data.get("has_mine", False)),
            adjacent_mines=_int_value(data.get("adjacent_mines", 0)),
            state=CellState(str(data.get("state", CellState.HIDDEN.value))),
            exploded=bool(data.get("exploded", False)),
        )


@dataclass(frozen=True, slots=True)
class Position:
    """Zero-based board coordinate."""

    x: int
    y: int

    def to_dict(self) -> dict[str, int]:
        """Serialize the position into JSON-compatible data."""
        return {"x": self.x, "y": self.y}

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> Position:
        """Deserialize a position from JSON-compatible data."""
        return cls(x=_int_value(data["x"]), y=_int_value(data["y"]))


@dataclass(slots=True)
class Board:
    """A minesweeper board with delayed mine placement support."""

    width: int
    height: int
    mine_count: int
    cells: list[Cell] = field(default_factory=list)
    mine_seeded: bool = False

    def __post_init__(self) -> None:
        """Initialize empty cells and validate board dimensions."""
        if self.width <= 0:
            raise ValueError("Board width must be positive.")
        if self.height <= 0:
            raise ValueError("Board height must be positive.")
        if self.mine_count < 0:
            raise ValueError("Mine count must not be negative.")
        if self.mine_count >= self.width * self.height:
            raise ValueError("Mine count must be less than cell count.")
        if not self.cells:
            self.cells = [Cell() for _ in range(self.width * self.height)]
        if len(self.cells) != self.width * self.height:
            raise ValueError("Cell count must equal width * height.")

    def index(self, position: Position) -> int:
        """Return the flat cell index for a position."""
        self.require_in_bounds(position)
        return position.y * self.width + position.x

    def cell_at(self, position: Position) -> Cell:
        """Return the cell at a position."""
        return self.cells[self.index(position)]

    def in_bounds(self, position: Position) -> bool:
        """Return whether a position is inside the board."""
        return 0 <= position.x < self.width and 0 <= position.y < self.height

    def require_in_bounds(self, position: Position) -> None:
        """Raise ValueError if a position is outside the board."""
        if not self.in_bounds(position):
            raise ValueError(f"Position out of bounds: ({position.x}, {position.y}).")

    def positions(self) -> list[Position]:
        """Return all board positions in row-major order."""
        return [
            Position(x=x, y=y)
            for y in range(self.height)
            for x in range(self.width)
        ]

    def neighbors(self, position: Position) -> list[Position]:
        """Return all valid neighboring positions around a cell."""
        self.require_in_bounds(position)
        result: list[Position] = []
        for y_offset in (-1, 0, 1):
            for x_offset in (-1, 0, 1):
                if x_offset == 0 and y_offset == 0:
                    continue
                neighbor = Position(position.x + x_offset, position.y + y_offset)
                if self.in_bounds(neighbor):
                    result.append(neighbor)
        return result

    def revealed_count(self) -> int:
        """Return the number of revealed cells."""
        return sum(1 for cell in self.cells if cell.state is CellState.REVEALED)

    def flagged_count(self) -> int:
        """Return the number of flagged cells."""
        return sum(1 for cell in self.cells if cell.state is CellState.FLAGGED)

    def hidden_safe_count(self) -> int:
        """Return hidden non-mine cells that still need to be revealed."""
        return sum(
            1
            for cell in self.cells
            if not cell.has_mine and cell.state is not CellState.REVEALED
        )

    def reset_mines(self) -> None:
        """Remove all mines and adjacent counts from the board."""
        for cell in self.cells:
            cell.has_mine = False
            cell.adjacent_mines = 0
            cell.exploded = False
        self.mine_seeded = False

    def to_dict(self) -> dict[str, object]:
        """Serialize the board into JSON-compatible data."""
        return {
            "width": self.width,
            "height": self.height,
            "mine_count": self.mine_count,
            "cells": [cell.to_dict() for cell in self.cells],
            "mine_seeded": self.mine_seeded,
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> Board:
        """Deserialize a board from JSON-compatible data."""
        raw_cells = data.get("cells", [])
        if not isinstance(raw_cells, list):
            raise ValueError("Board cells must be a list.")
        return cls(
            width=_int_value(data["width"]),
            height=_int_value(data["height"]),
            mine_count=_int_value(data["mine_count"]),
            cells=[
                Cell.from_dict(cell)
                for cell in raw_cells
                if isinstance(cell, dict)
            ],
            mine_seeded=bool(data.get("mine_seeded", False)),
        )


@dataclass(slots=True)
class GameState:
    """Serializable state for one minesweeper game."""

    session_id: str
    board: Board
    status: GameStatus
    difficulty: str
    started_at: float
    updated_at: float
    moves: int = 0
    owner_user_id: str | None = None
    board_message_ids: list[str] = field(default_factory=list)
    last_action: str = ""
    theme: str | None = None

    def is_active(self) -> bool:
        """Return whether the game still accepts operations."""
        return self.status == "active"

    def copy_from(self, snapshot: GameState) -> None:
        """Replace this game state with values from another game state."""
        self.session_id = snapshot.session_id
        self.board = snapshot.board
        self.status = snapshot.status
        self.difficulty = snapshot.difficulty
        self.started_at = snapshot.started_at
        self.updated_at = snapshot.updated_at
        self.moves = snapshot.moves
        self.owner_user_id = snapshot.owner_user_id
        self.board_message_ids = list(snapshot.board_message_ids)
        self.last_action = snapshot.last_action
        self.theme = snapshot.theme

    def to_dict(self) -> dict[str, object]:
        """Serialize the game into JSON-compatible data."""
        return {
            "session_id": self.session_id,
            "board": self.board.to_dict(),
            "status": self.status,
            "difficulty": self.difficulty,
            "started_at": self.started_at,
            "updated_at": self.updated_at,
            "moves": self.moves,
            "owner_user_id": self.owner_user_id,
            "board_message_ids": list(self.board_message_ids),
            "last_action": self.last_action,
            "theme": self.theme,
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> GameState:
        """Deserialize a game from JSON-compatible data."""
        raw_board = data["board"]
        if not isinstance(raw_board, dict):
            raise ValueError("Game board must be an object.")
        raw_ids = data.get("board_message_ids", [])
        if not isinstance(raw_ids, list):
            raw_ids = []
        status = str(data.get("status", "active"))
        if status not in {"active", "won", "lost", "quit"}:
            raise ValueError(f"Invalid game status: {status}.")
        return cls(
            session_id=str(data["session_id"]),
            board=Board.from_dict(raw_board),
            status=_game_status(status),
            difficulty=str(data.get("difficulty", "custom")),
            started_at=_float_value(data.get("started_at", 0.0)),
            updated_at=_float_value(data.get("updated_at", 0.0)),
            moves=_int_value(data.get("moves", 0)),
            owner_user_id=(
                str(data["owner_user_id"])
                if data.get("owner_user_id") is not None
                else None
            ),
            board_message_ids=[str(value) for value in raw_ids],
            last_action=str(data.get("last_action", "")),
            theme=(str(data["theme"]) if data.get("theme") is not None else None),
        )


def _int_value(value: object) -> int:
    if isinstance(value, str | bytes | bytearray | int | float | bool):
        return int(value)
    raise TypeError(f"Expected integer-compatible value, got {type(value).__name__}.")


def _float_value(value: object) -> float:
    if isinstance(value, str | bytes | bytearray | int | float | bool):
        return float(value)
    raise TypeError(f"Expected float-compatible value, got {type(value).__name__}.")


def _game_status(value: str) -> GameStatus:
    if value not in {"active", "won", "lost", "quit"}:
        raise ValueError(f"Invalid game status: {value}.")
    return cast(GameStatus, value)
