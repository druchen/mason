"""Assign tags to the selected image: hierarchical tags + context actions."""

from __future__ import annotations

from collections import defaultdict

from PySide6.QtCore import QEvent, QSize, Qt, Signal
from PySide6.QtGui import QMouseEvent, QWheelEvent
from PySide6.QtWidgets import (
    QAbstractItemView,
    QInputDialog,
    QMenu,
    QMessageBox,
    QToolButton,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.core.tags_store import TagsStore
from app.ui.mason_tab_widget import MasonPanelHeader
from app.ui.micro_icons import TAGGING_MODE_TOOLBUTTON_QSS, tag_icon
from app.ui.tag_check_tree import TagCheckTreeWidget


class TagsPanel(QWidget):
    """Tree of tags; check to assign to selected image(s); add/rename/delete via context menu."""

    tags_changed = Signal()
    tag_order_changed = Signal()

    def __init__(self, store: TagsStore, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._store = store
        self._selected_paths: list[str] = []
        self._tree_reload_active = False
        self._wheel_watch: set[QWidget] = set()

        self._tagging_btn = QToolButton()
        self._tagging_btn.setObjectName("tagsTaggingModeBtn")
        self._tagging_btn.setCheckable(True)
        self._tagging_btn.setAutoRaise(True)
        self._tagging_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._tagging_btn.setIcon(tag_icon())
        self._tagging_btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        self._tagging_btn.setIconSize(QSize(16, 16))
        self._tagging_btn.setToolTip("Tagging Mode")
        self._tagging_btn.setAccessibleName("Tagging Mode")
        self._tagging_btn.setStyleSheet(TAGGING_MODE_TOOLBUTTON_QSS)

        self._tree = TagCheckTreeWidget()
        self._tree.setColumnCount(1)
        self._tree.setHeaderHidden(True)
        self._tree.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._tree.setAnimated(True)
        self._tree.setIndentation(14)
        self._tree.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self._tree.setDragEnabled(True)
        self._tree.setAcceptDrops(True)
        self._tree.setDropIndicatorShown(True)
        self._tree.setDragDropOverwriteMode(False)
        self._tree.setDefaultDropAction(Qt.DropAction.MoveAction)
        self._tree.itemChanged.connect(self._on_item_changed)
        self._tree.reordered.connect(self._on_tree_reordered)
        self._tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._tree.customContextMenuRequested.connect(self._show_context_menu)

        self._header = MasonPanelHeader("Tags", self, trailing=self._tagging_btn)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(self._header)
        self._body = QWidget()
        body_lay = QVBoxLayout(self._body)
        body_lay.setContentsMargins(0, 8, 0, 0)
        body_lay.setSpacing(0)
        body_lay.addWidget(self._tree, 1)
        lay.addWidget(self._body, 1)

        self._wheel_watch.add(self)
        self._wheel_watch.add(self._body)
        self._wheel_watch.add(self._tree.viewport())
        self._wheel_watch.add(self._header)
        self._wheel_watch.add(self._header.divider_line())
        self._wheel_watch.update(self._header.findChildren(QWidget))
        for w in self._wheel_watch:
            w.installEventFilter(self)

        self._tagging_btn.toggled.connect(self._on_tagging_mode_toggled)

        # Do not take keyboard focus on click — preview keeps focus for arrow keys / shortcuts.
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._header.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._body.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        self._reload_tree()

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def set_selection(self, paths: list[str], primary: str | None) -> None:
        """``paths`` are all selected preview images; ``primary`` is the focused row (metadata path)."""
        seen: set[str] = set()
        ordered: list[str] = []
        for p in paths:
            if not p or p in seen:
                continue
            seen.add(p)
            ordered.append(p)
        if primary and primary not in seen:
            seen.add(primary)
            ordered.append(primary)
        self._selected_paths = ordered
        self._sync_checks()

    def eventFilter(self, obj, event) -> bool:  # type: ignore[override]
        if obj not in self._wheel_watch:
            return super().eventFilter(obj, event)
        if not self._tagging_btn.isChecked():
            return super().eventFilter(obj, event)
        if event.type() == QEvent.Type.Wheel and isinstance(event, QWheelEvent):
            self._tagging_handle_wheel(event)
            return True
        if event.type() == QEvent.Type.MouseButtonRelease and isinstance(event, QMouseEvent):
            if event.button() == Qt.MouseButton.MiddleButton:
                cur = self._tree.currentItem()
                if cur is not None:
                    self._on_middle_toggle_tag(cur)
                    return True
        return super().eventFilter(obj, event)

    def _on_tagging_mode_toggled(self, on: bool) -> None:
        if on and self._tree.currentItem() is None:
            rows = self._flatten_tag_items()
            if rows:
                self._tree.setCurrentItem(rows[0])
                self._tree.scrollToItem(rows[0], QAbstractItemView.ScrollHint.EnsureVisible)

    def _flatten_tag_items(self) -> list[QTreeWidgetItem]:
        out: list[QTreeWidgetItem] = []

        def walk(it: QTreeWidgetItem) -> None:
            tid = it.data(0, Qt.ItemDataRole.UserRole)
            if isinstance(tid, int):
                out.append(it)
            for i in range(it.childCount()):
                walk(it.child(i))

        for i in range(self._tree.topLevelItemCount()):
            walk(self._tree.topLevelItem(i))
        return out

    def _tagging_handle_wheel(self, event: QWheelEvent) -> None:
        items = self._flatten_tag_items()
        if not items:
            return
        cur = self._tree.currentItem()
        if cur is not None and cur in items:
            idx = items.index(cur)
        else:
            idx = 0
        dy = event.pixelDelta().y()
        if dy == 0:
            dy = event.angleDelta().y()
        if dy > 0:
            idx = max(0, idx - 1)
        elif dy < 0:
            idx = min(len(items) - 1, idx + 1)
        else:
            return
        nxt = items[idx]
        self._tree.setCurrentItem(nxt)
        self._tree.scrollToItem(nxt, QAbstractItemView.ScrollHint.EnsureVisible)

    def _on_middle_toggle_tag(self, item: QTreeWidgetItem | None) -> None:
        if not self._tagging_btn.isChecked():
            return
        if item is None:
            return
        if not (item.flags() & Qt.ItemFlag.ItemIsUserCheckable):
            return
        tid = item.data(0, Qt.ItemDataRole.UserRole)
        if not isinstance(tid, int):
            return
        self._toggle_item_check(item)

    def _toggle_item_check(self, item: QTreeWidgetItem) -> None:
        if item.checkState(0) == Qt.CheckState.Checked:
            item.setCheckState(0, Qt.CheckState.Unchecked)
        else:
            item.setCheckState(0, Qt.CheckState.Checked)

    # ------------------------------------------------------------------
    # Context menu
    # ------------------------------------------------------------------

    def _show_context_menu(self, pos) -> None:
        item = self._tree.itemAt(pos)
        menu = QMenu(self)
        if item is None:
            add_root = menu.addAction("Add Tag")
            menu.addSeparator()
            collapse = menu.addAction("Collapse All")
            expand = menu.addAction("Expand All")
            chosen = menu.exec(self._tree.viewport().mapToGlobal(pos))
            if chosen == add_root:
                self._prompt_add_tag(parent_id=None)
            elif chosen == collapse:
                self._tree.collapseAll()
            elif chosen == expand:
                self._tree.expandAll()
            return

        add_root = menu.addAction("Add Tag")
        add_sub = menu.addAction("Add Sub Tag")
        menu.addSeparator()
        rename_act = menu.addAction("Rename…")
        delete_act = menu.addAction("Delete tag")
        chosen = menu.exec(self._tree.viewport().mapToGlobal(pos))
        if chosen == add_root:
            self._prompt_add_tag(parent_id=None)
        elif chosen == add_sub:
            tid = item.data(0, Qt.ItemDataRole.UserRole)
            if isinstance(tid, int):
                self._prompt_add_tag(parent_id=tid)
        elif chosen == rename_act:
            self._rename_tag(item)
        elif chosen == delete_act:
            self._delete_tag(item)

    def _prompt_add_tag(self, parent_id: int | None) -> None:
        title = "Add Sub Tag" if parent_id is not None else "Add Tag"
        label = "Tag name:"
        name, ok = QInputDialog.getText(self, title, label)
        if not ok or not name.strip():
            return
        try:
            tid = self._store.add_tag(name.strip(), parent_id)
        except ValueError as exc:
            QMessageBox.warning(self, "Add tag failed", str(exc))
            return
        if tid == 0:
            QMessageBox.information(self, "Add tag", "A tag with that name already exists.")
            return
        for p in self._selected_paths:
            self._store.assign_tag_to_image(p, tid)
        self._reload_tree()
        self._expand_through_parent(parent_id)
        self.tags_changed.emit()
        self.tag_order_changed.emit()

    def _on_tree_reordered(self) -> None:
        if self._tree_reload_active:
            return
        self._persist_tree_layout()
        self.tag_order_changed.emit()

    def _persist_tree_layout(self) -> None:
        layout: list[tuple[int, int | None, int]] = []

        def walk(parent_item: QTreeWidgetItem | None, parent_tid: int | None) -> None:
            n = parent_item.childCount() if parent_item is not None else self._tree.topLevelItemCount()
            for i in range(n):
                it = parent_item.child(i) if parent_item is not None else self._tree.topLevelItem(i)
                raw = it.data(0, Qt.ItemDataRole.UserRole)
                if not isinstance(raw, int):
                    continue
                layout.append((raw, parent_tid, i))
                walk(it, raw)

        walk(None, None)
        self._store.apply_tag_tree_layout(layout)

    def _expand_through_parent(self, parent_id: int | None) -> None:
        if parent_id is None:
            return
        rows = self._store.get_tag_tree_rows()
        parent_of: dict[int, int | None] = {tid: p for tid, _, p, _ in rows}
        chain: list[int] = []
        pid: int | None = parent_id
        seen: set[int] = set()
        while pid is not None and pid not in seen:
            seen.add(pid)
            chain.append(pid)
            pid = parent_of.get(pid)
        for tid in reversed(chain):
            it = self._find_item_by_tag_id(tid)
            if it is not None:
                it.setExpanded(True)

    def _find_item_by_tag_id(self, tag_id: int) -> QTreeWidgetItem | None:
        def walk(it: QTreeWidgetItem) -> QTreeWidgetItem | None:
            tid = it.data(0, Qt.ItemDataRole.UserRole)
            if tid == tag_id:
                return it
            for i in range(it.childCount()):
                found = walk(it.child(i))
                if found is not None:
                    return found
            return None

        for i in range(self._tree.topLevelItemCount()):
            found = walk(self._tree.topLevelItem(i))
            if found is not None:
                return found
        return None

    def _rename_tag(self, item: QTreeWidgetItem) -> None:
        tid = item.data(0, Qt.ItemDataRole.UserRole)
        if not isinstance(tid, int):
            return
        base_name = item.text(0)
        new_name, ok = QInputDialog.getText(
            self, "Rename tag", "New name:", text=base_name
        )
        if not ok or not new_name.strip():
            return
        try:
            self._store.rename_tag(tid, new_name.strip())
        except Exception as exc:
            QMessageBox.warning(self, "Rename failed", str(exc))
            return
        self._reload_tree()
        self.tags_changed.emit()
        self.tag_order_changed.emit()

    def _delete_tag(self, item: QTreeWidgetItem) -> None:
        tid = item.data(0, Qt.ItemDataRole.UserRole)
        if not isinstance(tid, int):
            return
        base_name = item.text(0)
        n_tree = self._store.subtree_tag_count_including_root(tid)
        if n_tree > 1:
            msg = (
                f'Remove tag "{base_name}" and {n_tree - 1} nested sub-tag(s) from the library '
                "and from all images?"
            )
        else:
            msg = f'Remove tag "{base_name}" from the library and from all images?'
        ret = QMessageBox.question(self, "Delete tag", msg)
        if ret != QMessageBox.StandardButton.Yes:
            return
        self._store.delete_tag(tid)
        self._reload_tree()
        self.tags_changed.emit()
        self.tag_order_changed.emit()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _reload_tree(self) -> None:
        expanded: set[int] = set()
        if self._tree.topLevelItemCount() > 0:
            expanded = self._collect_expanded_tag_ids()

        rows = self._store.get_tag_tree_rows()
        by_parent: dict[int | None, list[tuple[int, str, int]]] = defaultdict(list)
        for tid, name, pid, sort_order in rows:
            by_parent[pid].append((tid, name, sort_order))
        for lst in by_parent.values():
            lst.sort(key=lambda x: (x[2], x[1].casefold()))

        self._tree_reload_active = True
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
                    | Qt.ItemFlag.ItemIsDragEnabled
                    | Qt.ItemFlag.ItemIsDropEnabled
                )
                it.setCheckState(0, Qt.CheckState.Unchecked)
                if parent_item is None:
                    self._tree.addTopLevelItem(it)
                else:
                    parent_item.addChild(it)
                add_children(it, tid)

        add_children(None, None)
        self._tree.blockSignals(False)
        self._tree_reload_active = False
        self._apply_expanded_tag_ids(expanded)
        self._sync_checks()

    def _collect_expanded_tag_ids(self) -> set[int]:
        out: set[int] = set()

        def walk(it: QTreeWidgetItem) -> None:
            tid = it.data(0, Qt.ItemDataRole.UserRole)
            if isinstance(tid, int) and it.isExpanded():
                out.add(tid)
            for i in range(it.childCount()):
                walk(it.child(i))

        for i in range(self._tree.topLevelItemCount()):
            walk(self._tree.topLevelItem(i))
        return out

    def _apply_expanded_tag_ids(self, ids: set[int]) -> None:
        if not ids:
            return

        def walk(it: QTreeWidgetItem) -> None:
            tid = it.data(0, Qt.ItemDataRole.UserRole)
            if isinstance(tid, int) and tid in ids:
                it.setExpanded(True)
            for i in range(it.childCount()):
                walk(it.child(i))

        for i in range(self._tree.topLevelItemCount()):
            walk(self._tree.topLevelItem(i))

    def _sync_checks(self) -> None:
        paths = self._selected_paths
        tag_by_path: dict[str, set[int]] = {}
        if paths:
            tag_by_path = {
                p: {tid for tid, _ in self._store.get_tags_for_image(p)} for p in paths
            }
        self._tree.blockSignals(True)

        def walk(it: QTreeWidgetItem) -> None:
            tid = it.data(0, Qt.ItemDataRole.UserRole)
            if isinstance(tid, int):
                if not paths:
                    st = Qt.CheckState.Unchecked
                elif len(paths) == 1:
                    only = paths[0]
                    st = (
                        Qt.CheckState.Checked
                        if tid in tag_by_path.get(only, set())
                        else Qt.CheckState.Unchecked
                    )
                else:
                    n = sum(1 for p in paths if tid in tag_by_path.get(p, set()))
                    if n == 0:
                        st = Qt.CheckState.Unchecked
                    elif n == len(paths):
                        st = Qt.CheckState.Checked
                    else:
                        st = Qt.CheckState.PartiallyChecked
                it.setCheckState(0, st)
            for i in range(it.childCount()):
                walk(it.child(i))

        for i in range(self._tree.topLevelItemCount()):
            walk(self._tree.topLevelItem(i))
        self._tree.blockSignals(False)

    def _on_item_changed(self, item: QTreeWidgetItem, column: int) -> None:
        if column != 0:
            return
        if not self._selected_paths:
            self._sync_checks()
            return
        state = item.checkState(0)
        if state == Qt.CheckState.PartiallyChecked:
            return
        tid = item.data(0, Qt.ItemDataRole.UserRole)
        if not isinstance(tid, int):
            return
        parent_item = item.parent()
        parent_tid = parent_item.data(0, Qt.ItemDataRole.UserRole) if parent_item else None
        if not isinstance(parent_tid, int):
            parent_tid = None
        for image_path in self._selected_paths:
            if state == Qt.CheckState.Checked:
                self._store.assign_tag_to_image(image_path, tid)
                if parent_tid is not None:
                    self._store.assign_tag_to_image(image_path, parent_tid)
            else:
                self._store.remove_tag_from_image(image_path, tid)
        self._sync_checks()
        self.tags_changed.emit()
