"""ShimAstrBotConfig — dict subclass with save_config() for AstrBot plugin config compatibility."""
from __future__ import annotations

import json
from pathlib import Path


class ShimAstrBotConfig(dict):
    """AstrBotConfig-compatible dict with persistent save_config().

    Reads initial values from a JSON config file. When save_config() is called,
    writes back to the same file.
    """

    def __init__(self, config_path: Path, schema_path: Path | None = None):
        super().__init__()
        self._config_path = config_path
        self._schema_path = schema_path
        self._load_from_schema()
        self._load_from_file()

    def _load_from_schema(self):
        """Load default values from _conf_schema.json if it exists."""
        if self._schema_path is None or not self._schema_path.exists():
            return
        try:
            schema = json.loads(self._schema_path.read_text(encoding="utf-8"))
            for group_data in schema.values():
                if isinstance(group_data, dict) and "items" in group_data:
                    for key, item_def in group_data["items"].items():
                        if isinstance(item_def, dict) and "default" in item_def:
                            group_name = None
                            for gk, gv in schema.items():
                                if gv.get("items") and key in gv["items"]:
                                    group_name = gk
                                    break
                            if group_name:
                                self.setdefault(group_name, {})[key] = item_def["default"]
        except Exception:
            pass

    def _load_from_file(self):
        """Load saved config values, overriding defaults."""
        if not self._config_path.exists():
            return
        try:
            saved = json.loads(self._config_path.read_text(encoding="utf-8"))
            for key, value in saved.items():
                if isinstance(value, dict) and isinstance(self.get(key), dict):
                    self[key].update(value)
                else:
                    self[key] = value
        except Exception:
            pass

    def save_config(self):
        """Persist current config to disk."""
        self._config_path.parent.mkdir(parents=True, exist_ok=True)
        self._config_path.write_text(
            json.dumps(dict(self), ensure_ascii=False, indent=4),
            encoding="utf-8",
        )
