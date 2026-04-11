"""
core/audio_recorder.py
----------------------
Gestion de l'enregistrement audio en temps réel via le microphone.

Utilise `sounddevice` (pas de compilateur C requis sur Windows) et
`scipy` pour sauvegarder en format WAV 16 kHz mono, optimisé pour Whisper.

Fonctionnement :
  1. Appeler start_enregistrement() → démarre la capture en arrière-plan
  2. Appeler stop_enregistrement()  → arrête et retourne le chemin du fichier .wav sauvegardé

Thread-safety : sounddevice utilise son propre thread audio interne.
Les échantillons sont accumulés dans une liste protégée par un threading.Lock.
"""

import threading
import time
import wave
import numpy as np
from pathlib import Path
from datetime import datetime

import sounddevice as sd
from scipy.io import wavfile

from utils.config import SAMPLE_RATE, CHANNELS, AUDIO_DTYPE, AUDIO_DIR


class AudioRecorder:
    """
    Enregistreur audio non-bloquant.

    Exemple d'utilisation :
        recorder = AudioRecorder()
        recorder.start_enregistrement()
        # ... l'utilisateur parle ...
        chemin, duree = recorder.stop_enregistrement()
    """

    def __init__(self):
        self._echantillons: list[np.ndarray] = []
        self._verrou = threading.Lock()
        self._stream: sd.InputStream | None = None
        self._en_cours = False
        self._heure_debut: float | None = None

    # ------------------------------------------------------------------
    # Interface publique
    # ------------------------------------------------------------------

    def start_enregistrement(self):
        """
        Démarre la capture du microphone.
        Lève RuntimeError si un enregistrement est déjà en cours.
        """
        if self._en_cours:
            raise RuntimeError("Un enregistrement est déjà en cours.")

        self._echantillons = []
        self._heure_debut = time.time()
        self._en_cours = True

        # Ouverture du flux audio en entrée
        self._stream = sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=CHANNELS,
            dtype=AUDIO_DTYPE,
            callback=self._callback_audio,
        )
        self._stream.start()

    def stop_enregistrement(self) -> tuple[str, float]:
        """
        Arrête l'enregistrement, sauvegarde le fichier .wav et retourne :
            (chemin_fichier: str, duree_secondes: float)

        Retourne ("", 0.0) si aucun enregistrement n'était actif.
        """
        if not self._en_cours:
            return "", 0.0

        # Arrêt du flux
        self._stream.stop()
        self._stream.close()
        self._stream = None
        self._en_cours = False

        duree = time.time() - self._heure_debut

        # Assemblage des échantillons
        with self._verrou:
            if not self._echantillons:
                return "", 0.0
            audio = np.concatenate(self._echantillons, axis=0)

        chemin = self._sauvegarder_wav(audio, duree)
        return chemin, duree

    def est_en_cours(self) -> bool:
        """Retourne True si un enregistrement est actif."""
        return self._en_cours

    def duree_actuelle(self) -> float:
        """Retourne la durée écoulée depuis le début de l'enregistrement (en secondes)."""
        if not self._en_cours or self._heure_debut is None:
            return 0.0
        return time.time() - self._heure_debut

    # ------------------------------------------------------------------
    # Méthodes internes
    # ------------------------------------------------------------------

    def _callback_audio(self, indata: np.ndarray, frames: int,
                         time_info, status):
        """
        Callback appelé par sounddevice à chaque bloc audio capturé.
        Copie les données dans la liste d'échantillons (thread-safe).
        """
        if status:
            # Affiche les warnings audio sans planter (ex: buffer overflow)
            print(f"[AudioRecorder] Avertissement sounddevice : {status}")
        with self._verrou:
            self._echantillons.append(indata.copy())

    def _sauvegarder_wav(self, audio: np.ndarray, duree: float) -> str:
        """
        Sauvegarde le tableau numpy en fichier .wav 16 kHz mono.
        Le nom du fichier contient l'horodatage pour l'unicité.
        Retourne le chemin absolu du fichier créé.
        """
        horodatage = datetime.now().strftime("%Y%m%d_%H%M%S")
        nom_fichier = f"note_{horodatage}.wav"
        chemin = str(AUDIO_DIR / nom_fichier)

        # Conversion float32 [-1, 1] → int16 pour compatibilité maximale
        audio_mono = audio[:, 0] if audio.ndim == 2 else audio
        audio_int16 = np.clip(audio_mono, -1.0, 1.0)
        audio_int16 = (audio_int16 * 32767).astype(np.int16)

        wavfile.write(chemin, SAMPLE_RATE, audio_int16)
        print(f"[AudioRecorder] Fichier sauvegardé : {chemin} ({duree:.1f}s)")
        return chemin


# ---------------------------------------------------------------------------
# Utilitaire : liste des microphones disponibles
# ---------------------------------------------------------------------------

def lister_microphones() -> list[str]:
    """
    Retourne la liste des noms des périphériques d'entrée disponibles.
    Utile pour déboguer si le mauvais micro est sélectionné.
    """
    dispositifs = sd.query_devices()
    entrees = []
    for d in dispositifs:
        if d["max_input_channels"] > 0:
            entrees.append(f"{d['index']}: {d['name']}")
    return entrees
