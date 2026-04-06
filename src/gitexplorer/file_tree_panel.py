"""Left panel: branch selector + git file tree."""
from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QBrush, QColor
from PyQt6.QtWidgets import (
    QAbstractScrollArea,
    QComboBox,
    QLabel,
    QSizePolicy,
    QTextBrowser,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from gitexplorer.git_backend import CommitDetails, GitBackend


def _sort_dirs_first(parent: QTreeWidget | QTreeWidgetItem) -> None:
    """Recursively sort tree children: directories before files, each group alphabetical."""
    is_root = isinstance(parent, QTreeWidget)
    n = parent.topLevelItemCount() if is_root else parent.childCount()

    children = []
    for _ in range(n):
        children.append(
            parent.takeTopLevelItem(0) if is_root else parent.takeChild(0)
        )

    children.sort(key=lambda c: (0 if c.childCount() > 0 else 1, c.text(0).lower()))

    for child in children:
        _sort_dirs_first(child)
        if is_root:
            parent.addTopLevelItem(child)
        else:
            parent.addChild(child)


class FileTreePanel(QWidget):
    """Emits *file_opened(filepath)* when the user double-clicks a file."""

    file_opened = pyqtSignal(str)
    _FILTER_ALL = "All files"
    _FILTER_COMMIT = "Only in Commit"

    def __init__(self, backend: GitBackend, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._backend = backend
        self._setup_ui()
        self._populate_branches()

    def _setup_ui(self) -> None:
        # Initialise early so workspace restore can call these safely before
        # the first _build_tree (which reassigns them).
        self._file_items: dict[str, QTreeWidgetItem] = {}
        self._dir_items:  dict[str, QTreeWidgetItem] = {}
        self._branch_files: list[str] = []
        self._commit_files: list[str] = []
        self._all_files_expanded_dirs: list[str] = []

        self.setSizePolicy(
            QSizePolicy.Policy.Preferred,
            QSizePolicy.Policy.Expanding,
        )
        self.setMinimumWidth(180)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        self._branch_combo = QComboBox()
        self._branch_combo.currentTextChanged.connect(self._on_branch_changed)
        layout.addWidget(self._branch_combo)

        self._filter_combo = QComboBox()
        self._filter_combo.addItems([self._FILTER_ALL, self._FILTER_COMMIT])
        self._filter_combo.currentTextChanged.connect(self._on_filter_changed)
        layout.addWidget(self._filter_combo)

        self._tree = QTreeWidget()
        self._tree.setHeaderHidden(True)
        self._tree.setAnimated(True)
        self._tree.setUniformRowHeights(True)
        self._tree.setSizeAdjustPolicy(
            QAbstractScrollArea.SizeAdjustPolicy.AdjustIgnored
        )
        self._tree.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        self._tree.itemDoubleClicked.connect(self._on_item_double_clicked)
        self._tree.itemExpanded.connect(self._on_tree_expanded_changed)
        self._tree.itemCollapsed.connect(self._on_tree_expanded_changed)
        font = self._tree.font()
        font.setPointSize(font.pointSize() + 3)
        self._tree.setFont(font)
        layout.addWidget(self._tree, stretch=1)

        info_label = QLabel("Commit")
        info_label.setStyleSheet("color: #aaaaaa; padding: 4px 2px 0 2px;")
        layout.addWidget(info_label)

        self._commit_info = QTextBrowser()
        self._commit_info.setOpenExternalLinks(False)
        self._commit_info.setReadOnly(True)
        self._commit_info.setMinimumHeight(140)
        self._commit_info.setMaximumHeight(220)
        self._commit_info.setStyleSheet("""
            QTextBrowser {
                background: #202020;
                color: #d8d8d8;
                border: 1px solid #3f3f3f;
                border-radius: 4px;
                padding: 6px;
            }
        """)
        self._commit_info.document().setDocumentMargin(6)
        layout.addWidget(self._commit_info)
        self.set_commit_info(None)

    def _populate_branches(self) -> None:
        branches = self._backend.get_branches()
        self._branch_combo.blockSignals(True)
        self._branch_combo.clear()
        self._branch_combo.addItems(branches)
        self._branch_combo.blockSignals(False)
        if branches:
            self._build_tree(branches[0])

    def _on_branch_changed(self, branch: str) -> None:
        if branch:
            self._build_tree(branch)

    def _on_filter_changed(self, _label: str) -> None:
        if self._filter_combo.currentText() == self._FILTER_COMMIT:
            self._all_files_expanded_dirs = self._current_tree_expanded_dirs()
        self._rebuild_tree(preserve_expanded=True)

    def _build_tree(self, branch: str) -> None:
        self._branch_files = self._backend.get_file_tree(branch)
        self._rebuild_tree(preserve_expanded=False)

    def _rebuild_tree(self, preserve_expanded: bool) -> None:
        expanded_dirs = self._expanded_dirs_for_rebuild(preserve_expanded)
        self._tree.clear()
        self._file_items: dict[str, QTreeWidgetItem] = {}   # filepath → item
        self._dir_items: dict[str, QTreeWidgetItem] = {}    # dirpath  → item

        all_path_items: dict[str, QTreeWidgetItem] = {}
        files = self._visible_files()

        for filepath in files:
            parts = filepath.split("/")
            parent: QTreeWidgetItem | QTreeWidget = self._tree
            path_so_far = ""

            for i, part in enumerate(parts):
                path_so_far = "/".join(parts[: i + 1])
                is_file = i == len(parts) - 1

                if path_so_far not in all_path_items:
                    item = QTreeWidgetItem(parent, [part])
                    if is_file:
                        item.setData(0, Qt.ItemDataRole.UserRole, filepath)
                        self._file_items[filepath] = item
                    else:
                        font = item.font(0)
                        font.setBold(True)
                        item.setFont(0, font)
                        self._dir_items[path_so_far] = item
                    all_path_items[path_so_far] = item
                else:
                    item = all_path_items[path_so_far]

                parent = item

        _sort_dirs_first(self._tree)
        if self._filter_combo.currentText() == self._FILTER_COMMIT:
            self._expand_all_dirs()
        elif preserve_expanded:
            self.restore_expanded_dirs(expanded_dirs)
        else:
            self._tree.collapseAll()

    def _expanded_dirs_for_rebuild(self, preserve_expanded: bool) -> list[str]:
        if not preserve_expanded:
            return []
        if self._filter_combo.currentText() == self._FILTER_COMMIT:
            return self.get_expanded_dirs()
        return self._all_files_expanded_dirs or self._current_tree_expanded_dirs()

    def _expand_all_dirs(self) -> None:
        for item in self._dir_items.values():
            item.setExpanded(True)

    def _on_tree_expanded_changed(self, _item: QTreeWidgetItem) -> None:
        if self._filter_combo.currentText() == self._FILTER_ALL:
            self._all_files_expanded_dirs = self._current_tree_expanded_dirs()

    def _current_tree_expanded_dirs(self) -> list[str]:
        return [
            path for path, item in self._dir_items.items()
            if item.isExpanded()
        ]

    def _visible_files(self) -> list[str]:
        if self._filter_combo.currentText() == self._FILTER_COMMIT:
            branch_files = set(self._branch_files)
            return sorted(fp for fp in self._commit_files if fp in branch_files)
        return self._branch_files

    def set_commit_files(self, filepaths: list[str]) -> None:
        self._commit_files = sorted(set(filepaths))
        if self._filter_combo.currentText() == self._FILTER_COMMIT:
            self._rebuild_tree(preserve_expanded=True)

    def highlight_files(self, filepaths: list[str]) -> None:
        """Highlight *filepaths* and their ancestor dirs; clear everything else."""
        file_color = QBrush(QColor("#4a3800"))
        dir_color  = QBrush(QColor("#2e2400"))
        empty      = QBrush()

        # Clear all existing highlights
        for item in self._file_items.values():
            item.setBackground(0, empty)
        for item in self._dir_items.values():
            item.setBackground(0, empty)

        changed = set(filepaths)
        if not changed:
            return

        # Collect ancestor directory paths
        changed_dirs: set[str] = set()
        for fp in changed:
            parts = fp.split("/")
            for depth in range(1, len(parts)):
                changed_dirs.add("/".join(parts[:depth]))

        for fp in changed:
            item = self._file_items.get(fp)
            if item:
                item.setBackground(0, file_color)

        for dp in changed_dirs:
            item = self._dir_items.get(dp)
            if item:
                item.setBackground(0, dir_color)

    def _on_item_double_clicked(self, item: QTreeWidgetItem, _col: int) -> None:
        filepath = item.data(0, Qt.ItemDataRole.UserRole)
        if filepath:  # None for directory items
            self.file_opened.emit(filepath)

    def current_branch(self) -> str:
        return self._branch_combo.currentText()

    def set_branch(self, branch: str) -> None:
        """Switch to *branch* if it exists in the combo box."""
        if branch and self._branch_combo.findText(branch) >= 0:
            self._branch_combo.setCurrentText(branch)
            # currentTextChanged fires → _on_branch_changed → _build_tree

    def get_expanded_dirs(self) -> list[str]:
        """Return paths of all currently expanded directory nodes."""
        if self._filter_combo.currentText() == self._FILTER_COMMIT:
            return list(self._all_files_expanded_dirs)
        return self._current_tree_expanded_dirs()

    def restore_expanded_dirs(self, dirs: list[str]) -> None:
        """Expand exactly the directories listed in *dirs*; collapse the rest."""
        self._all_files_expanded_dirs = list(dirs)
        expanded = set(dirs)
        for path, item in self._dir_items.items():
            item.setExpanded(path in expanded)

    def set_commit_info(self, details: CommitDetails | None) -> None:
        if details is None:
            self._commit_info.setHtml(
                "<div style='color:#8a8a8a;'>No commit selected</div>"
            )
            return

        message = details.message.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        lines = message.splitlines() or [""]
        subject = lines[0]
        body = "<br>".join(lines[1:]) if len(lines) > 1 else ""
        body_html = (
            f"<div style='margin-top:8px; color:#bcbcbc;'>{body}</div>"
            if body else ""
        )
        self._commit_info.setHtml(
            "<html><body style='font-family:sans-serif; font-size:12px;'>"
            f"<div style='color:#f0f0f0; font-weight:600;'>{subject}</div>"
            f"<div style='margin-top:8px;'><b>Commit:</b> <code>{details.short_hash}</code></div>"
            f"<div><b>Author:</b> {details.author}</div>"
            f"<div><b>Date:</b> {details.date}</div>"
            f"<div><b>Changed files:</b> {details.changed_files_count}</div>"
            f"{body_html}"
            "</body></html>"
        )
