"""Dialogue de gestion des profils de connexion (F7, jalon 1).

Permet d'ajouter / editer / supprimer un :class:`Profile` et de **tester la
connexion** (reutilise :func:`who_am_i` + :func:`build_settings` dans un
``QThread`` worker, comme la fenetre principale).

Garde-fous F7 :
- le mot de passe n'est jamais persiste en clair : il va dans le Credential
  Manager via :mod:`secret_store`, et le champ de saisie est masque ;
- a l'edition, un champ mot de passe vide signifie « inchange » (on ne
  reecrit pas le secret existant).
"""

from __future__ import annotations

from PyQt6.QtCore import QThread, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from threedx_cleaner.core.connection import who_am_i
from threedx_cleaner.credentials import profile_store, secret_store
from threedx_cleaner.credentials.settings_builder import build_settings
from threedx_cleaner.models.profile import Profile


class _TestConnectionWorker(QThread):
    """Teste la connexion d'un profil hors thread UI."""

    succeeded = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(self, profile: Profile, password: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._profile = profile
        self._password = password

    def run(self) -> None:  # noqa: D102
        try:
            settings = build_settings(self._profile, self._password)
            result = who_am_i(settings)
            self.succeeded.emit(result.one_line())
        except Exception as exc:  # noqa: BLE001 — on rapporte tout motif a l'UI
            self.failed.emit(f"{type(exc).__name__}: {exc}")


class ProfileDialog(QDialog):
    """Gestion CRUD des profils + test de connexion."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Gestion des profils 3DEXPERIENCE")
        self.resize(720, 460)

        self._worker: _TestConnectionWorker | None = None
        self._current_name: str | None = None  # profil en cours d'edition

        root = QHBoxLayout(self)

        # --- Colonne gauche : liste des profils ---
        left = QVBoxLayout()
        left.addWidget(QLabel("Profils enregistres"))
        self._list = QListWidget()
        self._list.currentTextChanged.connect(self._on_select)
        left.addWidget(self._list, stretch=1)
        self._new_btn = QPushButton("Nouveau")
        self._new_btn.clicked.connect(self._on_new)
        self._delete_btn = QPushButton("Supprimer")
        self._delete_btn.clicked.connect(self._on_delete)
        left.addWidget(self._new_btn)
        left.addWidget(self._delete_btn)
        root.addLayout(left, stretch=1)

        # --- Colonne droite : formulaire ---
        right = QVBoxLayout()
        form = QFormLayout()

        self._name = QLineEdit()
        self._deployment = QComboBox()
        self._deployment.addItem("On-premises", "on_prem")
        self._deployment.addItem("Cloud", "cloud")
        self._deployment.currentIndexChanged.connect(self._sync_mode_fields)
        self._username = QLineEdit()
        self._username.setPlaceholderText("prenom.nom@univ-lorraine.fr")
        self._base_url = QLineEdit()
        self._base_url.setPlaceholderText("https://3dexperience2025.univ-lorraine.fr")
        self._tenant_id = QLineEdit()
        self._platform_id = QLineEdit()
        self._security_context = QLineEdit()
        self._security_context.setPlaceholderText("ctx::<role>.<org>.<collabspace> (optionnel)")
        self._verify_ssl = QCheckBox("Verifier le certificat TLS")
        self._verify_ssl.setChecked(True)
        self._ca_bundle = QLineEdit()
        self._ca_bundle.setPlaceholderText("Bundle CA custom (optionnel)")
        self._password = QLineEdit()
        self._password.setEchoMode(QLineEdit.EchoMode.Password)
        self._password.setPlaceholderText("Mot de passe 3DPassport")

        form.addRow("Nom *", self._name)
        form.addRow("Mode *", self._deployment)
        form.addRow("Identifiant *", self._username)
        form.addRow("URL on-prem", self._base_url)
        form.addRow("Tenant cloud", self._tenant_id)
        form.addRow("Plateforme cloud", self._platform_id)
        form.addRow("Security context", self._security_context)
        form.addRow("", self._verify_ssl)
        form.addRow("CA bundle", self._ca_bundle)
        form.addRow("Mot de passe", self._password)
        right.addLayout(form)

        actions = QHBoxLayout()
        self._save_btn = QPushButton("Enregistrer")
        self._save_btn.clicked.connect(self._on_save)
        self._test_btn = QPushButton("Tester la connexion")
        self._test_btn.clicked.connect(self._on_test)
        actions.addWidget(self._save_btn)
        actions.addWidget(self._test_btn)
        actions.addStretch(1)
        right.addLayout(actions)

        self._status = QLabel("")
        self._status.setWordWrap(True)
        self._status.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        right.addWidget(self._status)
        right.addStretch(1)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        right.addWidget(buttons)

        root.addLayout(right, stretch=2)

        self._reload_list()
        self._on_new()

    # --- Liste ---

    def _reload_list(self, *, select: str | None = None) -> None:
        self._list.blockSignals(True)
        self._list.clear()
        names = [p.name for p in self._load_profiles_safe()]
        self._list.addItems(names)
        self._list.blockSignals(False)
        if select and select in names:
            self._list.setCurrentRow(names.index(select))

    def _load_profiles_safe(self) -> list[Profile]:
        try:
            return profile_store.load()
        except Exception as exc:  # noqa: BLE001 — fichier corrompu : on previent
            self._set_status(f"Lecture des profils impossible : {exc}", error=True)
            return []

    def _on_select(self, name: str) -> None:
        if not name:
            return
        profile = profile_store.get(name)
        if profile is None:
            return
        self._current_name = name
        self._name.setText(profile.name)
        self._deployment.setCurrentIndex(0 if profile.deployment == "on_prem" else 1)
        self._username.setText(profile.username)
        self._base_url.setText(profile.base_url)
        self._tenant_id.setText(profile.tenant_id)
        self._platform_id.setText(profile.platform_id)
        self._security_context.setText(profile.security_context)
        self._verify_ssl.setChecked(profile.verify_ssl)
        self._ca_bundle.setText(profile.ca_bundle)
        self._password.clear()
        has_secret = secret_store.has_password(name)
        self._password.setPlaceholderText(
            "(inchange — laisser vide)" if has_secret else "Mot de passe 3DPassport"
        )
        self._sync_mode_fields()
        self._set_status("")

    def _on_new(self) -> None:
        self._current_name = None
        self._list.blockSignals(True)
        self._list.setCurrentRow(-1)
        self._list.blockSignals(False)
        self._name.clear()
        self._deployment.setCurrentIndex(0)
        self._username.clear()
        self._base_url.clear()
        self._tenant_id.clear()
        self._platform_id.clear()
        self._security_context.clear()
        self._verify_ssl.setChecked(True)
        self._ca_bundle.clear()
        self._password.clear()
        self._password.setPlaceholderText("Mot de passe 3DPassport")
        self._sync_mode_fields()
        self._set_status("")
        self._name.setFocus()

    # --- Formulaire ---

    def _sync_mode_fields(self) -> None:
        """Active uniquement les champs pertinents pour le mode courant."""
        is_on_prem = self._deployment.currentData() == "on_prem"
        self._base_url.setEnabled(is_on_prem)
        self._tenant_id.setEnabled(not is_on_prem)
        self._platform_id.setEnabled(not is_on_prem)

    def _build_profile_from_form(self) -> Profile:
        """Construit (et valide) un Profile depuis les champs. Leve ValueError."""
        is_on_prem = self._deployment.currentData() == "on_prem"
        return Profile(
            name=self._name.text().strip(),
            deployment="on_prem" if is_on_prem else "cloud",
            username=self._username.text().strip(),
            base_url=self._base_url.text().strip() if is_on_prem else "",
            tenant_id="" if is_on_prem else self._tenant_id.text().strip(),
            platform_id="" if is_on_prem else self._platform_id.text().strip(),
            security_context=self._security_context.text().strip(),
            verify_ssl=self._verify_ssl.isChecked(),
            ca_bundle=self._ca_bundle.text().strip(),
        )

    def _on_save(self) -> None:
        try:
            profile = self._build_profile_from_form()
        except Exception as exc:  # noqa: BLE001 — erreur de validation a montrer
            self._set_status(f"Profil invalide : {exc}", error=True)
            return

        # Renommage : retirer l'ancienne entree (et son secret) si le nom change.
        renamed_from = (
            self._current_name
            if self._current_name and self._current_name != profile.name
            else None
        )

        profile_store.upsert(profile)
        password = self._password.text()
        if password:
            secret_store.set_password(profile.name, password)
        elif renamed_from:
            # Conserver le secret en le migrant vers le nouveau nom.
            old = secret_store.get_password(renamed_from)
            if old:
                secret_store.set_password(profile.name, old)

        if renamed_from:
            profile_store.delete(renamed_from)

        self._password.clear()
        self._current_name = profile.name
        self._reload_list(select=profile.name)
        self._set_status(f"Profil « {profile.name} » enregistre.")

    def _on_delete(self) -> None:
        item = self._list.currentItem()
        if item is None:
            return
        name = item.text()
        confirm = QMessageBox.question(
            self,
            "Supprimer le profil",
            f"Supprimer le profil « {name} » et son mot de passe enregistre ?",
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        profile_store.delete(name)
        self._reload_list()
        self._on_new()
        self._set_status(f"Profil « {name} » supprime.")

    # --- Test de connexion ---

    def _on_test(self) -> None:
        if self._worker is not None and self._worker.isRunning():
            return
        try:
            profile = self._build_profile_from_form()
        except Exception as exc:  # noqa: BLE001
            self._set_status(f"Profil invalide : {exc}", error=True)
            return

        password = self._password.text() or (
            secret_store.get_password(profile.name) or ""
        )
        if not password:
            self._set_status(
                "Aucun mot de passe : saisir un mot de passe pour tester.", error=True
            )
            return

        self._test_btn.setEnabled(False)
        self._set_status("Connexion en cours...")
        self._worker = _TestConnectionWorker(profile, password, self)
        self._worker.succeeded.connect(self._on_test_ok)
        self._worker.failed.connect(self._on_test_ko)
        self._worker.finished.connect(lambda: self._test_btn.setEnabled(True))
        self._worker.start()

    def _on_test_ok(self, message: str) -> None:
        self._set_status(f"OK — {message}")

    def _on_test_ko(self, message: str) -> None:
        self._set_status(f"ECHEC — {message}", error=True)

    # --- Utilitaires ---

    def _set_status(self, text: str, *, error: bool = False) -> None:
        self._status.setText(text)
        self._status.setStyleSheet("color: #b00020;" if error else "")
