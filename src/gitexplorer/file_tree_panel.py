"""Left panel: branch selector + git file tree."""
from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (
    QComboBox,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from gitexplorer.git_backend import GitBackend


class FileTreePanel(QWidget):
    """Emits *file_opened(filepath)* when the user double-clicks a file."""

    file_opened = pyqtSignal(str)

    def __init__(self, backend: GitBackend, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._backend = backend
        self._setup_ui()
        self._populate_branches()

    def _setup_ui(self) -> None:
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
        files = self._backend.get_file_tree(branch)

        # Build nested structure
        root_items: dict[str, QTreeWidgetItem] = {}

        for filepath in files:
            parts = filepath.split("/")
            parent: QTreeWidgetItem | QTreeWidget = self._tree
            path_so_far = ""

            for i, part in enumerate(parts):
                path_so_far = "/".join(parts[: i + 1])
                is_file = i == len(parts) - 1

                if path_so_far not in root_items:
                    item = QTreeWidgetItem(parent, [part])
                    if is_file:
                        item.setData(0, Qt.ItemDataRole.UserRole, filepath)
                        item.setForeground(0, item.foreground(0))  # default color
                    else:
                        # directory — make it bold
                        font = item.font(0)
                        font.setBold(True)
                        item.setFont(0, font)
                    root_items[path_so_far] = item
                else:
                    item = root_items[path_so_far]

                parent = item

        self._tree.expandAll()

    def _on_item_double_clicked(self, item: QTreeWidgetItem, _col: int) -> None:
        filepath = item.data(0, Qt.ItemDataRole.UserRole)
        if filepath:  # None for directory items
            self.file_opened.emit(filepath)

    def current_branch(self) -> str:
        return self._branch_combo.currentText()
