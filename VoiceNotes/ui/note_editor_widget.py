"""
ui/note_editor_widget.py
------------------------
Panneau droit : affichage et édition d'une note sélectionnée.

Fonctionnalités :
  - Affichage du titre (modifiable), de la transcription (éditeur de texte)
  - Affichage des thèmes assignés (modifiables manuellement)
  - Bouton "Classer automatiquement" → appel Claude Haiku en arrière-plan
  - Bouton "Sauvegarder les modifications"
  - Lecture du fichier audio associé (ouverture avec le lecteur Windows par défaut)

Signaux émis :
  - note_modifiee(note_id: int) : la note a été sauvegardée → la liste doit se rafraîchir
"""

import os
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QTextEdit, QPushButton, QFrame, QMessageBox, QProgressBar,
    QDialog, QDialogButtonBox
)
from PyQt6.QtCore import Qt, pyqtSignal, QThread, pyqtSlot
from PyQt6.QtGui import QFont

import core.database as db
from core.classifier import (
    classifier_note_avec_contexte,
    generer_prompt_markdown,
    parser_reponse_claude,
)
from utils.config import ANTHROPIC_API_KEY


# ---------------------------------------------------------------------------
# Dialogue de collage de la réponse Claude (mode sans clé API)
# ---------------------------------------------------------------------------

class DialogueImportReponse(QDialog):
    """
    Fenêtre modale permettant à l'utilisateur de coller la réponse
    copiée depuis claude.ai après avoir soumis le fichier .md exporté.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Importer la réponse de Claude")
        self.setMinimumSize(520, 320)
        self.setModal(True)
        self._configurer_ui()

    def _configurer_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(16, 16, 16, 16)

        lbl = QLabel("Collez ici la réponse de Claude :")
        lbl.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        layout.addWidget(lbl)

        explication = QLabel(
            "Réponse attendue (deux lignes) :\n"
            "  TITRE: Réunion projet Urbanloop\n"
            "  THEMES: Réunion, Travail"
        )
        explication.setFont(QFont("Consolas", 9))
        explication.setStyleSheet(
            "background: #f5f5f5; border: 1px solid #ddd; border-radius: 4px; padding: 8px;"
        )
        layout.addWidget(explication)

        self.zone_texte = QTextEdit()
        self.zone_texte.setFont(QFont("Consolas", 10))
        self.zone_texte.setPlaceholderText("Collez la réponse de Claude ici…")
        self.zone_texte.setStyleSheet("""
            QTextEdit {
                border: 1px solid #aaa;
                border-radius: 4px;
                padding: 8px;
            }
        """)
        layout.addWidget(self.zone_texte, stretch=1)

        boutons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        boutons.button(QDialogButtonBox.StandardButton.Ok).setText("Appliquer")
        boutons.button(QDialogButtonBox.StandardButton.Cancel).setText("Annuler")
        boutons.accepted.connect(self.accept)
        boutons.rejected.connect(self.reject)
        layout.addWidget(boutons)

    def get_reponse(self) -> str:
        return self.zone_texte.toPlainText().strip()


# ---------------------------------------------------------------------------
# Thread de classification (pour ne pas bloquer l'UI)
# ---------------------------------------------------------------------------

class ThreadClassification(QThread):
    """Lance la classification Claude Haiku dans un thread séparé."""
    resultat = pyqtSignal(list, str)   # (themes, titre)
    erreur   = pyqtSignal(str)

    def __init__(self, texte: str, themes_disponibles: list[str]):
        super().__init__()
        self._texte = texte
        self._themes_disponibles = themes_disponibles

    def run(self):
        try:
            themes, titre = classifier_note_avec_contexte(
                self._texte, self._themes_disponibles
            )
            self.resultat.emit(themes, titre)
        except Exception as e:
            self.erreur.emit(str(e))


# ---------------------------------------------------------------------------
# Widget principal
# ---------------------------------------------------------------------------

class NoteEditorWidget(QWidget):
    """Éditeur de note : titre, transcription, thèmes, actions."""

    note_modifiee = pyqtSignal(int)  # note_id

    def __init__(self, parent=None):
        super().__init__(parent)
        self._note_id: int | None = None
        self._chemin_audio: str = ""
        self._thread_classif: ThreadClassification | None = None
        self._configurer_ui()
        self._afficher_vide()

    # ------------------------------------------------------------------
    # Construction de l'interface
    # ------------------------------------------------------------------

    def _configurer_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 12)
        layout.setSpacing(8)

        # --- Titre ---
        lbl_titre_section = QLabel("Titre")
        lbl_titre_section.setFont(QFont("Segoe UI", 9))
        lbl_titre_section.setStyleSheet("color: #666;")
        layout.addWidget(lbl_titre_section)

        self.champ_titre = QLineEdit()
        self.champ_titre.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        self.champ_titre.setPlaceholderText("(titre de la note)")
        self.champ_titre.setStyleSheet("""
            QLineEdit {
                border: 1px solid #ddd;
                border-radius: 4px;
                padding: 6px 8px;
                background: #fafafa;
            }
            QLineEdit:focus { border-color: #1565c0; background: white; }
        """)
        layout.addWidget(self.champ_titre)

        # --- Transcription ---
        lbl_transcription = QLabel("Transcription")
        lbl_transcription.setFont(QFont("Segoe UI", 9))
        lbl_transcription.setStyleSheet("color: #666;")
        layout.addWidget(lbl_transcription)

        self.editeur_texte = QTextEdit()
        self.editeur_texte.setFont(QFont("Segoe UI", 11))
        self.editeur_texte.setPlaceholderText(
            "La transcription de votre note apparaîtra ici…\n\n"
            "Vous pouvez également saisir ou modifier le texte manuellement."
        )
        self.editeur_texte.setStyleSheet("""
            QTextEdit {
                border: 1px solid #ddd;
                border-radius: 4px;
                padding: 8px;
                background: #fafafa;
                line-height: 1.5;
            }
            QTextEdit:focus { border-color: #1565c0; background: white; }
        """)
        layout.addWidget(self.editeur_texte, stretch=1)

        # --- Thèmes ---
        lbl_themes = QLabel("Thèmes (séparés par des virgules)")
        lbl_themes.setFont(QFont("Segoe UI", 9))
        lbl_themes.setStyleSheet("color: #666;")
        layout.addWidget(lbl_themes)

        self.champ_themes = QLineEdit()
        self.champ_themes.setFont(QFont("Segoe UI", 10))
        self.champ_themes.setPlaceholderText("ex: Réunion, Travail, Idée")
        self.champ_themes.setStyleSheet("""
            QLineEdit {
                border: 1px solid #ddd;
                border-radius: 4px;
                padding: 6px 8px;
                background: #fafafa;
            }
            QLineEdit:focus { border-color: #1565c0; background: white; }
        """)
        layout.addWidget(self.champ_themes)

        # --- Barre de progression classification ---
        self.barre_progression = QProgressBar()
        self.barre_progression.setRange(0, 0)   # mode indéterminé
        self.barre_progression.setFixedHeight(4)
        self.barre_progression.setTextVisible(False)
        self.barre_progression.hide()
        layout.addWidget(self.barre_progression)

        self.lbl_classif_statut = QLabel("")
        self.lbl_classif_statut.setFont(QFont("Segoe UI", 9))
        self.lbl_classif_statut.setStyleSheet("color: #666; padding: 0;")
        layout.addWidget(self.lbl_classif_statut)

        # --- Boutons d'action (deux lignes) ---

        # Ligne 1 : classification
        ligne_classif = QHBoxLayout()
        ligne_classif.setSpacing(8)

        self.btn_classer = QPushButton("🤖  Classer via API")
        self.btn_classer.setFont(QFont("Segoe UI", 10))
        self.btn_classer.setEnabled(False)
        self.btn_classer.setToolTip(
            "Utilise l'API Anthropic (clé dans .env) pour classer automatiquement."
            if ANTHROPIC_API_KEY else
            "Clé API absente — utilisez « Exporter pour Claude » à la place."
        )
        self.btn_classer.clicked.connect(self._lancer_classification)
        self.btn_classer.setStyleSheet(self._style_bouton_secondaire())

        self.btn_exporter = QPushButton("📄  Exporter pour Claude")
        self.btn_exporter.setFont(QFont("Segoe UI", 10))
        self.btn_exporter.setEnabled(False)
        self.btn_exporter.setToolTip(
            "Génère un fichier .md à coller dans claude.ai pour obtenir la classification."
        )
        self.btn_exporter.clicked.connect(self._exporter_pour_claude)
        self.btn_exporter.setStyleSheet(self._style_bouton_secondaire())

        self.btn_importer = QPushButton("📥  Importer la réponse")
        self.btn_importer.setFont(QFont("Segoe UI", 10))
        self.btn_importer.setEnabled(False)
        self.btn_importer.setToolTip(
            "Collez la réponse de Claude pour appliquer le titre et les thèmes."
        )
        self.btn_importer.clicked.connect(self._importer_reponse_claude)
        self.btn_importer.setStyleSheet(self._style_bouton_secondaire())

        ligne_classif.addWidget(self.btn_classer)
        ligne_classif.addWidget(self.btn_exporter)
        ligne_classif.addWidget(self.btn_importer)
        ligne_classif.addStretch()
        layout.addLayout(ligne_classif)

        # Ligne 2 : audio + sauvegarder
        ligne_actions = QHBoxLayout()
        ligne_actions.setSpacing(8)

        self.btn_audio = QPushButton("▶  Écouter l'audio")
        self.btn_audio.setFont(QFont("Segoe UI", 10))
        self.btn_audio.setEnabled(False)
        self.btn_audio.clicked.connect(self._ecouter_audio)
        self.btn_audio.setStyleSheet(self._style_bouton_secondaire())

        self.btn_sauvegarder = QPushButton("💾  Sauvegarder")
        self.btn_sauvegarder.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        self.btn_sauvegarder.setEnabled(False)
        self.btn_sauvegarder.clicked.connect(self._sauvegarder)
        self.btn_sauvegarder.setStyleSheet("""
            QPushButton {
                background-color: #1565c0;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 8px 16px;
            }
            QPushButton:hover { background-color: #0d47a1; }
            QPushButton:disabled { background-color: #bbb; }
        """)

        ligne_actions.addWidget(self.btn_audio)
        ligne_actions.addStretch()
        ligne_actions.addWidget(self.btn_sauvegarder)
        layout.addLayout(ligne_actions)

    # ------------------------------------------------------------------
    # Interface publique
    # ------------------------------------------------------------------

    def charger_note(self, note_id: int):
        """Charge et affiche une note dans l'éditeur."""
        note = db.get_note_par_id(note_id)
        if not note:
            self._afficher_vide()
            return

        self._note_id = note_id
        self._chemin_audio = note.get("chemin_audio") or ""

        # Remplissage des champs
        self.champ_titre.setText(note.get("titre") or "")
        self.editeur_texte.setPlainText(note.get("transcription") or "")
        themes = note.get("themes") or ""
        self.champ_themes.setText(themes)

        # Activation des boutons
        a_texte = bool(note.get("transcription"))
        self.btn_sauvegarder.setEnabled(True)
        self.btn_classer.setEnabled(a_texte and bool(ANTHROPIC_API_KEY))
        self.btn_exporter.setEnabled(a_texte)
        self.btn_importer.setEnabled(a_texte)
        self.btn_audio.setEnabled(
            bool(self._chemin_audio) and os.path.isfile(self._chemin_audio)
        )
        self.lbl_classif_statut.setText("")

    def afficher_transcription_en_cours(self, note_id: int, chemin_audio: str, duree: float):
        """
        Appelé juste après un enregistrement, avant que la transcription soit terminée.
        Prépare l'éditeur pour une nouvelle note en cours de traitement.
        """
        self._note_id = note_id
        self._chemin_audio = chemin_audio
        self.champ_titre.setText("")
        self.editeur_texte.setPlainText("Transcription en cours…")
        self.editeur_texte.setEnabled(False)
        self.champ_themes.setText("")
        self.btn_sauvegarder.setEnabled(False)
        self.btn_classer.setEnabled(False)
        self.btn_exporter.setEnabled(False)
        self.btn_importer.setEnabled(False)
        self.btn_audio.setEnabled(False)
        self.barre_progression.show()
        self.lbl_classif_statut.setText("Whisper analyse l'audio…")

    def afficher_transcription_terminee(self, texte: str):
        """Appelé par la fenêtre principale quand Whisper a fini."""
        self.editeur_texte.setPlainText(texte)
        self.editeur_texte.setEnabled(True)
        self.barre_progression.hide()
        self.lbl_classif_statut.setText("Transcription terminée.")
        self.btn_sauvegarder.setEnabled(True)
        self.btn_classer.setEnabled(bool(texte) and bool(ANTHROPIC_API_KEY))
        self.btn_exporter.setEnabled(bool(texte))
        self.btn_importer.setEnabled(bool(texte))
        self.btn_audio.setEnabled(
            bool(self._chemin_audio) and os.path.isfile(self._chemin_audio)
        )

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _sauvegarder(self):
        if self._note_id is None:
            return
        titre = self.champ_titre.text().strip()
        transcription = self.editeur_texte.toPlainText().strip()
        themes_txt = self.champ_themes.text().strip()

        db.mettre_a_jour_note(self._note_id, titre=titre, transcription=transcription)
        themes_liste = [t.strip() for t in themes_txt.split(",") if t.strip()]
        db.assigner_themes_a_note(self._note_id, themes_liste)

        self.lbl_classif_statut.setText("Note sauvegardée.")
        self.lbl_classif_statut.setStyleSheet("color: #007700;")
        self.note_modifiee.emit(self._note_id)

    def _lancer_classification(self):
        """Démarre la classification Claude Haiku en arrière-plan."""
        texte = self.editeur_texte.toPlainText().strip()
        if not texte:
            QMessageBox.warning(self, "Texte vide",
                                "Il n'y a aucun texte à classifier.")
            return
        if not ANTHROPIC_API_KEY:
            QMessageBox.warning(
                self, "Clé API manquante",
                "Ajoutez votre clé Anthropic dans le fichier .env :\n"
                "ANTHROPIC_API_KEY=sk-ant-..."
            )
            return

        themes_disponibles = db.get_noms_themes()
        self.btn_classer.setEnabled(False)
        self.barre_progression.show()
        self.lbl_classif_statut.setText("Classification en cours (Claude Haiku)…")
        self.lbl_classif_statut.setStyleSheet("color: #555;")

        self._thread_classif = ThreadClassification(texte, themes_disponibles)
        self._thread_classif.resultat.connect(self._on_classification_ok)
        self._thread_classif.erreur.connect(self._on_classification_erreur)
        self._thread_classif.start()

    @pyqtSlot(list, str)
    def _on_classification_ok(self, themes: list[str], titre: str):
        self.barre_progression.hide()
        self.btn_classer.setEnabled(True)

        if titre:
            self.champ_titre.setText(titre)
        self.champ_themes.setText(", ".join(themes))
        self.lbl_classif_statut.setText(
            f"Thèmes proposés : {', '.join(themes)}"
        )
        self.lbl_classif_statut.setStyleSheet("color: #1565c0;")

    @pyqtSlot(str)
    def _on_classification_erreur(self, message: str):
        self.barre_progression.hide()
        self.btn_classer.setEnabled(True)
        self.lbl_classif_statut.setText(f"Erreur : {message}")
        self.lbl_classif_statut.setStyleSheet("color: #c62828;")
        QMessageBox.critical(self, "Erreur de classification", message)

    def _exporter_pour_claude(self):
        """
        Génère un fichier .md contenant le prompt à coller dans claude.ai,
        puis l'ouvre dans le Bloc-notes Windows pour que l'utilisateur puisse
        copier son contenu facilement.
        """
        texte = self.editeur_texte.toPlainText().strip()
        if not texte:
            QMessageBox.warning(self, "Texte vide",
                                "Aucun texte à exporter. Transcrivez d'abord la note.")
            return

        themes_disponibles = db.get_noms_themes()
        titre_actuel = self.champ_titre.text().strip()

        try:
            contenu, chemin = generer_prompt_markdown(texte, themes_disponibles, titre_actuel)
        except Exception as e:
            QMessageBox.critical(self, "Erreur d'export", str(e))
            return

        # Ouvre le fichier dans le Bloc-notes pour faciliter le copier-coller
        os.startfile(chemin)

        self.lbl_classif_statut.setText(
            f"Fichier exporté : {os.path.basename(chemin)}"
        )
        self.lbl_classif_statut.setStyleSheet("color: #1565c0;")

        QMessageBox.information(
            self,
            "Fichier exporté",
            f"Le fichier a été ouvert dans le Bloc-notes :\n{chemin}\n\n"
            "Étapes :\n"
            "  1. Sélectionnez tout (Ctrl+A) et copiez (Ctrl+C)\n"
            "  2. Collez dans claude.ai et envoyez\n"
            "  3. Revenez ici et cliquez sur « Importer la réponse »"
        )

    def _importer_reponse_claude(self):
        """
        Ouvre un dialogue pour que l'utilisateur colle la réponse de Claude.
        Parse le titre et les thèmes, puis les applique dans l'éditeur.
        """
        dialogue = DialogueImportReponse(self)
        if dialogue.exec() != QDialog.DialogCode.Accepted:
            return

        reponse = dialogue.get_reponse()
        if not reponse:
            QMessageBox.warning(self, "Réponse vide",
                                "Vous n'avez rien collé dans la zone de texte.")
            return

        try:
            themes, titre = parser_reponse_claude(reponse)
        except Exception as e:
            QMessageBox.critical(self, "Erreur de parsing", str(e))
            return

        if titre:
            self.champ_titre.setText(titre)
        self.champ_themes.setText(", ".join(themes))
        self.lbl_classif_statut.setText(
            f"Thèmes importés : {', '.join(themes)}"
        )
        self.lbl_classif_statut.setStyleSheet("color: #1565c0;")

    def _ecouter_audio(self):
        """Ouvre le fichier audio avec le lecteur Windows par défaut."""
        if self._chemin_audio and os.path.isfile(self._chemin_audio):
            os.startfile(self._chemin_audio)

    def _afficher_vide(self):
        """Réinitialise l'éditeur (aucune note chargée)."""
        self._note_id = None
        self._chemin_audio = ""
        self.champ_titre.setText("")
        self.editeur_texte.setPlainText("")
        self.champ_themes.setText("")
        self.btn_sauvegarder.setEnabled(False)
        self.btn_classer.setEnabled(False)
        self.btn_exporter.setEnabled(False)
        self.btn_importer.setEnabled(False)
        self.btn_audio.setEnabled(False)
        self.barre_progression.hide()
        self.lbl_classif_statut.setText("")

    # ------------------------------------------------------------------
    # Styles
    # ------------------------------------------------------------------

    def _style_bouton_secondaire(self) -> str:
        return """
            QPushButton {
                background-color: #f5f5f5;
                border: 1px solid #ccc;
                border-radius: 4px;
                padding: 7px 14px;
                color: #333;
            }
            QPushButton:hover { background-color: #e0e0e0; }
            QPushButton:disabled { color: #aaa; background-color: #f5f5f5; }
        """
