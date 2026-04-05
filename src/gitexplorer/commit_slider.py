"""Commit timeline widget — replaces the old QSlider-based approach.

_Timeline is a fully custom-painted widget: a horizontal line with a dot per
commit, date labels where space allows, hover highlighting, tooltip, and full
keyboard / mouse-wheel navigation.  No QSlider involved.
"""
from __future__ import annotations

from PyQt6.QtCore import QPoint, QRect, Qt, pyqtSignal
from PyQt6.QtGui import (
    QColor,
    QFont,
    QFontMetrics,
    QPainter,
    QPen,
    QWheelEvent,
)
from PyQt6.QtWidgets import QLabel, QSizePolicy, QToolTip, QVBoxLayout, QWidget

from gitexplorer.git_backend import CommitInfo

# ── geometry constants ────────────────────────────────────────────────────────
_MARGIN   = 14   # px reserved on each side for the end dots
_LINE_Y   = 20   # y of the timeline track
_R_NORMAL = 4    # dot radius — unselected
_R_HOVER  = 5    # dot radius — hovered
_R_SEL    = 7    # dot radius — selected
_LABEL_GAP = 7   # px between track and top of date labels
_FONT_PX  = 10   # date-label font size in pixels
_H        = 56   # total widget height


# ── internal helpers ──────────────────────────────────────────────────────────

def _x_for(index: int, n: int, width: int) -> int:
    """Pixel x for commit *index* (0 = oldest/left, n-1 = newest/right)."""
    if n <= 1:
        return width // 2
    return int(_MARGIN + index / (n - 1) * (width - 2 * _MARGIN))


def _index_at(x: int, n: int, width: int) -> int:
    """Nearest commit index for pixel *x*."""
    if n <= 1:
        return 0
    frac = (x - _MARGIN) / max(1, width - 2 * _MARGIN)
    return max(0, min(n - 1, round(frac * (n - 1))))


# ── timeline widget ───────────────────────────────────────────────────────────

class _Timeline(QWidget):
    """Custom-painted interactive commit timeline."""

    activated = pyqtSignal(int)   # emitted when the selected index changes

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._commits: list[CommitInfo] = []
        self._current = 0
        self._hovered = -1

        self.setFixedHeight(_H)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.ClickFocus)

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def set_commits(self, commits: list[CommitInfo], current: int) -> None:
        self._commits = commits
        self._current = current
        self._hovered = -1
        self.update()

    def set_current(self, index: int) -> None:
        self._current = index
        self.update()

    # ------------------------------------------------------------------
    # Painting
    # ------------------------------------------------------------------

    def paintEvent(self, event) -> None:  # noqa: N802
        n = len(self._commits)
        if n == 0:
            return

        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w = self.width()

        # ── track line ──────────────────────────────────────────────
        p.setPen(QPen(QColor("#4a4a4a"), 1))
        p.drawLine(_MARGIN, _LINE_Y, w - _MARGIN, _LINE_Y)

        # ── date labels ─────────────────────────────────────────────
        lbl_font = QFont()
        lbl_font.setPixelSize(_FONT_PX)
        p.setFont(lbl_font)
        fm = QFontMetrics(lbl_font)
        lbl_top = _LINE_Y + _LABEL_GAP

        prev_right = -9999
        for i, c in enumerate(self._commits):
            x = _x_for(i, n, w)
            label = c.date[:10]
            tw = fm.horizontalAdvance(label)
            lx = max(0, min(x - tw // 2, w - tw))

            if lx < prev_right + 3:
                continue

            color = QColor("#e0e0e0") if i == self._current else QColor("#666666")
            p.setPen(color)
            p.drawText(lx, lbl_top + fm.ascent(), label)
            prev_right = lx + tw

        # ── dots (drawn after labels so they sit on top) ─────────────
        for i in range(n):
            x = _x_for(i, n, w)
            is_sel = (i == self._current)
            is_hov = (i == self._hovered and not is_sel)

            if is_sel:
                r = _R_SEL
                p.setBrush(QColor("#f0f0f0"))
                p.setPen(QPen(QColor("#888888"), 1))
            elif is_hov:
                r = _R_HOVER
                p.setBrush(QColor("#999999"))
                p.setPen(QPen(QColor("#777777"), 1))
            else:
                r = _R_NORMAL
                p.setBrush(QColor("#555555"))
                p.setPen(QPen(QColor("#444444"), 1))

            p.drawEllipse(QPoint(x, _LINE_Y), r, r)

        p.end()

    # ------------------------------------------------------------------
    # Mouse
    # ------------------------------------------------------------------

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton and self._commits:
            idx = _index_at(event.pos().x(), len(self._commits), self.width())
            if idx != self._current:
                self._current = idx
                self.update()
                self.activated.emit(idx)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if not self._commits:
            return
        idx = _index_at(event.pos().x(), len(self._commits), self.width())
        if idx != self._hovered:
            self._hovered = idx
            self.update()
        c = self._commits[idx]
        QToolTip.showText(
            event.globalPosition().toPoint(),
            f"[{c.short_hash}]  {c.date}\n{c.author}\n{c.message}",
            self,
        )

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._hovered = -1
        self.update()

    def wheelEvent(self, event: QWheelEvent) -> None:
        if not self._commits:
            return
        step = 1 if event.angleDelta().y() > 0 else -1
        new = max(0, min(len(self._commits) - 1, self._current + step))
        if new != self._current:
            self._current = new
            self.update()
            self.activated.emit(new)
        event.accept()

    def keyPressEvent(self, event) -> None:  # noqa: N802
        n = len(self._commits)
        if not n:
            return
        key = event.key()
        if key == Qt.Key.Key_Left:
            new = max(0, self._current - 1)
        elif key == Qt.Key.Key_Right:
            new = min(n - 1, self._current + 1)
        elif key == Qt.Key.Key_Home:
            new = 0
        elif key == Qt.Key.Key_End:
            new = n - 1
        else:
            super().keyPressEvent(event)
            return
        if new != self._current:
            self._current = new
            self.update()
            self.activated.emit(new)


# ── public composite widget ───────────────────────────────────────────────────

class CommitSlider(QWidget):
    """Timeline + detail label.  Drop-in replacement for the old slider widget."""

    commit_changed = pyqtSignal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._commits: list[CommitInfo] = []
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        self._timeline = _Timeline()
        self._timeline.activated.connect(self._on_activated)
        layout.addWidget(self._timeline)

        self._info = QLabel()
        self._info.setStyleSheet("color: #cccccc; font-size: 14px;")
        self._info.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        layout.addWidget(self._info)

    # ------------------------------------------------------------------
    # Public API (same as before)
    # ------------------------------------------------------------------

    def set_commits(self, commits: list[CommitInfo]) -> None:
        self._commits = commits
        last = max(len(commits) - 1, 0)
        self._timeline.set_commits(commits, last)
        self._update_label(last)
        self.commit_changed.emit(last)

    def current_index(self) -> int:
        return self._timeline._current

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _on_activated(self, index: int) -> None:
        self._update_label(index)
        self.commit_changed.emit(index)

    def _update_label(self, index: int) -> None:
        if index < len(self._commits):
            c = self._commits[index]
            self._info.setText(
                f"[{c.short_hash}]  {c.date}  —  {c.author}:  {c.message}"
            )
        else:
            self._info.setText("")
