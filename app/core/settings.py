"""Persist user preferences and window geometry to JSON."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def app_data_dir() -> Path:
    """Cross-platform application data directory."""
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA") or str(Path.home())
        return Path(base) / "Mason"
    # macOS / Linux
    xdg = os.environ.get("XDG_DATA_HOME")
    if xdg:
        return Path(xdg) / "mason"
    return Path.home() / ".local" / "share" / "mason"


def settings_path() -> Path:
    d = app_data_dir()
    d.mkdir(parents=True, exist_ok=True)
    return d / "settings.json"


DEFAULT_SETTINGS: dict[str, Any] = {
    "last_folder": "",
    "thumbnail_size": 128,
    "layout_mode": "square",
    "sort_by": "name",
    "sort_ascending": True,
    "show_filenames": True,
    "tile_background": True,
    "window_geometry": None,  # dict x,y,w,h or None
    "splitter_main": None,
    "splitter_left": None,
    "splitter_right": None,
    "photoshop_exe": "",
    "drop_save_format": "webp",
    "favorite_folders": [],
}


def load_settings() -> dict[str, Any]:
    path = settings_path()
    if not path.is_file():
        return dict(DEFAULT_SETTINGS)
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return dict(DEFAULT_SETTINGS)
    merged = dict(DEFAULT_SETTINGS)
    merged.update(data)
    return merged


def save_settings(data: dict[str, Any]) -> None:
    path = settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    tmp.replace(path)
