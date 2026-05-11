import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QIcon
from src.gui.app import MainWindow
from src.config import load_settings


def resource_path(relative_path: str) -> str:
    """获取资源文件绝对路径（兼容 PyInstaller 打包）"""
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath(os.path.dirname(__file__)), relative_path)


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Code-Distiller")

    icon_path = resource_path("icon.ico")
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))

    settings = load_settings()
    from src.gui.theme import build_stylesheet
    app.setStyleSheet(build_stylesheet(settings.theme))

    win = MainWindow()
    if os.path.exists(icon_path):
        win.setWindowIcon(QIcon(icon_path))
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
