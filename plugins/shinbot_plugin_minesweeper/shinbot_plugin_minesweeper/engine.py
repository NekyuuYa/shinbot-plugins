"""Pure minesweeper rules engine."""

from __future__ import annotations

import random
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Protocol

from .models import Board, Cell, CellState, GameState, Position


class RandomSampler(Protocol):
    """Protocol for deterministic-testable random samplers."""

    def sample(self, population: list[Position], k: int) -> list[Position]:
        """Return k distinct positions sampled from population."""
        ...


class MinesweeperError(ValueError):
    """Base exception for invalid minesweeper operations."""


class GameAlreadyEndedError(MinesweeperError):
    """Raised when a move is attempted after the game has ended."""


class CellOperationError(MinesweeperError):
    """Raised when a requested cell operation is invalid."""


@dataclass(frozen=True, slots=True)
class BoardSpec:
    """Board dimensions and mine count for a new game."""

    width: int
    height: int
    mines: int
    difficulty: str = "custom"


@dataclass(frozen=True, slots=True)
class OperationStep:
    """Result for a single cell operation inside a batch."""

    position: Position
    action: str
    changed: bool = False
    revealed: int = 0
    flagged: bool | None = None
    message: str | None = None


@dataclass(frozen=True, slots=True)
class OperationResult:
    """Result for one operation or a left-to-right operation batch."""

    action: str
    steps: list[OperationStep] = field(default_factory=list)
    status: str = "active"
    stopped: bool = False
    changed: bool = False

    @property
    def revealed(self) -> int:
        """Return total revealed cells across all steps."""
        return sum(step.revealed for step in self.steps)


class MinesweeperEngine:
    """Pure rules engine for delayed-seeded minesweeper games."""

    def __init__(
        self,
        *,
        rng: RandomSampler | None = None,
        seed: int | None = None,
        clock: Callable[[], float] | None = None,
    ) -> None:
        """Initialize the engine.

        Args:
            rng: Optional sampler object. Takes precedence over seed.
            seed: Optional deterministic seed for Python's random generator.
            clock: Optional time provider for game timestamps.
        """
        self._rng: RandomSampler = rng if rng is not None else random.Random(seed)
        self._clock = clock if clock is not None else time.time

    def create_game(
        self,
        *,
        session_id: str,
        spec: BoardSpec,
        owner_user_id: str | None = None,
    ) -> GameState:
        """Create a new unseeded game."""
        self.validate_spec(spec)
        now = self._clock()
        return GameState(
            session_id=session_id,
            board=Board(spec.width, spec.height, spec.mines),
            status="active",
            difficulty=spec.difficulty,
            started_at=now,
            updated_at=now,
            owner_user_id=owner_user_id,
        )

    def validate_spec(self, spec: BoardSpec) -> None:
        """Validate basic board settings."""
        if spec.width <= 0:
            raise ValueError("Board width must be positive.")
        if spec.height <= 0:
            raise ValueError("Board height must be positive.")
        if spec.mines <= 0:
            raise ValueError("Mine count must be positive.")
        if spec.mines >= spec.width * spec.height:
            raise ValueError("Mine count must be less than cell count.")

    def seed_mines(self, board: Board, first_open: Position) -> None:
        """Place mines after the first open while keeping that cell safe.

        The generator first tries to exclude the first-open cell and all neighbors.
        If that leaves too few candidates, it falls back to excluding only the opened
        cell, which still guarantees first-open safety.
        """
        if board.mine_seeded:
            return
        board.require_in_bounds(first_open)
        board.reset_mines()
        all_positions = board.positions()
        preferred_exclusions = {first_open, *board.neighbors(first_open)}
        candidates = [
            position
            for position in all_positions
            if position not in preferred_exclusions
        ]
        if len(candidates) < board.mine_count:
            candidates = [
                position for position in all_positions if position != first_open
            ]
        if len(candidates) < board.mine_count:
            raise ValueError("Not enough candidate cells to place mines safely.")
        for position in self._rng.sample(candidates, board.mine_count):
            board.cell_at(position).has_mine = True
        self._compute_adjacent_counts(board)
        board.mine_seeded = True

    def open_cell(self, game: GameState, position: Position) -> OperationResult:
        """Open one cell and update game status."""
        return self.open_many(game, [position])

    def open_many(
        self,
        game: GameState,
        positions: list[Position],
    ) -> OperationResult:
        """Open cells left-to-right, stopping after win or loss."""
        self._require_active(game)
        for position in positions:
            game.board.require_in_bounds(position)
            cell = game.board.cell_at(position)
            if cell.state is CellState.FLAGGED:
                raise CellOperationError("Cannot open a flagged cell.")
        steps: list[OperationStep] = []
        changed = False
        for position in positions:
            step = self._open_one(game, position)
            steps.append(step)
            changed = changed or step.changed
            if game.status != "active":
                break
        if changed:
            self._record_move(game)
        return OperationResult(
            action="open",
            steps=steps,
            status=game.status,
            stopped=len(steps) < len(positions) or game.status != "active",
            changed=changed,
        )

    def toggle_flag(self, game: GameState, position: Position) -> OperationResult:
        """Toggle one flag and update game status."""
        return self.toggle_flags(game, [position])

    def toggle_flags(
        self,
        game: GameState,
        positions: list[Position],
    ) -> OperationResult:
        """Toggle flags left-to-right."""
        self._require_active(game)
        for position in positions:
            cell = game.board.cell_at(position)
            if cell.state is CellState.REVEALED:
                raise CellOperationError("Cannot flag a revealed cell.")
        steps: list[OperationStep] = []
        changed = False
        for position in positions:
            cell = game.board.cell_at(position)
            if cell.state is CellState.FLAGGED:
                cell.state = CellState.HIDDEN
                step = OperationStep(
                    position=position,
                    action="flag",
                    changed=True,
                    flagged=False,
                )
            else:
                cell.state = CellState.FLAGGED
                step = OperationStep(
                    position=position,
                    action="flag",
                    changed=True,
                    flagged=True,
                )
            steps.append(step)
            changed = True
        if changed:
            self._record_move(game)
        return OperationResult(
            action="flag",
            steps=steps,
            status=game.status,
            changed=changed,
        )

    def chord_cell(self, game: GameState, position: Position) -> OperationResult:
        """Chord one revealed numbered cell."""
        return self.chord_many(game, [position])

    def chord_many(
        self,
        game: GameState,
        positions: list[Position],
    ) -> OperationResult:
        """Chord cells left-to-right, stopping after win or loss."""
        self._require_active(game)
        snapshot = game.to_dict()
        steps: list[OperationStep] = []
        changed = False
        try:
            for position in positions:
                step = self._chord_one(game, position)
                steps.append(step)
                changed = changed or step.changed
                if game.status != "active":
                    break
        except (CellOperationError, ValueError):
            self._restore_game(game, GameState.from_dict(snapshot))
            raise
        if changed:
            self._record_move(game)
        return OperationResult(
            action="chord",
            steps=steps,
            status=game.status,
            stopped=len(steps) < len(positions) or game.status != "active",
            changed=changed,
        )

    def quit_game(self, game: GameState) -> OperationResult:
        """Mark an active game as quit."""
        self._require_active(game)
        game.status = "quit"
        self._touch(game)
        return OperationResult(action="quit", status=game.status, stopped=True)

    def _open_one(self, game: GameState, position: Position) -> OperationStep:
        board = game.board
        board.require_in_bounds(position)
        if not board.mine_seeded:
            self.seed_mines(board, position)
        cell = board.cell_at(position)
        if cell.state is CellState.FLAGGED:
            raise CellOperationError("Cannot open a flagged cell.")
        if cell.state is CellState.REVEALED:
            return OperationStep(position=position, action="open")
        if cell.has_mine:
            cell.state = CellState.REVEALED
            cell.exploded = True
            game.status = "lost"
            return OperationStep(
                position=position,
                action="open",
                changed=True,
                revealed=1,
                message="mine",
            )
        revealed = self._flood_open(board, position)
        self._check_win(game)
        return OperationStep(
            position=position,
            action="open",
            changed=revealed > 0,
            revealed=revealed,
        )

    def _chord_one(self, game: GameState, position: Position) -> OperationStep:
        board = game.board
        cell = self._validate_chord_target(board, position)
        neighbors = board.neighbors(position)
        flagged_count = sum(
            1
            for neighbor in neighbors
            if board.cell_at(neighbor).state is CellState.FLAGGED
        )
        if flagged_count != cell.adjacent_mines:
            return OperationStep(
                position=position,
                action="chord",
                message="flag_count_mismatch",
            )
        revealed = 0
        changed = False
        for neighbor in neighbors:
            neighbor_cell = board.cell_at(neighbor)
            if neighbor_cell.state is not CellState.HIDDEN:
                continue
            if neighbor_cell.has_mine:
                neighbor_cell.state = CellState.REVEALED
                neighbor_cell.exploded = True
                game.status = "lost"
                return OperationStep(
                    position=position,
                    action="chord",
                    changed=True,
                    revealed=revealed + 1,
                    message="mine",
                )
            opened = self._flood_open(board, neighbor)
            revealed += opened
            changed = changed or opened > 0
        self._check_win(game)
        return OperationStep(
            position=position,
            action="chord",
            changed=changed,
            revealed=revealed,
        )

    def _validate_chord_target(self, board: Board, position: Position) -> Cell:
        board.require_in_bounds(position)
        cell = board.cell_at(position)
        if cell.state is not CellState.REVEALED:
            raise CellOperationError("Can only chord a revealed cell.")
        if cell.adjacent_mines <= 0:
            raise CellOperationError("Can only chord a numbered cell.")
        return cell

    def _flood_open(self, board: Board, start: Position) -> int:
        revealed = 0
        queue: deque[Position] = deque([start])
        visited: set[Position] = set()
        while queue:
            position = queue.popleft()
            if position in visited:
                continue
            visited.add(position)
            cell = board.cell_at(position)
            if cell.state is not CellState.HIDDEN or cell.has_mine:
                continue
            cell.state = CellState.REVEALED
            revealed += 1
            if cell.adjacent_mines == 0:
                for neighbor in board.neighbors(position):
                    neighbor_cell = board.cell_at(neighbor)
                    if neighbor_cell.state is CellState.HIDDEN:
                        queue.append(neighbor)
        return revealed

    def _compute_adjacent_counts(self, board: Board) -> None:
        for position in board.positions():
            cell = board.cell_at(position)
            if cell.has_mine:
                cell.adjacent_mines = 0
                continue
            cell.adjacent_mines = sum(
                1
                for neighbor in board.neighbors(position)
                if board.cell_at(neighbor).has_mine
            )

    def _check_win(self, game: GameState) -> None:
        if game.board.hidden_safe_count() == 0:
            game.status = "won"

    def _require_active(self, game: GameState) -> None:
        if not game.is_active():
            raise GameAlreadyEndedError("Game has already ended.")

    def _record_move(self, game: GameState) -> None:
        game.moves += 1
        self._touch(game)

    def _touch(self, game: GameState) -> None:
        game.updated_at = self._clock()

    def _restore_game(self, game: GameState, snapshot: GameState) -> None:
        game.copy_from(snapshot)
