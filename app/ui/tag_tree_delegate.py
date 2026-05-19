"""Inline tag rename/add editor aligned to the tree item text rect."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QModelIndex, QRect, Qt
from PySide6.QtWidgets import (
    QApplication,
    QLineEdit,
    QStyle,
    QStyleOptionViewItem,
    QStyledItemDelegate,
)

from shiboken6 import isValid as _qt_valid

from app.ui.inline_field import make_inline_line_edit

if TYPE_CHECKING:
    from app.ui.tags_panel import TagsPanel

_PLACEHOLDER_ROLE = Qt.ItemDataRole.UserRole + 1
_SELECT_ALL_ROLE = Qt.ItemDataRole.UserRole + 2


class TagTreeNameDelegate(QStyledItemDelegate):
    """Places a compact line edit exactly where tag labels are drawn."""

    def __init__(self, panel: TagsPanel) -> None:
        super().__init__(panel._tree)
        self._panel = panel

    def createEditor(
        self,
        parent,
        option: QStyleOptionViewItem,
        index: QModelIndex,
    ) -> QLineEdit:
        ph = index.data(_PLACEHOLDER_ROLE) or "Tag name"
        text = index.data(Qt.ItemDataRole.DisplayRole) or ""
        host = option.widget
        if host is not None:
            parent = host.viewport()
        edit = make_inline_line_edit(
            parent,
            object_name="tagInlineEdit",
            placeholder=str(ph),
            text=str(text),
            compact=True,
        )
        self._panel._on_inline_editor_created(edit, index)
        return edit

    def setEditorData(self, editor: QLineEdit, index: QModelIndex) -> None:  # noqa: ARG002
        del editor, index

    def setModelData(self, editor: QLineEdit, model, index: QModelIndex) -> None:  # noqa: ARG002
        del model, index
        if self._panel._inline_skip_delegate_commit or self._panel._inline_finishing:
            return
        text = editor.text().strip() if _qt_valid(editor) else ""
        if self._panel.finish_inline_edit(text):
            self._panel._close_inline_editor_widget()

    def updateEditorGeometry(
        self,
        editor: QLineEdit,
        option: QStyleOptionViewItem,
        index: QModelIndex,  # noqa: ARG002
    ) -> None:
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        widget = option.widget
        style = widget.style() if widget else QApplication.style()
        text_rect = style.subElementRect(
            QStyle.SubElement.SE_ItemViewItemText,
            opt,
            widget,
        )
        eh = editor.sizeHint().height()
        h = min(eh, max(16, text_rect.height()))
        y = text_rect.y() + max(0, (text_rect.height() - h) // 2)
        editor.setGeometry(
            QRect(
                text_rect.x(),
                y,
                max(48, text_rect.width()),
                h,
            )
        )
