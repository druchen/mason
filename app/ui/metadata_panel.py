"""Display EXIF / file metadata for the selected image."""

from __future__ import annotations

from PySide6.QtWidgets import QLabel, QTextEdit, QVBoxLayout, QWidget

from app.core.metadata_reader import read_metadata


class MetadataPanel(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._text = QTextEdit()
        self._text.setReadOnly(True)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(QLabel("Metadata"))
        lay.addWidget(self._text)

    def clear(self) -> None:
        self._text.clear()

    def show_path(self, path: str | None) -> None:
        self._text.clear()
        if not path:
            return
        meta = read_metadata(path)
        lines = [f"{k}: {v}" for k, v in meta.items()]
        self._text.setPlainText("\n".join(lines))
