"""Mason — entry point."""

from __future__ import annotations

import sys

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

from app.window import MainWindow


def main() -> None:
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

    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
