"""
ui/main_window.py
-----------------
Fenêtre principale de VoiceNotes.

Assemble tous les widgets :
  - RecordingBar      (en haut)
  - NoteListWidget    (panneau gauche)
  - NoteEditorWidget  (panneau droit)

Orchestre le flux complet :
  1. Enregistrement → création de la note en base
  2. Transcription Whisper en arrière-plan → mise à jour de l'éditeur
  3. Sauvegarde → rafraîchissement de la liste

La transcription Whisper tourne dans un QThread dédié pour ne pas
geler l'interface pendant l'analyse audio.
"""

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QSplitter, QMenuBar, QStatusBar, QMessageBox, QFrame
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QFont, QAction

import core.database as db
from core.transcriber import transcrire_fichier, precharger_modele

from ui.recording_bar import RecordingBar
from ui.note_list_widget import NoteListWidget
from ui.note_editor_widget import NoteEditorWidget
from ui.theme_dialog import ThemeDialog


# ---------------------------------------------------------------------------
# Thread Whisper
# ---------------------------------------------------------------------------

class ThreadTranscription(QThread):
    """Exécute la transcription Whisper dans un thread séparé."""
    progression = pyqtSignal(str)   # message d'avancement
    terminee    = pyqtSignal(str)   # texte transcrit
    erreur      = pyqtSignal(str)   # message d'erreur

    def __init__(self, chemin_audio: str):
        super().__init__()
        self._chemin = chemin_audio

    def run(self):
        try:
            texte = transcrire_fichier(
                self._chemin,
                callback_progression=lambda msg: self.progression.emit(msg)
            )
            self.terminee.emit(texte)
        except Exception as e:
            self.erreur.emit(str(e))


# ---------------------------------------------------------------------------
# Thread de préchargement Whisper (démarrage silencieux)
# ---------------------------------------------------------------------------

class ThreadPrechargement(QThread):
    def run(self):
        try:
            precharger_modele()
        except Exception:
            pass   # Echec silencieux au démarrage, sera géré à l'usage


# ---------------------------------------------------------------------------
# Fenêtre principale
# ---------------------------------------------------------------------------

class MainWindow(QMainWindow):
    """Fenêtre principale de l'application VoiceNotes."""

    def __init__(self):
        super().__init__()
        self._note_id_en_cours: int | None = None
        self._thread_transcription: ThreadTranscription | None = None

        self.setWindowTitle("VoiceNotes — Notes vocales")
        self.setMinimumSize(900, 600)
        self.resize(1100, 680)

        self._configurer_ui()
        self._configurer_menus()
        self._configurer_statusbar()
        self._precharger_whisper()

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    def _configurer_ui(self):
        widget_central = QWidget()
        self.setCentralWidget(widget_central)
        layout_principal = QVBoxLayout(widget_central)
        layout_principal.setContentsMargins(0, 0, 0, 0)
        layout_principal.setSpacing(0)

        # Barre d'enregistrement (en haut)
        self.barre_enregistrement = RecordingBar()
        self.barre_enregistrement.setStyleSheet("background-color: #f8f8f8; border-bottom: 1px solid #ddd;")
        self.barre_enregistrement.enregistrement_arrete.connect(self._on_enregistrement_arrete)
        self.barre_enregistrement.erreur_enregistrement.connect(self._afficher_erreur)
        layout_principal.addWidget(self.barre_enregistrement)

        # Zone principale : liste | éditeur
        self.splitter = QSplitter(Qt.Orientation.Horizontal)

        self.liste_notes = NoteListWidget()
        self.liste_notes.note_selectionnee.connect(self._on_note_selectionnee)

        self.editeur_note = NoteEditorWidget()
        self.editeur_note.note_modifiee.connect(self._on_note_sauvegardee)

        self.splitter.addWidget(self.liste_notes)
        self.splitter.addWidget(self.editeur_note)
        self.splitter.setSizes([340, 760])
        self.splitter.setHandleWidth(4)
        self.splitter.setStyleSheet("QSplitter::handle { background-color: #e0e0e0; }")

        layout_principal.addWidget(self.splitter, stretch=1)

    def _configurer_menus(self):
        barre_menus = self.menuBar()

        # Menu "Notes"
        menu_notes = barre_menus.addMenu("Notes")

        action_nouvelle = QAction("Nouvelle note vide", self)
        action_nouvelle.setShortcut("Ctrl+N")
        action_nouvelle.triggered.connect(self._creer_note_vide)
        menu_notes.addAction(action_nouvelle)

        menu_notes.addSeparator()

        action_quitter = QAction("Quitter", self)
        action_quitter.setShortcut("Ctrl+Q")
        action_quitter.triggered.connect(self.close)
        menu_notes.addAction(action_quitter)

        # Menu "Thèmes"
        menu_themes = barre_menus.addMenu("Thèmes")
        action_gerer_themes = QAction("Gérer les thèmes…", self)
        action_gerer_themes.triggered.connect(self._ouvrir_gestion_themes)
        menu_themes.addAction(action_gerer_themes)

        # Menu "Aide"
        menu_aide = barre_menus.addMenu("Aide")
        action_a_propos = QAction("À propos de VoiceNotes", self)
        action_a_propos.triggered.connect(self._afficher_a_propos)
        menu_aide.addAction(action_a_propos)

    def _configurer_statusbar(self):
        self.statusBar().setFont(QFont("Segoe UI", 9))
        self.statusBar().showMessage("Prêt.")

    # ------------------------------------------------------------------
    # Préchargement Whisper
    # ------------------------------------------------------------------

    def _precharger_whisper(self):
        """Lance le chargement du modèle Whisper en arrière-plan au démarrage."""
        self._thread_prech = ThreadPrechargement()
        self._thread_prech.finished.connect(
            lambda: self.statusBar().showMessage("Modèle Whisper prêt.", 3000)
        )
        self._thread_prech.start()
        self.statusBar().showMessage("Chargement du modèle Whisper en arrière-plan…")

    # ------------------------------------------------------------------
    # Flux principal : enregistrement → transcription → sauvegarde
    # ------------------------------------------------------------------

    @pyqtSlot(str, float)
    def _on_enregistrement_arrete(self, chemin_audio: str, duree: float):
        """
        Appelé quand l'utilisateur clique sur "Arrêter".
        1. Crée la note en base avec un titre temporaire
        2. Lance la transcription Whisper en arrière-plan
        3. Met à jour l'éditeur en mode "traitement en cours"
        """
        # Création de la note en base (transcription vide pour l'instant)
        titre_temp = f"Note {duree:.0f}s"
        note_id = db.inserer_note(
            titre=titre_temp,
            transcription="",
            chemin_audio=chemin_audio,
            duree_secondes=duree
        )
        self._note_id_en_cours = note_id

        # Mise en attente dans l'éditeur
        self.editeur_note.afficher_transcription_en_cours(note_id, chemin_audio, duree)

        # Lancement de la transcription en arrière-plan
        self._thread_transcription = ThreadTranscription(chemin_audio)
        self._thread_transcription.progression.connect(
            lambda msg: self.statusBar().showMessage(msg)
        )
        self._thread_transcription.terminee.connect(self._on_transcription_terminee)
        self._thread_transcription.erreur.connect(self._on_transcription_erreur)
        self._thread_transcription.start()

        # Rafraîchissement partiel de la liste (note apparaît sans transcription)
        self.liste_notes.rafraichir()
        self.liste_notes.selectionner_note(note_id)

    @pyqtSlot(str)
    def _on_transcription_terminee(self, texte: str):
        """Appelé quand Whisper a fini — met à jour la base et l'éditeur."""
        if self._note_id_en_cours is not None:
            db.mettre_a_jour_note(self._note_id_en_cours, transcription=texte)
            self.editeur_note.afficher_transcription_terminee(texte)
            self.liste_notes.rafraichir()
            self.liste_notes.selectionner_note(self._note_id_en_cours)
            self.statusBar().showMessage("Transcription terminée. Vous pouvez maintenant classer la note.", 5000)
            self.barre_enregistrement.definir_statut(
                "Transcription terminée — cliquez sur « Classer automatiquement »",
                "#007700"
            )

    @pyqtSlot(str)
    def _on_transcription_erreur(self, message: str):
        """Appelé si Whisper échoue."""
        self.editeur_note.afficher_transcription_terminee(
            "[Erreur de transcription — vérifiez que ffmpeg est installé]"
        )
        self.statusBar().showMessage(f"Erreur de transcription : {message}", 8000)
        QMessageBox.warning(self, "Erreur de transcription",
                            f"La transcription a échoué :\n{message}\n\n"
                            "Vérifiez que ffmpeg est installé et dans le PATH.")

    # ------------------------------------------------------------------
    # Sélection et sauvegarde de notes
    # ------------------------------------------------------------------

    @pyqtSlot(int)
    def _on_note_selectionnee(self, note_id: int):
        self.editeur_note.charger_note(note_id)

    @pyqtSlot(int)
    def _on_note_sauvegardee(self, note_id: int):
        self.liste_notes.rafraichir()
        self.liste_notes.selectionner_note(note_id)
        self.statusBar().showMessage("Note sauvegardée.", 3000)

    # ------------------------------------------------------------------
    # Actions des menus
    # ------------------------------------------------------------------

    def _creer_note_vide(self):
        """Crée une note vide manuellement (sans enregistrement)."""
        note_id = db.inserer_note(
            titre="Nouvelle note",
            transcription="",
            chemin_audio="",
            duree_secondes=0
        )
        self.liste_notes.rafraichir()
        self.liste_notes.selectionner_note(note_id)
        self.editeur_note.charger_note(note_id)

    def _ouvrir_gestion_themes(self):
        dialogue = ThemeDialog(self)
        dialogue.exec()
        self.liste_notes.rafraichir()   # Le filtre par thème doit être mis à jour

    def _afficher_a_propos(self):
        QMessageBox.about(
            self,
            "À propos de VoiceNotes",
            "<b>VoiceNotes</b> — Notes vocales avec transcription automatique<br><br>"
            "Transcription locale : <b>Whisper</b> (OpenAI)<br>"
            "Classification : <b>Claude Haiku</b> (Anthropic)<br>"
            "Interface : <b>PyQt6</b><br><br>"
            "Développé pour Windows 10/11"
        )

    def _afficher_erreur(self, message: str):
        QMessageBox.critical(self, "Erreur", message)
