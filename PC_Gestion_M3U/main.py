import sys
import traceback

from PyQt6.QtWidgets import QApplication, QDialog, QMessageBox
from PyQt6.QtCore import Qt

from core.config_manager import load_config
from core.xtream_client import XtreamClient
from ui.login_dialog import LoginDialog
from ui.main_window import MainWindow


def try_auto_connect():
    """Tente une connexion automatique avec la config sauvegardée.
    Retourne un XtreamClient authentifié ou None."""
    config = load_config()
    base_url = config.get("base_url", "").strip()
    username = config.get("username", "").strip()
    password = config.get("password", "").strip()

    if not (base_url and username and password):
        return None

    try:
        client = XtreamClient(base_url, username, password)
        client.authenticate()
        return client
    except Exception:
        return None


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    try:
        # Tentative de connexion automatique
        client = try_auto_connect()

        if client is None:
            login = LoginDialog()
            if login.exec() != QDialog.DialogCode.Accepted:
                sys.exit(0)
            # Mode hors ligne : client reste None, MainWindow gère l'absence de serveur
            client = login.get_client()

        window = MainWindow(client)
        window.show()

        sys.exit(app.exec())

    except Exception:
        # Afficher l'erreur dans une boîte de dialogue au lieu de crasher
        error = traceback.format_exc()
        QMessageBox.critical(None, "Erreur fatale", error)
        sys.exit(1)


if __name__ == "__main__":
    main()
