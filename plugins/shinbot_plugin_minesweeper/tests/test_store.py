"""Tests for minesweeper game stores."""

from __future__ import annotations

from pathlib import Path

from shinbot_plugin_minesweeper.engine import BoardSpec, MinesweeperEngine
from shinbot_plugin_minesweeper.models import GameState
from shinbot_plugin_minesweeper.store import JsonGameStore, safe_session_key


def test_safe_session_key_includes_digest_to_avoid_collisions() -> None:
    assert safe_session_key("a:b") != safe_session_key("a/b")
    assert safe_session_key("x" * 200) != safe_session_key("x" * 199 + "y")


def test_json_store_load_ignores_corrupt_state(tmp_path: Path) -> None:
    store: JsonGameStore[GameState] = JsonGameStore(
        tmp_path,
        serialize=lambda game: game.to_dict(),
        deserialize=GameState.from_dict,
        updated_at=lambda game: game.updated_at,
    )
    (tmp_path / f"{safe_session_key('s1')}.json").write_text(
        '{"session_id":"s1","board":"bad"}',
        encoding="utf-8",
    )

    assert store.load("s1") is None


def test_json_store_round_trips_with_safe_key(tmp_path: Path) -> None:
    engine = MinesweeperEngine(clock=lambda: 1.0)
    game = engine.create_game(
        session_id="a:b",
        spec=BoardSpec(width=5, height=5, mines=3),
    )
    game.theme = "dark"
    store: JsonGameStore[GameState] = JsonGameStore(
        tmp_path,
        serialize=lambda item: item.to_dict(),
        deserialize=GameState.from_dict,
        updated_at=lambda item: item.updated_at,
    )

    store.save(game)

    assert (tmp_path / f"{safe_session_key('a:b')}.json").is_file()
    loaded = store.load("a:b")
    assert loaded is not None
    assert loaded.theme == "dark"
