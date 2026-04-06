"""Fuzzy file-search dialog (Ctrl+Shift+F).

Matching rules
--------------
* No slash in query  → subsequence match against the filename, fallback to
                        the full path.
* Slash in query     → each slash-delimited part is matched as a subsequence
                        against consecutive path segments in order.

Example: ``pha/chara/mode.py`` matches ``phasesix/characters/models.py``
because "pha" ⊆ "phasesix", "chara" ⊆ "characters", "mode.py" ⊆ "models.py".
"""
from __future__ import annotations

from PyQt6.QtCore import QEvent, Qt
from PyQt6.QtGui import QFont, QKeySequence
from PyQt6.QtWidgets import (
    QDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
)


# ── fuzzy matching ────────────────────────────────────────────────────────────

def _seq_score(query: str, text: str) -> int:
    """Return a positive score when *query* is a subsequence of *text*, else -1.

    Higher score = tighter match (consecutive runs, prefix matches).
    """
    qi = 0
    score = 0
    prev = -2

    for ti, tc in enumerate(text):
        if qi >= len(query):
            break
        if tc == query[qi]:
            if ti == prev + 1:          # consecutive bonus
                score += 3
            if ti == 0:                 # prefix bonus
                score += 4
            elif text[ti - 1] in "-_./ ":   # word-boundary bonus
                score += 2
            score += 1
            prev = ti
            qi += 1

    return score if qi == len(query) else -1


def _match_score(query: str, filepath: str) -> int:
    """Return a match score ≥ 0, or -1 if the file does not match."""
    if not query:
        return 0

    q = query.lower()
    fp = filepath.lower()

    if "/" not in query:
        # Prefer a hit in the filename; fall back to full path
        filename = fp.rsplit("/", 1)[-1]
        s = _seq_score(q, filename)
        if s >= 0:
            return s + 50           # filename hits rank higher
        return _seq_score(q, fp)   # may be -1

    # Segment-aware matching
    q_parts = [p for p in q.split("/") if p]
    p_parts = [p for p in fp.split("/") if p]

    total = 0
    pi = 0
    for qp in q_parts:
        matched = False
        while pi < len(p_parts):
            s = _seq_score(qp, p_parts[pi])
            pi += 1
            if s >= 0:
                total += s
                matched = True
                break
        if not matched:
            return -1

    return total


def fuzzy_filter(query: str, files: list[str], limit: int = 200) -> list[str]:
    """Return *files* that match *query*, sorted by descending score."""
    scored = [(s, f) for f in files if (s := _match_score(query, f)) >= 0]
    scored.sort(key=lambda t: -t[0])
    return [f for _, f in scored[:limit]]


# ── dialog ────────────────────────────────────────────────────────────────────

class FileSearchDialog(QDialog):
    """Command-palette style fuzzy file opener."""

    def __init__(self, files: list[str], parent=None) -> None:
        super().__init__(parent, Qt.WindowType.Dialog)
        self._all_files = files
        self._setup_ui()
        self._refresh("")

        # Position near top-centre of the parent window
        if parent:
            pg = parent.geometry()
            dw, dh = 920, 560
            self.setGeometry(
                pg.x() + (pg.width() - dw) // 2,
                pg.y() + 80,
                dw, dh,
            )

    def _setup_ui(self) -> None:
        self.setWindowTitle("Open File")
        self.setModal(True)
        self.setStyleSheet("""
            QDialog   { background: #1e1e1e; }
            QLineEdit {
                background: #2d2d2d; color: #f8f8f2;
                border: 1px solid #555; border-radius: 3px;
                padding: 6px 8px; font-size: 15px;
            }
            QListWidget {
                background: #252525; color: #d0d0d0;
                border: 1px solid #444; border-radius: 3px;
                font-family: monospace; font-size: 13px;
                outline: none;
            }
            QListWidget::item            { padding: 4px 8px; }
            QListWidget::item:selected   { background: #094771; color: #ffffff; }
            QListWidget::item:hover      { background: #2a2a2a; }
            QLabel { color: #777; font-size: 11px; padding: 2px 4px; }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(6)

        self._search = QLineEdit()
        self._search.setPlaceholderText("Search files…  (e.g.  src/mod.py  or  pha/chara/mode.py)")
        self._search.textChanged.connect(self._refresh)
        self._search.installEventFilter(self)
        layout.addWidget(self._search)

        self._list = QListWidget()
        self._list.itemActivated.connect(self._accept_current)
        layout.addWidget(self._list)

        self._hint = QLabel()
        layout.addWidget(self._hint)

    # ------------------------------------------------------------------
    # Filtering
    # ------------------------------------------------------------------

    def _refresh(self, query: str) -> None:
        self._list.clear()
        results = (
            self._all_files[:200] if not query.strip()
            else fuzzy_filter(query.strip(), self._all_files)
        )
        for path in results:
            self._list.addItem(QListWidgetItem(path))
        if self._list.count():
            self._list.setCurrentRow(0)
        total = len(self._all_files)
        shown = self._list.count()
        self._hint.setText(f"{shown} of {total} files")

    # ------------------------------------------------------------------
    # Keyboard routing: keep focus in the search field while navigating
    # ------------------------------------------------------------------

    def eventFilter(self, obj, event) -> bool:
        if obj is self._search and event.type() == QEvent.Type.KeyPress:
            key = event.key()
            n   = self._list.count()
            row = self._list.currentRow()

            if key == Qt.Key.Key_Down:
                self._list.setCurrentRow(min(row + 1, n - 1))
                return True
            if key == Qt.Key.Key_Up:
                self._list.setCurrentRow(max(row - 1, 0))
                return True
            if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                self._accept_current()
                return True
            if key == Qt.Key.Key_Escape:
                self.reject()
                return True

        return super().eventFilter(obj, event)

    # ------------------------------------------------------------------

    def _accept_current(self, _item=None) -> None:
        item = self._list.currentItem()
        if item:
            self._selected = item.text()
            self.accept()

    def selected_file(self) -> str | None:
        return getattr(self, "_selected", None)
