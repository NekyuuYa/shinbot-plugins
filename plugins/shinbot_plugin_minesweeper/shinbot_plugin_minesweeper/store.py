"""Storage backends for ShinBot minesweeper game state."""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from hashlib import sha256
from pathlib import Path
from typing import Protocol, TypeVar


class StoredGame(Protocol):
    """Minimum game shape required by stores."""

    session_id: str


GameT = TypeVar("GameT", bound=StoredGame)

Serializer = Callable[[GameT], dict[str, object]]
Deserializer = Callable[[dict[str, object]], GameT]


class GameStore(Protocol[GameT]):
    """Persistence interface for per-session minesweeper games."""

    def load(self, session_id: str) -> GameT | None:
        """Load a game for a session, returning ``None`` when absent."""

    def save(self, game: GameT) -> None:
        """Persist a game state."""

    def delete(self, session_id: str) -> None:
        """Delete any game state for a session."""

    def cleanup_expired(self, now: float, ttl_seconds: int) -> int:
        """Delete expired games and return the number removed."""


class MemoryGameStore(GameStore[GameT]):
    """In-memory game store keyed by ShinBot session id."""

    def __init__(self, updated_at: Callable[[GameT], float]) -> None:
        """Create an in-memory game store.

        Args:
            updated_at: Function that extracts the last update timestamp from a game.
        """
        self._games: dict[str, GameT] = {}
        self._updated_at = updated_at

    def load(self, session_id: str) -> GameT | None:
        """Load a game for a session, returning ``None`` when absent."""
        return self._games.get(session_id)

    def save(self, game: GameT) -> None:
        """Persist a game state."""
        self._games[game.session_id] = game

    def delete(self, session_id: str) -> None:
        """Delete any game state for a session."""
        self._games.pop(session_id, None)

    def cleanup_expired(self, now: float, ttl_seconds: int) -> int:
        """Delete expired games and return the number removed."""
        expired = [
            session_id
            for session_id, game in self._games.items()
            if now - self._updated_at(game) > ttl_seconds
        ]
        for session_id in expired:
            self.delete(session_id)
        return len(expired)


class JsonGameStore(GameStore[GameT]):
    """JSON-file game store under a plugin-owned data directory."""

    def __init__(
        self,
        directory: Path,
        *,
        serialize: Serializer[GameT],
        deserialize: Deserializer[GameT],
        updated_at: Callable[[GameT], float],
    ) -> None:
        """Create a JSON-backed game store.

        Args:
            directory: Directory where session JSON files are stored.
            serialize: Convert a game object into JSON-compatible data.
            deserialize: Convert JSON-compatible data back into a game object.
            updated_at: Function that extracts the last update timestamp from a game.
        """
        self._directory = directory
        self._serialize = serialize
        self._deserialize = deserialize
        self._updated_at = updated_at
        self._directory.mkdir(parents=True, exist_ok=True)

    def load(self, session_id: str) -> GameT | None:
        """Load a game for a session, returning ``None`` when absent."""
        path = self._path_for_session(session_id)
        if not path.is_file():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if not isinstance(payload, dict):
            return None
        try:
            return self._deserialize(payload)
        except (KeyError, TypeError, ValueError):
            return None

    def save(self, game: GameT) -> None:
        """Persist a game state."""
        session_id = str(game.session_id)
        path = self._path_for_session(session_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = self._serialize(game)
        path.write_text(
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8",
        )

    def delete(self, session_id: str) -> None:
        """Delete any game state for a session."""
        try:
            self._path_for_session(session_id).unlink()
        except FileNotFoundError:
            return

    def cleanup_expired(self, now: float, ttl_seconds: int) -> int:
        """Delete expired games and return the number removed."""
        removed = 0
        for path in self._directory.glob("*.json"):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(payload, dict):
                continue
            try:
                game = self._deserialize(payload)
            except (KeyError, TypeError, ValueError):
                continue
            if now - self._updated_at(game) <= ttl_seconds:
                continue
            try:
                path.unlink()
            except FileNotFoundError:
                pass
            removed += 1
        return removed

    def _path_for_session(self, session_id: str) -> Path:
        return self._directory / f"{safe_session_key(session_id)}.json"


def safe_session_key(session_id: str) -> str:
    """Return a filesystem-safe key for a ShinBot session id."""
    normalized = re.sub(r"[^A-Za-z0-9_.-]+", "_", session_id.strip())
    digest = sha256(session_id.encode("utf-8")).hexdigest()[:16]
    prefix = normalized[:120] or "session"
    return f"{prefix}-{digest}"
