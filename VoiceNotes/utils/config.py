"""
utils/config.py
---------------
Configuration centralisée de l'application VoiceNotes.
Charge les variables d'environnement depuis le fichier .env et définit
tous les chemins et constantes utilisés dans l'application.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# --- Chargement du fichier .env (doit se trouver à la racine du projet) ---
_racine = Path(__file__).resolve().parent.parent
load_dotenv(_racine / ".env")

# --- Clé API Anthropic (obligatoire pour la classification des thèmes) ---
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

# --- Dossier de données (créé automatiquement si absent) ---
# Par défaut : sous-dossier "data" à la racine du projet.
# L'utilisateur peut surcharger en ajoutant DATA_DIR=/mon/chemin dans .env
_data_dir_env = os.getenv("DATA_DIR", "")
if _data_dir_env:
    DATA_DIR = Path(_data_dir_env)
else:
    DATA_DIR = _racine / "data"

DATA_DIR.mkdir(parents=True, exist_ok=True)

# Sous-dossier pour les fichiers audio
AUDIO_DIR = DATA_DIR / "recordings"
AUDIO_DIR.mkdir(parents=True, exist_ok=True)

# Chemin de la base de données SQLite
DB_PATH = str(DATA_DIR / "voicenotes.db")

# --- Paramètres audio ---
SAMPLE_RATE = 16000          # Fréquence d'échantillonnage en Hz (optimal pour Whisper)
CHANNELS = 1                  # Mono (Whisper fonctionne en mono)
AUDIO_DTYPE = "float32"       # Format des échantillons sounddevice

# --- Paramètres Whisper ---
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "base")   # "tiny", "base", "small", "medium", "large"
WHISPER_LANGUAGE = os.getenv("WHISPER_LANGUAGE", "fr")  # Langue principale des notes

# --- Paramètres Anthropic ---
CLAUDE_MODEL = "claude-haiku-4-5-20251001"   # Modèle rapide et économique pour la classification

# --- Thèmes par défaut (utilisés si la base est vide) ---
THEMES_PAR_DEFAUT = [
    "Personnel",
    "Travail",
    "Réunion",
    "Idée",
    "Action à faire",
    "Divers",
]

# --- Limites d'affichage ---
EXTRAIT_LONGUEUR = 120   # Nombre de caractères affichés dans la liste des notes
