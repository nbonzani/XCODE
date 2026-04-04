from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QMessageBox
)
from PyQt6.QtCore import QThread, pyqtSignal
from core.xtream_client import XtreamClient
from core.config_manager import load_config, save_config


class AuthWorker(QThread):
    result = pyqtSignal(bool, str, object)

    def __init__(self, client):
        super().__init__()
        self.client = client

    def run(self):
        try:
            user_info = self.client.authenticate()
            if user_info:
                self.result.emit(True, "Connexion reussie", user_info)
            else:
                self.result.emit(False, "Identifiants incorrects", None)
        except Exception as e:
            self.result.emit(False, str(e), None)


class ConnectionDialog(QDialog):
    """
    Boite de dialogue pour modifier les parametres de connexion Xtream.
    - Tester : teste la connexion et active "Appliquer et recharger"
    - OK : sauvegarde les parametres sans synchroniser (ou supprime si vides)
    - Appliquer et recharger : sauvegarde + relance le chargement
    """
    connection_changed = pyqtSignal(object)   # Emet le nouveau XtreamClient

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Parametres de connexion")
        self.setMinimumWidth(420)
        self._client = None
        self._worker = None

        layout = QVBoxLayout(self)

        # Chargement de la config existante
        config = load_config()

        # Champs de saisie
        layout.addWidget(QLabel("URL du serveur :"))
        self.edit_url = QLineEdit(config.get("base_url", ""))
        self.edit_url.setPlaceholderText("http://monserveur.com:8080")
        layout.addWidget(self.edit_url)

        layout.addWidget(QLabel("Nom d'utilisateur :"))
        self.edit_user = QLineEdit(config.get("username", ""))
        layout.addWidget(self.edit_user)

        layout.addWidget(QLabel("Mot de passe :"))
        self.edit_pass = QLineEdit(config.get("password", ""))
        self.edit_pass.setEchoMode(QLineEdit.EchoMode.Normal)
        layout.addWidget(self.edit_pass)

        # Statut
        self.lbl_status = QLabel("")
        layout.addWidget(self.lbl_status)

        # Boutons
        hbox = QHBoxLayout()
        self.btn_test = QPushButton("Tester la connexion")
        self.btn_ok = QPushButton("OK")
        self.btn_apply = QPushButton("Appliquer et recharger")
        self.btn_cancel = QPushButton("Annuler")
        self.btn_apply.setEnabled(False)
        hbox.addWidget(self.btn_test)
        hbox.addStretch()
        hbox.addWidget(self.btn_ok)
        hbox.addWidget(self.btn_apply)
        hbox.addWidget(self.btn_cancel)
        layout.addLayout(hbox)

        self.btn_test.clicked.connect(self._test_connection)
        self.btn_ok.clicked.connect(self._save_and_close)
        self.btn_apply.clicked.connect(self._apply)
        self.btn_cancel.clicked.connect(self.reject)

    def _test_connection(self):
        self.btn_test.setEnabled(False)
        self.lbl_status.setStyleSheet("color: orange;")
        self.lbl_status.setText("Connexion en cours...")
        client = XtreamClient(
            self.edit_url.text().strip(),
            self.edit_user.text().strip(),
            self.edit_pass.text().strip()
        )
        self._worker = AuthWorker(client)
        self._worker.result.connect(self._on_auth_result)
        self._worker.client = client
        self._worker.start()

    def _on_auth_result(self, success, message, user_info):
        self.btn_test.setEnabled(True)
        if success:
            self.lbl_status.setStyleSheet("color: green;")
            self.lbl_status.setText(f"OK {message}")
            self._client = self._worker.client
            self.btn_apply.setEnabled(True)
            save_config({
                "base_url": self.edit_url.text().strip(),
                "username": self.edit_user.text().strip(),
                "password": self.edit_pass.text().strip(),
            })
        else:
            self.lbl_status.setStyleSheet("color: red;")
            self.lbl_status.setText(f"Echec : {message}")
            self.btn_apply.setEnabled(False)

    def _save_and_close(self):
        """Sauvegarde les parametres sans synchroniser.
        Si tous les champs sont vides, supprime la config (mode hors ligne)."""
        url = self.edit_url.text().strip()
        user = self.edit_user.text().strip()
        pwd = self.edit_pass.text().strip()

        if not url and not user and not pwd:
            # Champs vides → supprimer la config (mode hors ligne)
            save_config({})
            self.lbl_status.setStyleSheet("color: gray;")
            self.lbl_status.setText("Configuration supprimee (mode hors ligne)")
        else:
            save_config({
                "base_url": url,
                "username": user,
                "password": pwd,
            })
            self.lbl_status.setStyleSheet("color: green;")
            self.lbl_status.setText("Parametres sauvegardes")

        self.accept()

    def _apply(self):
        self.connection_changed.emit(self._client)
        self.accept()
