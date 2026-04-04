import datetime

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QFrame,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QFont

from core.xtream_client import XtreamClient
from core.config_manager import load_config, save_config


class AuthWorker(QThread):
    """Thread d'authentification pour ne pas bloquer l'interface."""

    result = pyqtSignal(bool, str, object)

    def __init__(self, client: XtreamClient, parent=None):
        super().__init__(parent)
        self.client = client

    def run(self):
        try:
            data = self.client.authenticate()
            user_info = data.get("user_info", {})
            active_cons = user_info.get("active_cons", "?")
            max_connections = user_info.get("max_connections", "?")
            msg = f"✓ Connexion réussie — {active_cons}/{max_connections} connexions"
            self.result.emit(True, msg, data)
        except (ValueError, ConnectionError) as e:
            self.result.emit(False, str(e), None)
        except Exception as e:
            self.result.emit(False, f"Erreur inattendue : {e}", None)


class LoginDialog(QDialog):
    """Boîte de dialogue de connexion au serveur Xtream Codes."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._client = None
        self._worker = None
        self._setup_ui()
        self._load_saved_config()

    def _setup_ui(self):
        self.setWindowTitle("M3U Manager — Connexion")
        self.setFixedSize(420, 280)

        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        # Titre
        title = QLabel("M3U Manager")
        title_font = QFont()
        title_font.setPointSize(18)
        title_font.setBold(True)
        title.setFont(title_font)
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        # Sous-titre
        subtitle = QLabel("Connexion au serveur Xtream Codes")
        subtitle_font = QFont()
        subtitle_font.setPointSize(10)
        subtitle.setFont(subtitle_font)
        subtitle.setStyleSheet("color: gray;")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(subtitle)

        # Séparateur
        sep1 = QFrame()
        sep1.setFrameShape(QFrame.Shape.HLine)
        sep1.setFrameShadow(QFrame.Shadow.Sunken)
        layout.addWidget(sep1)

        # Champs de saisie
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("http://serveur.com:8080")
        layout.addWidget(self.url_input)

        self.username_input = QLineEdit()
        self.username_input.setPlaceholderText("Nom d'utilisateur")
        layout.addWidget(self.username_input)

        self.password_input = QLineEdit()
        self.password_input.setPlaceholderText("Mot de passe")
        self.password_input.setEchoMode(QLineEdit.EchoMode.Normal)
        layout.addWidget(self.password_input)

        # Bouton test
        self.test_btn = QPushButton("Tester la connexion")
        self.test_btn.setStyleSheet(
            "QPushButton { background-color: #2196F3; color: white; padding: 6px; }"
            "QPushButton:hover { background-color: #1976D2; }"
            "QPushButton:disabled { background-color: #90CAF9; }"
        )
        self.test_btn.clicked.connect(self._on_test_connection)
        layout.addWidget(self.test_btn)

        # Label de statut
        self.status_label = QLabel("")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.status_label)

        # Séparateur
        sep2 = QFrame()
        sep2.setFrameShape(QFrame.Shape.HLine)
        sep2.setFrameShadow(QFrame.Shadow.Sunken)
        layout.addWidget(sep2)

        # Boutons
        btn_layout = QHBoxLayout()

        self.btn_offline = QPushButton("Hors ligne")
        self.btn_offline.setStyleSheet(
            "QPushButton { background-color: #757575; color: white; padding: 6px; }"
            "QPushButton:hover { background-color: #616161; }"
        )
        self.btn_offline.clicked.connect(self._on_offline)
        self.btn_offline.setVisible(False)
        btn_layout.addWidget(self.btn_offline)

        btn_layout.addStretch()

        self.btn_connect = QPushButton("Se connecter")
        self.btn_connect.setEnabled(False)
        self.btn_connect.clicked.connect(self.accept)
        btn_layout.addWidget(self.btn_connect)

        btn_quit = QPushButton("Quitter")
        btn_quit.clicked.connect(self.reject)
        btn_layout.addWidget(btn_quit)

        layout.addLayout(btn_layout)
        self._offline_mode = False

    def _load_saved_config(self):
        config = load_config()
        if config.get("base_url"):
            self.url_input.setText(config["base_url"])
        if config.get("username"):
            self.username_input.setText(config["username"])
        if config.get("password"):
            self.password_input.setText(config["password"])

        # Montrer le bouton "Hors ligne" si aucun paramètre serveur enregistré
        has_params = bool(config.get("base_url") or config.get("username"))
        self.btn_offline.setVisible(not has_params)

    def _on_test_connection(self):
        base_url = self.url_input.text().strip()
        username = self.username_input.text().strip()
        password = self.password_input.text().strip()

        if not base_url or not username or not password:
            self.status_label.setStyleSheet("color: red;")
            self.status_label.setText("Veuillez remplir tous les champs")
            return

        self.test_btn.setEnabled(False)
        self.status_label.setStyleSheet("color: orange;")
        self.status_label.setText("Connexion en cours...")

        self._client = XtreamClient(base_url, username, password)
        self._worker = AuthWorker(self._client, self)
        self._worker.result.connect(self._on_auth_result)
        self._worker.start()

    def _on_auth_result(self, success: bool, message: str, data: object):
        self.test_btn.setEnabled(True)

        if success:
            self.status_label.setStyleSheet("color: green;")
            self.status_label.setText(message)
            self.btn_connect.setEnabled(True)

            # Sauvegarder la configuration
            save_config({
                "base_url": self.url_input.text().strip(),
                "username": self.username_input.text().strip(),
                "password": self.password_input.text().strip(),
                "last_connected": datetime.datetime.now().isoformat(),
            })
        else:
            self.status_label.setStyleSheet("color: red;")
            self.status_label.setText(message)
            self.btn_connect.setEnabled(False)

    def _on_offline(self):
        self._offline_mode = True
        self.accept()

    def is_offline(self) -> bool:
        """Retourne True si l'utilisateur a choisi le mode hors ligne."""
        return self._offline_mode

    def get_client(self) -> XtreamClient:
        """Retourne l'instance XtreamClient authentifiée, ou None en mode hors ligne."""
        return self._client

    def get_credentials(self) -> tuple:
        """Retourne (base_url, username, password)."""
        return (
            self.url_input.text().strip(),
            self.username_input.text().strip(),
            self.password_input.text().strip(),
        )
