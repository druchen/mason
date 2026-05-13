"""Assign tags to the selected image."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal, QModelIndex
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.core.tags_store import TagsStore


class TagsPanel(QWidget):
    """Checklist of all tags; check to assign to selected image; add/delete/rename tags."""

    tags_changed = Signal()
    tag_order_changed = Signal()

    def __init__(self, store: TagsStore, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._store = store
        self._current_image: str | None = None

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(QLabel("Tags"))

        row = QHBoxLayout()
        self._edit = QLineEdit()
        self._edit.setPlaceholderText("New tag…")
        self._edit.returnPressed.connect(self._add_tag)
        self._add_btn = QPushButton("Add")
        self._add_btn.clicked.connect(lambda: self._add_tag())
        row.addWidget(self._edit)
        row.addWidget(self._add_btn)
        lay.addLayout(row)

        self._list = QListWidget()
        self._list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._list.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self._list.setDragEnabled(True)
        self._list.setAcceptDrops(True)
        self._list.setDropIndicatorShown(True)
        self._list.setDragDropOverwriteMode(False)
        self._list.setDefaultDropAction(Qt.DropAction.MoveAction)
        self._list.itemChanged.connect(self._on_item_changed)
        self._list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._list.customContextMenuRequested.connect(self._show_context_menu)
        self._list.model().rowsMoved.connect(self._on_tag_rows_moved)
        lay.addWidget(self._list)

        self._reload_list()

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def set_selected_image(self, path: str | None) -> None:
        self._current_image = path
        self._sync_checks()

    # ------------------------------------------------------------------
    # Context menu
    # ------------------------------------------------------------------

    def _show_context_menu(self, pos) -> None:
        item = self._list.itemAt(pos)
        if not item:
            return
        menu = QMenu(self)
        rename_act = menu.addAction("Rename…")
        menu.addSeparator()
        delete_act = menu.addAction("Delete tag")
        action = menu.exec(self._list.mapToGlobal(pos))
        if action == rename_act:
            self._rename_tag(item)
        elif action == delete_act:
            self._delete_tag(item)

    def _rename_tag(self, item: QListWidgetItem) -> None:
        tid = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(tid, int):
            return
        new_name, ok = QInputDialog.getText(
            self, "Rename tag", "New name:", text=item.text()
        )
        if not ok or not new_name.strip():
            return
        try:
            self._store.rename_tag(tid, new_name.strip())
        except Exception as exc:
            QMessageBox.warning(self, "Rename failed", str(exc))
            return
        self._reload_list()
        self.tags_changed.emit()

    def _delete_tag(self, item: QListWidgetItem) -> None:
        tid = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(tid, int):
            return
        ret = QMessageBox.question(
            self,
            "Delete tag",
            f'Remove tag "{item.text()}" from all images?',
        )
        if ret != QMessageBox.StandardButton.Yes:
            return
        self._store.delete_tag(tid)
        self._reload_list()
        self.tags_changed.emit()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _reload_list(self) -> None:
        """Rebuild the list from the database, preserving check states."""
        self._list.blockSignals(True)
        self._list.clear()
        for tid, name in self._store.get_all_tags():
            item = QListWidgetItem(name)
            item.setData(Qt.ItemDataRole.UserRole, tid)
            item.setFlags(
                item.flags()
                | Qt.ItemFlag.ItemIsUserCheckable
                | Qt.ItemFlag.ItemIsDragEnabled
            )
            item.setCheckState(Qt.CheckState.Unchecked)
            self._list.addItem(item)
        self._list.blockSignals(False)
        self._sync_checks()

    def _on_tag_rows_moved(
        self,
        parent: QModelIndex,
        start: int,
        end: int,
        destination_parent: QModelIndex,
        destination_row: int,
    ) -> None:
        """After drag-reorder, persist order to SQLite."""
        del parent, start, end, destination_parent, destination_row
        ids: list[int] = []
        for i in range(self._list.count()):
            it = self._list.item(i)
            tid = it.data(Qt.ItemDataRole.UserRole)
            if isinstance(tid, int):
                ids.append(tid)
        if ids:
            self._store.set_tag_order(ids)
        self.tag_order_changed.emit()

    def _sync_checks(self) -> None:
        assigned_ids: set[int] = set()
        if self._current_image:
            assigned_ids = {tid for tid, _ in self._store.get_tags_for_image(self._current_image)}
        self._list.blockSignals(True)
        for i in range(self._list.count()):
            it = self._list.item(i)
            tid = it.data(Qt.ItemDataRole.UserRole)
            if isinstance(tid, int):
                it.setCheckState(
                    Qt.CheckState.Checked if tid in assigned_ids else Qt.CheckState.Unchecked
                )
        self._list.blockSignals(False)

    def _on_item_changed(self, item: QListWidgetItem) -> None:
        if not self._current_image:
            self._sync_checks()
            return
        tid = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(tid, int):
            return
        if item.checkState() == Qt.CheckState.Checked:
            self._store.assign_tag_to_image(self._current_image, tid)
        else:
            self._store.remove_tag_from_image(self._current_image, tid)
        self.tags_changed.emit()

    def _add_tag(self) -> None:
        name = self._edit.text().strip()
        if not name:
            return
        try:
            tid = self._store.add_tag(name)
        except ValueError:
            return
        self._edit.clear()
        if self._current_image:
            self._store.assign_tag_to_image(self._current_image, tid)
        self._reload_list()
        self.tags_changed.emit()
