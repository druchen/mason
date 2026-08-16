"""Display file / image metadata for the selected image (two-column layout)."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app.core.metadata_reader import read_metadata_summary
from app.ui.mason_tab_widget import MasonPanelHeader


class MetadataPanel(QWidget):
    _ROWS_MAIN: tuple[tuple[str, str], ...] = (
        ("Filename", "filename"),
        ("Dimensions", "dimensions"),
        ("File Size", "file_size"),
        ("Date Created", "date_created"),
        ("Date Modified", "date_modified"),
        ("File Format", "file_format"),
        ("Color Mode", "color_mode"),
    )
    _ROWS_EXTRA: tuple[tuple[str, str], ...] = (
        ("Rating", "rating"),
        ("Authors", "authors"),
        ("Comments", "comments"),
    )

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("metadataPanel")

        scroll = QScrollArea()
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidgetResizable(True)
        scroll.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        inner = QWidget()
        inner.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        inner_lay = QVBoxLayout(inner)
        inner_lay.setContentsMargins(12, 0, 12, 0)
        inner_lay.setSpacing(0)

        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(0)
        grid.setColumnStretch(1, 1)
        grid.setColumnMinimumWidth(0, 108)

        self._value_labels: dict[str, QLabel] = {}
        row = 0
        for label_text, key in self._ROWS_MAIN:
            row = self._add_metadata_row(grid, row, label_text, key)
        row = self._add_section_divider(grid, row)
        for label_text, key in self._ROWS_EXTRA:
            row = self._add_metadata_row(grid, row, label_text, key)

        inner_lay.addLayout(grid)
        inner_lay.addStretch(1)

        scroll.setWidget(inner)

        self._header = MasonPanelHeader("Metadata")

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._header)
        body = QWidget()
        body_lay = QVBoxLayout(body)
        body_lay.setContentsMargins(0, 8, 0, 0)
        body_lay.setSpacing(0)
        body_lay.addWidget(scroll, 1)
        root.addWidget(body, 1)

        self.setStyleSheet(
            """
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

    def _add_metadata_row(self, grid: QGridLayout, row: int, label_text: str, key: str) -> int:
        kl = QLabel(label_text)
        kl.setObjectName("metadataKey")
        kl.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        kl.setWordWrap(False)
        vl = QLabel("—")
        vl.setObjectName("metadataValue")
        vl.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        wrap = key in ("filename", "authors", "comments")
        vl.setWordWrap(wrap)
        vl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        vl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        kl.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Minimum)
        grid.addWidget(kl, row, 0, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        grid.addWidget(vl, row, 1, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self._value_labels[key] = vl
        return row + 1

    def _add_section_divider(self, grid: QGridLayout, row: int) -> int:
        wrap = QWidget()
        wrap_lay = QVBoxLayout(wrap)
        wrap_lay.setContentsMargins(0, 8, 0, 8)
        wrap_lay.setSpacing(0)
        line = QFrame()
        line.setFrameShape(QFrame.Shape.NoFrame)
        line.setFixedHeight(1)
        line.setStyleSheet("background-color: #666666;")
        wrap_lay.addWidget(line)
        grid.addWidget(wrap, row, 0, 1, 2)
        return row + 1

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
            "rating",
            "authors",
            "comments",
        ):
            if key in self._value_labels:
                self._value_labels[key].setText(summary.get(key, "—"))
