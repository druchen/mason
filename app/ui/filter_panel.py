"""Filter preview by tags (match mode + clear checkboxes)."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QLabel,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.core.sort_filter import TagMatchMode
from app.core.tags_store import TagsStore
from app.ui.tag_checkbox_list import TagCheckListWidget

_UNCHECK_ALL = "__uncheck_all__"


class FilterPanel(QWidget):
    filter_changed = Signal()

    def __init__(self, store: TagsStore, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._store = store

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(QLabel("Filter"))

        self._mode = QComboBox()
        self._mode.addItem("Match All Checked", "all")
        self._mode.addItem("Match Any Checked", "any")
        self._mode.addItem("Uncheck All", _UNCHECK_ALL)
        self._mode.currentIndexChanged.connect(self._on_mode_changed)
        lay.addWidget(self._mode)

        self._list = TagCheckListWidget()
        self._list.itemChanged.connect(lambda _: self.filter_changed.emit())
        lay.addWidget(self._list)

        self.reload_tags()

    def _on_mode_changed(self, _index: int) -> None:
        data = self._mode.currentData()
        if data == _UNCHECK_ALL:
            self._list.blockSignals(True)
            for i in range(self._list.count()):
                self._list.item(i).setCheckState(Qt.CheckState.Unchecked)
            self._list.blockSignals(False)
            self._mode.blockSignals(True)
            self._mode.setCurrentIndex(0)
            self._mode.blockSignals(False)
            self.filter_changed.emit()
            return
        self.filter_changed.emit()

    def tag_match_mode(self) -> TagMatchMode:
        data = self._mode.currentData()
        if data == "any":
            return "any"
        return "all"

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
