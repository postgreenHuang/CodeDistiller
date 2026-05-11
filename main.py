import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from PySide6.QtWidgets import QApplication
from src.gui.app import MainWindow
from src.config import load_settings


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Code-Distiller")

    settings = load_settings()
    from src.gui.theme import build_stylesheet
    app.setStyleSheet(build_stylesheet(settings.theme))

    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
