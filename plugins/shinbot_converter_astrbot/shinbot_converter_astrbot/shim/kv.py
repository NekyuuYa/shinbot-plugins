"""ShimKVStore — JSON-file-backed key-value store mimicking Star.put_kv_data/get_kv_data."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any


class ShimKVStore:
    """Simple async KV store backed by a JSON file."""

    def __init__(self, store_path: Path):
        self._path = store_path
        self._lock = asyncio.Lock()

    def _load(self) -> dict[str, Any]:
        if not self._path.exists():
            return {}
        try:
            return json.loads(self._path.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _save(self, data: dict[str, Any]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    async def get_kv_data(self, key: str, default=None):
        async with self._lock:
            data = self._load()
            return data.get(key, default)

    async def put_kv_data(self, key: str, value) -> None:
        async with self._lock:
            data = self._load()
            if value is None:
                data.pop(key, None)
            else:
                data[key] = value
            self._save(data)
