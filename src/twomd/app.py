import sys

from pydantic import ValidationError
from PySide6.QtWidgets import QApplication, QMessageBox

from twomd.config import load_settings, settings_path
from twomd.ui.main_window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("2MD")
    app.setOrganizationName("2MD")
    try:
        settings = load_settings(settings_path())
    except (OSError, ValidationError, ValueError):
        QMessageBox.critical(
            None,
            "Error de configuración",
            "No se puede leer la configuración local. Comprueba el archivo y sus permisos; "
            "no se ha modificado.",
        )
        return 1
    window = MainWindow(settings, settings_path())
    window.show()
    return app.exec()
