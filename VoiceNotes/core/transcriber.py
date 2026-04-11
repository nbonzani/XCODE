"""
core/transcriber.py
-------------------
Transcription automatique d'un fichier audio en texte via Whisper (exécution 100% locale).

Whisper est chargé une seule fois en mémoire au premier appel (lazy loading)
pour ne pas ralentir le démarrage de l'application.

⚠️ Dépendance externe : `openai-whisper` + `ffmpeg` installé et dans le PATH Windows.
   Modèles disponibles (par ordre croissant de précision/lenteur) :
   "tiny", "base", "small", "medium", "large"
   Le modèle "base" offre un bon compromis vitesse/qualité pour le français.

Fonctionnement asynchrone recommandé :
  Appeler transcire_fichier() dans un QThread PyQt6 pour ne pas bloquer l'interface.
"""

import os
from pathlib import Path
from utils.config import WHISPER_MODEL, WHISPER_LANGUAGE

# Import différé : whisper est importé au premier usage pour accélérer le démarrage
_whisper_model = None


def _charger_modele():
    """
    Charge le modèle Whisper en mémoire (opération longue, ~3–30 s selon le modèle).
    Appelé automatiquement au premier besoin (lazy loading).
    """
    global _whisper_model
    if _whisper_model is None:
        try:
            import whisper
            print(f"[Transcriber] Chargement du modèle Whisper '{WHISPER_MODEL}'...")
            _whisper_model = whisper.load_model(WHISPER_MODEL)
            print(f"[Transcriber] Modèle '{WHISPER_MODEL}' chargé.")
        except ImportError:
            raise ImportError(
                "Le module 'openai-whisper' n'est pas installé.\n"
                "Exécutez : pip install openai-whisper"
            )
    return _whisper_model


def transcrire_fichier(chemin_audio: str,
                       callback_progression=None) -> str:
    """
    Transcrit un fichier audio en texte.

    Paramètres :
        chemin_audio        : chemin absolu vers le fichier .wav ou .mp3
        callback_progression: fonction optionnelle appelée avec (message: str)
                              pour informer l'UI de l'avancement

    Retourne :
        Le texte transcrit (str). Retourne "" si le fichier est vide ou illisible.

    Lève :
        FileNotFoundError si le fichier audio n'existe pas.
        ImportError si openai-whisper n'est pas installé.
    """
    if not os.path.isfile(chemin_audio):
        raise FileNotFoundError(f"Fichier audio introuvable : {chemin_audio}")

    if callback_progression:
        callback_progression("Chargement du modèle Whisper…")

    model = _charger_modele()

    if callback_progression:
        callback_progression("Transcription en cours…")

    # Whisper accepte directement un chemin de fichier
    # language="fr" évite l'étape de détection automatique (plus rapide)
    try:
        resultat = model.transcribe(
            chemin_audio,
            language=WHISPER_LANGUAGE,
            fp16=False,        # fp16=False requis si pas de GPU CUDA
            verbose=False,
        )
        texte = resultat.get("text", "").strip()
    except Exception as e:
        print(f"[Transcriber] Erreur lors de la transcription : {e}")
        raise

    if callback_progression:
        callback_progression("Transcription terminée.")

    print(f"[Transcriber] Texte ({len(texte)} caractères) : {texte[:80]}…")
    return texte


def precharger_modele():
    """
    Force le chargement immédiat du modèle Whisper.
    À appeler en arrière-plan au démarrage de l'app pour éviter le délai
    lors de la première transcription.
    """
    _charger_modele()
