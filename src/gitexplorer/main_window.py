"""Application main window."""
from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction, QKeySequence
from PyQt6.QtWidgets import (
    QApplication,
    QInputDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QSplitter,
    QStatusBar,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from gitexplorer import __version__
from gitexplorer.diff_view import FileTab
from gitexplorer.file_search import FileSearchDialog
from gitexplorer.file_tree_panel import FileTreePanel
from gitexplorer.git_backend import GitBackend
from gitexplorer.workspace import load_workspace, save_workspace

_DEFAULT_FONT_SIZE = 13
_MIN_FONT_SIZE = 6
_MAX_FONT_SIZE = 32


class MainWindow(QMainWindow):
    def __init__(self, repo_path: Path) -> None:
        super().__init__()
        self._backend = GitBackend(repo_path)
        self.setWindowTitle(f"GitExplorer — {repo_path}")
        self.resize(1280, 800)
        self._font_size = _DEFAULT_FONT_SIZE

        self._setup_menus()

        if not self._backend.valid:
            self._show_no_repo(repo_path)
        else:
            self._setup_ui()
            self._restore_workspace()

    # ------------------------------------------------------------------
    # Menus
    # ------------------------------------------------------------------

    def _setup_menus(self) -> None:
        mb = self.menuBar()

        # File ──────────────────────────────────────────────────────────
        file_menu = mb.addMenu("&File")

        quit_action = QAction("&Quit", self)
        quit_action.setShortcut(QKeySequence.StandardKey.Quit)
        quit_action.setStatusTip("Quit GitExplorer")
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)

        # Edit ──────────────────────────────────────────────────────────
        edit_menu = mb.addMenu("&Edit")

        cut_action = QAction("Cu&t", self)
        cut_action.setShortcut(QKeySequence.StandardKey.Cut)
        cut_action.setStatusTip("Cut the current selection")
        cut_action.triggered.connect(lambda: self._trigger_focused_edit_method("cut"))
        edit_menu.addAction(cut_action)

        copy_action = QAction("&Copy", self)
        copy_action.setShortcut(QKeySequence.StandardKey.Copy)
        copy_action.setStatusTip("Copy the current selection")
        copy_action.triggered.connect(lambda: self._trigger_focused_edit_method("copy"))
        edit_menu.addAction(copy_action)

        paste_action = QAction("&Paste", self)
        paste_action.setStatusTip("Paste from the clipboard")
        paste_action.triggered.connect(lambda: self._trigger_focused_edit_method("paste"))
        edit_menu.addAction(paste_action)

        edit_menu.addSeparator()

        find_action = QAction("&Find in File…", self)
        find_action.setShortcut(QKeySequence("Ctrl+Shift+F"))
        find_action.setStatusTip("Search within the active file (Ctrl+Shift+F or /)")
        find_action.triggered.connect(self._open_find_in_current_tab)
        edit_menu.addAction(find_action)

        search_action = QAction("&Open File…", self)
        search_action.setShortcut(QKeySequence("Ctrl+O"))
        search_action.setStatusTip("Fuzzy-search and open a file (Ctrl+O)")
        search_action.triggered.connect(self._open_search_dialog)
        edit_menu.addAction(search_action)

        # View ──────────────────────────────────────────────────────────
        view_menu = mb.addMenu("&View")

        increase_action = QAction("Increase Font Size", self)
        increase_action.setShortcut(QKeySequence("Ctrl+="))
        increase_action.setStatusTip("Increase editor font size")
        increase_action.triggered.connect(lambda: self._adjust_font_size(+1))
        view_menu.addAction(increase_action)

        decrease_action = QAction("Decrease Font Size", self)
        decrease_action.setShortcut(QKeySequence("Ctrl+-"))
        decrease_action.setStatusTip("Decrease editor font size")
        decrease_action.triggered.connect(lambda: self._adjust_font_size(-1))
        view_menu.addAction(decrease_action)

        reset_action = QAction("Reset Font Size", self)
        reset_action.setShortcut(QKeySequence("Ctrl+0"))
        reset_action.setStatusTip(f"Reset editor font size to {_DEFAULT_FONT_SIZE}pt")
        reset_action.triggered.connect(lambda: self._set_font_size(_DEFAULT_FONT_SIZE))
        view_menu.addAction(reset_action)

        view_menu.addSeparator()

        set_size_action = QAction("Set Font Size…", self)
        set_size_action.setStatusTip("Choose an exact editor font size")
        set_size_action.triggered.connect(self._prompt_font_size)
        view_menu.addAction(set_size_action)

        # Help ──────────────────────────────────────────────────────────
        help_menu = mb.addMenu("&Help")

        about_action = QAction("&About", self)
        about_action.setStatusTip("About GitExplorer")
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)

    # ------------------------------------------------------------------
    # Edit helpers
    # ------------------------------------------------------------------

    def _trigger_focused_edit_method(self, method_name: str) -> None:
        widget = QApplication.focusWidget()
        if widget is None:
            return
        method = getattr(widget, method_name, None)
        if callable(method):
            method()

    def _open_find_in_current_tab(self) -> None:
        if not hasattr(self, "_tabs"):
            return
        tab = self._tabs.currentWidget()
        if isinstance(tab, FileTab):
            tab.open_find()

    # ------------------------------------------------------------------
    # Font size helpers
    # ------------------------------------------------------------------

    def _adjust_font_size(self, delta: int) -> None:
        self._set_font_size(self._font_size + delta)

    def _set_font_size(self, pt: int) -> None:
        pt = max(_MIN_FONT_SIZE, min(_MAX_FONT_SIZE, pt))
        if pt == self._font_size:
            return
        self._font_size = pt
        if hasattr(self, "_tabs"):
            for i in range(self._tabs.count()):
                widget = self._tabs.widget(i)
                if isinstance(widget, FileTab):
                    widget.set_font_size(pt)
        self.statusBar().showMessage(f"Font size: {pt}pt", 2000)

    def _prompt_font_size(self) -> None:
        pt, ok = QInputDialog.getInt(
            self,
            "Set Font Size",
            f"Font size (pt)  [{_MIN_FONT_SIZE}–{_MAX_FONT_SIZE}]:",
            value=self._font_size,
            min=_MIN_FONT_SIZE,
            max=_MAX_FONT_SIZE,
        )
        if ok:
            self._set_font_size(pt)

    # ------------------------------------------------------------------
    # About dialog
    # ------------------------------------------------------------------

    def _show_about(self) -> None:
        QMessageBox.about(
            self,
            "About GitExplorer",
            f"<h3>GitExplorer {__version__}</h3>"
            "<p>A PyQt6 Git history browser.<br>"
            "Browse file history with syntax-highlighted inline "
            "and side-by-side diffs.</p>"
            "<p>Built with PyQt6, GitPython, and Pygments.</p>",
        )

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------

    def _show_no_repo(self, path: Path) -> None:
        w = QWidget()
        layout = QVBoxLayout(w)
        label = QLabel(
            f"<h2>No git repository found</h2>"
            f"<p>Path: <code>{path}</code></p>"
            f"<p>Start GitExplorer from inside a git repository, "
            f"or pass a path as argument: <code>gitexplorer /path/to/repo</code></p>"
        )
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(label)
        self.setCentralWidget(w)

    def _setup_ui(self) -> None:
        splitter = QSplitter(Qt.Orientation.Horizontal)

        self._file_tree = FileTreePanel(self._backend)
        self._file_tree.file_opened.connect(self._open_file)
        splitter.addWidget(self._file_tree)

        self._tabs = QTabWidget()
        self._tabs.setTabsClosable(True)
        self._tabs.setDocumentMode(True)
        self._tabs.setMovable(True)
        self._tabs.tabCloseRequested.connect(self._close_tab)
        self._tabs.currentChanged.connect(self._on_tab_switched)
        self._tabs.setStyleSheet(
            "QTabWidget::pane { border: none; }"
            "QTabBar::tab { padding: 4px 12px; }"
        )
        splitter.addWidget(self._tabs)

        splitter.setSizes([260, 1020])
        self.setCentralWidget(splitter)
        self.setStatusBar(QStatusBar())
        self.statusBar().showMessage(
            f"Repository: {self._backend.repo_root}"
        )

    # ------------------------------------------------------------------
    # Tab management
    # ------------------------------------------------------------------

    def _open_file(self, filepath: str, cursor_line_col: tuple[int, int] | None = (0, 0)) -> None:
        # Reuse existing tab if the file is already open
        for i in range(self._tabs.count()):
            if self._tabs.tabToolTip(i) == filepath:
                self._tabs.setCurrentIndex(i)
                tab = self._tabs.widget(i)
                if isinstance(tab, FileTab) and cursor_line_col is not None:
                    tab.restore_cursor(*cursor_line_col)
                    tab.focus_editor()
                return

        branch = self._file_tree.current_branch()
        tab = FileTab(filepath, self._backend)
        tab.set_font_size(self._font_size)
        tab.zoom_requested.connect(self._adjust_font_size)
        tab.commit_selected.connect(self._on_commit_selected)
        tab.load(branch, cursor_line_col)

        label = filepath.split("/")[-1]
        idx = self._tabs.addTab(tab, label)
        self._tabs.setTabToolTip(idx, filepath)
        self._tabs.setCurrentIndex(idx)
        tab.focus_editor()

    def _close_tab(self, index: int) -> None:
        self._tabs.removeTab(index)
        if self._tabs.count() == 0:
            self._file_tree.highlight_files([])

    def _on_commit_selected(self, commit_hash: str) -> None:
        # Only apply highlights from the currently visible tab
        sender = self.sender()
        if self._tabs.currentWidget() is sender:
            files = self._backend.get_changed_files(commit_hash)
            self._file_tree.highlight_files(files)

    # ------------------------------------------------------------------
    # File search
    # ------------------------------------------------------------------

    def _open_search_dialog(self) -> None:
        if not self._backend.valid:
            return
        branch = self._file_tree.current_branch()
        files  = self._backend.get_file_tree(branch)
        dlg = FileSearchDialog(files, parent=self)
        if dlg.exec() and (filepath := dlg.selected_file()):
            self._open_file(filepath)

    # ------------------------------------------------------------------
    # Workspace persistence
    # ------------------------------------------------------------------

    def _restore_workspace(self) -> None:
        ws = load_workspace(self._backend.repo_root)
        if not ws:
            return

        # 1. Branch (rebuilds the tree)
        if branch := ws.get("branch", ""):
            self._file_tree.set_branch(branch)

        # 2. Tree collapse state
        self._file_tree.restore_expanded_dirs(ws.get("tree_expanded", []))

        # 3. Re-open tabs (skip files that no longer exist in the repo)
        active_file = ws.get("active_file", "")
        cursor_positions = self._decode_cursor_positions(ws.get("cursor_positions", []))
        for filepath in ws.get("open_files", []):
            self._open_file(filepath, cursor_positions.get(filepath, (0, 0)))

        # 4. Restore active tab
        if active_file:
            for i in range(self._tabs.count()):
                if self._tabs.tabToolTip(i) == active_file:
                    self._tabs.setCurrentIndex(i)
                    tab = self._tabs.widget(i)
                    if isinstance(tab, FileTab):
                        tab.focus_editor()
                    break

    def _save_workspace(self) -> None:
        if not self._backend.valid or not hasattr(self, "_tabs"):
            return
        open_files = [self._tabs.tabToolTip(i) for i in range(self._tabs.count())]
        active_file = self._tabs.tabToolTip(self._tabs.currentIndex()) if self._tabs.count() else ""
        cursor_positions: list[str] = []
        for i in range(self._tabs.count()):
            tab = self._tabs.widget(i)
            filepath = self._tabs.tabToolTip(i)
            if isinstance(tab, FileTab):
                line_no, col_no = tab.cursor_line_col()
                cursor_positions.append(f"{filepath}\t{line_no}\t{col_no}")
        save_workspace(self._backend.repo_root, {
            "branch":       self._file_tree.current_branch(),
            "open_files":   open_files,
            "active_file":  active_file,
            "tree_expanded": self._file_tree.get_expanded_dirs(),
            "cursor_positions": cursor_positions,
        })

    def closeEvent(self, event) -> None:  # noqa: N802
        self._save_workspace()
        super().closeEvent(event)

    def _on_tab_switched(self, _index: int) -> None:
        tab = self._tabs.currentWidget()
        if isinstance(tab, FileTab) and tab._current_commit_hash:
            files = self._backend.get_changed_files(tab._current_commit_hash)
            self._file_tree.highlight_files(files)
            tab.focus_editor()
        else:
            self._file_tree.highlight_files([])

    def _decode_cursor_positions(self, rows: list[str]) -> dict[str, tuple[int, int]]:
        positions: dict[str, tuple[int, int]] = {}
        for row in rows:
            try:
                filepath, line_no, col_no = row.rsplit("\t", 2)
                positions[filepath] = (int(line_no), int(col_no))
            except (TypeError, ValueError):
                continue
        return positions
