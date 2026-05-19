"""Shared QLineEdit styling for toolbar search, folder path, and inline tree edits."""

from __future__ import annotations

from PySide6.QtGui import QColor, QFontMetrics, QPalette
from PySide6.QtWidgets import QLineEdit, QWidget

_INLINE_BORDER = "#383838"
_INLINE_BORDER_HOVER = "#4a4a4a"
_INLINE_BORDER_FOCUS = "#357abd"


def inline_line_edit_stylesheet(object_name: str) -> str:
    return f"""
    QLineEdit#{object_name} {{
        background-color: #1a1a1a;
        border: 0.5px solid {_INLINE_BORDER};
        border-radius: 4px;
        padding-top: 2px;
        padding-bottom: 2px;
        padding-left: 4px;
        padding-right: 4px;
        color: #ececec;
        selection-background-color: #5ab4f5;
        selection-color: #ffffff;
    }}
    QLineEdit#{object_name}:hover:!focus {{
        border: 0.5px solid {_INLINE_BORDER_HOVER};
    }}
    QLineEdit#{object_name}:focus {{
        border: 0.5px solid {_INLINE_BORDER_FOCUS};
    }}
    """


def inline_line_edit_height(widget: QWidget) -> int:
    fm = QFontMetrics(widget.font())
    return max(22, min(28, fm.height() + 10))


def compact_inline_line_edit_height(widget: QWidget) -> int:
    """Shorter field for tree rows (tag add/rename)."""
    fm = QFontMetrics(widget.font())
    return max(18, min(22, fm.height() + 4))


def make_inline_line_edit(
    parent: QWidget | None,
    *,
    object_name: str = "inlineFieldEdit",
    placeholder: str = "",
    text: str = "",
    compact: bool = False,
) -> QLineEdit:
    edit = QLineEdit(parent)
    edit.setObjectName(object_name)
    edit.setPlaceholderText(placeholder)
    edit.setText(text)
    pal = edit.palette()
    pal.setColor(QPalette.ColorGroup.All, QPalette.ColorRole.PlaceholderText, QColor(140, 140, 140))
    edit.setPalette(pal)
    if compact:
        edit.setStyleSheet(
            inline_line_edit_stylesheet(object_name).replace(
                "padding-top: 2px;\n        padding-bottom: 2px;",
                "padding-top: 1px;\n        padding-bottom: 1px;",
            )
        )
        edit.setFixedHeight(compact_inline_line_edit_height(edit))
    else:
        edit.setStyleSheet(inline_line_edit_stylesheet(object_name))
        edit.setFixedHeight(inline_line_edit_height(edit))
    return edit
