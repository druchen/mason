"""Assign tags to the selected image: hierarchical tags + context actions."""

from __future__ import annotations

from collections import defaultdict
from typing import Literal

from PySide6.QtCore import QEvent, QPoint, QSize, Qt, Signal, QTimer
from PySide6.QtGui import QKeyEvent, QMouseEvent, QWheelEvent
from PySide6.QtWidgets import (
    QAbstractItemDelegate,
    QAbstractItemView,
    QApplication,
    QHBoxLayout,
    QLineEdit,
    QMenu,
    QMessageBox,
    QToolButton,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)
from shiboken6 import isValid as _qt_valid

from app.core.tags_store import TagsStore
from app.ui.context_menus import style_context_menu
from app.ui.mason_tab_widget import MasonPanelHeader
from app.ui.micro_icons import (
    ICON_TOOLBUTTON_QSS,
    TAGGING_MODE_TOOLBUTTON_QSS,
    scan_tags_icon,
    tag_icon,
)
from app.ui.tag_check_tree import TagCheckTreeWidget
from app.ui.tag_tree_delegate import (
    TagTreeNameDelegate,
    _PLACEHOLDER_ROLE,
    _SELECT_ALL_ROLE,
)

_InlineMode = Literal["add", "rename"]


class TagsPanel(QWidget):
    """Tree of tags; check to assign to selected image(s); add/rename/delete via context menu."""

    tags_changed = Signal()
    tag_order_changed = Signal()
    scan_tags_requested = Signal()

    def __init__(self, store: TagsStore, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._store = store
        self._selected_paths: list[str] = []
        self._tree_reload_active = False
        self._wheel_watch: set[QWidget] = set()
        self._inline_click_watch: set[QWidget] = set()
        self._inline_item: QTreeWidgetItem | None = None
        self._inline_mode: _InlineMode | None = None
        self._inline_add_parent_id: int | None = None
        self._inline_rename_original = ""
        self._inline_line_edit = None
        self._inline_finishing = False
        self._inline_blur_commit_scheduled = False
        self._inline_suppress_blur = False
        self._inline_skip_delegate_commit = False

        self._scan_btn = QToolButton()
        self._scan_btn.setObjectName("tagsScanBtn")
        self._scan_btn.setAutoRaise(True)
        self._scan_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._scan_btn.setIcon(scan_tags_icon())
        self._scan_btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        self._scan_btn.setIconSize(QSize(12, 12))
        self._scan_btn.setToolTip("Scan & Add Tags")
        self._scan_btn.setAccessibleName("Scan and Add Tags")
        self._scan_btn.setStyleSheet(
            ICON_TOOLBUTTON_QSS
            + """
QToolButton#tagsScanBtn {
    padding: 0px;
    min-width: 18px;
    max-width: 18px;
    min-height: 18px;
    max-height: 18px;
}
"""
        )

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
        self._tree.setItemDelegate(TagTreeNameDelegate(self))
        self._tree.set_tags_panel(self)

        header_actions = QWidget()
        header_actions.setObjectName("tagsHeaderActions")
        header_actions.setStyleSheet("background-color: #1f1f1f;")
        header_actions_lay = QHBoxLayout(header_actions)
        header_actions_lay.setContentsMargins(0, 0, 0, 0)
        header_actions_lay.setSpacing(2)
        header_actions_lay.addWidget(self._scan_btn)
        header_actions_lay.addWidget(self._tagging_btn)
        self._header = MasonPanelHeader("Tags", self, trailing=header_actions)

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

        for w in (
            self,
            self._body,
            self._tree,
            self._tree.viewport(),
            self._tree.verticalScrollBar(),
            self._tree.horizontalScrollBar(),
            self._header,
            self._header.divider_line(),
        ):
            self._wheel_watch.add(w)
            self._inline_click_watch.add(w)
        self._wheel_watch.update(self._header.findChildren(QWidget))
        for w in self._wheel_watch:
            w.installEventFilter(self)

        self._scan_btn.clicked.connect(self.scan_tags_requested.emit)
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

    def reload_tree_from_store(self) -> None:
        """Rebuild the tag tree after the store changed without going through this panel."""
        self._reload_tree()
        self._sync_checks()

    def set_scan_busy(self, busy: bool) -> None:
        self._scan_btn.setEnabled(not busy)

    def sync_checks_from_store(self) -> None:
        """Refresh row checkboxes from SQLite (tag list shape unchanged)."""
        self._sync_checks()

    def rename_focused_tag(self) -> bool:
        """Start inline rename for the current/selected tag (e.g. F2). Returns False if none."""
        if self._is_inline_editing():
            return False
        item = self._tree.currentItem()
        if item is None:
            selected = self._tree.selectedItems()
            if selected:
                item = selected[-1]
        if item is None:
            return False
        tid = item.data(0, Qt.ItemDataRole.UserRole)
        if not isinstance(tid, int):
            return False
        self._start_inline_rename(tid)
        return True

    def eventFilter(self, obj, event) -> bool:  # type: ignore[override]
        edit = self._inline_line_edit
        if edit is not None and obj is edit and _qt_valid(edit):
            if (
                event.type() == QEvent.Type.KeyPress
                and isinstance(event, QKeyEvent)
                and event.key() == Qt.Key.Key_Escape
            ):
                if self._is_inline_editing():
                    self._close_inline_editor_widget(
                        QAbstractItemDelegate.EndEditHint.RevertModelCache
                    )
                return True
            return False
        if (
            obj in self._inline_click_watch
            and event.type() == QEvent.Type.MouseButtonPress
            and isinstance(event, QMouseEvent)
            and event.button() == Qt.MouseButton.LeftButton
        ):
            self._maybe_commit_inline_on_click(event)
        if obj not in self._wheel_watch:
            return super().eventFilter(obj, event)
        if not self._tagging_btn.isChecked():
            return super().eventFilter(obj, event)
        if event.type() == QEvent.Type.Wheel and isinstance(event, QWheelEvent):
            self._tagging_handle_wheel(event)
            return True
        if isinstance(event, QMouseEvent) and event.button() == Qt.MouseButton.MiddleButton:
            # Swallow middle-button press/double-click so Qt does not move the current row;
            # only the active tag (currentItem) is toggled on release, from any panel hit.
            if event.type() in (
                QEvent.Type.MouseButtonPress,
                QEvent.Type.MouseButtonDblClick,
            ):
                return True
            if event.type() == QEvent.Type.MouseButtonRelease:
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
        if self._inline_item is not None:
            self._inline_suppress_blur = True
            self._cancel_inline_edit()
            self._inline_suppress_blur = False

        item = self._tree.itemAt(pos)
        tag_id: int | None = None
        if item is not None:
            raw = item.data(0, Qt.ItemDataRole.UserRole)
            if isinstance(raw, int):
                tag_id = raw

        menu = QMenu(self)
        style_context_menu(menu)
        global_pos = self._tree.viewport().mapToGlobal(pos)
        self._inline_suppress_blur = True
        try:
            if item is None:
                add_root = menu.addAction("Add Tag")
                menu.addSeparator()
                collapse = menu.addAction("Collapse All")
                expand = menu.addAction("Expand All")
                chosen = menu.exec(global_pos)
                if chosen == add_root:
                    self._start_inline_add(parent_id=None)
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
            chosen = menu.exec(global_pos)
            if chosen == add_root:
                self._start_inline_add(parent_id=None)
            elif chosen == add_sub and tag_id is not None:
                self._start_inline_add(parent_id=tag_id)
            elif chosen == rename_act and tag_id is not None:
                self._start_inline_rename(tag_id)
            elif chosen == delete_act and tag_id is not None:
                row = self._find_item_by_tag_id(tag_id)
                if row is not None:
                    self._delete_tag(row)
        finally:
            self._inline_suppress_blur = False

    def _start_inline_add(self, parent_id: int | None) -> None:
        self._cancel_inline_edit()
        parent_item: QTreeWidgetItem | None = None
        if parent_id is not None:
            parent_item = self._find_item_by_tag_id(parent_id)
            if parent_item is None:
                return

        it = QTreeWidgetItem()
        it.setFlags(
            Qt.ItemFlag.ItemIsUserCheckable
            | Qt.ItemFlag.ItemIsEnabled
            | Qt.ItemFlag.ItemIsSelectable
        )
        it.setCheckState(0, Qt.CheckState.Unchecked)
        it.setData(0, Qt.ItemDataRole.UserRole, None)

        if parent_item is None:
            self._tree.addTopLevelItem(it)
        else:
            parent_item.addChild(it)
            parent_item.setExpanded(True)

        self._inline_item = it
        self._inline_mode = "add"
        self._inline_add_parent_id = parent_id
        self._show_inline_editor(
            it,
            placeholder="Tag name",
            text="",
            select_all=False,
        )
        self._tree.scrollToItem(it, QAbstractItemView.ScrollHint.EnsureVisible)

    def _start_inline_rename(self, tag_id: int) -> None:
        item = self._find_item_by_tag_id(tag_id)
        if item is None:
            return
        self._cancel_inline_edit()
        item = self._find_item_by_tag_id(tag_id)
        if item is None:
            return
        self._inline_item = item
        self._inline_mode = "rename"
        self._inline_add_parent_id = None
        self._inline_rename_original = item.text(0)
        self._show_inline_editor(
            item,
            placeholder="Tag name",
            text=self._inline_rename_original,
            select_all=True,
        )
        self._tree.scrollToItem(item, QAbstractItemView.ScrollHint.EnsureVisible)

    def _show_inline_editor(
        self,
        item: QTreeWidgetItem,
        *,
        placeholder: str,
        text: str,
        select_all: bool,
    ) -> None:
        del text  # label stays on the item for rename; add uses empty text below
        item.setData(0, _PLACEHOLDER_ROLE, placeholder)
        item.setData(0, _SELECT_ALL_ROLE, select_all)
        if self._inline_mode == "add":
            item.setText(0, "")
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
        self._tree.blockSignals(True)
        self._tree.clearSelection()
        self._tree.setCurrentItem(None)
        self._tree.blockSignals(False)
        self._tree.editItem(item, 0)

    def _on_inline_editor_created(self, edit: QLineEdit, index) -> None:
        item = self._tree.itemFromIndex(index)
        if item is None:
            return
        self._inline_line_edit = edit
        edit.installEventFilter(self)
        select_all = bool(index.data(_SELECT_ALL_ROLE))
        QTimer.singleShot(0, lambda: self._focus_inline_edit(select_all))

    def _focus_inline_edit(self, select_all: bool) -> None:
        edit = self._inline_line_edit
        if edit is None or not _qt_valid(edit):
            return
        self._inline_suppress_blur = True
        edit.setFocus(Qt.FocusReason.OtherFocusReason)
        if select_all:
            edit.selectAll()
        QTimer.singleShot(0, self._clear_inline_blur_suppress)

    def _clear_inline_blur_suppress(self) -> None:
        self._inline_suppress_blur = False

    def _is_inline_editing(self) -> bool:
        edit = self._inline_line_edit
        return (
            self._inline_item is not None
            and self._inline_mode is not None
            and not self._inline_finishing
            and edit is not None
            and _qt_valid(edit)
            and self._tree.state() == QAbstractItemView.State.EditingState
        )

    def _click_targets_inline_editor(self, global_pos: QPoint) -> bool:
        edit = self._inline_line_edit
        if edit is None or not _qt_valid(edit):
            return False
        w = QApplication.widgetAt(global_pos)
        while w is not None:
            if w is edit:
                return True
            w = w.parentWidget()
        return False

    def _maybe_commit_inline_on_click(self, event: QMouseEvent) -> bool:
        if not self._is_inline_editing() or self._inline_suppress_blur:
            return False
        if QApplication.activeModalWidget() is not None:
            return False
        global_pos = event.globalPosition().toPoint()
        if self._click_targets_inline_editor(global_pos):
            return False
        return self._commit_open_inline_editor()

    def _commit_open_inline_editor(self) -> bool:
        """Click-away commit: read text before Qt tears down the editor."""
        if not self._is_inline_editing():
            return False
        edit = self._inline_line_edit
        if edit is None or not _qt_valid(edit):
            return False
        name = edit.text().strip()
        self._inline_skip_delegate_commit = True
        try:
            if self.finish_inline_edit(name):
                self._close_inline_editor_widget()
        finally:
            self._inline_skip_delegate_commit = False
        return True

    def on_tree_close_editor(self, editor: QWidget, hint: QAbstractItemDelegate.EndEditHint) -> None:
        """Runs before the view destroys the delegate editor (incl. Escape / Revert)."""
        if self._inline_finishing or self._inline_item is None:
            return
        if hint != QAbstractItemDelegate.EndEditHint.RevertModelCache:
            return
        item = self._inline_item
        if self._inline_mode == "add":
            self._discard_inline_add_row(item)
            return
        if self._inline_mode == "rename":
            try:
                item.setText(0, self._inline_rename_original)
            except RuntimeError:
                pass
            self._stop_editing_item(item)
            self._reset_inline_session()

    def _close_inline_editor_widget(
        self,
        hint: QAbstractItemDelegate.EndEditHint = QAbstractItemDelegate.EndEditHint.SubmitModelCache,
    ) -> None:
        edit = self._inline_line_edit
        if edit is None or not _qt_valid(edit):
            return
        if self._tree.state() == QAbstractItemView.State.EditingState:
            self._tree.closeEditor(edit, hint)

    def finish_inline_edit(self, name: str) -> bool:
        """Apply add/rename. Returns True when the editor should close."""
        if self._inline_finishing or self._inline_item is None or self._inline_mode is None:
            return True
        name = name.strip()
        mode = self._inline_mode
        item = self._inline_item
        parent_id = self._inline_add_parent_id
        original = self._inline_rename_original

        self._inline_finishing = True
        try:
            if mode == "add":
                if not name:
                    self._discard_inline_add_row(item)
                    return True
                try:
                    tid = self._store.add_tag(name, parent_id)
                except ValueError as exc:
                    QMessageBox.warning(self, "Add tag failed", str(exc))
                    self._focus_inline_edit(select_all=True)
                    return False
                if tid == 0:
                    QMessageBox.information(
                        self, "Add tag", "A tag with that name already exists."
                    )
                    self._focus_inline_edit(select_all=True)
                    return False
                for p in self._selected_paths:
                    self._store.assign_tag_to_image(p, tid)
                try:
                    item.setText(0, name)
                except RuntimeError:
                    pass
                pid = parent_id
                QTimer.singleShot(0, lambda: self._apply_add_tag_done(tid, pid))
                return True

            tid = item.data(0, Qt.ItemDataRole.UserRole)
            if not isinstance(tid, int):
                self._discard_inline_add_row(item)
                return True
            if not name:
                try:
                    item.setText(0, original)
                except RuntimeError:
                    pass
                self._reset_inline_session()
                self._stop_editing_item(item)
                return True
            if name == original:
                self._reset_inline_session()
                self._stop_editing_item(item)
                return True
            try:
                self._store.rename_tag(tid, name)
            except Exception as exc:
                QMessageBox.warning(self, "Rename failed", str(exc))
                self._focus_inline_edit(select_all=True)
                return False
            try:
                item.setText(0, name)
            except RuntimeError:
                pass
            QTimer.singleShot(0, lambda: self._apply_rename_tag_done(tid))
            return True
        finally:
            self._inline_finishing = False

    def _apply_add_tag_done(self, tid: int, parent_id: int | None) -> None:
        self._reset_inline_session()
        self._reload_tree()
        self._expand_through_parent(parent_id)
        self.tags_changed.emit()
        self.tag_order_changed.emit()
        created = self._find_item_by_tag_id(tid)
        if created is not None:
            self._tree.scrollToItem(created, QAbstractItemView.ScrollHint.EnsureVisible)

    def _apply_rename_tag_done(self, tid: int) -> None:
        self._reset_inline_session()
        self._reload_tree()
        self.tags_changed.emit()
        self.tag_order_changed.emit()
        item = self._find_item_by_tag_id(tid)
        if item is not None:
            self._tree.scrollToItem(item, QAbstractItemView.ScrollHint.EnsureVisible)

    def _cancel_inline_edit(self) -> None:
        if not self._is_inline_editing():
            return
        self._inline_suppress_blur = True
        try:
            self._close_inline_editor_widget(
                QAbstractItemDelegate.EndEditHint.RevertModelCache
            )
        finally:
            self._inline_suppress_blur = False

    def _discard_inline_add_row(self, item: QTreeWidgetItem) -> None:
        """Remove a new-tag placeholder immediately (Esc or empty confirm)."""
        self._inline_skip_delegate_commit = True
        try:
            self._detach_inline_row(item)
            self._reset_inline_session()
        finally:
            self._inline_skip_delegate_commit = False

    def _detach_inline_row(self, item: QTreeWidgetItem) -> None:
        parent = item.parent()
        if parent is not None:
            parent.removeChild(item)
        else:
            idx = self._tree.indexOfTopLevelItem(item)
            if idx >= 0:
                self._tree.takeTopLevelItem(idx)

    def _stop_editing_item(self, item: QTreeWidgetItem | None) -> None:
        if item is None:
            return
        try:
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        except RuntimeError:
            pass

    def _reset_inline_session(self) -> None:
        edit = self._inline_line_edit
        if edit is not None and _qt_valid(edit):
            edit.blockSignals(True)
            edit.removeEventFilter(self)
        self._inline_item = None
        self._inline_mode = None
        self._inline_add_parent_id = None
        self._inline_rename_original = ""
        self._inline_line_edit = None
        self._inline_blur_commit_scheduled = False
        self._inline_suppress_blur = False

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
        if self._inline_item is not None:
            item = self._inline_item
            if self._inline_mode == "add":
                self._discard_inline_add_row(item)
            else:
                edit = self._inline_line_edit
                self._reset_inline_session()
                if edit is not None and _qt_valid(edit):
                    self._tree.closeEditor(edit, QAbstractItemDelegate.EndEditHint.RevertModelCache)
                self._stop_editing_item(item)
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
        if item is self._inline_item:
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
