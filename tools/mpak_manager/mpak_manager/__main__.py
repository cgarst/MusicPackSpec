"""Entry point for MPAK Manager."""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

from . import APP_NAME
from .main_window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    initial = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    win = MainWindow(initial_path=initial)
    win.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
