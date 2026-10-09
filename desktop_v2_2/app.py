import sys

from PySide6.QtWidgets import QApplication

from downloader_app.ui import MainWindow


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Shield Stream Video Downloader")
    app.setStyle("Fusion")
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
