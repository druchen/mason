# Mason

Lightweight cross-platform image browser (Windows & macOS) including folder tree, multiple preview layouts, metadata, tags, and filtering.

## Requirements

- Python 3.11+
- PySide6, Pillow (see `requirements.txt`)

## Run

```bash
pip install -r requirements.txt
python main.py
```

## Project layout

- `main.py` — application entry
- `app/window.py` — main window and splitter layout
- `app/ui/` — toolbar, navigation bar, folder tree, preview host, info bar, keywords, filter, metadata
- `app/views/` — masonry, justified grid, square grid, filmstrip, list preview modes
- `app/core/` — scanning, thumbnails, metadata, SQLite keywords, sort/filter, settings

Settings and thumbnail cache are stored under:

- **Windows:** `%LOCALAPPDATA%\Mason\`
- **macOS/Linux:** `~/.local/share/mason/` (or `$XDG_DATA_HOME/mason`)

## Supported formats

JPG, PNG, GIF, BMP, WEBP, TIFF, SVG (non-RAW as planned).
