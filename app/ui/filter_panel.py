"""Filter preview by tags (must match all checked)."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QLabel, QListWidget, QListWidgetItem, QVBoxLayout, QWidget

from app.core.tags_store import TagsStore


class FilterPanel(QWidget):
    filter_changed = Signal()

    def __init__(self, store: TagsStore, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._store = store

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(QLabel("Filter by tags"))
        lay.addWidget(QLabel("(match all checked)"))

        self._list = QListWidget()
        self._list.itemChanged.connect(lambda _: self.filter_changed.emit())
        lay.addWidget(self._list)

        self.reload_tags()

    def reload_tags(self) -> None:
        checked = set(self.selected_tag_ids())
        self._list.blockSignals(True)
        self._list.clear()
        for tid, name in self._store.get_all_tags():
            item = QListWidgetItem(name)
            item.setData(Qt.ItemDataRole.UserRole, tid)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(
                Qt.CheckState.Checked if tid in checked else Qt.CheckState.Unchecked
            )
            self._list.addItem(item)
        self._list.blockSignals(False)

    def selected_tag_ids(self) -> list[int]:
        ids: list[int] = []
        for i in range(self._list.count()):
            it = self._list.item(i)
            if it.checkState() == Qt.CheckState.Checked:
                tid = it.data(Qt.ItemDataRole.UserRole)
                if isinstance(tid, int):
                    ids.append(tid)
        return ids
