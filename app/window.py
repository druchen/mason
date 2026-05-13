"""Main window: layout splitters and signal wiring."""

from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import QPoint, QMimeData, Qt, QTimer
from PySide6.QtWidgets import (
    QDialog,
    QMainWindow,
    QMessageBox,
    QSplitter,
    QVBoxLayout,
    QWidget,
    QMenu,
    QInputDialog,
)

from app.core import file_scanner, settings as settings_mod, sort_filter
from app.core.tags_store import TagsStore
from app.core.thumbnail_cache import ThumbnailCache
from app.ui.filter_panel import FilterPanel
from app.ui.folder_panel import FolderPanel
from app.ui.info_bar import InfoBar
from app.ui.tags_panel import TagsPanel
from app.ui.metadata_panel import MetadataPanel
from app.ui.preview_panel import PreviewPanel
from app.ui.settings_dialog import SettingsDialog
from app.ui.toolbar import MainToolbar
from app.ui import drop_import, image_actions


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self._did_apply_initial_splitters = False
        self.setWindowTitle("Mason")
        self.resize(1280, 800)

        self.setUpdatesEnabled(False)
        try:
            self._init_content()
        finally:
            self.setUpdatesEnabled(True)

    def _init_content(self) -> None:
        self._settings = settings_mod.load_settings()
        self._store = TagsStore()
        self._thumb_cache = ThumbnailCache(self)

        self._folder = self._settings.get("last_folder") or str(Path.home())
        self._raw_paths: list[str] = []
        self._selected_image: str | None = None
        self._fullscreen_view = None
        self._photoshop_exe = str(self._settings.get("photoshop_exe") or "")
        self._locked_mode = os.environ.get("MASON_LOCK_PREVIEW_MODE", "").strip().lower() or None
        self._pending_thumb_size: int | None = None
        self._thumb_size_timer = QTimer(self)
        self._thumb_size_timer.setSingleShot(True)
        self._thumb_size_timer.timeout.connect(self._apply_pending_thumb_size)

        self._toolbar = MainToolbar()
        self._folder_panel = FolderPanel()
        self._metadata = MetadataPanel(self._store)
        self._preview = PreviewPanel(self._thumb_cache)
        self._info = InfoBar()
        self._tags = TagsPanel(self._store)
        self._filter = FilterPanel(self._store)

        self._setup_layout()
        self._apply_stylesheet()
        self._wire_signals()

        fav_raw = self._settings.get("favorite_folders")
        fav_list = fav_raw if isinstance(fav_raw, list) else []
        self._folder_panel.set_favorites(fav_list)
        self._preview.set_favorites_tabs(self._folder_panel.favorites_for_settings())

        start_mode = str(self._settings.get("layout_mode") or "square")
        if self._locked_mode:
            start_mode = self._locked_mode
        self._toolbar.set_mode(start_mode)
        self._preview.set_layout_mode(start_mode)
        self._preview.set_sort(
            str(self._settings.get("sort_by") or "name"),
            bool(self._settings.get("sort_ascending", True)),
        )
        self._info.set_thumbnail_size(int(self._settings.get("thumbnail_size") or 128))
        self._preview.apply_prefs(int(self._settings.get("thumbnail_size") or 128))

        self._folder_panel.select_path(self._folder)
        self._preview.set_import_drop_folder(self._folder)

        geo = self._settings.get("window_geometry")
        if isinstance(geo, dict) and all(k in geo for k in ("x", "y", "w", "h")):
            self.setGeometry(int(geo["x"]), int(geo["y"]), int(geo["w"]), int(geo["h"]))

        self._load_folder(self._folder)

    def showEvent(self, event) -> None:  # type: ignore[override]
        super().showEvent(event)
        self._maybe_apply_initial_splitters()

    def resizeEvent(self, event) -> None:  # type: ignore[override]
        super().resizeEvent(event)
        self._maybe_apply_initial_splitters()

    def _maybe_apply_initial_splitters(self) -> None:
        if self._did_apply_initial_splitters:
            return
        if self.width() < 80 or self.height() < 80:
            return
        self._did_apply_initial_splitters = True
        self._apply_splitter_sizes()

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------

    def _apply_splitter_sizes(self) -> None:
        total_w = self._split_main.width()
        sm = self._settings.get("splitter_main")
        if isinstance(sm, list) and len(sm) == 3 and sum(sm) > 0:
            self._split_main.setSizes([int(sm[0]), int(sm[1]), int(sm[2])])
        else:
            left_w = max(200, int(total_w * 0.18))
            right_w = max(220, int(total_w * 0.20))
            self._split_main.setSizes([left_w, max(200, total_w - left_w - right_w), right_w])

        total_h = self._split_left.height()
        sl = self._settings.get("splitter_left")
        if isinstance(sl, list) and len(sl) == 2 and sum(sl) > 0:
            self._split_left.setSizes([int(sl[0]), int(sl[1])])
        else:
            self._split_left.setSizes([max(300, int(total_h * 0.65)), max(120, int(total_h * 0.35))])

        sr = self._settings.get("splitter_right")
        if isinstance(sr, list) and len(sr) == 2 and sum(sr) > 0:
            self._split_right.setSizes([int(sr[0]), int(sr[1])])
        else:
            self._split_right.setSizes([max(200, int(total_h * 0.55)), max(120, int(total_h * 0.45))])

    def _setup_layout(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._toolbar)

        self._info.setFixedHeight(40)

        center_widget = QWidget()
        center_widget.setMinimumWidth(0)
        center_col = QVBoxLayout(center_widget)
        center_col.setContentsMargins(0, 0, 0, 0)
        center_col.setSpacing(0)
        center_col.addWidget(self._preview, stretch=1)
        self._preview.setMinimumWidth(0)
        center_col.addWidget(self._info)

        self._split_main = QSplitter(Qt.Orientation.Horizontal)
        self._split_left = QSplitter(Qt.Orientation.Vertical)
        self._split_right = QSplitter(Qt.Orientation.Vertical)

        self._split_left.addWidget(self._folder_panel)
        self._split_left.addWidget(self._metadata)

        self._split_right.addWidget(self._tags)
        self._split_right.addWidget(self._filter)

        self._split_main.addWidget(self._split_left)
        self._split_main.addWidget(center_widget)
        self._split_main.addWidget(self._split_right)

        root.addWidget(self._split_main, stretch=1)

    def _apply_stylesheet(self) -> None:
        self.setStyleSheet(
            """
            QWidget { background-color: #2b2b2b; color: #e0e0e0; }
            QLineEdit, QComboBox, QTextEdit, QListWidget, QTreeView {
                background-color: #3c3c3c; border: 1px solid #555; border-radius: 4px;
            }
            QToolButton:checked { background-color: #555; }
            QSplitter::handle { background: #444; }
            """
        )

    # ------------------------------------------------------------------
    # Signal wiring
    # ------------------------------------------------------------------

    def _wire_signals(self) -> None:
        self._folder_panel.folder_selected.connect(self._on_folder_selected)
        self._folder_panel.favorites_changed.connect(self._on_favorites_changed)
        self._toolbar.layout_mode_changed.connect(self._on_layout_mode)
        self._toolbar.search_changed.connect(lambda _: self._refresh_paths())
        self._preview.sort_changed.connect(lambda _: self._refresh_paths())
        self._preview.ascending_changed.connect(lambda _: self._refresh_paths())
        self._preview.favorite_folder_selected.connect(self._on_folder_selected)
        self._preview.favorites_order_changed.connect(self._on_preview_favorites_reordered)
        self._preview.selection_changed.connect(self._on_preview_selection)
        self._info.thumbnail_size_changed.connect(self._on_thumb_size)
        self._tags.tags_changed.connect(self._on_tags_changed)
        self._tags.tag_order_changed.connect(self._filter.reload_tags)
        self._filter.filter_changed.connect(self._refresh_paths)
        self._preview.fullscreen_requested.connect(self._open_fullscreen)
        self._preview.delete_requested.connect(self._delete_files)
        self._preview.image_context_menu_requested.connect(self._on_preview_image_context_menu)
        self._preview.open_in_photoshop_requested.connect(self._open_in_photoshop)
        self._toolbar.settings_clicked.connect(self._on_settings)
        self._preview.set_import_drop_handler(self._handle_preview_import_drop)

    # ------------------------------------------------------------------
    # Folder / path management
    # ------------------------------------------------------------------

    def _visible_paths(self) -> list[str]:
        paths = list(self._raw_paths)
        paths = sort_filter.filter_by_search(paths, self._toolbar.search_query())
        paths = sort_filter.filter_by_tags(
            paths,
            self._filter.selected_tag_ids(),
            self._store,
            self._filter.tag_match_mode(),
        )
        paths = sort_filter.sort_paths(paths, self._preview.sort_key(), self._preview.ascending())
        return paths

    def _path_matches_visible(self, saved: str, visible: list[str]) -> str | None:
        if saved in visible:
            return saved
        try:
            tr = Path(saved).resolve()
        except OSError:
            tr = Path(saved)
        for p in visible:
            try:
                if Path(p).resolve() == tr:
                    return p
            except OSError:
                if p == saved:
                    return p
        return None

    def _handle_preview_import_drop(self, mime: QMimeData) -> None:
        from app.core.tags_importer import import_tags_from_folder

        saved = drop_import.import_from_mime_data(
            self,
            Path(self._folder),
            str(self._settings.get("drop_save_format") or "webp"),
            mime,
        )
        if not saved:
            return
        self._raw_paths = file_scanner.scan_folder(self._folder)
        import_tags_from_folder(self._raw_paths, self._store)
        self._refresh_paths()
        last = saved[-1]
        pick = self._path_matches_visible(last, self._visible_paths())
        if pick is not None:
            self._preview.select_primary_path(pick)

    def _on_folder_selected(self, path: str) -> None:
        self._folder = path
        self._preview.set_import_drop_folder(self._folder)
        self._folder_panel.select_path(path)
        self._preview.sync_favorite_tab_for_path(path)
        self._load_folder(path)

    def _on_favorites_changed(self, data: object) -> None:
        if isinstance(data, list):
            self._settings["favorite_folders"] = data
            self._save_settings()
        self._preview.set_favorites_tabs(self._folder_panel.favorites_for_settings())
        self._preview.sync_favorite_tab_for_path(self._folder)

    def _on_preview_favorites_reordered(self, ordered: object) -> None:
        if not isinstance(ordered, list):
            return
        self._folder_panel.set_favorites(ordered, emit_changed=False)
        self._settings["favorite_folders"] = self._folder_panel.favorites_for_settings()
        self._save_settings()
        self._preview.set_favorites_tabs(self._folder_panel.favorites_for_settings())
        self._preview.sync_favorite_tab_for_path(self._folder)

    def _load_folder(self, folder: str) -> None:
        from app.core.tags_importer import import_tags_from_folder
        self._raw_paths = file_scanner.scan_folder(folder)
        import_tags_from_folder(self._raw_paths, self._store)
        self._selected_image = None
        self._metadata.clear()
        self._tags.set_selected_image(None)
        self._refresh_paths()

    def _refresh_paths(self) -> None:
        """Re-sort/filter the current folder, preserving the current image selection."""
        paths = self._visible_paths()
        self._preview.set_paths(paths)
        self._info.set_item_count(len(paths))
        if self._selected_image and self._selected_image not in paths:
            self._selected_image = None
            self._metadata.clear()
            self._tags.set_selected_image(None)
        self._preview.sync_favorite_tab_for_path(self._folder)

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------

    def _on_preview_selection(self, path: str) -> None:
        self._selected_image = path
        self._metadata.show_path(path)
        self._tags.set_selected_image(path)
        self._preview.take_preview_focus()

    def _on_layout_mode(self, mode: str) -> None:
        if self._locked_mode:
            mode = self._locked_mode
        self._toolbar.set_mode(mode)
        self._preview.set_layout_mode(mode)

    def _on_thumb_size(self, size: int) -> None:
        # Coalesce rapid slider ticks into one rebuild.
        self._pending_thumb_size = int(size)
        self._thumb_size_timer.start(140)

    def _apply_pending_thumb_size(self) -> None:
        if self._pending_thumb_size is None:
            return
        self._preview.set_thumbnail_size(self._pending_thumb_size)
        self._pending_thumb_size = None

    def _on_tags_changed(self) -> None:
        self._filter.reload_tags()
        self._refresh_paths()

    def _on_settings(self) -> None:
        dlg = SettingsDialog(
            self._photoshop_exe,
            str(self._settings.get("drop_save_format") or "webp"),
            self,
        )
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        self._photoshop_exe = dlg.photoshop_exe()
        self._settings["photoshop_exe"] = self._photoshop_exe
        self._settings["drop_save_format"] = dlg.drop_save_format()
        self._save_settings()

    def _open_in_photoshop(self, path: str) -> None:
        err = image_actions.launch_photoshop(self._photoshop_exe, path, self)
        if err:
            QMessageBox.warning(self, "Photoshop", err)

    def _on_preview_image_context_menu(self, path: str, global_pos: QPoint) -> None:
        if not path or not Path(path).is_file():
            return
        menu = QMenu(self)
        menu.addAction("Open in Photoshop", lambda: self._open_in_photoshop(path))
        menu.addAction("Locate file", lambda: self._locate_file(path))
        menu.addAction("Copy image", lambda: self._copy_image(path))
        menu.addAction("Rename…", lambda: self._rename_file(path))
        menu.addAction("Delete…", lambda: self._delete_files([path]))
        menu.exec(global_pos)

    def _locate_file(self, path: str) -> None:
        err = image_actions.locate_file_in_explorer(path)
        if err:
            QMessageBox.warning(self, "Locate file", err)

    def _copy_image(self, path: str) -> None:
        err = image_actions.copy_image_to_clipboard(path)
        if err:
            QMessageBox.warning(self, "Copy image", err)

    def _rename_file(self, path: str) -> None:
        old = Path(path)
        if not old.is_file():
            QMessageBox.warning(self, "Rename", "File does not exist.")
            return
        new_name, ok = QInputDialog.getText(self, "Rename file", "New filename:", text=old.name)
        if not ok:
            return
        new_name = new_name.strip()
        if not new_name or new_name == old.name:
            return
        if any(sep in new_name for sep in ("/", "\\", ":")):
            QMessageBox.warning(self, "Rename", "Invalid filename.")
            return
        new_path = old.parent / new_name
        if new_path.exists():
            QMessageBox.warning(self, "Rename", "A file with that name already exists.")
            return
        try:
            old_res = old.resolve()
        except OSError:
            old_res = old
        try:
            old.rename(new_path)
        except OSError as e:
            QMessageBox.warning(self, "Rename", str(e))
            return

        new_str = str(new_path.resolve())
        try:
            self._store.rename_image_path(str(old_res), new_str)
        except Exception:
            pass

        for i, p in enumerate(self._raw_paths):
            try:
                if p == str(old) or Path(p).resolve() == old_res:
                    self._raw_paths[i] = new_str
                    break
            except OSError:
                if p == str(old):
                    self._raw_paths[i] = new_str
                    break

        if self._selected_image:
            try:
                sel_res = Path(self._selected_image).resolve()
            except OSError:
                sel_res = None
            if sel_res == old_res or self._selected_image == str(old):
                self._selected_image = new_str
                self._metadata.show_path(new_str)
                self._tags.set_selected_image(new_str)

        self._refresh_paths()

    # ------------------------------------------------------------------
    # Fullscreen viewer
    # ------------------------------------------------------------------

    def _open_fullscreen(self, path: str) -> None:
        from app.views.fullscreen_view import FullscreenView
        paths = self._preview.active_view().paths() or [path]
        if path not in paths:
            paths = [path]
        fv = FullscreenView(paths, path)
        self._fullscreen_view = fv  # keep a reference
        fv.navigation_changed.connect(self._on_fullscreen_nav)
        fv.closed.connect(self._on_fullscreen_closed)

    def _on_fullscreen_nav(self, path: str) -> None:
        """Keep metadata / tags panels in sync while navigating in fullscreen."""
        self._selected_image = path
        self._metadata.show_path(path)
        self._tags.set_selected_image(path)

    def _on_fullscreen_closed(self) -> None:
        self._fullscreen_view = None

    # ------------------------------------------------------------------
    # File deletion
    # ------------------------------------------------------------------

    def _delete_files(self, paths: list[str]) -> None:
        if not paths:
            return
        count = len(paths)
        noun = "file" if count == 1 else "files"
        names = "\n".join(Path(p).name for p in paths[:8])
        if count > 8:
            names += f"\n… and {count - 8} more"
        ret = QMessageBox.question(
            self,
            "Delete files",
            f"Permanently delete {count} {noun}?\n\n{names}\n\nThis cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if ret != QMessageBox.StandardButton.Yes:
            return

        deleted: set[str] = set()
        for path in paths:
            try:
                os.remove(path)
                deleted.add(path)
            except OSError as e:
                QMessageBox.warning(self, "Delete failed", f"{Path(path).name}: {e}")
            # Clean up SQLite tag assignments
            try:
                norm = str(Path(path).resolve())
                for tid, _ in self._store.get_tags_for_image(norm):
                    self._store.remove_tag_from_image(norm, tid)
            except Exception:
                pass
            # Clean up dimension cache entry
            try:
                from app.core import image_cache as _ic
                _ic._mem.pop(path, None)
            except Exception:
                pass

        if not deleted:
            return

        # Update raw paths list and refresh
        self._raw_paths = [p for p in self._raw_paths if p not in deleted]
        if self._selected_image in deleted:
            self._selected_image = None
            self._metadata.clear()
            self._tags.set_selected_image(None)
        self._refresh_paths()

    def closeEvent(self, event) -> None:  # type: ignore[override]
        self._save_settings()
        self._thumb_cache.clear_pending()
        from PySide6.QtCore import QThreadPool
        QThreadPool.globalInstance().waitForDone(2000)
        super().closeEvent(event)

    def _save_settings(self) -> None:
        g = self.geometry()
        settings_mod.save_settings({
            "last_folder": self._folder,
            "thumbnail_size": self._info.thumbnail_size(),
            "layout_mode": self._toolbar.current_mode(),
            "sort_by": self._preview.sort_key(),
            "sort_ascending": self._preview.ascending(),
            "photoshop_exe": self._photoshop_exe,
            "drop_save_format": str(self._settings.get("drop_save_format") or "webp"),
            "favorite_folders": self._folder_panel.favorites_for_settings(),
            "window_geometry": {"x": g.x(), "y": g.y(), "w": g.width(), "h": g.height()},
            "splitter_main": self._split_main.sizes(),
            "splitter_left": self._split_left.sizes(),
            "splitter_right": self._split_right.sizes(),
        })
