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
    "layout_mode": "essential",
    "sort_by": "name",
    "sort_ascending": True,
    "tile_background": True,
    "window_geometry": None,  # dict x,y,w,h or None
    "splitter_main": None,
    "splitter_left": None,
    "splitter_right": None,
    "splitters_by_mode": {},  # layout_mode -> {splitter_main, splitter_left, splitter_right}
    "photoshop_exe": "",
    "drop_save_format": "webp",
    "favorite_folders": [],
}

# Must match app.ui.toolbar.MainToolbar.MODES (avoid importing Qt from here).
KNOWN_LAYOUT_MODES: tuple[str, ...] = ("essential", "filmstrip", "list")


def _validate_splitter_list(raw: Any, expected_len: int) -> list[int] | None:
    if not isinstance(raw, list) or len(raw) != expected_len:
        return None
    vals: list[int] = []
    for v in raw:
        try:
            iv = int(v)
        except (TypeError, ValueError):
            return None
        if iv <= 0 or iv > 20000:
            return None
        vals.append(iv)
    return vals


def _sanitize_qt_splitter_state_hex(raw: Any) -> str | None:
    if not isinstance(raw, str) or not raw or len(raw) > 20000 or len(raw) % 2 != 0:
        return None
    try:
        bytes.fromhex(raw)
    except ValueError:
        return None
    return raw


def _sanitize_splitters_by_mode(raw: Any) -> dict[str, dict[str, Any]]:
    modes = set(KNOWN_LAYOUT_MODES)
    out: dict[str, dict[str, Any]] = {}
    if not isinstance(raw, dict):
        return out
    for k, v in raw.items():
        ks = str(k)
        if ks not in modes or not isinstance(v, dict):
            continue
        sm = _validate_splitter_list(v.get("splitter_main"), 3)
        sl = _validate_splitter_list(v.get("splitter_left"), 2)
        sr = _validate_splitter_list(v.get("splitter_right"), 2)
        if sm is not None and sl is not None and sr is not None:
            entry: dict[str, Any] = {"splitter_main": sm, "splitter_left": sl, "splitter_right": sr}
            for qk in ("qt_main", "qt_left", "qt_right"):
                qh = _sanitize_qt_splitter_state_hex(v.get(qk))
                if qh is not None:
                    entry[qk] = qh
            out[ks] = entry
    return out


def _sanitize_settings(data: dict[str, Any]) -> dict[str, Any]:
    out = dict(data)

    # Keep thumbnail size in sync with the info-bar slider (48–512) and BaseImageView clamp.
    try:
        thumb = int(out.get("thumbnail_size", DEFAULT_SETTINGS["thumbnail_size"]))
    except (TypeError, ValueError):
        thumb = int(DEFAULT_SETTINGS["thumbnail_size"])
    out["thumbnail_size"] = max(48, min(512, thumb))

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
        out[key] = _validate_splitter_list(out.get(key), expected_len)

    sbm = _sanitize_splitters_by_mode(out.get("splitters_by_mode"))
    lm = out.get("splitter_main")
    ll = out.get("splitter_left")
    lr = out.get("splitter_right")
    if lm is not None and ll is not None and lr is not None:
        seed = {"splitter_main": list(lm), "splitter_left": list(ll), "splitter_right": list(lr)}
        for m in KNOWN_LAYOUT_MODES:
            if m not in sbm:
                sbm[m] = {k: list(v) for k, v in seed.items()}
    out["splitters_by_mode"] = sbm

    valid_modes = set(KNOWN_LAYOUT_MODES)
    lm_mode = str(out.get("layout_mode", DEFAULT_SETTINGS["layout_mode"])).strip().lower()
    if lm_mode not in valid_modes:
        out["layout_mode"] = str(DEFAULT_SETTINGS["layout_mode"])
    else:
        out["layout_mode"] = lm_mode

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
    base: dict[str, Any] = dict(DEFAULT_SETTINGS)
    if path.is_file():
        try:
            with open(path, encoding="utf-8") as f:
                disk = json.load(f)
            if isinstance(disk, dict):
                base.update(disk)
        except (OSError, json.JSONDecodeError):
            pass
    base.update(data)
    out = _sanitize_settings(base)
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)
    tmp.replace(path)
