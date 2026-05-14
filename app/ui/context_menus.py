"""Shared Mason context-menu (right-click) look: hover, padding, cursor.

Call ``style_context_menu(menu)`` on every ``QMenu`` right after ``QMenu(parent)``
and before ``addAction`` / ``exec``, so new menus stay visually consistent.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMenu

MASON_CONTEXT_MENU_OBJECT_NAME = "masonContextMenu"

MASON_CONTEXT_MENU_QSS = f"""
QMenu#{MASON_CONTEXT_MENU_OBJECT_NAME} {{
    background-color: #2a2a2a;
    border: 1px solid #555555;
    border-radius: 4px;
    padding: 4px 8px;
}}
QMenu#{MASON_CONTEXT_MENU_OBJECT_NAME}::item {{
    background-color: transparent;
    border: none;
    border-radius: 3px;
    padding: 7px 12px;
    color: #e0e0e0;
}}
QMenu#{MASON_CONTEXT_MENU_OBJECT_NAME}::item:selected {{
    background-color: #505050;
    color: #f0f0f0;
}}
QMenu#{MASON_CONTEXT_MENU_OBJECT_NAME}::item:hover {{
    background-color: #222222;
    color: #f0f0f0;
}}
QMenu#{MASON_CONTEXT_MENU_OBJECT_NAME}::item:pressed {{
    background-color: #505050;
    color: #f0f0f0;
}}
QMenu#{MASON_CONTEXT_MENU_OBJECT_NAME}::separator {{
    height: 1px;
    margin: 4px 8px;
    background: #444444;
}}
"""


def style_context_menu(menu: QMenu) -> None:
    """Apply Mason context-menu styling (matches panel icon toolbutton hover)."""
    menu.setObjectName(MASON_CONTEXT_MENU_OBJECT_NAME)
    menu.setStyleSheet(MASON_CONTEXT_MENU_QSS)
    menu.setCursor(Qt.CursorShape.PointingHandCursor)
