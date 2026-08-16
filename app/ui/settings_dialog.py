"""Frameless settings dialog. Add new sections via ``_section`` / ``_row``."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import (
    Property,
    QEasingCurve,
    QPoint,
    QPointF,
    QPropertyAnimation,
    QRectF,
    QSize,
    Qt,
    QTimer,
)
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QAbstractButton,
    QComboBox,
    QDialog,
    QFileDialog,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.core import file_scanner
from app.core.thumbnail_cache import ThumbnailCache
from app.ui.drop_import import normalize_drop_format
from app.ui.image_actions import locate_folder_in_explorer

# Tuned against the main window palette (window.py _apply_stylesheet).
_SURFACE = "#232323"
_HAIRLINE = "#333333"
_FIELD_BG = "#1a1a1a"
_FIELD_BORDER = "#383838"
_ACCENT = "#5ab4f5"
_TEXT = "#e0e0e0"
_TEXT_DIM = "#8c8c8c"
_TEXT_FAINT = "#6e6e6e"

_CORNER_R = 10
_SHADOW_PAD = 18  # translucent margin the drop shadow is painted into


class ToggleSwitch(QAbstractButton):
    """Sliding switch. A QCheckBox indicator reads as a Windows control."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(38, 20)
        self._pos = 0.0
        self._anim = QPropertyAnimation(self, b"knob", self)
        self._anim.setDuration(130)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.toggled.connect(self._animate)

    def _animate(self, on: bool) -> None:
        self._anim.stop()
        self._anim.setStartValue(self._pos)
        self._anim.setEndValue(1.0 if on else 0.0)
        self._anim.start()

    def setChecked(self, on: bool) -> None:  # type: ignore[override]
        super().setChecked(on)
        self._anim.stop()
        self._set_knob(1.0 if on else 0.0)

    def _get_knob(self) -> float:
        return self._pos

    def _set_knob(self, v: float) -> None:
        self._pos = float(v)
        self.update()

    knob = Property(float, _get_knob, _set_knob)

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        h = self.height()
        r = h / 2.0
        track_off = QColor("#3a3a3a")
        track_on = QColor(_ACCENT)
        track = QColor(
            int(track_off.red() + (track_on.red() - track_off.red()) * self._pos),
            int(track_off.green() + (track_on.green() - track_off.green()) * self._pos),
            int(track_off.blue() + (track_on.blue() - track_off.blue()) * self._pos),
        )
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(track)
        p.drawRoundedRect(QRectF(0, 0, self.width(), h), r, r)
        knob_r = r - 3.0
        cx = r + self._pos * (self.width() - 2 * r)
        p.setBrush(QColor("#f0f0f0" if self._pos > 0.5 else "#c8c8c8"))
        p.drawEllipse(QRectF(cx - knob_r, r - knob_r, knob_r * 2, knob_r * 2))
        p.end()

    def sizeHint(self) -> QSize:
        return QSize(38, 20)


class _Combo(QComboBox):
    """Combo that draws its own chevron; the native arrow is the Windows tell."""

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(QColor(_TEXT_DIM))
        pen.setWidthF(1.4)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
        cx = self.width() - 14.0
        cy = self.height() / 2.0
        p.drawLine(QPointF(cx - 3.5, cy - 1.5), QPointF(cx, cy + 2.0))
        p.drawLine(QPointF(cx, cy + 2.0), QPointF(cx + 3.5, cy - 1.5))
        p.end()


class _CloseButton(QAbstractButton):
    """Hairline ✕ that lights up on hover."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(28, 28)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._hover = False

    def enterEvent(self, e) -> None:
        self._hover = True
        self.update()
        super().enterEvent(e)

    def leaveEvent(self, e) -> None:
        self._hover = False
        self.update()
        super().leaveEvent(e)

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self._hover:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor("#3a3a3a"))
            p.drawRoundedRect(QRectF(0, 0, self.width(), self.height()), 5, 5)
        pen = QPen(QColor(_TEXT if self._hover else _TEXT_DIM))
        pen.setWidthF(1.3)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        c, d = self.width() / 2.0, 4.0
        p.drawLine(int(c - d), int(c - d), int(c + d), int(c + d))
        p.drawLine(int(c + d), int(c - d), int(c - d), int(c + d))
        p.end()


class SettingsDialog(QDialog):
    """User preferences."""

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
        self._drag_from: QPoint | None = None

        self.setWindowTitle("Settings")
        self.setWindowFlags(
            Qt.WindowType.Dialog
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.NoDropShadowWindowHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setModal(True)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(_SHADOW_PAD, _SHADOW_PAD, _SHADOW_PAD, _SHADOW_PAD)

        self._card = QWidget()
        self._card.setObjectName("settingsCard")
        outer.addWidget(self._card)

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(34)
        shadow.setOffset(0, 6)
        shadow.setColor(QColor(0, 0, 0, 190))
        self._card.setGraphicsEffect(shadow)

        card = QVBoxLayout(self._card)
        card.setContentsMargins(0, 0, 0, 0)
        card.setSpacing(0)

        card.addWidget(self._build_title_bar())

        body = QWidget()
        body_lay = QVBoxLayout(body)
        body_lay.setContentsMargins(22, 18, 22, 4)
        body_lay.setSpacing(0)
        card.addWidget(body)

        # --- external ---
        body_lay.addWidget(self._section("External"))
        self._photoshop_edit = QLineEdit(photoshop_exe.strip())
        self._photoshop_edit.setPlaceholderText("Photoshop.exe")
        self._photoshop_edit.setClearButtonEnabled(True)
        self._photoshop_edit.setCursorPosition(0)  # show the head of the path
        browse = QPushButton("Browse")
        browse.setObjectName("ghost")
        browse.setCursor(Qt.CursorShape.PointingHandCursor)
        browse.clicked.connect(self._browse_photoshop)
        ps = QWidget()
        ps_lay = QHBoxLayout(ps)
        ps_lay.setContentsMargins(0, 0, 0, 0)
        ps_lay.setSpacing(6)
        ps_lay.addWidget(self._photoshop_edit, 1)
        ps_lay.addWidget(browse, 0)
        body_lay.addWidget(self._row("Photoshop", ps, stretch_control=True))

        # --- images ---
        body_lay.addWidget(self._section("Images"))
        self._format = _Combo()
        self._format.setCursor(Qt.CursorShape.PointingHandCursor)
        for key, label in (("webp", "WebP"), ("jpeg", "JPEG"), ("png", "PNG")):
            self._format.addItem(label, key)
        idx = self._format.findData(normalize_drop_format(drop_save_format))
        self._format.setCurrentIndex(idx if idx >= 0 else 0)
        self._format.setFixedWidth(120)
        body_lay.addWidget(self._row("Drop format", self._format))

        self._confirm_delete_cb = ToggleSwitch()
        self._confirm_delete_cb.setChecked(confirm_delete_files)
        body_lay.addWidget(self._row("Confirm deletes", self._confirm_delete_cb))

        # --- thumbnails ---
        body_lay.addWidget(self._section("Thumbnails"))
        self._folder_label = QLabel()
        self._folder_label.setObjectName("pathHint")
        self._folder_label.setToolTip(self._current_folder or "No folder open")
        body_lay.addWidget(self._folder_label)
        body_lay.addSpacing(8)

        self._gen_thumbs_btn = QPushButton("Generate")
        self._gen_thumbs_btn.clicked.connect(self._on_generate_thumbnails)
        self._open_thumb_dir_btn = QPushButton("Open cache")
        self._open_thumb_dir_btn.clicked.connect(self._on_open_thumbnail_folder)
        self._purge_thumbs_btn = QPushButton("Purge")
        self._purge_thumbs_btn.setObjectName("danger")
        self._purge_armed = False
        self._purge_thumbs_btn.clicked.connect(self._on_purge_thumbnails)
        thumb_row = QHBoxLayout()
        thumb_row.setContentsMargins(0, 0, 0, 0)
        thumb_row.setSpacing(6)
        for b in (self._gen_thumbs_btn, self._open_thumb_dir_btn, self._purge_thumbs_btn):
            b.setObjectName(b.objectName() or "ghost")
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setEnabled(self._thumb_cache is not None)
            thumb_row.addWidget(b)
        thumb_row.addStretch(1)
        body_lay.addLayout(thumb_row)

        card.addStretch(1)
        card.addWidget(self._build_footer())

        self.setFixedWidth(520 + 2 * _SHADOW_PAD)
        self._apply_style()
        self._sync_folder_caption()

    # ---------------- chrome ----------------

    def _build_title_bar(self) -> QWidget:
        bar = QWidget()
        bar.setObjectName("titleBar")
        bar.setFixedHeight(44)
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(20, 0, 10, 0)
        title = QLabel("Settings")
        title.setObjectName("title")
        lay.addWidget(title, 0, Qt.AlignmentFlag.AlignVCenter)
        lay.addStretch(1)
        close = _CloseButton()
        close.clicked.connect(self.reject)
        lay.addWidget(close, 0, Qt.AlignmentFlag.AlignVCenter)
        bar.installEventFilter(self)
        self._title_bar = bar
        return bar

    def _build_footer(self) -> QWidget:
        foot = QWidget()
        foot.setObjectName("footer")
        foot.setFixedHeight(58)
        lay = QHBoxLayout(foot)
        lay.setContentsMargins(22, 0, 22, 0)
        lay.setSpacing(8)
        self._status = QLabel("")
        self._status.setObjectName("status")
        lay.addWidget(self._status, 1, Qt.AlignmentFlag.AlignVCenter)
        cancel = QPushButton("Cancel")
        cancel.setObjectName("ghost")
        cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel.clicked.connect(self.reject)
        done = QPushButton("Done")
        done.setObjectName("primary")
        done.setCursor(Qt.CursorShape.PointingHandCursor)
        done.setDefault(True)
        done.clicked.connect(self.accept)
        lay.addWidget(cancel, 0)
        lay.addWidget(done, 0)
        return foot

    def _section(self, text: str) -> QWidget:
        w = QLabel(text.upper())
        w.setObjectName("sectionLabel")
        f = QFont(w.font())
        f.setPointSizeF(max(7.0, f.pointSizeF() - 2.0))
        f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 1.1)
        f.setBold(True)
        w.setFont(f)
        return w

    def _row(self, label: str, control: QWidget, *, stretch_control: bool = False) -> QWidget:
        w = QWidget()
        w.setObjectName("row")
        lay = QHBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(12)
        lab = QLabel(label)
        lab.setObjectName("rowLabel")
        lab.setFixedWidth(120)
        lay.addWidget(lab, 0, Qt.AlignmentFlag.AlignVCenter)
        lay.addWidget(control, 1 if stretch_control else 0, Qt.AlignmentFlag.AlignVCenter)
        if not stretch_control:
            lay.addStretch(1)
        return w

    def eventFilter(self, obj, event):
        """Drag the frameless window by its title bar."""
        if obj is getattr(self, "_title_bar", None):
            if event.type() == event.Type.MouseButtonPress:
                if event.button() == Qt.MouseButton.LeftButton:
                    handle = self.windowHandle()
                    if handle is not None:
                        handle.startSystemMove()
                    else:
                        self._drag_from = event.globalPosition().toPoint() - self.pos()
                    return True
            elif event.type() == event.Type.MouseMove and self._drag_from is not None:
                self.move(event.globalPosition().toPoint() - self._drag_from)
                return True
            elif event.type() == event.Type.MouseButtonRelease:
                self._drag_from = None
        return super().eventFilter(obj, event)

    def _apply_style(self) -> None:
        self.setStyleSheet(
            f"""
            QWidget#settingsCard {{
                background-color: {_SURFACE};
                border-radius: {_CORNER_R}px;
            }}
            QWidget#titleBar {{
                background-color: {_SURFACE};
                border-top-left-radius: {_CORNER_R}px;
                border-top-right-radius: {_CORNER_R}px;
                border-bottom: 1px solid {_HAIRLINE};
            }}
            QWidget#footer {{
                background-color: {_SURFACE};
                border-bottom-left-radius: {_CORNER_R}px;
                border-bottom-right-radius: {_CORNER_R}px;
                border-top: 1px solid {_HAIRLINE};
            }}
            QLabel {{ background: transparent; color: {_TEXT}; }}
            QLabel#title {{ color: {_TEXT}; }}
            QLabel#sectionLabel {{
                color: {_TEXT_FAINT};
                padding-top: 14px;
                padding-bottom: 8px;
            }}
            QLabel#rowLabel {{ color: {_TEXT_DIM}; }}
            QLabel#pathHint {{ color: {_TEXT_FAINT}; }}
            QLabel#status {{ color: {_TEXT_FAINT}; }}
            QWidget#row {{ min-height: 30px; }}

            QLineEdit, QComboBox {{
                background-color: {_FIELD_BG};
                border: 1px solid {_FIELD_BORDER};
                border-radius: 5px;
                padding: 5px 9px;
                color: {_TEXT};
                selection-background-color: {_ACCENT};
                selection-color: #10222e;
            }}
            QLineEdit:hover, QComboBox:hover {{ border-color: #4a4a4a; }}
            QLineEdit:focus, QComboBox:focus {{ border-color: {_ACCENT}; }}
            QComboBox::drop-down {{ border: none; width: 18px; }}
            QComboBox QAbstractItemView {{
                background-color: #1e1e1e;
                border: 1px solid {_FIELD_BORDER};
                border-radius: 5px;
                selection-background-color: #33506b;
                outline: none;
                padding: 3px;
            }}

            QPushButton {{
                border-radius: 5px;
                padding: 6px 14px;
                min-height: 18px;
            }}
            QPushButton#ghost {{
                background-color: transparent;
                border: 1px solid {_FIELD_BORDER};
                color: {_TEXT};
            }}
            QPushButton#ghost:hover {{ background-color: #2d2d2d; border-color: #4a4a4a; }}
            QPushButton#ghost:pressed {{ background-color: #363636; }}
            QPushButton#ghost:disabled {{ color: #555555; border-color: #2c2c2c; }}
            QPushButton#danger {{
                background-color: transparent;
                border: 1px solid #4a3030;
                color: #d98b8b;
            }}
            QPushButton#danger:hover {{ background-color: #3a2626; border-color: #6a4040; }}
            QPushButton#danger:disabled {{ color: #4a3a3a; border-color: #2c2424; }}
            QPushButton#primary {{
                background-color: {_ACCENT};
                border: none;
                color: #0f1c26;
                font-weight: 600;
                padding: 6px 20px;
            }}
            QPushButton#primary:hover {{ background-color: #74c2f7; }}
            QPushButton#primary:pressed {{ background-color: #4aa3e4; }}
            """
        )

    # ---------------- values ----------------

    def photoshop_exe(self) -> str:
        return self._photoshop_edit.text().strip()

    def drop_save_format(self) -> str:
        data = self._format.currentData()
        return normalize_drop_format(str(data) if data is not None else "webp")

    def confirm_delete_files(self) -> bool:
        return self._confirm_delete_cb.isChecked()

    # ---------------- behaviour ----------------

    def _flash(self, msg: str) -> None:
        """Transient footer note, in place of an information popup."""
        self._status.setText(msg)
        QTimer.singleShot(4000, lambda: self._status.setText(""))

    def _sync_folder_caption(self) -> None:
        if not self._current_folder:
            self._folder_label.setText("No folder open")
            return
        fm = QFontMetrics(self._folder_label.font())
        self._folder_label.setText(
            fm.elidedText(self._current_folder, Qt.TextElideMode.ElideMiddle, 470)
        )

    def _on_generate_thumbnails(self) -> None:
        if self._thumb_cache is None:
            return
        root = Path(self._current_folder) if self._current_folder else None
        if root is None or not root.is_dir():
            self._flash("No valid folder open")
            return
        paths = file_scanner.scan_folder(root, recursive=False)
        if not paths:
            self._flash("No supported images in this folder")
            return
        for p in paths:
            self._thumb_cache.request(p, 512)
            self._thumb_cache.request(p, 1024)
        self._flash(f"Queued {len(paths):,} images")

    def _on_open_thumbnail_folder(self) -> None:
        if self._thumb_cache is None:
            return
        err = locate_folder_in_explorer(str(self._thumb_cache.cache_directory()))
        if err:
            self._flash(err)

    def _reset_purge_button(self) -> None:
        self._purge_armed = False
        self._purge_thumbs_btn.setText("Purge")

    def _on_purge_thumbnails(self) -> None:
        """Arm on the first click, purge on the second — avoids a native popup."""
        if self._thumb_cache is None:
            return
        if not self._purge_armed:
            self._purge_armed = True
            self._purge_thumbs_btn.setText("Click to confirm")
            self._flash("Removes cached thumbnails only")
            QTimer.singleShot(4000, self._reset_purge_button)
            return
        self._reset_purge_button()
        self._thumb_cache.purge_disk_and_memory()
        self._flash("Cache purged")

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

    def paintEvent(self, _event) -> None:
        """Round the translucent top level so the card's corners are not squared off."""
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(
            QRectF(self._card.geometry()), float(_CORNER_R), float(_CORNER_R)
        )
        p.fillPath(path, QColor(_SURFACE))
        p.end()
