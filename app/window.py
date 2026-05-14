"""Main window: layout splitters and signal wiring."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, cast

from PySide6.QtCore import QByteArray, QPoint, QMimeData, Qt, QThread, QTimer, Signal
from PySide6.QtWidgets import (
    QCheckBox,
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
from app.ui.context_menus import style_context_menu
from app.ui.filter_panel import FilterPanel
from app.ui.folder_panel import FolderPanel
from app.ui.info_bar import InfoBar
from app.ui.tags_panel import TagsPanel
from app.ui.metadata_panel import MetadataPanel
from app.ui.preview_panel import PreviewPanel
from app.ui.settings_dialog import SettingsDialog
from app.ui.toolbar import MainToolbar
from app.ui import drop_import, image_actions


class _EmbeddedTagScanThread(QThread):
    """Scans image files for embedded keywords without touching ``TagsStore`` (thread-safe)."""

    scanned = Signal(list)

    def __init__(self, paths: list[str]) -> None:
        super().__init__()
        self._paths = paths

    def run(self) -> None:  # type: ignore[override]
        from app.core.tags_importer import scan_paths_for_embedded_tags

        if self.isInterruptionRequested():
            return
        pairs = scan_paths_for_embedded_tags(
            self._paths, should_abort=lambda: self.isInterruptionRequested()
        )
        if not self.isInterruptionRequested():
            self.scanned.emit(pairs)


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self._did_apply_initial_splitters = False
        self._splitter_reapply_done = False
        self._splitter_reapply_attempts = 0
        self._applying_splitter_sizes = False
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
        if self._locked_mode and self._locked_mode not in settings_mod.KNOWN_LAYOUT_MODES:
            self._locked_mode = None
        self._pending_thumb_size: int | None = None
        self._tag_import_thread: QThread | None = None
        self._tag_import_generation = 0
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

        start_mode = str(self._settings.get("layout_mode") or "essential")
        if self._locked_mode:
            start_mode = self._locked_mode
        self._splitters_layout_mode = start_mode
        self._toolbar.set_mode(start_mode)
        # Apply saved thumbnail size before switching layout so new views see the correct _thumb_size.
        thumb_px = int(self._settings.get("thumbnail_size") or 128)
        self._info.set_thumbnail_size(thumb_px)
        self._preview.apply_prefs(thumb_px)
        self._preview.set_layout_mode(start_mode)
        self._preview.set_sort(
            str(self._settings.get("sort_by") or "name"),
            bool(self._settings.get("sort_ascending", True)),
        )

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
        self._apply_splitter_sizes(self._splitters_layout_mode)
        # First pass can run before Qt has finished laying out children; reapply once on the event loop.
        QTimer.singleShot(0, self._reapply_splitters_once)

    def _reapply_splitters_once(self) -> None:
        if self._splitter_reapply_done:
            return
        if self.width() < 80 or self.height() < 80:
            self._splitter_reapply_attempts += 1
            if self._splitter_reapply_attempts < 60:
                QTimer.singleShot(50, self._reapply_splitters_once)
            else:
                self._splitter_reapply_done = True
            return
        self._splitter_reapply_done = True
        self._apply_splitter_sizes(self._splitters_layout_mode)

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------

    @staticmethod
    def _splitter_size_lists_valid(m: list[int], l: list[int], r: list[int]) -> bool:
        return (
            len(m) == 3
            and all(x > 0 for x in m)
            and sum(m) > 0
            and len(l) == 2
            and all(x > 0 for x in l)
            and sum(l) > 0
            and len(r) == 2
            and all(x > 0 for x in r)
            and sum(r) > 0
        )

    @staticmethod
    def _fit_splitter_sizes(sizes: list[int], total: int, floor_each: int = 48) -> list[int]:
        total = max(1, int(total))
        if len(sizes) < 1:
            return sizes
        ssum = sum(sizes)
        if ssum <= 0:
            return sizes
        out = [max(floor_each, int(round(s * total / ssum))) for s in sizes]
        diff = total - sum(out)
        guard = 0
        while diff != 0 and guard < 10000:
            guard += 1
            i = max(range(len(out)), key=lambda j: out[j])
            step = 1 if diff > 0 else -1
            if out[i] + step < floor_each:
                break
            out[i] += step
            diff -= step
        return out

    def _try_restore_splitters_from_qt_state(self, entry: dict[str, Any]) -> bool:
        keys = ("qt_main", "qt_left", "qt_right")
        splitters = (self._split_main, self._split_left, self._split_right)
        backup = [bytes(sp.saveState()) for sp in splitters]
        blobs: list[QByteArray] = []
        for k in keys:
            raw = entry.get(k)
            if not isinstance(raw, str) or not raw:
                return False
            try:
                blobs.append(QByteArray(bytes.fromhex(raw)))
            except ValueError:
                return False
        ok = all(sp.restoreState(ba) for sp, ba in zip(splitters, blobs))
        if not ok:
            for sp, b in zip(splitters, backup):
                sp.restoreState(QByteArray(b))
        return ok

    def _splitter_lists_for_mode(self, mode: str) -> tuple[list[int] | None, list[int] | None, list[int] | None]:
        sbm = self._settings.get("splitters_by_mode")
        if not isinstance(sbm, dict):
            return None, None, None
        entry = sbm.get(mode)
        if not isinstance(entry, dict):
            return None, None, None
        sm = entry.get("splitter_main")
        sl = entry.get("splitter_left")
        sr = entry.get("splitter_right")
        if (
            isinstance(sm, list)
            and len(sm) == 3
            and sum(sm) > 0
            and isinstance(sl, list)
            and len(sl) == 2
            and sum(sl) > 0
            and isinstance(sr, list)
            and len(sr) == 2
            and sum(sr) > 0
        ):
            return [int(sm[0]), int(sm[1]), int(sm[2])], [int(sl[0]), int(sl[1])], [int(sr[0]), int(sr[1])]
        return None, None, None

    def _store_splitters_for_mode(self, mode: str) -> None:
        m = [int(x) for x in self._split_main.sizes()]
        l = [int(x) for x in self._split_left.sizes()]
        r = [int(x) for x in self._split_right.sizes()]
        if not self._splitter_size_lists_valid(m, l, r):
            return
        raw = self._settings.get("splitters_by_mode")
        sbm: dict[str, Any] = dict(raw) if isinstance(raw, dict) else {}
        sbm[mode] = {
            "splitter_main": m,
            "splitter_left": l,
            "splitter_right": r,
            "qt_main": bytes(self._split_main.saveState()).hex(),
            "qt_left": bytes(self._split_left.saveState()).hex(),
            "qt_right": bytes(self._split_right.saveState()).hex(),
        }
        self._settings["splitters_by_mode"] = sbm

    def _on_splitter_moved(self, _pos: int, _index: int) -> None:
        if self._applying_splitter_sizes:
            return
        self._store_splitters_for_mode(self._splitters_layout_mode)

    def _apply_splitter_sizes(self, mode: str | None = None) -> None:
        use_mode = mode if mode is not None else self._splitters_layout_mode
        sm, sl, sr = self._splitter_lists_for_mode(use_mode)
        entry: dict[str, Any] | None = None
        sbm = self._settings.get("splitters_by_mode")
        if isinstance(sbm, dict):
            raw_e = sbm.get(use_mode)
            if isinstance(raw_e, dict):
                entry = raw_e

        splitters = (self._split_main, self._split_left, self._split_right)
        self._applying_splitter_sizes = True
        for sp in splitters:
            sp.blockSignals(True)
        try:
            total_w = max(1, self._split_main.width())
            total_h_l = max(1, self._split_left.height())
            total_h_r = max(1, self._split_right.height())

            restored = False
            if (
                entry is not None
                and self._split_main.width() > 160
                and self._split_left.height() > 100
                and self._split_right.height() > 100
            ):
                restored = self._try_restore_splitters_from_qt_state(entry)

            if not restored and sm is not None and sl is not None and sr is not None:
                main_fit = self._fit_splitter_sizes(sm, total_w, floor_each=48)
                left_fit = self._fit_splitter_sizes(sl, total_h_l, floor_each=64)
                right_fit = self._fit_splitter_sizes(sr, total_h_r, floor_each=64)
                self._split_main.setSizes(main_fit)
                self._split_left.setSizes(left_fit)
                self._split_right.setSizes(right_fit)
            elif not restored:
                min_side = 72
                min_mid = 80
                left_w = max(min_side, int(total_w * 0.17))
                right_w = max(min_side, int(total_w * 0.19))
                mid = total_w - left_w - right_w
                if mid < min_mid:
                    deficit = min_mid - mid
                    dl = min(deficit // 2 + deficit % 2, max(0, left_w - 48))
                    left_w -= dl
                    deficit -= dl
                    dr = min(deficit, max(0, right_w - 48))
                    right_w -= dr
                    mid = total_w - left_w - right_w
                self._split_main.setSizes([left_w, max(48, mid), right_w])
                self._split_left.setSizes(
                    [max(120, int(total_h_l * 0.62)), max(80, int(total_h_l * 0.38))]
                )
                self._split_right.setSizes(
                    [max(100, int(total_h_r * 0.55)), max(72, int(total_h_r * 0.45))]
                )
        finally:
            for sp in splitters:
                sp.blockSignals(False)
            self._applying_splitter_sizes = False

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
        self._split_main.setChildrenCollapsible(True)
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

            QTabWidget#mason_panel_tabs::pane {
                border: none;
                background: transparent;
                padding: 8px 0 0 0;
                top: 0px;
            }
            QTabBar::tab {
                background: #1f1f1f;
                color: #d8d8d8;
                border: 1px solid #404040;
                border-top-left-radius: 3px;
                border-top-right-radius: 3px;
                padding: 5px 12px;
                margin-right: 2px;
                min-height: 1.2em;
            }
            QTabBar::tab:selected {
                background: #2b2b2b;
                border-top: 1px solid #666;
                border-left: 1px solid #666;
                border-right: 1px solid #666;
                border-bottom: none;
                border-top-left-radius: 3px;
                border-top-right-radius: 3px;
                margin-bottom: 0;
                padding: 5px 12px;
                color: #e0e0e0;
            }
            QTabBar::tab:hover:!selected { background: #2a2a2a; }

            QScrollBar:vertical {
                border: none;
                background: transparent;
                width: 10px;
                margin: 0;
            }
            QScrollBar::handle:vertical {
                background: #5a5a5a;
                border-radius: 4px;
                min-height: 28px;
                margin: 2px;
            }
            QScrollBar::handle:vertical:hover { background: #707070; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                border: none;
                background: transparent;
                height: 0px;
                width: 0px;
            }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
                background: transparent;
            }

            QScrollBar:horizontal {
                border: none;
                background: transparent;
                height: 10px;
                margin: 0;
            }
            QScrollBar::handle:horizontal {
                background: #5a5a5a;
                border-radius: 4px;
                min-width: 28px;
                margin: 2px;
            }
            QScrollBar::handle:horizontal:hover { background: #707070; }
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
                border: none;
                background: transparent;
                height: 0px;
                width: 0px;
            }
            QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {
                background: transparent;
            }
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

        self._split_main.splitterMoved.connect(self._on_splitter_moved)
        self._split_left.splitterMoved.connect(self._on_splitter_moved)
        self._split_right.splitterMoved.connect(self._on_splitter_moved)

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
        saved = drop_import.import_from_mime_data(
            self,
            Path(self._folder),
            str(self._settings.get("drop_save_format") or "webp"),
            mime,
        )
        if not saved:
            return
        self._raw_paths = file_scanner.scan_folder(self._folder)
        self._start_embedded_tag_import(list(self._raw_paths))
        self._refresh_paths()
        last = saved[-1]
        pick = self._path_matches_visible(last, self._visible_paths())
        if pick is not None:
            self._preview.select_primary_path(pick)

    def _on_folder_selected(self, path: str) -> None:
        try:
            new_n = str(Path(path).resolve())
            cur_n = str(Path(self._folder).resolve())
        except OSError:
            new_n, cur_n = path, self._folder
        same_folder = new_n == cur_n

        self._folder = path
        self._preview.set_import_drop_folder(self._folder)
        self._folder_panel.select_path(path)
        self._preview.sync_favorite_tab_for_path(path)
        if same_folder:
            return
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
        self._raw_paths = file_scanner.scan_folder(folder)
        self._selected_image = None
        self._metadata.clear()
        self._sync_tags_selection()
        self._refresh_paths()
        self._start_embedded_tag_import(list(self._raw_paths))

    def _start_embedded_tag_import(self, paths: list[str]) -> None:
        """Merge embedded file keywords into SQLite without blocking the UI thread."""
        self._tag_import_generation += 1
        gen = self._tag_import_generation
        old = self._tag_import_thread
        if old is not None:
            old.requestInterruption()
            try:
                old.scanned.disconnect()
            except TypeError:
                pass
            old.wait(8000)
            old.deleteLater()
            self._tag_import_thread = None
        th = _EmbeddedTagScanThread(paths)
        self._tag_import_thread = th
        th.scanned.connect(lambda pairs, g=gen: self._on_embedded_tag_scan_finished(pairs, g))
        th.finished.connect(self._on_embedded_tag_thread_finished)
        th.start()

    def _on_embedded_tag_thread_finished(self) -> None:
        th = self.sender()
        if th is self._tag_import_thread:
            self._tag_import_thread = None

    def _on_embedded_tag_scan_finished(self, pairs: object, generation: int) -> None:
        if generation != self._tag_import_generation:
            return
        if not isinstance(pairs, list):
            return
        from app.core.tags_importer import apply_embedded_tags_to_store

        apply_embedded_tags_to_store(self._store, cast(list[tuple[str, list[str]]], pairs))
        self._filter.reload_tags()
        self._tags.reload_tree_from_store()
        self._refresh_paths()
        if self._selected_image:
            self._metadata.show_path(self._selected_image)

    def _refresh_paths(self) -> None:
        """Re-sort/filter the current folder, preserving the current image selection."""
        paths = self._visible_paths()
        self._preview.set_paths(paths)
        self._info.set_item_count(len(paths))
        if self._selected_image and self._selected_image not in paths:
            self._selected_image = None
            self._metadata.clear()
            self._tags.set_selection([], None)
        elif self._selected_image:
            self._sync_tags_selection()
        self._preview.sync_favorite_tab_for_path(self._folder)

    def _sync_tags_selection(self) -> None:
        primary = self._selected_image
        if not primary:
            self._tags.set_selection([], None)
            return
        paths = self._preview.selected_paths()
        if not paths:
            paths = [primary]
        self._tags.set_selection(paths, primary)

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------

    def _on_preview_selection(self, path: str) -> None:
        self._selected_image = path
        self._metadata.show_path(path)
        self._sync_tags_selection()
        self._preview.take_preview_focus()

    def _on_layout_mode(self, mode: str) -> None:
        if self._locked_mode:
            mode = self._locked_mode
        prev = self._splitters_layout_mode
        if prev != mode:
            self._store_splitters_for_mode(prev)
        self._splitters_layout_mode = mode
        self._toolbar.set_mode(mode)
        self._preview.set_layout_mode(mode)
        self._apply_splitter_sizes(mode)

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
            current_folder=self._folder,
            thumbnail_cache=self._thumb_cache,
            confirm_delete_files=bool(self._settings.get("confirm_delete_files", True)),
        )
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        self._photoshop_exe = dlg.photoshop_exe()
        self._settings["photoshop_exe"] = self._photoshop_exe
        self._settings["drop_save_format"] = dlg.drop_save_format()
        self._settings["confirm_delete_files"] = dlg.confirm_delete_files()
        self._save_settings()

    def _open_in_photoshop(self, path: str) -> None:
        err = image_actions.launch_photoshop(self._photoshop_exe, path, self)
        if err:
            QMessageBox.warning(self, "Photoshop", err)

    def _on_preview_image_context_menu(self, path: str, global_pos: QPoint) -> None:
        if not path or not Path(path).is_file():
            return
        menu = QMenu(self)
        style_context_menu(menu)
        menu.addAction("Copy Image", lambda: self._copy_image(path))
        menu.addAction("Locate File", lambda: self._locate_file(path))
        menu.addAction("Open In Photoshop", lambda: self._open_in_photoshop(path))
        menu.addAction("Clear Tags", lambda: self._clear_tags_for_image(path))
        menu.addAction("Rename…", lambda: self._rename_file(path))
        menu.addAction("Delete…", lambda: self._delete_files([path]))
        menu.exec(global_pos)

    def _clear_tags_for_image(self, path: str) -> None:
        self._store.clear_tags_for_image(path)
        self._on_tags_changed()
        self._tags.sync_checks_from_store()
        if self._selected_image:
            self._metadata.show_path(self._selected_image)

    def _locate_file(self, path: str) -> None:
        err = image_actions.locate_file_in_explorer(path)
        if err:
            QMessageBox.warning(self, "Locate File", err)

    def _copy_image(self, path: str) -> None:
        err = image_actions.copy_image_to_clipboard(path)
        if err:
            QMessageBox.warning(self, "Copy Image", err)

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
        self._tags.set_selection([path], path)

    def _on_fullscreen_closed(self) -> None:
        self._fullscreen_view = None
        self._sync_tags_selection()

    # ------------------------------------------------------------------
    # File deletion
    # ------------------------------------------------------------------

    def _delete_files(self, paths: list[str]) -> None:
        if not paths:
            return
        if self._settings.get("confirm_delete_files", True):
            count = len(paths)
            noun = "file" if count == 1 else "files"
            names = "\n".join(Path(p).name for p in paths[:8])
            if count > 8:
                names += f"\n… and {count - 8} more"
            mb = QMessageBox(self)
            mb.setIcon(QMessageBox.Icon.Question)
            mb.setWindowTitle("Delete files")
            mb.setText(f"Permanently delete {count} {noun}?")
            mb.setInformativeText(f"{names}\n\nThis cannot be undone.")
            mb.setStandardButtons(
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            mb.setDefaultButton(QMessageBox.StandardButton.No)
            dont_ask = QCheckBox("Don't ask again")
            mb.setCheckBox(dont_ask)
            if mb.exec() != QMessageBox.StandardButton.Yes:
                return
            if dont_ask.isChecked():
                self._settings["confirm_delete_files"] = False
                settings_mod.save_settings({"confirm_delete_files": False})
        self._execute_delete(paths)

    def _execute_delete(self, paths: list[str]) -> None:
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
            self._tags.set_selection([], None)
        self._refresh_paths()

    def closeEvent(self, event) -> None:  # type: ignore[override]
        self._tag_import_generation += 1
        t = self._tag_import_thread
        if t is not None:
            t.requestInterruption()
            t.wait(3000)
        self._save_settings()
        self._thumb_cache.clear_pending()
        from PySide6.QtCore import QThreadPool
        QThreadPool.globalInstance().waitForDone(2000)
        super().closeEvent(event)

    def _save_settings(self) -> None:
        self._store_splitters_for_mode(self._splitters_layout_mode)
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
            "confirm_delete_files": bool(self._settings.get("confirm_delete_files", True)),
            "window_geometry": {"x": g.x(), "y": g.y(), "w": g.width(), "h": g.height()},
            "splitter_main": self._split_main.sizes(),
            "splitter_left": self._split_left.sizes(),
            "splitter_right": self._split_right.sizes(),
            "splitters_by_mode": self._settings.get("splitters_by_mode") or {},
        })
