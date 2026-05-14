"""Mason — entry point."""

from __future__ import annotations

import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

from app.ui.qt_chrome import install_transient_scroll_style
from app.window import MainWindow


def main() -> None:
    # Prefer non-native child widgets on Windows to reduce HWND churn / flicker
    # when many QLabel tiles are created or reparented. (Avoid AA_UseSoftwareOpenGL;
    # it can add its own visual issues.)
    QApplication.setAttribute(Qt.ApplicationAttribute.AA_NativeWindows, False)
    QApplication.setAttribute(Qt.ApplicationAttribute.AA_DontCreateNativeWidgetSiblings, True)

    app = QApplication(sys.argv)
    app.setApplicationName("Mason")
    app.setOrganizationName("Mason")

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
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
