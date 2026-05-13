"""Display file / image metadata for the selected image (two-column layout)."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QGridLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app.core.metadata_reader import read_metadata_summary
from app.core.tags_store import TagsStore


class MetadataPanel(QWidget):
    _ROWS: tuple[tuple[str, str], ...] = (
        ("Filename", "filename"),
        ("Dimensions", "dimensions"),
        ("File Size", "file_size"),
        ("Date Created", "date_created"),
        ("Date Modified", "date_modified"),
        ("File Format", "file_format"),
        ("Color Mode", "color_mode"),
        ("Tags", "tags"),
    )

    def __init__(self, store: TagsStore, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._store = store
        self.setObjectName("metadataPanel")

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(4)

        title = QLabel("Metadata")
        title.setObjectName("metadataTitle")
        root.addWidget(title)

        scroll = QScrollArea()
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidgetResizable(True)
        scroll.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        inner = QWidget()
        inner.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        inner_lay = QVBoxLayout(inner)
        inner_lay.setContentsMargins(0, 0, 0, 0)
        inner_lay.setSpacing(0)

        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(0)
        grid.setColumnStretch(1, 1)
        grid.setColumnMinimumWidth(0, 108)

        self._value_labels: dict[str, QLabel] = {}
        for row, (label_text, key) in enumerate(self._ROWS):
            kl = QLabel(label_text)
            kl.setObjectName("metadataKey")
            kl.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
            kl.setWordWrap(False)
            vl = QLabel("—")
            vl.setObjectName("metadataValue")
            vl.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
            wrap = key in ("filename", "tags")
            vl.setWordWrap(wrap)
            vl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            vl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
            kl.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Minimum)
            grid.addWidget(kl, row, 0, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
            grid.addWidget(vl, row, 1, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
            self._value_labels[key] = vl

        inner_lay.addLayout(grid)
        inner_lay.addStretch(1)

        scroll.setWidget(inner)
        root.addWidget(scroll, 1)

        self.setStyleSheet(
            """
            QWidget#metadataPanel QLabel#metadataTitle {
                color: #e0e0e0;
                font-weight: bold;
                margin-bottom: 2px;
            }
            QWidget#metadataPanel QLabel#metadataKey {
                color: #8a8a8a;
                margin: 0px;
                padding: 0px;
            }
            QWidget#metadataPanel QLabel#metadataValue {
                color: #ececec;
                margin: 0px;
                padding: 0px;
            }
            """
        )

    def clear(self) -> None:
        for lbl in self._value_labels.values():
            lbl.setText("—")

    def show_path(self, path: str | None) -> None:
        self.clear()
        if not path:
            return
        summary = read_metadata_summary(path)
        for key in (
            "filename",
            "dimensions",
            "file_size",
            "date_created",
            "date_modified",
            "file_format",
            "color_mode",
        ):
            if key in self._value_labels:
                self._value_labels[key].setText(summary.get(key, "—"))
        names = [name for _tid, name in self._store.get_tags_for_image(path)]
        self._value_labels["tags"].setText(", ".join(names) if names else "—")
