"""Fenetre principale (jalon 0).

Fenetre PyQt6 minimale avec un smoke test de connexion : construit un
``Settings`` depuis l'environnement, authentifie via la couche endpoints du
moteur et affiche ``who_am_i``. Le test tourne dans un ``QThread`` worker pour
ne pas figer l'UI (fondation du futur executeur batch, jalon 3).
"""

from __future__ import annotations

from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtWidgets import (
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
from threedx_cleaner.credentials import build_settings_from_env


class _ConnectionWorker(QThread):
    """Execute le test de connexion hors thread UI."""

    succeeded = pyqtSignal(str)
    failed = pyqtSignal(str)

    def run(self) -> None:  # noqa: D102
        try:
            settings = build_settings_from_env()
            result = who_am_i(settings)
            self.succeeded.emit(result.one_line())
        except Exception as exc:  # noqa: BLE001 — on rapporte tout motif a l'UI
            self.failed.emit(f"{type(exc).__name__}: {exc}")


class MainWindow(QMainWindow):
    """Fenetre principale de 3dx-cleaner (squelette jalon 0)."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(f"3dx-cleaner v{__version__}")
        self.resize(720, 420)

        self._worker: _ConnectionWorker | None = None

        central = QWidget(self)
        root = QVBoxLayout(central)

        intro = QLabel(
            "Purge controlee de donnees 3DEXPERIENCE (usage pedagogique).\n"
            "Jalon 0 — smoke test de connexion via variables d'environnement "
            "(THREEDX_BASE_URL / THREEDX_USERNAME / THREEDX_PASSWORD)."
        )
        intro.setWordWrap(True)
        root.addWidget(intro)

        actions = QHBoxLayout()
        self._test_btn = QPushButton("Tester la connexion")
        self._test_btn.clicked.connect(self._on_test_connection)
        actions.addWidget(self._test_btn)
        actions.addStretch(1)
        root.addLayout(actions)

        self._log = QPlainTextEdit()
        self._log.setReadOnly(True)
        self._log.setPlaceholderText("Resultat du test de connexion...")
        root.addWidget(self._log, stretch=1)

        self.setCentralWidget(central)

    # --- Smoke test ---

    def _on_test_connection(self) -> None:
        if self._worker is not None and self._worker.isRunning():
            return
        self._test_btn.setEnabled(False)
        self._append("Connexion en cours...")

        self._worker = _ConnectionWorker(self)
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
