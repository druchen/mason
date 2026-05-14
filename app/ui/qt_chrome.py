"""Application-wide Qt styling helpers (scrollbars, etc.)."""

from __future__ import annotations

from PySide6.QtWidgets import QApplication, QProxyStyle, QStyle


class TransientScrollProxyStyle(QProxyStyle):
    """Overlay scrollbars that appear while scrolling / on hover (platform-dependent)."""

    def styleHint(
        self,
        hint: QStyle.StyleHint,
        option=None,
        widget=None,
        returnData=None,
    ) -> int:
        if hint == QStyle.StyleHint.SH_ScrollBar_Transient:
            return 1
        return super().styleHint(hint, option, widget, returnData)


def install_transient_scroll_style(app: QApplication) -> None:
    """Wrap the current application style so scroll areas use transient scrollbars."""
    base = app.style()
    if base is None or isinstance(base, TransientScrollProxyStyle):
        return
    app.setStyle(TransientScrollProxyStyle(base))
