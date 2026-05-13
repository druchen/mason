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
    "tile_background": True,
    "window_geometry": None,  # dict x,y,w,h or None
    "splitter_main": None,
    "splitter_left": None,
    "splitter_right": None,
    "photoshop_exe": "",
    "drop_save_format": "webp",
    "favorite_folders": [],
}


def _sanitize_settings(data: dict[str, Any]) -> dict[str, Any]:
    out = dict(data)

    # Prevent pathological startup cost from extreme thumbnail sizes.
    try:
        thumb = int(out.get("thumbnail_size", DEFAULT_SETTINGS["thumbnail_size"]))
    except (TypeError, ValueError):
        thumb = int(DEFAULT_SETTINGS["thumbnail_size"])
    out["thumbnail_size"] = max(48, min(256, thumb))

    # Drop invalid/absurd window geometry and splitter payloads.
    geo = out.get("window_geometry")
    if not isinstance(geo, dict):
        out["window_geometry"] = None
    else:
        try:
            w = int(geo.get("w", 0))
            h = int(geo.get("h", 0))
            x = int(geo.get("x", 0))
            y = int(geo.get("y", 0))
        except (TypeError, ValueError):
            out["window_geometry"] = None
        else:
            if w < 600 or h < 400 or w > 10000 or h > 10000:
                out["window_geometry"] = None
            else:
                out["window_geometry"] = {"x": x, "y": y, "w": w, "h": h}

    for key, expected_len in (("splitter_main", 3), ("splitter_left", 2), ("splitter_right", 2)):
        raw = out.get(key)
        if not isinstance(raw, list) or len(raw) != expected_len:
            out[key] = None
            continue
        vals: list[int] = []
        ok = True
        for v in raw:
            try:
                iv = int(v)
            except (TypeError, ValueError):
                ok = False
                break
            if iv <= 0 or iv > 20000:
                ok = False
                break
            vals.append(iv)
        out[key] = vals if ok else None

    return out


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
    return _sanitize_settings(merged)


def save_settings(data: dict[str, Any]) -> None:
    path = settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    tmp.replace(path)
