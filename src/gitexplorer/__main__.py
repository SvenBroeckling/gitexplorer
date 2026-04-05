import sys
from pathlib import Path

from PyQt6.QtWidgets import QApplication

from gitexplorer.main_window import MainWindow


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("GitExplorer")
    app.setOrganizationName("gitexplorer")

    repo_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.cwd()

    window = MainWindow(repo_path)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
