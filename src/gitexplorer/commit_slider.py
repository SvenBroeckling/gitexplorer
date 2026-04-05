"""Horizontal commit timeline slider widget."""
from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QPen
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from gitexplorer.git_backend import CommitInfo


class _TickSlider(QSlider):
    """QSlider that paints prominent diamond-shaped commit marks."""

    TICK_H = 8  # tick height in pixels

    def paintEvent(self, event):  # noqa: N802
        super().paintEvent(event)
        if self.maximum() == self.minimum():
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()
        usable = w - 20  # Qt slider groove margin (approx)
        span = self.maximum() - self.minimum()

        pen = QPen(QColor("#aaaaaa"), 1)
        painter.setPen(pen)
        painter.setBrush(QColor("#888888"))

        for i in range(self.minimum(), self.maximum() + 1):
            frac = i / span if span else 0
            x = int(10 + frac * usable)
            cy = h - self.TICK_H - 2
            size = 3
            # diamond
            pts_x = [x, x + size, x, x - size]
            pts_y = [cy, cy + size, cy + size * 2, cy + size]
            from PyQt6.QtCore import QPoint
            from PyQt6.QtGui import QPolygon
            poly = QPolygon([QPoint(px, py) for px, py in zip(pts_x, pts_y)])
            painter.drawPolygon(poly)

        painter.end()


class CommitSlider(QWidget):
    """Displays a timeline of commits; emits *commit_changed(index)* on navigation."""

    commit_changed = pyqtSignal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._commits: list[CommitInfo] = []
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        self._slider = _TickSlider(Qt.Orientation.Horizontal)
        self._slider.setTickPosition(QSlider.TickPosition.NoTicks)  # we paint our own
        self._slider.setMinimum(0)
        self._slider.setMaximum(0)
        self._slider.setMinimumHeight(36)
        self._slider.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._slider.valueChanged.connect(self._on_value_changed)
        layout.addWidget(self._slider)

        self._info = QLabel()
        self._info.setStyleSheet("color: #aaaaaa; font-size: 11px;")
        self._info.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        layout.addWidget(self._info)

    def set_commits(self, commits: list[CommitInfo]) -> None:
        self._commits = commits
        self._slider.blockSignals(True)
        self._slider.setMinimum(0)
        self._slider.setMaximum(max(len(commits) - 1, 0))
        self._slider.setValue(0)
        self._slider.blockSignals(False)
        self._update_label(0)
        self.commit_changed.emit(0)

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
