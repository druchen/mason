"""Assign tags to the selected image: hierarchical tags + context actions."""

from __future__ import annotations

from collections import defaultdict

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QInputDialog,
    QMenu,
    QMessageBox,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.core.tags_store import TagsStore
from app.ui.mason_tab_widget import MasonTabWidget
from app.ui.tag_check_tree import TagCheckTreeWidget


class TagsPanel(QWidget):
    """Tree of tags; check to assign to selected image; add/rename/delete via context menu."""

    tags_changed = Signal()
    tag_order_changed = Signal()

    def __init__(self, store: TagsStore, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._store = store
        self._current_image: str | None = None
        self._tree_reload_active = False

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

        self._tabs = MasonTabWidget()
        self._tabs.addTab(self._tree, "Tags")

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self._tabs, 1)

        self._reload_tree()

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
        if self._current_image:
            self._store.assign_tag_to_image(self._current_image, tid)
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
        assigned_ids: set[int] = set()
        if self._current_image:
            assigned_ids = {tid for tid, _ in self._store.get_tags_for_image(self._current_image)}
        self._tree.blockSignals(True)

        def walk(it: QTreeWidgetItem) -> None:
            tid = it.data(0, Qt.ItemDataRole.UserRole)
            if isinstance(tid, int):
                it.setCheckState(
                    0,
                    Qt.CheckState.Checked if tid in assigned_ids else Qt.CheckState.Unchecked,
                )
            for i in range(it.childCount()):
                walk(it.child(i))

        for i in range(self._tree.topLevelItemCount()):
            walk(self._tree.topLevelItem(i))
        self._tree.blockSignals(False)

    def _on_item_changed(self, item: QTreeWidgetItem, column: int) -> None:
        if column != 0:
            return
        if not self._current_image:
            self._sync_checks()
            return
        tid = item.data(0, Qt.ItemDataRole.UserRole)
        if not isinstance(tid, int):
            return
        parent_item = item.parent()
        parent_tid = parent_item.data(0, Qt.ItemDataRole.UserRole) if parent_item else None
        if not isinstance(parent_tid, int):
            parent_tid = None
        if item.checkState(0) == Qt.CheckState.Checked:
            self._store.assign_tag_to_image(self._current_image, tid)
            if parent_tid is not None:
                self._store.assign_tag_to_image(self._current_image, parent_tid)
        else:
            self._store.remove_tag_from_image(self._current_image, tid)
        self._sync_checks()
        self.tags_changed.emit()
