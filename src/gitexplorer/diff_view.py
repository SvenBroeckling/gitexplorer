"""Per-file tab: commit slider + diff-mode selector + source/diff view."""
from __future__ import annotations

from PyQt6.QtCore import QPoint, Qt, pyqtSignal
from PyQt6.QtGui import (
    QColor,
    QFont,
    QKeyEvent,
    QPainter,
    QPaintEvent,
    QTextCharFormat,
    QTextCursor,
    QTextDocument,
    QTextOption,
    QWheelEvent,
)
from PyQt6.QtWidgets import (
    QApplication,
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

from gitexplorer.find_bar import FindBar

from gitexplorer.commit_slider import CommitSlider
from gitexplorer.git_backend import CommitInfo, DiffLine, GitBackend, pair_diff_lines
from gitexplorer.syntax_highlighter import DiffHighlighter

# ── view indices in QStackedWidget ──────────────────────────────────────────
_CLEAN = 0
_INLINE = 1
_SIDEBYSIDE = 2

_MODES = ["Clean", "Inline Diff", "Side-by-Side"]
_DEFAULT_MODE = "Inline Diff"
_VISUAL_NONE = "none"
_VISUAL_CHAR = "char"
_VISUAL_LINE = "line"
_VISUAL_BLOCK = "block"


# ── scroll helpers ───────────────────────────────────────────────────────────

def _top_visible_line(editor: QTextEdit) -> int:
    """Block number of the first visible line in the viewport."""
    return editor.cursorForPosition(QPoint(0, 0)).blockNumber()


def _scroll_to_line(editor: QTextEdit, line_no: int) -> None:
    """Scroll *editor* so that block *line_no* lands within a safe viewport band."""
    block = editor.document().findBlockByNumber(max(0, line_no))
    if not block.isValid():
        block = editor.document().lastBlock()
    cursor = QTextCursor(block)
    editor.setTextCursor(cursor)
    _reposition_cursor_in_viewport(editor)


def _reposition_cursor_in_viewport(editor: QTextEdit) -> None:
    """Keep the cursor away from the viewport edges using a 1/3-height margin."""
    editor.ensureCursorVisible()

    rect = editor.cursorRect()
    viewport_height = editor.viewport().height()
    if viewport_height <= 0:
        return

    top_margin = viewport_height // 3
    bottom_limit = viewport_height - top_margin - rect.height()
    if top_margin <= rect.top() <= bottom_limit:
        return

    scrollbar = editor.verticalScrollBar()
    scrollbar.setValue(scrollbar.value() + rect.top() - top_margin)


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
    """Read-only code view with minimal vim-style navigation."""

    zoom_requested = pyqtSignal(int)  # +1 or -1
    find_requested = pyqtSignal()
    overlays_changed = pyqtSignal()

    _VISUAL_BLOCK_BG = QColor(210, 140, 0, 110)
    _BLOCK_CURSOR_BG = QColor(248, 248, 242, 130)

    def wheelEvent(self, event: QWheelEvent) -> None:
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            delta = 1 if event.angleDelta().y() > 0 else -1
            self.zoom_requested.emit(delta)
            event.accept()
        else:
            super().wheelEvent(event)

    def __init__(self) -> None:
        super().__init__()
        self._search_selections: list[QTextEdit.ExtraSelection] = []
        self._visual_mode = _VISUAL_NONE
        self._visual_anchor = 0
        self._block_anchor_line = 0
        self._block_anchor_col = 0
        self._syncing_visual_cursor = False
        self.cursorPositionChanged.connect(self._on_cursor_position_changed)

    def paintEvent(self, event: QPaintEvent) -> None:
        super().paintEvent(event)
        if not self.hasFocus():
            return

        rect = self.cursorRect()
        if rect.isNull():
            return

        painter = QPainter(self.viewport())
        painter.fillRect(rect.adjusted(0, 0, self._cursor_block_width() - rect.width(), 0), self._BLOCK_CURSOR_BG)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        key = event.key()
        mods = event.modifiers()

        if mods == Qt.KeyboardModifier.NoModifier:
            if key == Qt.Key.Key_V:
                self._start_visual(_VISUAL_CHAR)
                event.accept()
                return
            if key == Qt.Key.Key_Y and self._visual_mode != _VISUAL_NONE:
                self.copy()
                self._clear_visual_selection()
                event.accept()
                return
            if key == Qt.Key.Key_Escape and self._visual_mode != _VISUAL_NONE:
                self._clear_visual_selection()
                event.accept()
                return
            if key == Qt.Key.Key_H:
                self._move_cursor(QTextCursor.MoveOperation.Left)
                event.accept()
                return
            if key == Qt.Key.Key_J:
                self._move_cursor(QTextCursor.MoveOperation.Down)
                event.accept()
                return
            if key == Qt.Key.Key_K:
                self._move_cursor(QTextCursor.MoveOperation.Up)
                event.accept()
                return
            if key == Qt.Key.Key_L:
                self._move_cursor(QTextCursor.MoveOperation.Right)
                event.accept()
                return
            if key == Qt.Key.Key_Slash:
                self.find_requested.emit()
                event.accept()
                return

        if mods == Qt.KeyboardModifier.ShiftModifier and key == Qt.Key.Key_V:
            self._start_visual(_VISUAL_LINE)
            event.accept()
            return

        if mods == Qt.KeyboardModifier.ControlModifier:
            if key == Qt.Key.Key_V:
                self._start_visual(_VISUAL_BLOCK)
                event.accept()
                return
            if key == Qt.Key.Key_F:
                self.verticalScrollBar().setValue(
                    self.verticalScrollBar().value() + self.verticalScrollBar().pageStep()
                )
                event.accept()
                return
            if key == Qt.Key.Key_B:
                self.verticalScrollBar().setValue(
                    self.verticalScrollBar().value() - self.verticalScrollBar().pageStep()
                )
                event.accept()
                return

        super().keyPressEvent(event)

    def copy(self) -> None:
        text = self._selected_text()
        if text:
            QApplication.clipboard().setText(text)

    def set_search_selections(self, selections: list[QTextEdit.ExtraSelection]) -> None:
        self._search_selections = selections
        self._apply_overlays()

    def clear_search_selections(self) -> None:
        self._search_selections = []
        self._apply_overlays()

    def cursor_line_col(self) -> tuple[int, int]:
        cursor = self.textCursor()
        return cursor.blockNumber(), cursor.positionInBlock()

    def set_cursor_line_col(self, line_no: int, col_no: int) -> None:
        block = self.document().findBlockByNumber(max(0, line_no))
        if not block.isValid():
            block = self.document().lastBlock()
        col_no = max(0, min(col_no, max(0, len(block.text()))))
        cursor = QTextCursor(block)
        cursor.setPosition(block.position() + col_no)
        self.setTextCursor(cursor)
        self._clear_visual_selection()

    def ensure_cursor_band(self) -> None:
        _reposition_cursor_in_viewport(self)

    def _cursor_block_width(self) -> int:
        cursor = self.textCursor()
        block = cursor.block()
        if not block.isValid():
            return max(8, self.fontMetrics().horizontalAdvance(" "))
        text = block.text()
        pos = cursor.positionInBlock()
        ch = text[pos] if pos < len(text) else " "
        return max(8, self.fontMetrics().horizontalAdvance(ch))

    def _move_cursor(self, operation: QTextCursor.MoveOperation) -> None:
        mode = (
            QTextCursor.MoveMode.KeepAnchor
            if self._visual_mode in (_VISUAL_CHAR, _VISUAL_LINE)
            else QTextCursor.MoveMode.MoveAnchor
        )
        self.moveCursor(operation, mode)
        if self._visual_mode == _VISUAL_LINE:
            self._update_line_visual_selection()
        elif self._visual_mode == _VISUAL_BLOCK:
            self._apply_overlays()
        self.ensure_cursor_band()
        self.viewport().update()

    def _selected_text(self) -> str:
        if self._visual_mode == _VISUAL_BLOCK:
            return self._block_selected_text()
        return self.textCursor().selectedText().replace("\u2029", "\n")

    def _start_visual(self, mode: str) -> None:
        cursor = self.textCursor()
        self._visual_mode = mode
        self._visual_anchor = cursor.position()
        self._block_anchor_line, self._block_anchor_col = self.cursor_line_col()
        if mode == _VISUAL_LINE:
            self._update_line_visual_selection()
        else:
            self._apply_overlays()
        self.viewport().update()

    def _clear_visual_selection(self) -> None:
        if self._visual_mode == _VISUAL_NONE and not self.textCursor().hasSelection():
            return
        cursor = self.textCursor()
        cursor.clearSelection()
        self.setTextCursor(cursor)
        self._visual_mode = _VISUAL_NONE
        self._apply_overlays()
        self.viewport().update()

    def _update_line_visual_selection(self) -> None:
        if self._syncing_visual_cursor:
            return
        cursor = self.textCursor()
        start = min(self._visual_anchor, cursor.position())
        end = max(self._visual_anchor, cursor.position())
        start_block = self.document().findBlock(start)
        end_block = self.document().findBlock(end)
        line_cursor = QTextCursor(self.document())
        line_cursor.setPosition(start_block.position())
        end_pos = end_block.position() + len(end_block.text())
        line_cursor.setPosition(end_pos, QTextCursor.MoveMode.KeepAnchor)
        self._syncing_visual_cursor = True
        try:
            self.setTextCursor(line_cursor)
        finally:
            self._syncing_visual_cursor = False

    def _block_selected_text(self) -> str:
        start_line, end_line, start_col, end_col = self._block_bounds()
        parts: list[str] = []
        for line_no in range(start_line, end_line + 1):
            block = self.document().findBlockByNumber(line_no)
            if not block.isValid():
                continue
            text = block.text()
            parts.append(text[start_col:min(end_col, len(text))])
        return "\n".join(parts)

    def _block_bounds(self) -> tuple[int, int, int, int]:
        line_no, col_no = self.cursor_line_col()
        start_line = min(self._block_anchor_line, line_no)
        end_line = max(self._block_anchor_line, line_no)
        start_col = min(self._block_anchor_col, col_no)
        end_col = max(self._block_anchor_col, col_no) + 1
        return start_line, end_line, start_col, end_col

    def _block_selections(self) -> list[QTextEdit.ExtraSelection]:
        if self._visual_mode != _VISUAL_BLOCK:
            return []
        start_line, end_line, start_col, end_col = self._block_bounds()
        selections: list[QTextEdit.ExtraSelection] = []
        for line_no in range(start_line, end_line + 1):
            block = self.document().findBlockByNumber(line_no)
            if not block.isValid():
                continue
            start_pos = block.position() + min(start_col, len(block.text()))
            end_pos = block.position() + min(end_col, len(block.text()))
            if end_pos < start_pos:
                end_pos = start_pos
            cursor = QTextCursor(self.document())
            cursor.setPosition(start_pos)
            cursor.setPosition(end_pos, QTextCursor.MoveMode.KeepAnchor)
            sel = QTextEdit.ExtraSelection()
            sel.cursor = cursor
            sel.format.setBackground(self._VISUAL_BLOCK_BG)
            selections.append(sel)
        return selections

    def _apply_overlays(self) -> None:
        super().setExtraSelections(self._search_selections + self._block_selections())
        self.overlays_changed.emit()

    def _on_cursor_position_changed(self) -> None:
        if self._syncing_visual_cursor:
            self.viewport().update()
            return
        if self._visual_mode == _VISUAL_LINE:
            self._update_line_visual_selection()
        elif self._visual_mode == _VISUAL_BLOCK:
            self._apply_overlays()
        self.viewport().update()


def _make_editor(filename: str = "") -> tuple[_CodeEditor, DiffHighlighter]:
    editor = _CodeEditor()
    editor.setReadOnly(True)
    editor.setUndoRedoEnabled(False)
    editor.setTextInteractionFlags(
        Qt.TextInteractionFlag.TextSelectableByKeyboard
        | Qt.TextInteractionFlag.TextSelectableByMouse
    )
    editor.setCursorWidth(0)
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

    def set_cursor_line_col(self, line_no: int, col_no: int) -> None:
        self._left.set_cursor_line_col(line_no, col_no)
        self._right.set_cursor_line_col(line_no, col_no)

    def ensure_cursor_band(self) -> None:
        self._left.ensure_cursor_band()
        self._right.ensure_cursor_band()


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
        self._match_cursors: list[QTextCursor] = []
        self._match_idx: int = 0
        self._pending_cursor: tuple[int, int] | None = (0, 0)
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

        self._btn_prev_commit = QPushButton("◀ Commit")
        self._btn_prev_commit.setToolTip("Go to previous commit")
        self._btn_prev_commit.clicked.connect(lambda: self._slider.step(-1))
        top.addWidget(self._btn_prev_commit)

        self._btn_next_commit = QPushButton("Commit ▶")
        self._btn_next_commit.setToolTip("Go to next commit")
        self._btn_next_commit.clicked.connect(lambda: self._slider.step(+1))
        top.addWidget(self._btn_next_commit)

        sep1 = QLabel("|")
        sep1.setStyleSheet("color: #555555;")
        top.addWidget(sep1)

        self._btn_prev = QPushButton("↑ Change")
        self._btn_prev.setToolTip("Jump to previous changed hunk in this file")
        self._btn_prev.clicked.connect(self._on_prev_change)
        top.addWidget(self._btn_prev)

        self._btn_next = QPushButton("↓ Change")
        self._btn_next.setToolTip("Jump to next changed hunk in this file")
        self._btn_next.clicked.connect(self._on_next_change)
        top.addWidget(self._btn_next)

        sep2 = QLabel("|")
        sep2.setStyleSheet("color: #555555;")
        top.addWidget(sep2)

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
            editor.find_requested.connect(self.open_find)

        self._stack.insertWidget(_CLEAN, self._clean_edit)
        self._stack.insertWidget(_INLINE, self._inline_edit)
        self._stack.insertWidget(_SIDEBYSIDE, self._sbs)

        root.addWidget(self._stack, stretch=1)

        self._find_bar = FindBar()
        self._find_bar.search_changed.connect(self._on_search_changed)
        self._find_bar.next_requested.connect(self._go_next_match)
        self._find_bar.prev_requested.connect(self._go_prev_match)
        self._find_bar.closed.connect(self._on_find_closed)
        root.addWidget(self._find_bar)

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

    def open_find(self) -> None:
        self._find_bar.open()

    def load(self, branch: str, cursor_line_col: tuple[int, int] | None = (0, 0)) -> None:
        self._jump_on_next_render = cursor_line_col is None
        self._pending_cursor = cursor_line_col
        # oldest (left) → newest (right)
        self._commits = list(reversed(
            self._backend.get_file_commits(branch, self._filepath)
        ))
        self._slider.set_commits(self._commits)

    def cursor_line_col(self) -> tuple[int, int]:
        editor = self._active_editor()
        if not editor:
            return (0, 0)
        return editor.cursor_line_col()

    def focus_editor(self) -> None:
        editor = self._active_editor()
        if editor:
            editor.setFocus()
            editor.ensure_cursor_band()

    def restore_cursor(self, line_no: int, col_no: int) -> None:
        self._pending_cursor = (line_no, col_no)
        editor = self._active_editor()
        if not editor:
            return
        if self._mode == "Side-by-Side":
            self._sbs.set_cursor_line_col(line_no, col_no)
            self._sbs.ensure_cursor_band()
        else:
            editor.set_cursor_line_col(line_no, col_no)
            editor.ensure_cursor_band()

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

    # ------------------------------------------------------------------
    # Find / search
    # ------------------------------------------------------------------

    # Highlight colours (chosen to contrast against green/red diff backgrounds)
    _FMT_MATCH = QTextCharFormat()
    _FMT_MATCH.setBackground(QColor("#4a3800"))      # dim amber — all matches

    _FMT_CURRENT = QTextCharFormat()
    _FMT_CURRENT.setBackground(QColor("#c07000"))    # bright amber — current match
    _FMT_CURRENT.setForeground(QColor("#ffffff"))

    def _on_search_changed(self, query: str) -> None:
        self._apply_search(query)

    def _on_find_closed(self) -> None:
        self._clear_highlights()
        # Return focus to the active editor
        editor = self._active_editor()
        if editor:
            editor.setFocus()

    def _apply_search(self, query: str | None = None) -> None:
        if query is None:
            query = self._find_bar.query()

        editor = self._active_editor()
        if not editor:
            return

        self._clear_highlights(editor)
        self._match_cursors = []
        self._match_idx = 0

        if not query:
            self._find_bar.set_status(0, 0)
            return

        # Collect all matches
        doc = editor.document()
        flags = QTextDocument.FindFlag(0)   # case-insensitive by default
        cursor = doc.find(query, 0, flags)
        while not cursor.isNull():
            self._match_cursors.append(QTextCursor(cursor))
            cursor = doc.find(query, cursor, flags)

        total = len(self._match_cursors)
        if total == 0:
            self._find_bar.set_status(0, 0)
            return

        # Highlight all matches, then override the current one
        sels = []
        for i, mc in enumerate(self._match_cursors):
            sel = QTextEdit.ExtraSelection()
            sel.cursor = mc
            sel.format = self._FMT_CURRENT if i == self._match_idx else self._FMT_MATCH
            sels.append(sel)
        editor.set_search_selections(sels)

        # Scroll to current match
        self._scroll_to_match(editor, self._match_idx)
        self._find_bar.set_status(self._match_idx + 1, total)

    def _go_next_match(self) -> None:
        if not self._match_cursors:
            return
        self._match_idx = (self._match_idx + 1) % len(self._match_cursors)
        self._redraw_highlights()

    def _go_prev_match(self) -> None:
        if not self._match_cursors:
            return
        self._match_idx = (self._match_idx - 1) % len(self._match_cursors)
        self._redraw_highlights()

    def _redraw_highlights(self) -> None:
        editor = self._active_editor()
        if not editor or not self._match_cursors:
            return
        sels = []
        for i, mc in enumerate(self._match_cursors):
            sel = QTextEdit.ExtraSelection()
            sel.cursor = mc
            sel.format = self._FMT_CURRENT if i == self._match_idx else self._FMT_MATCH
            sels.append(sel)
        editor.set_search_selections(sels)
        self._scroll_to_match(editor, self._match_idx)
        self._find_bar.set_status(self._match_idx + 1, len(self._match_cursors))

    def _scroll_to_match(self, editor: QTextEdit, idx: int) -> None:
        cursor = QTextCursor(self._match_cursors[idx])
        editor.setTextCursor(cursor)
        _reposition_cursor_in_viewport(editor)

    def _clear_highlights(self, editor: QTextEdit | None = None) -> None:
        if editor is None:
            editor = self._active_editor()
        if isinstance(editor, _CodeEditor):
            editor.clear_search_selections()

    def _set_mode(self, mode: str) -> None:
        self._mode = mode
        mapping = {"Clean": _CLEAN, "Inline Diff": _INLINE, "Side-by-Side": _SIDEBYSIDE}
        self._stack.setCurrentIndex(mapping.get(mode, _INLINE))

    def _refresh_view(self, commit_hash: str) -> None:
        editor = self._active_editor()
        saved_cursor = (
            None if self._jump_on_next_render else (editor.cursor_line_col() if editor else None)
        )
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

        # Re-apply any active search after content reload
        if self._find_bar.isVisible() and self._find_bar.query():
            self._apply_search()

        # Scroll: restore saved cursor/viewport, or jump to the initial cursor
        editor = self._active_editor()
        if editor:
            target_cursor = self._pending_cursor if self._pending_cursor is not None else saved_cursor
            if target_cursor is not None:
                line_no, col_no = target_cursor
                if self._mode == "Side-by-Side":
                    self._sbs.set_cursor_line_col(line_no, col_no)
                    self._sbs.ensure_cursor_band()
                else:
                    editor.set_cursor_line_col(line_no, col_no)
                    editor.ensure_cursor_band()
                self._pending_cursor = None
                self._jump_on_next_render = False
            elif saved_line is not None:
                _scroll_to_line(editor, saved_line)
                if self._mode == "Side-by-Side":
                    _scroll_to_line(self._sbs._left, saved_line)
