"""Modal settings dialog; add new sections here as the app grows."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.core import file_scanner
from app.core.thumbnail_cache import ThumbnailCache
from app.ui.drop_import import normalize_drop_format


class SettingsDialog(QDialog):
    """User preferences. Extend with additional group boxes / rows as needed."""

    def __init__(
        self,
        photoshop_exe: str,
        drop_save_format: str = "webp",
        parent: QWidget | None = None,
        *,
        current_folder: str = "",
        thumbnail_cache: ThumbnailCache | None = None,
        confirm_delete_files: bool = True,
    ) -> None:
        super().__init__(parent)
        self._current_folder = current_folder.strip()
        self._thumb_cache = thumbnail_cache

        self.setWindowTitle("Settings")
        self.setMinimumWidth(520)

        root = QVBoxLayout(self)
        root.setSpacing(12)

        external = QGroupBox("External applications")
        ext_lay = QVBoxLayout(external)
        ext_lay.setSpacing(8)

        ext_lay.addWidget(QLabel("Adobe Photoshop executable (Photoshop.exe):"))
        row = QHBoxLayout()
        self._photoshop_edit = QLineEdit()
        self._photoshop_edit.setPlaceholderText("Not set — use Browse to choose Photoshop.exe")
        self._photoshop_edit.setText(photoshop_exe.strip())
        self._photoshop_edit.setClearButtonEnabled(True)
        row.addWidget(self._photoshop_edit, stretch=1)
        browse = QPushButton("Browse…")
        browse.clicked.connect(self._browse_photoshop)
        row.addWidget(browse)
        ext_lay.addLayout(row)

        root.addWidget(external)

        save_grp = QGroupBox("Dropped images (preview panel)")
        save_lay = QVBoxLayout(save_grp)
        save_lay.setSpacing(6)
        save_lay.addWidget(
            QLabel(
                "When you drag an image from another app onto the preview area, "
                "it is converted and saved into the active folder:"
            )
        )
        self._format = QComboBox()
        for key, label in (
            ("webp", "WebP (.webp)"),
            ("jpeg", "JPEG (.jpg)"),
            ("png", "PNG (.png)"),
        ):
            self._format.addItem(label, key)
        idx = self._format.findData(normalize_drop_format(drop_save_format))
        self._format.setCurrentIndex(idx if idx >= 0 else 0)
        save_lay.addWidget(self._format)

        root.addWidget(save_grp)

        files_grp = QGroupBox("Files")
        files_lay = QVBoxLayout(files_grp)
        files_lay.setSpacing(6)
        self._confirm_delete_cb = QCheckBox("Ask for confirmation before deleting images")
        self._confirm_delete_cb.setChecked(confirm_delete_files)
        files_lay.addWidget(self._confirm_delete_cb)
        root.addWidget(files_grp)

        thumbs_grp = QGroupBox("Thumbnails")
        thumbs_lay = QVBoxLayout(thumbs_grp)
        thumbs_lay.setSpacing(8)
        thumbs_lay.addWidget(
            QLabel(
                "Generate queues 512px and 1024px WebP previews for every image in the "
                "folder currently open in Mason (same scope as the folder tree, not subfolders)."
            )
        )
        self._folder_label = QLabel()
        self._folder_label.setWordWrap(True)
        self._folder_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self._sync_folder_caption()
        thumbs_lay.addWidget(self._folder_label)
        gen_row = QHBoxLayout()
        self._gen_thumbs_btn = QPushButton("Generate thumbnails for current folder")
        self._gen_thumbs_btn.clicked.connect(self._on_generate_thumbnails)
        gen_row.addWidget(self._gen_thumbs_btn)
        gen_row.addStretch(1)
        thumbs_lay.addLayout(gen_row)

        thumbs_lay.addWidget(
            QLabel(
                "Purge deletes all WebP files in the app thumbnail cache directory "
                "(not your original photos)."
            )
        )
        purge_row = QHBoxLayout()
        self._purge_thumbs_btn = QPushButton("Purge thumbnail cache…")
        self._purge_thumbs_btn.clicked.connect(self._on_purge_thumbnails)
        purge_row.addWidget(self._purge_thumbs_btn)
        purge_row.addStretch(1)
        thumbs_lay.addLayout(purge_row)

        root.addWidget(thumbs_grp)

        enable_thumb_actions = self._thumb_cache is not None
        self._gen_thumbs_btn.setEnabled(enable_thumb_actions)
        self._purge_thumbs_btn.setEnabled(enable_thumb_actions)

        root.addStretch(1)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def photoshop_exe(self) -> str:
        return self._photoshop_edit.text().strip()

    def drop_save_format(self) -> str:
        data = self._format.currentData()
        return normalize_drop_format(str(data) if data is not None else "webp")

    def confirm_delete_files(self) -> bool:
        return self._confirm_delete_cb.isChecked()

    def _sync_folder_caption(self) -> None:
        if not self._current_folder:
            self._folder_label.setText("Current folder: (none — open a folder in Mason first)")
            return
        self._folder_label.setText(f"Current folder:\n{self._current_folder}")

    def _on_generate_thumbnails(self) -> None:
        if self._thumb_cache is None:
            return
        folder = self._current_folder
        if not folder:
            QMessageBox.warning(
                self,
                "Thumbnails",
                "No folder is open. Browse to a folder in Mason first.",
            )
            return
        root = Path(folder)
        if not root.is_dir():
            QMessageBox.warning(self, "Thumbnails", "The current folder path is not valid.")
            return
        paths = file_scanner.scan_folder(root, recursive=False)
        if not paths:
            QMessageBox.information(
                self,
                "Thumbnails",
                "No supported images were found in the current folder.",
            )
            return
        for p in paths:
            self._thumb_cache.request(p, 512)
            self._thumb_cache.request(p, 1024)
        QMessageBox.information(
            self,
            "Thumbnails",
            f"Queued {len(paths)} images for 512px and 1024px previews. "
            "Generation runs in the background.",
        )

    def _on_purge_thumbnails(self) -> None:
        if self._thumb_cache is None:
            return
        ret = QMessageBox.question(
            self,
            "Purge thumbnails",
            "Remove all WebP thumbnail files from Mason’s cache folder?\n\n"
            "Your original images are not affected.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if ret != QMessageBox.StandardButton.Yes:
            return
        self._thumb_cache.purge_disk_and_memory()
        QMessageBox.information(self, "Thumbnails", "Thumbnail cache purged.")

    def _browse_photoshop(self) -> None:
        cur = self._photoshop_edit.text().strip()
        start = str(Path(cur).parent) if cur and Path(cur).parent.is_dir() else str(Path.home())
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Photoshop executable",
            start,
            "Executable (Photoshop.exe);;All files (*.*)",
        )
        if path:
            self._photoshop_edit.setText(path)
