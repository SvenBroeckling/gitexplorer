"""Inline find bar that sits at the bottom of the editor area (Ctrl+F)."""
from __future__ import annotations

from PyQt6.QtCore import QEvent, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QWidget,
)


class FindBar(QWidget):
    """Compact find bar; hidden by default, shown on Ctrl+F.

    Signals
    -------
    search_changed(query)   – text in the input changed
    next_requested()        – user wants the next match
    prev_requested()        – user wants the previous match
    closed()                – bar was dismissed
    """

    search_changed = pyqtSignal(str)
    next_requested = pyqtSignal()
    prev_requested = pyqtSignal()
    closed         = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._setup_ui()
        self.hide()

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        self.setStyleSheet("""
            FindBar {
                background: #2a2a2a;
                border-top: 1px solid #444;
            }
            QLineEdit {
                background: #1e1e1e; color: #f8f8f2;
                border: 1px solid #555; border-radius: 3px;
                padding: 3px 7px; font-size: 13px;
                min-width: 220px;
            }
            QLineEdit[no_match="true"] {
                border-color: #c04040;
                background: #3a1a1a;
            }
            QPushButton {
                background: #383838; color: #cccccc;
                border: 1px solid #555; border-radius: 3px;
                padding: 3px 10px; font-size: 12px;
            }
            QPushButton:hover   { background: #484848; }
            QPushButton:pressed { background: #585858; }
            QLabel { color: #777777; font-size: 12px; padding: 0 6px; }
        """)
        self.setFixedHeight(36)

        row = QHBoxLayout(self)
        row.setContentsMargins(8, 4, 8, 4)
        row.setSpacing(4)

        self._input = QLineEdit()
        self._input.setPlaceholderText("Find in file…")
        self._input.textChanged.connect(self.search_changed)
        self._input.installEventFilter(self)
        row.addWidget(self._input)

        self._btn_prev = QPushButton("↑")
        self._btn_prev.setToolTip("Previous match  (Shift+Enter)")
        self._btn_prev.setFixedWidth(30)
        self._btn_prev.clicked.connect(self.prev_requested)
        row.addWidget(self._btn_prev)

        self._btn_next = QPushButton("↓")
        self._btn_next.setToolTip("Next match  (Enter)")
        self._btn_next.setFixedWidth(30)
        self._btn_next.clicked.connect(self.next_requested)
        row.addWidget(self._btn_next)

        self._status = QLabel()
        row.addWidget(self._status)

        row.addStretch()

        close_btn = QPushButton("✕")
        close_btn.setToolTip("Close  (Esc)")
        close_btn.setFixedWidth(28)
        close_btn.clicked.connect(self._close)
        row.addWidget(close_btn)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def open(self) -> None:
        """Show the bar, focus the input, select existing text."""
        self.show()
        self._input.setFocus()
        self._input.selectAll()

    def query(self) -> str:
        return self._input.text()

    def set_status(self, current: int, total: int) -> None:
        if total == 0:
            text = "No results" if self._input.text() else ""
            self._status.setText(text)
            self._input.setProperty("no_match", bool(self._input.text()))
        else:
            self._status.setText(f"{current} / {total}")
            self._input.setProperty("no_match", False)
        # Force stylesheet re-evaluation for the dynamic property
        self._input.style().unpolish(self._input)
        self._input.style().polish(self._input)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _close(self) -> None:
        self.hide()
        self.closed.emit()

    def eventFilter(self, obj, event) -> bool:  # noqa: N802
        if obj is self._input and event.type() == QEvent.Type.KeyPress:
            key = event.key()
            mods = event.modifiers()
            if key == Qt.Key.Key_Escape:
                self._close()
                return True
            if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                if mods & Qt.KeyboardModifier.ShiftModifier:
                    self.prev_requested.emit()
                else:
                    self.next_requested.emit()
                return True
        return super().eventFilter(obj, event)
