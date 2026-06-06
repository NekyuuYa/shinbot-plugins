"""Unit tests for the pure minesweeper engine."""

from __future__ import annotations

import pytest

from shinbot_plugin_minesweeper.engine import (
    BoardSpec,
    CellOperationError,
    GameAlreadyEndedError,
    MinesweeperEngine,
)
from shinbot_plugin_minesweeper.models import Board, CellState, Position


def test_first_open_delays_seeding_and_excludes_neighbors() -> None:
    """First open seeds mines after excluding the clicked cell and neighbors."""
    engine = MinesweeperEngine(seed=1, clock=lambda: 1.0)
    game = engine.create_game(
        session_id="s1",
        spec=BoardSpec(width=5, height=5, mines=3, difficulty="custom"),
    )

    assert not game.board.mine_seeded
    result = engine.open_cell(game, Position(2, 2))

    assert result.changed
    assert game.board.mine_seeded
    excluded = {Position(2, 2), *game.board.neighbors(Position(2, 2))}
    assert all(not game.board.cell_at(position).has_mine for position in excluded)
    assert game.board.cell_at(Position(2, 2)).state is CellState.REVEALED


def test_first_open_neighbor_exclusion_falls_back_when_needed() -> None:
    """Dense boards fall back to excluding only the first opened cell."""
    engine = MinesweeperEngine(seed=3, clock=lambda: 1.0)
    game = engine.create_game(
        session_id="s1",
        spec=BoardSpec(width=3, height=3, mines=7, difficulty="custom"),
    )

    engine.open_cell(game, Position(1, 1))

    assert not game.board.cell_at(Position(1, 1)).has_mine
    assert sum(1 for cell in game.board.cells if cell.has_mine) == 7


def test_zero_open_expands_contiguous_empty_area() -> None:
    """Opening a zero cell reveals connected empty cells and numeric borders."""
    engine = MinesweeperEngine(clock=lambda: 1.0)
    board = Board(width=4, height=4, mine_count=1)
    board.cell_at(Position(3, 3)).has_mine = True
    engine._compute_adjacent_counts(board)
    board.mine_seeded = True
    game = engine.create_game(
        session_id="s1",
        spec=BoardSpec(width=4, height=4, mines=1),
    )
    game.board = board

    result = engine.open_cell(game, Position(0, 0))

    assert result.revealed == 15
    assert game.status == "won"
    assert board.cell_at(Position(3, 3)).state is CellState.HIDDEN


def test_flag_toggle_and_revealed_flag_rejection() -> None:
    """Flags toggle on hidden cells and cannot be placed on revealed cells."""
    engine = MinesweeperEngine(seed=1, clock=lambda: 1.0)
    game = engine.create_game(
        session_id="s1",
        spec=BoardSpec(width=5, height=5, mines=1),
    )

    flagged = engine.toggle_flag(game, Position(0, 0))
    unflagged = engine.toggle_flag(game, Position(0, 0))

    assert flagged.steps[0].flagged is True
    assert unflagged.steps[0].flagged is False
    assert game.board.cell_at(Position(0, 0)).state is CellState.HIDDEN

    engine.open_cell(game, Position(1, 1))
    with pytest.raises(CellOperationError):
        engine.toggle_flag(game, Position(1, 1))


def test_open_flagged_cell_is_rejected() -> None:
    """Opening a flagged cell raises an operation error."""
    engine = MinesweeperEngine(seed=1, clock=lambda: 1.0)
    game = engine.create_game(
        session_id="s1",
        spec=BoardSpec(width=5, height=5, mines=1),
    )
    engine.toggle_flag(game, Position(0, 0))

    with pytest.raises(CellOperationError):
        engine.open_cell(game, Position(0, 0))


def test_open_many_flagged_cell_rejection_is_atomic() -> None:
    """A batch open with a flagged cell does not reveal earlier cells."""
    engine = MinesweeperEngine(clock=lambda: 1.0)
    board = Board(width=3, height=1, mine_count=1)
    board.cell_at(Position(2, 0)).has_mine = True
    engine._compute_adjacent_counts(board)
    board.mine_seeded = True
    board.cell_at(Position(1, 0)).state = CellState.FLAGGED
    game = engine.create_game(
        session_id="s1",
        spec=BoardSpec(width=3, height=1, mines=1),
    )
    game.board = board

    with pytest.raises(CellOperationError):
        engine.open_many(game, [Position(0, 0), Position(1, 0)])

    assert board.cell_at(Position(0, 0)).state is CellState.HIDDEN
    assert board.cell_at(Position(1, 0)).state is CellState.FLAGGED
    assert game.moves == 0


def test_toggle_flags_revealed_cell_rejection_is_atomic() -> None:
    """A batch flag with a revealed cell does not toggle earlier flags."""
    engine = MinesweeperEngine(clock=lambda: 1.0)
    board = Board(width=3, height=1, mine_count=1)
    board.cell_at(Position(0, 0)).state = CellState.HIDDEN
    board.cell_at(Position(1, 0)).state = CellState.REVEALED
    board.mine_seeded = True
    game = engine.create_game(
        session_id="s1",
        spec=BoardSpec(width=3, height=1, mines=1),
    )
    game.board = board

    with pytest.raises(CellOperationError):
        engine.toggle_flags(game, [Position(0, 0), Position(1, 0)])

    assert board.cell_at(Position(0, 0)).state is CellState.HIDDEN
    assert board.cell_at(Position(1, 0)).state is CellState.REVEALED
    assert game.moves == 0


def test_chord_opens_neighbors_when_flag_count_matches() -> None:
    """Chord reveals surrounding hidden cells when flags match the number."""
    engine = MinesweeperEngine(clock=lambda: 1.0)
    board = Board(width=3, height=3, mine_count=1)
    board.cell_at(Position(0, 0)).has_mine = True
    engine._compute_adjacent_counts(board)
    board.mine_seeded = True
    board.cell_at(Position(0, 0)).state = CellState.FLAGGED
    board.cell_at(Position(1, 1)).state = CellState.REVEALED
    game = engine.create_game(
        session_id="s1",
        spec=BoardSpec(width=3, height=3, mines=1),
    )
    game.board = board

    result = engine.chord_cell(game, Position(1, 1))

    assert result.changed
    assert result.revealed == 7
    assert game.status == "won"


def test_chord_does_nothing_when_flag_count_mismatches() -> None:
    """Chord leaves the board unchanged if adjacent flags do not match."""
    engine = MinesweeperEngine(clock=lambda: 1.0)
    board = Board(width=3, height=3, mine_count=1)
    board.cell_at(Position(0, 0)).has_mine = True
    engine._compute_adjacent_counts(board)
    board.mine_seeded = True
    board.cell_at(Position(1, 1)).state = CellState.REVEALED
    game = engine.create_game(
        session_id="s1",
        spec=BoardSpec(width=3, height=3, mines=1),
    )
    game.board = board

    result = engine.chord_cell(game, Position(1, 1))

    assert not result.changed
    assert result.steps[0].message == "flag_count_mismatch"


def test_chord_many_invalid_later_cell_rolls_back() -> None:
    """Chord batches roll back earlier changes when a later cell is invalid."""
    engine = MinesweeperEngine(clock=lambda: 1.0)
    board = Board(width=6, height=6, mine_count=5)
    board.cell_at(Position(0, 0)).has_mine = True
    board.cell_at(Position(2, 0)).has_mine = True
    board.cell_at(Position(0, 2)).has_mine = True
    board.cell_at(Position(2, 2)).has_mine = True
    board.cell_at(Position(5, 5)).has_mine = True
    engine._compute_adjacent_counts(board)
    board.mine_seeded = True
    board.cell_at(Position(0, 0)).state = CellState.FLAGGED
    board.cell_at(Position(2, 0)).state = CellState.FLAGGED
    board.cell_at(Position(0, 2)).state = CellState.FLAGGED
    board.cell_at(Position(2, 2)).state = CellState.FLAGGED
    board.cell_at(Position(1, 1)).state = CellState.REVEALED
    board.cell_at(Position(5, 0)).state = CellState.REVEALED
    game = engine.create_game(
        session_id="s1",
        spec=BoardSpec(width=6, height=6, mines=5),
    )
    game.board = board
    snapshot = game.to_dict()

    with pytest.raises(CellOperationError):
        engine.chord_many(game, [Position(1, 1), Position(5, 0)])

    assert game.to_dict() == snapshot


def test_loss_sets_exploded_cell_and_blocks_future_moves() -> None:
    """Opening a mine loses the game and future operations are rejected."""
    engine = MinesweeperEngine(clock=lambda: 1.0)
    board = Board(width=2, height=2, mine_count=1)
    board.cell_at(Position(1, 1)).has_mine = True
    engine._compute_adjacent_counts(board)
    board.mine_seeded = True
    game = engine.create_game(
        session_id="s1",
        spec=BoardSpec(width=2, height=2, mines=1),
    )
    game.board = board

    result = engine.open_cell(game, Position(1, 1))

    assert result.status == "lost"
    assert board.cell_at(Position(1, 1)).exploded
    with pytest.raises(GameAlreadyEndedError):
        engine.open_cell(game, Position(0, 0))


def test_open_many_stops_after_terminal_state() -> None:
    """Batches process left-to-right and ignore cells after loss."""
    engine = MinesweeperEngine(clock=lambda: 1.0)
    board = Board(width=3, height=1, mine_count=1)
    board.cell_at(Position(1, 0)).has_mine = True
    engine._compute_adjacent_counts(board)
    board.mine_seeded = True
    game = engine.create_game(
        session_id="s1",
        spec=BoardSpec(width=3, height=1, mines=1),
    )
    game.board = board

    result = engine.open_many(
        game,
        [Position(0, 0), Position(1, 0), Position(2, 0)],
    )

    assert result.stopped
    assert len(result.steps) == 2
    assert game.board.cell_at(Position(2, 0)).state is CellState.HIDDEN


def test_game_state_serialization_round_trip() -> None:
    """Game state can be serialized and restored."""
    engine = MinesweeperEngine(seed=1, clock=lambda: 1.0)
    game = engine.create_game(
        session_id="s1",
        spec=BoardSpec(width=5, height=5, mines=2, difficulty="easy"),
        owner_user_id="u1",
    )
    engine.open_cell(game, Position(0, 0))
    game.board_message_ids.append("m1")

    restored = type(game).from_dict(game.to_dict())

    assert restored.session_id == game.session_id
    assert restored.board.width == 5
    assert restored.board.mine_seeded
    assert restored.owner_user_id == "u1"
    assert restored.board_message_ids == ["m1"]


def test_game_state_copy_from_replaces_serialized_state() -> None:
    """Game state restore logic stays centralized on the model."""
    engine = MinesweeperEngine(seed=1, clock=lambda: 1.0)
    game = engine.create_game(
        session_id="s1",
        spec=BoardSpec(width=5, height=5, mines=2, difficulty="easy"),
        owner_user_id="u1",
    )
    snapshot = type(game).from_dict(game.to_dict())

    game.board.width = 6
    game.status = "lost"
    game.moves = 10
    game.board_message_ids.append("changed")
    game.last_action = "changed"
    game.copy_from(snapshot)

    assert game.to_dict() == snapshot.to_dict()
