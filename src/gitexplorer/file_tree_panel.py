"""Left panel: branch selector + git file tree."""
from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QBrush, QColor
from PyQt6.QtWidgets import (
    QComboBox,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from gitexplorer.git_backend import GitBackend


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

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        self._branch_combo = QComboBox()
        self._branch_combo.currentTextChanged.connect(self._on_branch_changed)
        layout.addWidget(self._branch_combo)

        self._tree = QTreeWidget()
        self._tree.setHeaderHidden(True)
        self._tree.setAnimated(True)
        self._tree.setUniformRowHeights(True)
        self._tree.itemDoubleClicked.connect(self._on_item_double_clicked)
        font = self._tree.font()
        font.setPointSize(font.pointSize() + 3)
        self._tree.setFont(font)
        layout.addWidget(self._tree, stretch=1)

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

    def _build_tree(self, branch: str) -> None:
        self._tree.clear()
        self._file_items: dict[str, QTreeWidgetItem] = {}   # filepath → item
        self._dir_items: dict[str, QTreeWidgetItem] = {}    # dirpath  → item

        files = self._backend.get_file_tree(branch)
        all_path_items: dict[str, QTreeWidgetItem] = {}

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
        self._tree.collapseAll()

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
        return [
            path for path, item in self._dir_items.items()
            if item.isExpanded()
        ]

    def restore_expanded_dirs(self, dirs: list[str]) -> None:
        """Expand exactly the directories listed in *dirs*; collapse the rest."""
        expanded = set(dirs)
        for path, item in self._dir_items.items():
            item.setExpanded(path in expanded)
