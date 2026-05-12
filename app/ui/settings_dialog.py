"""Modal settings dialog; add new sections here as the app grows."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class SettingsDialog(QDialog):
    """User preferences. Extend with additional group boxes / rows as needed."""

    def __init__(self, photoshop_exe: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
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
        root.addStretch(1)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def photoshop_exe(self) -> str:
        return self._photoshop_edit.text().strip()

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
