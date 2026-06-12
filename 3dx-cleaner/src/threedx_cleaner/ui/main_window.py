"""Fenetre principale (jalon 1).

Selecteur de profil + acces a la gestion des profils (F7). Le test de
connexion construit un ``Settings`` depuis le profil selectionne et son mot de
passe (lu du Credential Manager), authentifie via la couche endpoints du moteur
et affiche ``who_am_i``. Le test tourne dans un ``QThread`` worker pour ne pas
figer l'UI (fondation du futur executeur batch, jalon 3).
"""

from __future__ import annotations

from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from threedx_cleaner import __version__
from threedx_cleaner.core.connection import who_am_i
from threedx_cleaner.credentials import profile_store, secret_store
from threedx_cleaner.credentials.settings_builder import build_settings
from threedx_cleaner.models.profile import Profile
from threedx_cleaner.ui.profile_dialog import ProfileDialog
from threedx_cleaner.ui.search_panel import SearchPanel


class _ConnectionWorker(QThread):
    """Execute le test de connexion d'un profil hors thread UI."""

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


class MainWindow(QMainWindow):
    """Fenetre principale de 3dx-cleaner (jalon 1)."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(f"3dx-cleaner v{__version__}")
        self.resize(720, 420)

        self._worker: _ConnectionWorker | None = None

        central = QWidget(self)
        root = QVBoxLayout(central)

        intro = QLabel(
            "Purge controlee de donnees 3DEXPERIENCE (usage pedagogique).\n"
            "Selectionnez un profil puis testez la connexion."
        )
        intro.setWordWrap(True)
        root.addWidget(intro)

        # --- Selecteur de profil ---
        selector = QHBoxLayout()
        selector.addWidget(QLabel("Profil :"))
        self._profile_combo = QComboBox()
        self._profile_combo.setMinimumWidth(260)
        selector.addWidget(self._profile_combo)
        self._manage_btn = QPushButton("Gerer les profils...")
        self._manage_btn.clicked.connect(self._on_manage_profiles)
        selector.addWidget(self._manage_btn)
        selector.addStretch(1)
        root.addLayout(selector)

        # --- Actions ---
        actions = QHBoxLayout()
        self._test_btn = QPushButton("Tester la connexion")
        self._test_btn.clicked.connect(self._on_test_connection)
        self._explore_btn = QPushButton("Explorer les objets...")
        self._explore_btn.clicked.connect(self._on_explore)
        actions.addWidget(self._test_btn)
        actions.addWidget(self._explore_btn)
        actions.addStretch(1)
        root.addLayout(actions)

        self._explorer: QMainWindow | None = None

        self._log = QPlainTextEdit()
        self._log.setReadOnly(True)
        self._log.setPlaceholderText("Resultat du test de connexion...")
        root.addWidget(self._log, stretch=1)

        self.setCentralWidget(central)
        self._reload_profiles()

    # --- Profils ---

    def _reload_profiles(self, *, select: str | None = None) -> None:
        current = select or self._profile_combo.currentText()
        self._profile_combo.blockSignals(True)
        self._profile_combo.clear()
        try:
            names = [p.name for p in profile_store.load()]
        except Exception as exc:  # noqa: BLE001
            names = []
            self._append(f"Lecture des profils impossible : {exc}")
        self._profile_combo.addItems(names)
        if current in names:
            self._profile_combo.setCurrentIndex(names.index(current))
        self._profile_combo.blockSignals(False)

        has_profiles = bool(names)
        self._test_btn.setEnabled(has_profiles)
        self._explore_btn.setEnabled(has_profiles)
        if not has_profiles:
            self._log.setPlaceholderText(
                "Aucun profil. Cliquez « Gerer les profils... » pour en creer un."
            )

    def _on_manage_profiles(self) -> None:
        dialog = ProfileDialog(self)
        dialog.exec()
        self._reload_profiles()

    # --- Exploration (F3) ---

    def _on_explore(self) -> None:
        name = self._profile_combo.currentText()
        if not name:
            self._append("Aucun profil selectionne.")
            return
        profile = profile_store.get(name)
        if profile is None:
            self._append(f"Profil « {name} » introuvable.")
            return
        password = secret_store.get_password(name)
        if not password:
            self._append(
                f"Aucun mot de passe enregistre pour « {name} ». "
                "Ouvrez « Gerer les profils... » pour le saisir."
            )
            return
        try:
            settings = build_settings(profile, password)
        except Exception as exc:  # noqa: BLE001
            self._append(f"Configuration invalide : {type(exc).__name__}: {exc}")
            return

        window = QMainWindow(self)
        window.setWindowTitle(f"Explorer — {name}")
        window.resize(960, 600)
        window.setCentralWidget(SearchPanel(settings, window))
        window.show()
        self._explorer = window  # conserve une reference (evite le GC)

    # --- Test de connexion ---

    def _on_test_connection(self) -> None:
        if self._worker is not None and self._worker.isRunning():
            return
        name = self._profile_combo.currentText()
        if not name:
            self._append("Aucun profil selectionne.")
            return
        profile = profile_store.get(name)
        if profile is None:
            self._append(f"Profil « {name} » introuvable.")
            return
        password = secret_store.get_password(name)
        if not password:
            self._append(
                f"Aucun mot de passe enregistre pour « {name} ». "
                "Ouvrez « Gerer les profils... » pour le saisir."
            )
            return

        self._test_btn.setEnabled(False)
        self._append(f"Connexion au profil « {name} » en cours...")

        self._worker = _ConnectionWorker(profile, password, self)
        self._worker.succeeded.connect(self._on_success)
        self._worker.failed.connect(self._on_failure)
        self._worker.finished.connect(lambda: self._test_btn.setEnabled(True))
        self._worker.start()

    def _on_success(self, message: str) -> None:
        self._append(f"OK — {message}")

    def _on_failure(self, message: str) -> None:
        self._append(f"ECHEC — {message}")

    def _append(self, line: str) -> None:
        self._log.appendPlainText(line)
