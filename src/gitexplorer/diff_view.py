"""Per-file tab: commit slider + diff-mode selector + source/diff view."""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QTextOption
from PyQt6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QSplitter,
    QStackedWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from gitexplorer.commit_slider import CommitSlider
from gitexplorer.git_backend import CommitInfo, DiffLine, GitBackend, pair_diff_lines
from gitexplorer.syntax_highlighter import DiffHighlighter

# ── view indices in QStackedWidget ──────────────────────────────────────────
_CLEAN = 0
_INLINE = 1
_SIDEBYSIDE = 2

_MODES = ["Clean", "Inline Diff", "Side-by-Side"]
_DEFAULT_MODE = "Inline Diff"


def _make_editor(filename: str = "") -> tuple[QTextEdit, DiffHighlighter]:
    editor = QTextEdit()
    editor.setReadOnly(False)           # selectable + copyable + optionally editable
    editor.setUndoRedoEnabled(False)
    font = QFont("Monospace", 10)
    font.setStyleHint(QFont.StyleHint.TypeWriter)
    editor.setFont(font)
    editor.setWordWrapMode(QTextOption.WrapMode.NoWrap)
    editor.setStyleSheet(
        "QTextEdit { background: #272822; color: #f8f8f2; border: none; }"
    )
    highlighter = DiffHighlighter(editor.document(), filename)
    return editor, highlighter


def _load_editor(
    editor: QTextEdit,
    highlighter: DiffHighlighter,
    lines: list[str],
    types: list[str],
) -> None:
    """Populate *editor* with *lines* and apply diff highlighting."""
    text = "\n".join(lines)
    line_types = {i: t for i, t in enumerate(types)}
    # Block signals while updating to avoid cursor flicker
    editor.blockSignals(True)
    pos = editor.verticalScrollBar().value() if hasattr(editor, "verticalScrollBar") else 0
    highlighter.update_content(text, line_types)
    # update_content calls rehighlight which requires the text to be set first
    editor.blockSignals(False)
    # Set plain text (highlighter operates on the document)
    editor.setPlainText(text)
    # Re-run with the actual text now in the document
    highlighter.update_content(text, line_types)


class _SideBySideWidget(QWidget):
    def __init__(self, filename: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        self._left, self._left_hl = _make_editor(filename)
        self._right, self._right_hl = _make_editor(filename)
        splitter.addWidget(self._left)
        splitter.addWidget(self._right)
        layout.addWidget(splitter)

        # Synchronize vertical scrollbars
        ls = self._left.verticalScrollBar()
        rs = self._right.verticalScrollBar()
        ls.valueChanged.connect(rs.setValue)
        rs.valueChanged.connect(ls.setValue)

    def load(self, diff_lines: list[DiffLine]) -> None:
        lt, rt, lty, rty = pair_diff_lines(diff_lines)
        _load_editor(self._left, self._left_hl, lt, lty)
        _load_editor(self._right, self._right_hl, rt, rty)


class FileTab(QWidget):
    """The main widget placed inside a QTabWidget tab for one file."""

    def __init__(self, filepath: str, backend: GitBackend, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._filepath = filepath
        self._backend = backend
        self._commits: list[CommitInfo] = []
        self._mode = _DEFAULT_MODE
        self._setup_ui()

    def _setup_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(4)

        # ── top bar: slider + mode selector ─────────────────────────────
        top = QHBoxLayout()
        top.setSpacing(8)

        self._slider = CommitSlider()
        self._slider.commit_changed.connect(self._on_commit_changed)
        top.addWidget(self._slider, stretch=1)

        mode_label = QLabel("View:")
        mode_label.setStyleSheet("color: #aaaaaa;")
        top.addWidget(mode_label)

        self._mode_combo = QComboBox()
        self._mode_combo.addItems(_MODES)
        self._mode_combo.setCurrentText(_DEFAULT_MODE)
        self._mode_combo.currentTextChanged.connect(self._on_mode_changed)
        top.addWidget(self._mode_combo)

        root.addLayout(top)

        # ── stacked source views ─────────────────────────────────────────
        self._stack = QStackedWidget()

        self._clean_edit, self._clean_hl = _make_editor(self._filepath)

        self._inline_edit, self._inline_hl = _make_editor(self._filepath)

        self._sbs = _SideBySideWidget(self._filepath)

        self._stack.insertWidget(_CLEAN, self._clean_edit)
        self._stack.insertWidget(_INLINE, self._inline_edit)
        self._stack.insertWidget(_SIDEBYSIDE, self._sbs)

        root.addWidget(self._stack, stretch=1)

        self._set_mode(_DEFAULT_MODE)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load(self, branch: str) -> None:
        self._commits = self._backend.get_file_commits(branch, self._filepath)
        self._slider.set_commits(self._commits)
        # slider emits commit_changed(0) in set_commits, which triggers _on_commit_changed

    # ------------------------------------------------------------------
    # Internal slots
    # ------------------------------------------------------------------

    def _on_commit_changed(self, index: int) -> None:
        if not self._commits or index >= len(self._commits):
            return
        commit_hash = self._commits[index].hash
        self._refresh_view(commit_hash)

    def _on_mode_changed(self, mode: str) -> None:
        self._set_mode(mode)
        # Re-render current commit
        idx = self._slider.current_index()
        if self._commits and idx < len(self._commits):
            self._refresh_view(self._commits[idx].hash)

    def _set_mode(self, mode: str) -> None:
        self._mode = mode
        mapping = {"Clean": _CLEAN, "Inline Diff": _INLINE, "Side-by-Side": _SIDEBYSIDE}
        self._stack.setCurrentIndex(mapping.get(mode, _INLINE))

    def _refresh_view(self, commit_hash: str) -> None:
        if self._mode == "Clean":
            content = self._backend.get_file_content(commit_hash, self._filepath)
            lines = content.splitlines()
            types = ["context"] * len(lines)
            _load_editor(self._clean_edit, self._clean_hl, lines, types)

        elif self._mode == "Inline Diff":
            diff_lines = self._backend.get_diff(commit_hash, self._filepath)
            lines = [dl.content for dl in diff_lines]
            types = [dl.line_type for dl in diff_lines]
            _load_editor(self._inline_edit, self._inline_hl, lines, types)

        elif self._mode == "Side-by-Side":
            diff_lines = self._backend.get_diff(commit_hash, self._filepath)
            self._sbs.load(diff_lines)
