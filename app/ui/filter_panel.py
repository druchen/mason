"""Filter preview by tags (match mode + clear checkboxes)."""

from __future__ import annotations

from collections import defaultdict

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QFontMetrics, QIcon, QMouseEvent
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QToolButton,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.core.sort_filter import TagMatchMode
from app.core.tags_store import TagsStore
from app.ui.micro_icons import ICON_TOOLBUTTON_QSS, chevron_down_small_pm, no_sign_pm
from app.ui.tag_check_tree import TagCheckTreeWidget

_FILTER_POPUP_WIDTH_PX = 140
_TOOLBAR_BORDER = "#383838"
_TOOLBAR_BORDER_HOVER = "#4a4a4a"


class _FilterArrowLabel(QLabel):
    def __init__(self, combo: QComboBox, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._combo = combo
        self.setObjectName("filterControlArrow")
        self.setAutoFillBackground(False)
        self.setPixmap(chevron_down_small_pm())
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("Choose filter mode…")

    def mousePressEvent(self, event: QMouseEvent) -> None:  # type: ignore[override]
        if event.button() == Qt.MouseButton.LeftButton:
            self._combo.setFocus()
            self._combo.showPopup()
        super().mousePressEvent(event)


class FilterPanel(QWidget):
    filter_changed = Signal()

    def __init__(self, store: TagsStore, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._store = store

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)

        lay.addWidget(QLabel("Filter"))

        row = QWidget()
        row_lay = QHBoxLayout(row)
        row_lay.setContentsMargins(0, 0, 0, 0)
        row_lay.setSpacing(3)

        self._frame = QFrame()
        self._frame.setObjectName("filterControlFrame")
        inner = QHBoxLayout(self._frame)
        inner.setContentsMargins(0, 0, 3, 0)
        inner.setSpacing(1)

        self._prefix = QLabel("Filter by")
        self._prefix.setObjectName("filterControlPrefix")
        inner.addWidget(self._prefix, 0, Qt.AlignmentFlag.AlignVCenter)

        self._mode = QComboBox()
        self._mode.setObjectName("filterControlCombo")
        self._mode.addItem("All Checked", "all")
        self._mode.addItem("Any Checked", "any")
        self._mode.currentIndexChanged.connect(lambda _: self.filter_changed.emit())
        self._mode.setMinimumWidth(56)
        inner.addWidget(self._mode, 1)

        self._arrow = _FilterArrowLabel(self._mode, self._frame)
        inner.addWidget(self._arrow, 0, Qt.AlignmentFlag.AlignVCenter)

        self._apply_frame_style()

        self._clear_btn = QToolButton()
        self._clear_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._clear_btn.setAutoRaise(True)
        self._clear_btn.setCheckable(False)
        self._clear_btn.setIcon(QIcon(no_sign_pm(14)))
        self._clear_btn.setStyleSheet(ICON_TOOLBUTTON_QSS)
        self._clear_btn.setToolTip("Clear Filter")
        self._clear_btn.clicked.connect(self._on_clear_filter_clicked)

        row_lay.addWidget(self._frame, 0)
        row_lay.addWidget(self._clear_btn, 0)
        lay.addWidget(row)

        self._tree = TagCheckTreeWidget()
        self._tree.setColumnCount(1)
        self._tree.setHeaderHidden(True)
        self._tree.setIndentation(14)
        self._tree.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._tree.setDragDropMode(QAbstractItemView.DragDropMode.NoDragDrop)
        self._tree.setDragEnabled(False)
        self._tree.setAcceptDrops(False)
        self._tree.itemChanged.connect(self._on_tree_item_changed)
        lay.addWidget(self._tree)

        self._configure_popup_width()
        self._sync_filter_row_height()
        self.reload_tags()

    def _apply_frame_style(self) -> None:
        self._frame.setStyleSheet(
            f"""
            QFrame#filterControlFrame {{
                background-color: #1a1a1a;
                border: 0.5px solid {_TOOLBAR_BORDER};
                border-radius: 3px;
            }}
            QFrame#filterControlFrame:hover {{
                border: 0.5px solid {_TOOLBAR_BORDER_HOVER};
            }}
            QLabel#filterControlPrefix {{
                color: #8c8c8c;
                background: transparent;
                border: none;
                padding-left: 4px;
                padding-right: 0px;
            }}
            QLabel#filterControlArrow {{
                background: transparent;
                border: none;
            }}
            QComboBox#filterControlCombo {{
                border: none;
                background: transparent;
                color: #8c8c8c;
                padding: 0px 2px;
                min-height: 0px;
            }}
            QComboBox#filterControlCombo::drop-down {{
                width: 0px;
                height: 0px;
                border: none;
            }}
            """
        )

    def _configure_popup_width(self) -> None:
        view = self._mode.view()
        if view is None:
            return
        view.setFixedWidth(_FILTER_POPUP_WIDTH_PX)
        view.setTextElideMode(Qt.TextElideMode.ElideNone)

    def _sync_filter_row_height(self) -> None:
        fm = QFontMetrics(self.font())
        h = max(17, min(21, fm.height() + 4))
        self._frame.setFixedHeight(h)
        self._arrow.setFixedSize(11, h)
        self._clear_btn.setFixedSize(max(20, h), h)
        self._clear_btn.setIconSize(QSize(12, 12))

    def _on_tree_item_changed(self, item: QTreeWidgetItem, column: int) -> None:
        if column != 0:
            return
        if item.checkState(0) == Qt.CheckState.Checked:
            parent = item.parent()
            if parent is not None and parent.checkState(0) != Qt.CheckState.Checked:
                self._tree.blockSignals(True)
                parent.setCheckState(0, Qt.CheckState.Checked)
                self._tree.blockSignals(False)
        self.filter_changed.emit()

    def _on_clear_filter_clicked(self) -> None:
        self._tree.blockSignals(True)

        def walk(it: QTreeWidgetItem) -> None:
            it.setCheckState(0, Qt.CheckState.Unchecked)
            for i in range(it.childCount()):
                walk(it.child(i))

        for i in range(self._tree.topLevelItemCount()):
            walk(self._tree.topLevelItem(i))
        self._tree.blockSignals(False)
        self.filter_changed.emit()

    def tag_match_mode(self) -> TagMatchMode:
        data = self._mode.currentData()
        if data == "any":
            return "any"
        return "all"

    def reload_tags(self) -> None:
        checked = set(self.selected_tag_ids())
        rows = self._store.get_tag_tree_rows()
        by_parent: dict[int | None, list[tuple[int, str, int]]] = defaultdict(list)
        for tid, name, pid, sort_order in rows:
            by_parent[pid].append((tid, name, sort_order))
        for lst in by_parent.values():
            lst.sort(key=lambda x: (x[2], x[1].casefold()))

        self._tree.blockSignals(True)
        self._tree.clear()

        def add_children(parent_item: QTreeWidgetItem | None, pid: int | None) -> None:
            for tid, name, _so in by_parent.get(pid, []):
                it = QTreeWidgetItem()
                it.setText(0, name)
                it.setData(0, Qt.ItemDataRole.UserRole, tid)
                it.setFlags(
                    it.flags()
                    | Qt.ItemFlag.ItemIsUserCheckable
                    | Qt.ItemFlag.ItemIsEnabled
                    | Qt.ItemFlag.ItemIsSelectable
                )
                it.setCheckState(
                    0,
                    Qt.CheckState.Checked if tid in checked else Qt.CheckState.Unchecked,
                )
                if parent_item is None:
                    self._tree.addTopLevelItem(it)
                else:
                    parent_item.addChild(it)
                add_children(it, tid)

        add_children(None, None)
        self._tree.expandAll()
        self._tree.blockSignals(False)

    def selected_tag_ids(self) -> list[int]:
        ids: list[int] = []

        def walk(it: QTreeWidgetItem) -> None:
            tid = it.data(0, Qt.ItemDataRole.UserRole)
            if isinstance(tid, int) and it.checkState(0) == Qt.CheckState.Checked:
                ids.append(tid)
            for i in range(it.childCount()):
                walk(it.child(i))

        for i in range(self._tree.topLevelItemCount()):
            walk(self._tree.topLevelItem(i))
        return ids
