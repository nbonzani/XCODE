import os
import re
import requests

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton,
    QTableWidget, QTableWidgetItem, QProgressBar,
    QLabel, QHeaderView, QMessageBox
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QColor, QBrush


def _sanitize_filename(name: str) -> str:
    """Retire les caracteres invalides pour un nom de fichier."""
    name = re.sub(r'[<>:"/\\|?*]', '_', name)
    name = name.strip('. ')
    return name or "video"


def _extension_from_url(url: str) -> str:
    """Extrait l'extension du fichier depuis l'URL."""
    path = url.split('?')[0].split('#')[0]
    _, ext = os.path.splitext(path)
    if ext and len(ext) <= 6:
        return ext
    return ".ts"


class DownloadWorker(QThread):
    """Telecharge les fichiers un par un dans un thread separe."""
    progress = pyqtSignal(int, int, int)       # index, bytes_recus, bytes_total
    file_done = pyqtSignal(int, str)            # index, filepath
    file_error = pyqtSignal(int, str)           # index, message erreur
    all_done = pyqtSignal()

    def __init__(self, entries: list, dest_dir: str):
        super().__init__()
        self.entries = entries
        self.dest_dir = dest_dir
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        session = requests.Session()
        session.headers.update({"User-Agent": "M3UManager/1.0"})

        for i, entry in enumerate(self.entries):
            if self._cancelled:
                break

            url = entry.get("url", "")
            name = entry.get("name", "Video")
            if not url:
                self.file_error.emit(i, "URL vide")
                continue

            filename = _sanitize_filename(name) + _extension_from_url(url)
            filepath = os.path.join(self.dest_dir, filename)

            # Eviter d'ecraser un fichier existant
            base, ext = os.path.splitext(filepath)
            counter = 1
            while os.path.exists(filepath):
                filepath = f"{base} ({counter}){ext}"
                counter += 1

            try:
                resp = session.get(url, stream=True, timeout=(15, 600))
                resp.raise_for_status()

                total = int(resp.headers.get("content-length", 0))
                received = 0

                with open(filepath, "wb") as f:
                    for chunk in resp.iter_content(chunk_size=256 * 1024):
                        if self._cancelled:
                            break
                        f.write(chunk)
                        received += len(chunk)
                        self.progress.emit(i, received, total)

                if self._cancelled:
                    # Supprimer le fichier partiel
                    try:
                        os.remove(filepath)
                    except OSError:
                        pass
                    break

                self.file_done.emit(i, filepath)

            except Exception as e:
                self.file_error.emit(i, str(e))
                # Supprimer le fichier partiel en cas d'erreur
                try:
                    if os.path.exists(filepath):
                        os.remove(filepath)
                except OSError:
                    pass

        self.all_done.emit()


class DownloadDialog(QDialog):
    """Fenetre de telechargement avec progression pour les fichiers selectionnes."""

    def __init__(self, entries: list, dest_dir: str, parent=None):
        super().__init__(parent)
        self.entries = entries
        self.dest_dir = dest_dir
        self._worker = None

        self.setWindowTitle(f"Telechargement — {len(entries)} fichier(s)")
        self.resize(700, 450)
        self.setModal(True)

        layout = QVBoxLayout(self)

        # Label info
        self.lbl_info = QLabel(
            f"Telechargement de {len(entries)} fichier(s) vers :\n{dest_dir}"
        )
        layout.addWidget(self.lbl_info)

        # Tableau de progression
        self.table = QTableWidget(len(entries), 3)
        self.table.setHorizontalHeaderLabels(["Nom", "Progression", "Statut"])
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self.table.verticalHeader().setVisible(False)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(1, 150)
        self.table.setColumnWidth(2, 100)

        for i, entry in enumerate(entries):
            self.table.setItem(i, 0, QTableWidgetItem(entry.get("name", "")))
            self.table.setItem(i, 1, QTableWidgetItem(""))
            self.table.setItem(i, 2, QTableWidgetItem("En attente"))

        layout.addWidget(self.table)

        # Barre de progression globale
        self.progress_global = QProgressBar()
        self.progress_global.setRange(0, len(entries))
        self.progress_global.setValue(0)
        self.progress_global.setFormat("%v / %m fichier(s)")
        layout.addWidget(self.progress_global)

        # Boutons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self.btn_cancel = QPushButton("Annuler")
        self.btn_cancel.setFixedSize(100, 32)
        self.btn_cancel.clicked.connect(self._cancel)
        btn_layout.addWidget(self.btn_cancel)

        self.btn_close = QPushButton("Fermer")
        self.btn_close.setFixedSize(100, 32)
        self.btn_close.clicked.connect(self.accept)
        self.btn_close.setEnabled(False)
        btn_layout.addWidget(self.btn_close)

        layout.addLayout(btn_layout)

        # Lancer le telechargement
        self._start()

    def _start(self):
        self._worker = DownloadWorker(self.entries, self.dest_dir)
        self._worker.progress.connect(self._on_progress)
        self._worker.file_done.connect(self._on_file_done)
        self._worker.file_error.connect(self._on_file_error)
        self._worker.all_done.connect(self._on_all_done)
        self._worker.start()

    def _on_progress(self, index: int, received: int, total: int):
        if total > 0:
            pct = int(received * 100 / total)
            size_mb = f"{received / 1048576:.1f} / {total / 1048576:.1f} Mo"
            self.table.setItem(index, 1, QTableWidgetItem(f"{pct}% — {size_mb}"))
        else:
            size_mb = f"{received / 1048576:.1f} Mo"
            self.table.setItem(index, 1, QTableWidgetItem(size_mb))
        self.table.setItem(index, 2, QTableWidgetItem("En cours..."))

    def _on_file_done(self, index: int, filepath: str):
        self.table.setItem(index, 1, QTableWidgetItem("100%"))
        item = QTableWidgetItem("Termine")
        item.setForeground(QBrush(QColor("#2E7D32")))
        self.table.setItem(index, 2, item)
        self.progress_global.setValue(self.progress_global.value() + 1)

    def _on_file_error(self, index: int, message: str):
        self.table.setItem(index, 1, QTableWidgetItem(""))
        item = QTableWidgetItem("Erreur")
        item.setForeground(QBrush(QColor("#C62828")))
        item.setToolTip(message)
        self.table.setItem(index, 2, item)
        self.progress_global.setValue(self.progress_global.value() + 1)

    def _on_all_done(self):
        self.btn_cancel.setEnabled(False)
        self.btn_close.setEnabled(True)
        self.lbl_info.setText("Telechargement termine.")

    def _cancel(self):
        if self._worker and self._worker.isRunning():
            self._worker.cancel()
            self.lbl_info.setText("Annulation en cours...")
            self.btn_cancel.setEnabled(False)

    def closeEvent(self, event):
        if self._worker and self._worker.isRunning():
            self._worker.cancel()
            self._worker.wait(3000)
        super().closeEvent(event)
