"""Folder tree, favorites shortcuts, and folder path (editable in Folders tab)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtCore import QDir, QModelIndex, Qt, Signal
from PySide6.QtGui import QColor, QFontMetrics, QPalette
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFileSystemModel,
    QInputDialog,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QTreeView,
    QVBoxLayout,
    QWidget,
)

from app.ui.context_menus import style_context_menu
from app.ui.mason_tab_widget import MasonTabWidget

_PATH_FRAME_BORDER = "#383838"
_PATH_FRAME_BORDER_HOVER = "#4a4a4a"
_PATH_FRAME_BORDER_FOCUS = "#357abd"


def _favorite_entry(path: str, name: str | None = None) -> dict[str, Any]:
    return {"path": path, "name": name}


class FolderPanel(QWidget):
    folder_selected = Signal(str)
    favorites_changed = Signal(list)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._favorites: list[dict[str, Any]] = []

        self._model = QFileSystemModel()
        self._model.setFilter(QDir.Filter.Dirs | QDir.Filter.NoDotAndDotDot)
        self._model.setRootPath("")

        self._path_edit = QLineEdit()
        self._path_edit.setObjectName("folderPathEdit")
        self._path_edit.setPlaceholderText("Folder path — paste and press Enter")
        self._path_edit.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self._path_edit.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        self._path_edit.returnPressed.connect(self._on_path_edit_return)
        pal = self._path_edit.palette()
        pal.setColor(QPalette.ColorGroup.All, QPalette.ColorRole.PlaceholderText, QColor(140, 140, 140))
        self._path_edit.setPalette(pal)
        self._path_edit.setStyleSheet(
            f"""
            QLineEdit#folderPathEdit {{
                background-color: #1a1a1a;
                border: 0.5px solid {_PATH_FRAME_BORDER};
                border-radius: 4px;
                padding-top: 2px;
                padding-bottom: 2px;
                padding-left: 4px;
                padding-right: 4px;
                color: #ececec;
                selection-background-color: #5ab4f5;
                selection-color: #ffffff;
            }}
            QLineEdit#folderPathEdit:hover:!focus {{
                border: 0.5px solid {_PATH_FRAME_BORDER_HOVER};
            }}
            QLineEdit#folderPathEdit:focus {{
                border: 0.5px solid {_PATH_FRAME_BORDER_FOCUS};
            }}
            """
        )
        self._sync_path_edit_height()

        self._tree = QTreeView()
        self._tree.setModel(self._model)
        for col in range(1, 4):
            self._tree.hideColumn(col)
        self._tree.setHeaderHidden(True)
        self._tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._tree.customContextMenuRequested.connect(self._on_tree_context_menu)
        self._tree.clicked.connect(self._on_tree_clicked)

        self._folders_page = QWidget()
        folders_lay = QVBoxLayout(self._folders_page)
        folders_lay.setContentsMargins(0, 0, 0, 0)
        folders_lay.setSpacing(4)
        folders_lay.addWidget(self._path_edit)
        folders_lay.addWidget(self._tree, stretch=1)

        self._fav_list = QListWidget()
        self._fav_list.itemClicked.connect(self._on_favorite_item_activated)
        self._fav_list.itemActivated.connect(self._on_favorite_item_activated)
        self._fav_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._fav_list.customContextMenuRequested.connect(self._on_favorite_context_menu)
        self._fav_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._fav_list.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self._fav_list.setDragEnabled(True)
        self._fav_list.setAcceptDrops(True)
        self._fav_list.setDropIndicatorShown(True)
        self._fav_list.setDragDropOverwriteMode(False)
        self._fav_list.setDefaultDropAction(Qt.DropAction.MoveAction)
        self._fav_list.model().rowsMoved.connect(self._on_favorite_rows_moved)

        self._tabs = MasonTabWidget()
        self._tabs.addTab(self._fav_list, "Favorite")
        self._tabs.addTab(self._folders_page, "Folders")
        self._tabs.setCurrentIndex(1)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self._tabs, 1)

    def _sync_path_edit_height(self) -> None:
        fm = QFontMetrics(self.font())
        h = max(22, min(28, fm.height() + 10))
        self._path_edit.setFixedHeight(h)

    def _favorite_path_set(self) -> set[str]:
        return {str(e["path"]) for e in self._favorites if e.get("path")}

    def _norm_folder(self, path: str) -> str | None:
        try:
            p = Path(path.strip().strip('"')).expanduser()
            if not p.is_dir():
                return None
            return str(p.resolve())
        except OSError:
            return None

    def _on_path_edit_return(self) -> None:
        text = self._path_edit.text().strip()
        n = self._norm_folder(text)
        if n:
            self.folder_selected.emit(n)
        else:
            QMessageBox.warning(self, "Folder", "That path is not an existing folder.")

    def _on_tree_clicked(self, index: QModelIndex) -> None:
        path = self._model.filePath(index)
        n = self._norm_folder(path)
        if n:
            self.folder_selected.emit(n)

    def _on_tree_context_menu(self, pos) -> None:
        idx = self._tree.indexAt(pos)
        if not idx.isValid():
            return
        n = self._norm_folder(self._model.filePath(idx))
        if not n:
            return
        menu = QMenu(self)
        style_context_menu(menu)
        add = menu.addAction("Add to Favorite")
        add.setEnabled(n not in self._favorite_path_set())
        act = menu.exec(self._tree.viewport().mapToGlobal(pos))
        if act is add and add.isEnabled():
            self._add_favorite(n)

    def _add_favorite(self, path: str) -> None:
        n = self._norm_folder(path)
        if not n or n in self._favorite_path_set():
            return
        self._favorites.append(_favorite_entry(n, None))
        self._sync_favorite_list()
        self.favorites_changed.emit(self.favorites_for_settings())

    def _remove_favorite(self, path: str) -> None:
        try:
            key = str(Path(path).resolve())
        except OSError:
            return
        before = len(self._favorites)
        self._favorites = [e for e in self._favorites if str(e.get("path")) != key]
        if len(self._favorites) == before:
            return
        self._sync_favorite_list()
        self.favorites_changed.emit(self.favorites_for_settings())

    def _rename_favorite(self, path: str) -> None:
        entry = next((e for e in self._favorites if str(e.get("path")) == path), None)
        if entry is None:
            return
        current = entry.get("name") or Path(path).name
        text, ok = QInputDialog.getText(self, "Rename favorite", "Display name:", text=str(current))
        if not ok:
            return
        label = text.strip()
        entry["name"] = label if label else None
        self._sync_favorite_list()
        self.favorites_changed.emit(self.favorites_for_settings())

    def _sync_favorite_list(self) -> bool:
        kept: list[dict[str, Any]] = []
        for e in self._favorites:
            p = e.get("path")
            if not p or not Path(str(p)).is_dir():
                continue
            try:
                resolved = str(Path(str(p)).resolve())
            except OSError:
                continue
            ne = dict(e)
            ne["path"] = resolved
            kept.append(ne)
        pruned_changed = len(kept) != len(self._favorites)
        self._favorites = kept
        self._fav_list.clear()
        for e in self._favorites:
            p = str(e["path"])
            label = e.get("name")
            display = str(label).strip() if isinstance(label, str) and label.strip() else Path(p).name
            item = QListWidgetItem(display)
            item.setToolTip(p)
            item.setData(Qt.ItemDataRole.UserRole, p)
            self._fav_list.addItem(item)
        return pruned_changed

    def _on_favorite_item_activated(self, item: QListWidgetItem) -> None:
        raw = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(raw, str) and Path(raw).is_dir():
            self.folder_selected.emit(raw)

    def _on_favorite_context_menu(self, pos) -> None:
        item = self._fav_list.itemAt(pos)
        if item is None:
            return
        path = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(path, str):
            return
        menu = QMenu(self)
        style_context_menu(menu)
        ren = menu.addAction("Rename")
        rem = menu.addAction("Remove from Favorite")
        act = menu.exec(self._fav_list.viewport().mapToGlobal(pos))
        if act is ren:
            self._rename_favorite(path)
        elif act is rem:
            self._remove_favorite(path)

    def _on_favorite_rows_moved(
        self,
        parent: QModelIndex,
        start: int,
        end: int,
        destination_parent: QModelIndex,
        destination_row: int,
    ) -> None:
        del parent, start, end, destination_parent, destination_row
        by_path: dict[str, dict[str, Any]] = {}
        for e in self._favorites:
            p = str(e.get("path", ""))
            if p:
                by_path[p] = e
        new_order: list[dict[str, Any]] = []
        for i in range(self._fav_list.count()):
            it = self._fav_list.item(i)
            raw = it.data(Qt.ItemDataRole.UserRole)
            if isinstance(raw, str) and raw in by_path:
                new_order.append(by_path[raw])
        if new_order and len(new_order) == len(self._favorites):
            self._favorites = new_order
            self.favorites_changed.emit(self.favorites_for_settings())

    def set_favorites(self, data: object, *, emit_changed: bool = True) -> None:
        self._favorites = []
        if not isinstance(data, list):
            pruned = self._sync_favorite_list()
            if pruned and emit_changed:
                self.favorites_changed.emit(self.favorites_for_settings())
            return
        seen: set[str] = set()
        for raw in data:
            if isinstance(raw, str):
                n = self._norm_folder(raw)
                if n and n not in seen:
                    seen.add(n)
                    self._favorites.append(_favorite_entry(n, None))
            elif isinstance(raw, dict):
                p = raw.get("path")
                n = self._norm_folder(str(p)) if p else None
                if not n or n in seen:
                    continue
                seen.add(n)
                name = raw.get("name")
                nm = str(name).strip() if isinstance(name, str) and str(name).strip() else None
                self._favorites.append(_favorite_entry(n, nm))
        pruned = self._sync_favorite_list()
        if pruned and emit_changed:
            self.favorites_changed.emit(self.favorites_for_settings())

    def favorites_for_settings(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for e in self._favorites:
            p = str(e["path"])
            d: dict[str, Any] = {"path": p}
            nm = e.get("name")
            if isinstance(nm, str) and nm.strip():
                d["name"] = nm.strip()
            out.append(d)
        return out

    def favorite_paths(self) -> list[str]:
        return [str(e["path"]) for e in self._favorites]

    def set_folder_path_display(self, path: str) -> None:
        self._path_edit.setText(path)
        self._path_edit.home(False)

    def set_root_path(self, path: str) -> None:
        self._tree.setRootIndex(self._model.index(path))

    def select_path(self, path: str) -> None:
        self.set_folder_path_display(path)
        p = Path(path)
        if p.is_dir():
            idx = self._model.index(str(p))
            if idx.isValid():
                self._tree.setCurrentIndex(idx)
                self._tree.expand(idx)
