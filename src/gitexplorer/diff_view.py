"""Per-file tab: commit slider + diff-mode selector + source/diff view."""
from __future__ import annotations

from PyQt6.QtCore import QPoint, Qt, pyqtSignal
from PyQt6.QtGui import QFont, QTextCursor, QTextOption, QWheelEvent
from PyQt6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
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


# ── scroll helpers ───────────────────────────────────────────────────────────

def _top_visible_line(editor: QTextEdit) -> int:
    """Block number of the first visible line in the viewport."""
    return editor.cursorForPosition(QPoint(0, 0)).blockNumber()


def _scroll_to_line(editor: QTextEdit, line_no: int) -> None:
    """Scroll *editor* so that block *line_no* is near the top."""
    block = editor.document().findBlockByNumber(max(0, line_no))
    if not block.isValid():
        block = editor.document().lastBlock()
    cursor = QTextCursor(block)
    editor.setTextCursor(cursor)
    editor.ensureCursorVisible()


def _hunk_starts(line_types: list[str]) -> list[int]:
    """Line indices at the start of each changed hunk (added/removed block)."""
    starts: list[int] = []
    for i, t in enumerate(line_types):
        if t in ("added", "removed"):
            if i == 0 or line_types[i - 1] == "context":
                starts.append(i)
    return starts


# ── editor widget ────────────────────────────────────────────────────────────

class _CodeEditor(QTextEdit):
    """QTextEdit that emits *zoom_requested(delta)* on Ctrl+Wheel."""

    zoom_requested = pyqtSignal(int)  # +1 or -1

    def wheelEvent(self, event: QWheelEvent) -> None:
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            delta = 1 if event.angleDelta().y() > 0 else -1
            self.zoom_requested.emit(delta)
            event.accept()
        else:
            super().wheelEvent(event)


def _make_editor(filename: str = "") -> tuple[_CodeEditor, DiffHighlighter]:
    editor = _CodeEditor()
    editor.setReadOnly(False)
    editor.setUndoRedoEnabled(False)
    font = QFont("Monospace", 13)
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
    editor.blockSignals(True)
    highlighter.update_content(text, line_types)
    editor.blockSignals(False)
    editor.setPlainText(text)
    highlighter.update_content(text, line_types)


# ── side-by-side container ───────────────────────────────────────────────────

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

        ls = self._left.verticalScrollBar()
        rs = self._right.verticalScrollBar()
        ls.valueChanged.connect(rs.setValue)
        rs.valueChanged.connect(ls.setValue)

    def load(self, lt: list[str], rt: list[str],
             lty: list[str], rty: list[str]) -> None:
        _load_editor(self._left,  self._left_hl,  lt, lty)
        _load_editor(self._right, self._right_hl, rt, rty)

    def set_font_size(self, pt: int) -> None:
        for editor in (self._left, self._right):
            font = editor.font()
            font.setPointSize(pt)
            editor.setFont(font)


# ── main file tab ────────────────────────────────────────────────────────────

class FileTab(QWidget):
    """The main widget placed inside a QTabWidget tab for one file."""

    zoom_requested = pyqtSignal(int)   # forwarded from any child editor
    commit_selected = pyqtSignal(str)  # emitted with commit hash on every slider move

    def __init__(self, filepath: str, backend: GitBackend,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._filepath = filepath
        self._backend = backend
        self._commits: list[CommitInfo] = []
        self._current_commit_hash: str = ""
        self._current_line_types: list[str] = []
        self._jump_on_next_render: bool = False
        self._mode = _DEFAULT_MODE
        self._setup_ui()

    def _setup_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(4)

        # ── top bar ──────────────────────────────────────────────────────
        top = QHBoxLayout()
        top.setSpacing(6)

        self._slider = CommitSlider()
        self._slider.commit_changed.connect(self._on_commit_changed)
        top.addWidget(self._slider, stretch=1)

        self._btn_prev = QPushButton("◀ Prev")
        self._btn_prev.setToolTip("Jump to previous change (Alt+Up)")
        self._btn_prev.setFixedWidth(80)
        self._btn_prev.clicked.connect(self._on_prev_change)
        top.addWidget(self._btn_prev)

        self._btn_next = QPushButton("Next ▶")
        self._btn_next.setToolTip("Jump to next change (Alt+Down)")
        self._btn_next.setFixedWidth(80)
        self._btn_next.clicked.connect(self._on_next_change)
        top.addWidget(self._btn_next)

        sep = QLabel("|")
        sep.setStyleSheet("color: #555555;")
        top.addWidget(sep)

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

        for editor in (self._clean_edit, self._inline_edit,
                       self._sbs._left, self._sbs._right):
            editor.zoom_requested.connect(self.zoom_requested)

        self._stack.insertWidget(_CLEAN, self._clean_edit)
        self._stack.insertWidget(_INLINE, self._inline_edit)
        self._stack.insertWidget(_SIDEBYSIDE, self._sbs)

        root.addWidget(self._stack, stretch=1)

        self._set_mode(_DEFAULT_MODE)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_font_size(self, pt: int) -> None:
        for editor in (self._clean_edit, self._inline_edit):
            font = editor.font()
            font.setPointSize(pt)
            editor.setFont(font)
        self._sbs.set_font_size(pt)

    def load(self, branch: str) -> None:
        self._jump_on_next_render = True
        # oldest (left) → newest (right)
        self._commits = list(reversed(
            self._backend.get_file_commits(branch, self._filepath)
        ))
        self._slider.set_commits(self._commits)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _active_editor(self) -> _CodeEditor | None:
        if self._mode == "Clean":
            return self._clean_edit
        if self._mode == "Inline Diff":
            return self._inline_edit
        if self._mode == "Side-by-Side":
            return self._sbs._right
        return None

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _on_commit_changed(self, index: int) -> None:
        if not self._commits or index >= len(self._commits):
            return
        commit_hash = self._commits[index].hash
        self._current_commit_hash = commit_hash
        self.commit_selected.emit(commit_hash)
        self._refresh_view(commit_hash)

    def _on_mode_changed(self, mode: str) -> None:
        self._set_mode(mode)
        idx = self._slider.current_index()
        if self._commits and idx < len(self._commits):
            self._jump_on_next_render = True
            self._refresh_view(self._commits[idx].hash)

    def _on_prev_change(self) -> None:
        hunks = _hunk_starts(self._current_line_types)
        if not hunks:
            return
        editor = self._active_editor()
        if not editor:
            return
        current = _top_visible_line(editor)
        # last hunk that starts strictly before the current top line
        target = next((h for h in reversed(hunks) if h < current), hunks[-1])
        _scroll_to_line(editor, target)
        if self._mode == "Side-by-Side":
            _scroll_to_line(self._sbs._left, target)

    def _on_next_change(self) -> None:
        hunks = _hunk_starts(self._current_line_types)
        if not hunks:
            return
        editor = self._active_editor()
        if not editor:
            return
        current = _top_visible_line(editor)
        # first hunk that starts strictly after the current top line
        target = next((h for h in hunks if h > current), hunks[0])
        _scroll_to_line(editor, target)
        if self._mode == "Side-by-Side":
            _scroll_to_line(self._sbs._left, target)

    def _set_mode(self, mode: str) -> None:
        self._mode = mode
        mapping = {"Clean": _CLEAN, "Inline Diff": _INLINE, "Side-by-Side": _SIDEBYSIDE}
        self._stack.setCurrentIndex(mapping.get(mode, _INLINE))

    def _refresh_view(self, commit_hash: str) -> None:
        editor = self._active_editor()
        saved_line = (
            None if self._jump_on_next_render
            else (_top_visible_line(editor) if editor else None)
        )

        if self._mode == "Clean":
            content = self._backend.get_file_content(commit_hash, self._filepath)
            lines = content.splitlines()
            types = ["context"] * len(lines)
            _load_editor(self._clean_edit, self._clean_hl, lines, types)
            self._current_line_types = types

        elif self._mode == "Inline Diff":
            diff_lines = self._backend.get_diff(commit_hash, self._filepath)
            lines = [dl.content for dl in diff_lines]
            types = [dl.line_type for dl in diff_lines]
            _load_editor(self._inline_edit, self._inline_hl, lines, types)
            self._current_line_types = types

        elif self._mode == "Side-by-Side":
            diff_lines = self._backend.get_diff(commit_hash, self._filepath)
            lt, rt, lty, rty = pair_diff_lines(diff_lines)
            self._sbs.load(lt, rt, lty, rty)
            self._current_line_types = rty

        # Scroll: jump to first change on open, otherwise restore position
        editor = self._active_editor()
        if editor:
            if self._jump_on_next_render:
                hunks = _hunk_starts(self._current_line_types)
                if hunks:
                    _scroll_to_line(editor, hunks[0])
                    if self._mode == "Side-by-Side":
                        _scroll_to_line(self._sbs._left, hunks[0])
                self._jump_on_next_render = False
            elif saved_line is not None:
                _scroll_to_line(editor, saved_line)
                if self._mode == "Side-by-Side":
                    _scroll_to_line(self._sbs._left, saved_line)
