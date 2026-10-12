"""Tiny JSON settings store (theme + last used folders). Failures are non-fatal."""

from __future__ import annotations

import json
import os
from pathlib import Path


def config_dir() -> Path:
    override = os.environ.get("GUITAR_CONFIG_DIR")
    return Path(override) if override else Path.home() / ".guitar"


def settings_file() -> Path:
    return config_dir() / "settings.json"


def load_settings() -> dict:
    try:
        data = json.loads(settings_file().read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_settings(data: dict) -> bool:
    try:
        config_dir().mkdir(parents=True, exist_ok=True)
        tmp = settings_file().with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        os.replace(tmp, settings_file())
        return True
    except OSError:
        return False
