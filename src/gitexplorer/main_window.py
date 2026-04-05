"""Application main window."""
from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QLabel,
    QMainWindow,
    QSplitter,
    QStatusBar,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from gitexplorer.diff_view import FileTab
from gitexplorer.file_tree_panel import FileTreePanel
from gitexplorer.git_backend import GitBackend


class MainWindow(QMainWindow):
    def __init__(self, repo_path: Path) -> None:
        super().__init__()
        self._backend = GitBackend(repo_path)
        self.setWindowTitle(f"GitExplorer — {repo_path}")
        self.resize(1280, 800)

        if not self._backend.valid:
            self._show_no_repo(repo_path)
        else:
            self._setup_ui()

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

    def _open_file(self, filepath: str) -> None:
        # Reuse existing tab if the file is already open
        for i in range(self._tabs.count()):
            if self._tabs.tabToolTip(i) == filepath:
                self._tabs.setCurrentIndex(i)
                return

        branch = self._file_tree.current_branch()
        tab = FileTab(filepath, self._backend)
        tab.load(branch)

        label = filepath.split("/")[-1]
        idx = self._tabs.addTab(tab, label)
        self._tabs.setTabToolTip(idx, filepath)
        self._tabs.setCurrentIndex(idx)

    def _close_tab(self, index: int) -> None:
        self._tabs.removeTab(index)
