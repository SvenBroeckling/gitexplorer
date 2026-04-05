"""Horizontal commit timeline slider widget."""
from __future__ import annotations

from PyQt6.QtCore import QPoint, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QPainter, QPen, QPolygon, QWheelEvent
from PyQt6.QtWidgets import (
    QLabel,
    QSizePolicy,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from gitexplorer.git_backend import CommitInfo


# ── helpers ──────────────────────────────────────────────────────────────────

def _commit_x(index: int, span: int, usable: int, margin: int = 10) -> int:
    """Pixel x for commit *index* given the groove geometry."""
    frac = index / span if span else 0
    return int(margin + frac * usable)


# ── tick slider ───────────────────────────────────────────────────────────────

class _TickSlider(QSlider):
    """QSlider with custom diamond ticks; wheel moves exactly one step."""

    TICK_H = 8

    def paintEvent(self, event) -> None:  # noqa: N802
        super().paintEvent(event)
        span = self.maximum() - self.minimum()
        if span == 0:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w, h = self.width(), self.height()
        usable = w - 20

        painter.setPen(QPen(QColor("#aaaaaa"), 1))
        painter.setBrush(QColor("#888888"))

        size = 3
        cy = h - self.TICK_H - 2

        for i in range(self.minimum(), self.maximum() + 1):
            x = _commit_x(i, span, usable)
            pts = [QPoint(x, cy), QPoint(x + size, cy + size),
                   QPoint(x, cy + size * 2), QPoint(x - size, cy + size)]
            painter.drawPolygon(QPolygon(pts))

        painter.end()

    def wheelEvent(self, event: QWheelEvent) -> None:
        step = 1 if event.angleDelta().y() > 0 else -1
        self.setValue(self.value() + step)
        event.accept()


# ── date ruler ────────────────────────────────────────────────────────────────

class _DateRuler(QWidget):
    """Paints short date strings aligned under each commit tick mark.

    x-positions mirror *_TickSlider* exactly so labels sit under diamonds.
    """

    _FONT_PX = 10
    _H = 18        # fixed widget height

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._dates: list[str] = []
        self.setFixedHeight(self._H)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def set_dates(self, dates: list[str]) -> None:
        self._dates = dates
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        if not self._dates:
            return

        span = len(self._dates) - 1
        usable = self.width() - 20

        painter = QPainter(self)
        font = QFont()
        font.setPixelSize(self._FONT_PX)
        painter.setFont(font)
        painter.setPen(QColor("#777777"))
        metrics = painter.fontMetrics()

        prev_right = -9999
        baseline = self._H - 2

        for i, label in enumerate(self._dates):
            x = _commit_x(i, span, usable)
            text_w = metrics.horizontalAdvance(label)
            lx = x - text_w // 2

            # clamp to widget bounds
            lx = max(0, min(lx, self.width() - text_w))

            if lx < prev_right + 4:   # skip if overlapping
                continue

            painter.drawText(lx, baseline, label)
            prev_right = lx + text_w

        painter.end()


# ── public widget ─────────────────────────────────────────────────────────────

class CommitSlider(QWidget):
    """Commit timeline: slider + date ruler + detail label."""

    commit_changed = pyqtSignal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._commits: list[CommitInfo] = []
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._slider = _TickSlider(Qt.Orientation.Horizontal)
        self._slider.setTickPosition(QSlider.TickPosition.NoTicks)
        self._slider.setMinimum(0)
        self._slider.setMaximum(0)
        self._slider.setMinimumHeight(36)
        self._slider.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._slider.valueChanged.connect(self._on_value_changed)
        layout.addWidget(self._slider)

        self._ruler = _DateRuler()
        layout.addWidget(self._ruler)

        self._info = QLabel()
        self._info.setStyleSheet("color: #cccccc; font-size: 14px;")
        self._info.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        layout.addWidget(self._info)

    def set_commits(self, commits: list[CommitInfo]) -> None:
        self._commits = commits

        self._slider.blockSignals(True)
        self._slider.setMinimum(0)
        self._slider.setMaximum(max(len(commits) - 1, 0))
        last = max(len(commits) - 1, 0)
        self._slider.setValue(last)
        self._slider.blockSignals(False)

        # Date ruler: show only the date part ("YYYY-MM-DD") to keep labels compact
        self._ruler.set_dates([c.date[:10] for c in commits])

        self._update_label(last)
        self.commit_changed.emit(last)

    def current_index(self) -> int:
        return self._slider.value()

    def _on_value_changed(self, value: int) -> None:
        self._update_label(value)
        self.commit_changed.emit(value)

    def _update_label(self, index: int) -> None:
        if index < len(self._commits):
            c = self._commits[index]
            self._info.setText(
                f"[{c.short_hash}]  {c.date}  —  {c.author}:  {c.message}"
            )
        else:
            self._info.setText("")
