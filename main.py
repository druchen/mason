"""Mason — entry point."""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QIcon
from PySide6.QtWidgets import QApplication

from app.ui.qt_chrome import install_transient_scroll_style
from app.window import MainWindow


def _app_icon_path() -> Path | None:
    """Bundled Mason.ico when frozen (PyInstaller onedir) or dev tree under assets/icons."""
    if getattr(sys, "frozen", False):
        base = Path(sys.executable).resolve().parent
        ico = base / "_internal" / "assets" / "icons" / "Mason.ico"
        return ico if ico.is_file() else None
    root = Path(__file__).resolve().parent
    ico = root / "assets" / "icons" / "Mason.ico"
    return ico if ico.is_file() else None


def main() -> None:
    # Prefer non-native child widgets on Windows to reduce HWND churn / flicker
    # when many QLabel tiles are created or reparented. (Avoid AA_UseSoftwareOpenGL;
    # it can add its own visual issues.)
    QApplication.setAttribute(Qt.ApplicationAttribute.AA_NativeWindows, False)
    QApplication.setAttribute(Qt.ApplicationAttribute.AA_DontCreateNativeWidgetSiblings, True)

    app = QApplication(sys.argv)
    app.setApplicationName("Mason")
    app.setOrganizationName("Mason")

    icon_path = _app_icon_path()
    if icon_path is not None:
        app.setWindowIcon(QIcon(str(icon_path)))

    # Pixel-only system fonts (pointSize == -1) + stylesheet font sizes can make Qt
    # call setPointSize(-1) on some widgets. Use an explicit point-sized UI font.
    src = app.font()
    ui = QFont(src)
    ps = src.pointSize()
    if ps > 0:
        ui.setPointSize(ps)
    else:
        ui.setPointSize(13)
    app.setFont(ui)
    install_transient_scroll_style(app)

    win = MainWindow()
    if icon_path is not None:
        win.setWindowIcon(QIcon(str(icon_path)))
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
