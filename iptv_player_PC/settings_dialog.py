"""
settings_dialog.py - Dialogue de configuration de la connexion Xtream.

Ce dialogue permet à l'utilisateur de saisir les paramètres de son
serveur IPTV (URL, port, identifiants) et de tester la connexion.
"""

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton,
    QFormLayout, QMessageBox, QGroupBox, QCheckBox
)
from PyQt6.QtCore import Qt

from config import load_config, save_config
from xtream_api import XtreamClient


class SettingsDialog(QDialog):
    """Dialogue de paramétrage de la connexion au serveur Xtream."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.config = load_config()
        self.setWindowTitle("Paramètres de connexion")
        self.setMinimumWidth(480)
        self.setModal(True)

        self._setup_ui()
        self._load_values()

    # ------------------------------------------------------------------ #
    #  Construction de l'interface                                          #
    # ------------------------------------------------------------------ #

    def _setup_ui(self):
        """Crée tous les widgets du dialogue."""
        self.setStyleSheet("""
            QDialog { background-color: #1a1a2e; color: white; }
            QGroupBox {
                color: #aaa;
                border: 1px solid #333;
                border-radius: 6px;
                margin-top: 10px;
                padding-top: 10px;
            }
            QGroupBox::title { subcontrol-origin: margin; left: 10px; color: #7eb8f7; }
            QLabel { color: #ccc; }
            QLineEdit {
                background-color: #2d2d44;
                color: white;
                border: 1px solid #444;
                border-radius: 4px;
                padding: 6px 10px;
            }
            QLineEdit:focus { border: 1px solid #2196F3; }
            QCheckBox { color: #ccc; }
            QCheckBox::indicator { width: 16px; height: 16px; }
        """)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)

        # ---- Groupe : Connexion au serveur ----
        conn_group = QGroupBox("Serveur Xtream Codes")
        form = QFormLayout(conn_group)
        form.setSpacing(10)
        form.setContentsMargins(15, 15, 15, 15)

        self.url_edit = QLineEdit()
        self.url_edit.setPlaceholderText("ex : http://monserveur.com")
        form.addRow("URL du serveur :", self.url_edit)

        self.port_edit = QLineEdit()
        self.port_edit.setPlaceholderText("ex : 8080  (laisser vide si déjà dans l'URL)")
        form.addRow("Port :", self.port_edit)

        self.username_edit = QLineEdit()
        self.username_edit.setPlaceholderText("Nom d'utilisateur")
        form.addRow("Utilisateur :", self.username_edit)

        self.password_edit = QLineEdit()
        self.password_edit.setPlaceholderText("Mot de passe")
        self.password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        form.addRow("Mot de passe :", self.password_edit)

        layout.addWidget(conn_group)

        # ---- Groupe : Filtres de contenu ----
        filter_group = QGroupBox("Filtres de contenu")
        filter_layout = QVBoxLayout(filter_group)
        filter_layout.setContentsMargins(15, 15, 15, 15)

        self.french_check = QCheckBox(
            "Afficher uniquement le contenu en français (VF / VOSTFR)"
        )
        filter_layout.addWidget(self.french_check)

        info_label = QLabel(
            "ℹ  La détection se base sur les noms de catégories du serveur\n"
            "   (mots-clés : FR, VF, VOSTFR, FRANÇAIS, FRENCH…)"
        )
        info_label.setStyleSheet("color: #888; font-size: 11px;")
        filter_layout.addWidget(info_label)

        layout.addWidget(filter_group)

        # ---- Bouton de test ----
        test_btn = QPushButton("🔌  Tester la connexion")
        test_btn.setStyleSheet("""
            QPushButton {
                background-color: #2d2d44;
                color: white;
                border: 1px solid #444;
                border-radius: 4px;
                padding: 9px;
                font-size: 13px;
            }
            QPushButton:hover { background-color: #383855; border-color: #2196F3; }
        """)
        test_btn.clicked.connect(self._test_connection)
        layout.addWidget(test_btn)

        # ---- Boutons Enregistrer / Annuler ----
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        cancel_btn = QPushButton("Annuler")
        cancel_btn.setStyleSheet("""
            QPushButton { background-color: #333; color: white; border: none;
                          border-radius: 4px; padding: 9px 22px; }
            QPushButton:hover { background-color: #444; }
        """)
        cancel_btn.clicked.connect(self.reject)

        save_btn = QPushButton("Enregistrer")
        save_btn.setDefault(True)
        save_btn.setStyleSheet("""
            QPushButton { background-color: #1565C0; color: white; border: none;
                          border-radius: 4px; padding: 9px 22px; font-weight: bold; }
            QPushButton:hover { background-color: #1976D2; }
        """)
        save_btn.clicked.connect(self._save)

        btn_layout.addWidget(cancel_btn)
        btn_layout.addWidget(save_btn)
        layout.addLayout(btn_layout)

    # ------------------------------------------------------------------ #
    #  Chargement et sauvegarde                                            #
    # ------------------------------------------------------------------ #

    def _load_values(self):
        """Pré-remplit les champs avec la configuration existante."""
        self.url_edit.setText(self.config.get("server_url", ""))
        self.port_edit.setText(self.config.get("port", "8080"))
        self.username_edit.setText(self.config.get("username", ""))
        self.password_edit.setText(self.config.get("password", ""))
        self.french_check.setChecked(
            self.config.get("language_filter", "french") == "french"
        )

    def _save(self):
        """Valide les champs et sauvegarde la configuration."""
        url = self.url_edit.text().strip()
        username = self.username_edit.text().strip()
        password = self.password_edit.text().strip()

        if not url:
            QMessageBox.warning(self, "Champ manquant", "Veuillez saisir l'URL du serveur.")
            self.url_edit.setFocus()
            return
        if not username:
            QMessageBox.warning(self, "Champ manquant", "Veuillez saisir le nom d'utilisateur.")
            self.username_edit.setFocus()
            return
        if not password:
            QMessageBox.warning(self, "Champ manquant", "Veuillez saisir le mot de passe.")
            self.password_edit.setFocus()
            return

        # S'assurer que l'URL commence bien par http:// ou https://
        if not url.startswith(("http://", "https://")):
            url = "http://" + url

        self.config["server_url"] = url
        self.config["port"] = self.port_edit.text().strip()
        self.config["username"] = username
        self.config["password"] = password
        self.config["language_filter"] = "french" if self.french_check.isChecked() else "all"

        save_config(self.config)
        self.accept()

    # ------------------------------------------------------------------ #
    #  Test de connexion                                                    #
    # ------------------------------------------------------------------ #

    def _test_connection(self):
        """
        Tente une authentification avec les paramètres saisis
        et affiche le résultat à l'utilisateur.
        """
        url = self.url_edit.text().strip()
        port = self.port_edit.text().strip()
        username = self.username_edit.text().strip()
        password = self.password_edit.text().strip()

        if not url or not username or not password:
            QMessageBox.warning(
                self, "Champs manquants",
                "Veuillez remplir l'URL, le nom d'utilisateur et le mot de passe."
            )
            return

        if not url.startswith(("http://", "https://")):
            url = "http://" + url

        try:
            client = XtreamClient(url, port, username, password)
            data = client.authenticate()
            user_info = data.get("user_info", {})

            # Formater la date d'expiration si disponible
            exp_timestamp = user_info.get("exp_date")
            if exp_timestamp:
                from datetime import datetime
                try:
                    exp_date = datetime.fromtimestamp(int(exp_timestamp)).strftime("%d/%m/%Y")
                except Exception:
                    exp_date = str(exp_timestamp)
            else:
                exp_date = "N/A"

            message = (
                f"✅  Connexion réussie !\n\n"
                f"Compte    : {user_info.get('username', 'N/A')}\n"
                f"Statut    : {user_info.get('status', 'N/A')}\n"
                f"Expire le : {exp_date}\n"
                f"Connexions actives : {user_info.get('active_cons', 'N/A')} "
                f"/ {user_info.get('max_connections', 'N/A')}"
            )
            QMessageBox.information(self, "Connexion réussie", message)

        except Exception as e:
            QMessageBox.critical(
                self, "Erreur de connexion",
                f"La connexion a échoué :\n\n{e}"
            )
