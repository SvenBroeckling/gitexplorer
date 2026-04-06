"""Project-wide search dialog for symbol-style navigation."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shutil
import subprocess

from PyQt6.QtCore import QEvent, Qt
from PyQt6.QtWidgets import (
    QDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
)


@dataclass
class ProjectSearchResult:
    filepath: str
    line_no: int
    col_no: int
    preview: str

    def display_text(self) -> str:
        return f"{self.filepath}:{self.line_no}:{self.col_no}: {self.preview}"


def search_word_in_repo(repo_root: Path, word: str) -> tuple[list[ProjectSearchResult], str]:
    """Search *repo_root* for whole-word literal matches of *word*."""
    if not word:
        return [], "Enter a word to search"

    if shutil.which("rg"):
        cmd = ["rg", "--column", "--line-number", "--no-heading", "--color", "never", "-w", "-F", word, "."]
        parser = _parse_rg_line
        tool_name = "ripgrep"
    else:
        cmd = ["grep", "-RInw", "-F", word, "."]
        parser = _parse_grep_line
        tool_name = "grep"

    try:
        proc = subprocess.run(
            cmd,
            cwd=repo_root,
            text=True,
            capture_output=True,
            check=False,
        )
    except OSError:
        return [], f"Search tool unavailable for {word!r}"

    results = [
        result
        for line in proc.stdout.splitlines()
        if (result := parser(line)) is not None
    ]
    return results, f"{len(results)} matches for {word!r} via {tool_name}"


def _parse_rg_line(line: str) -> ProjectSearchResult | None:
    parts = line.split(":", 3)
    if len(parts) != 4:
        return None
    filepath, line_no, col_no, preview = parts
    try:
        return ProjectSearchResult(_normalize_result_path(filepath), int(line_no), int(col_no), preview)
    except ValueError:
        return None


def _parse_grep_line(line: str) -> ProjectSearchResult | None:
    parts = line.split(":", 2)
    if len(parts) != 3:
        return None
    filepath, line_no, preview = parts
    try:
        return ProjectSearchResult(_normalize_result_path(filepath), int(line_no), 1, preview)
    except ValueError:
        return None


def _normalize_result_path(filepath: str) -> str:
    if filepath.startswith("./"):
        return filepath[2:]
    return filepath


class ProjectSearchDialog(QDialog):
    """Result-picker for project-wide grep output."""

    def __init__(self, repo_root: Path, word: str, parent=None) -> None:
        super().__init__(parent, Qt.WindowType.Dialog)
        self._results, summary = search_word_in_repo(repo_root, word)
        self._setup_ui(word, summary)
        self._refresh("")

        if parent:
            pg = parent.geometry()
            dw, dh = 1080, 620
            self.setGeometry(
                pg.x() + (pg.width() - dw) // 2,
                pg.y() + 80,
                dw, dh,
            )

    def _setup_ui(self, word: str, summary: str) -> None:
        self.setWindowTitle(f"Search Project: {word}")
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
        self._search.setPlaceholderText("Filter results…")
        self._search.setText(word)
        self._search.selectAll()
        self._search.textChanged.connect(self._refresh)
        self._search.installEventFilter(self)
        layout.addWidget(self._search)

        self._list = QListWidget()
        self._list.itemActivated.connect(self._accept_current)
        layout.addWidget(self._list)

        self._hint = QLabel(summary)
        layout.addWidget(self._hint)

    def _refresh(self, query: str) -> None:
        self._list.clear()
        query = query.strip().lower()
        visible = [
            result for result in self._results
            if not query or query in result.display_text().lower()
        ]
        for result in visible:
            item = QListWidgetItem(result.display_text())
            item.setData(Qt.ItemDataRole.UserRole, result)
            self._list.addItem(item)
        if self._list.count():
            self._list.setCurrentRow(0)
        self._hint.setText(f"{self._list.count()} of {len(self._results)} matches")

    def eventFilter(self, obj, event) -> bool:
        if obj is self._search and event.type() == QEvent.Type.KeyPress:
            key = event.key()
            n = self._list.count()
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

    def _accept_current(self, _item=None) -> None:
        item = self._list.currentItem()
        if item:
            self._selected = item.data(Qt.ItemDataRole.UserRole)
            self.accept()

    def selected_result(self) -> ProjectSearchResult | None:
        return getattr(self, "_selected", None)
