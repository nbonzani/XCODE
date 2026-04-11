# VoiceNotes — Notes vocales avec transcription automatique

Application desktop Windows pour enregistrer des notes vocales,
les transcrire automatiquement (Whisper, 100% local) et les classer
par thèmes intelligemment (Claude Haiku, API Anthropic).

---

## Prérequis

- Windows 10 ou 11 (64 bits)
- Microphone fonctionnel
- Connexion internet (uniquement pour la classification par thèmes et le premier téléchargement de Whisper)

---

## Installation étape par étape

### Étape 1 — Installer Python

1. Allez sur [https://www.python.org/downloads/](https://www.python.org/downloads/)
2. Cliquez sur **"Download Python 3.12"** (ou version 3.10+)
3. Lancez l'installeur
4. **IMPORTANT** : cochez la case **"Add Python to PATH"** avant de cliquer sur "Install Now"
5. Cliquez sur "Install Now" et attendez la fin

**Vérification** : ouvrez un terminal (touche Windows + R, tapez `cmd`, Entrée) et tapez :
```
python --version
```
Vous devez voir quelque chose comme `Python 3.12.x`

---

### Étape 2 — Installer ffmpeg (requis par Whisper)

1. Allez sur [https://github.com/BtbN/FFmpeg-Builds/releases](https://github.com/BtbN/FFmpeg-Builds/releases)
2. Téléchargez le fichier **`ffmpeg-master-latest-win64-gpl.zip`**
3. Extrayez l'archive (clic droit → "Extraire tout")
4. Ouvrez le dossier extrait → entrez dans le sous-dossier `bin`
5. Copiez le chemin de ce dossier (ex: `C:\ffmpeg\bin`)
6. Ajoutez ce chemin au PATH Windows :
   - Touche Windows → tapez "Variables d'environnement" → cliquez sur le résultat
   - Cliquez sur "Variables d'environnement..."
   - Dans "Variables système", double-cliquez sur "Path"
   - Cliquez "Nouveau" et collez le chemin du dossier `bin`
   - Cliquez OK × 3

**Vérification** : dans un nouveau terminal, tapez :
```
ffmpeg -version
```
Vous devez voir la version de ffmpeg s'afficher.

---

### Étape 3 — Télécharger VoiceNotes

Placez le dossier `VoiceNotes` où vous le souhaitez sur votre ordinateur
(par exemple dans `C:\Users\VotreNom\Documents\VoiceNotes`).

---

### Étape 4 — Installer les dépendances Python

Ouvrez un terminal dans le dossier VoiceNotes :
- Naviguez vers le dossier dans l'Explorateur Windows
- Cliquez dans la barre d'adresse, tapez `cmd`, appuyez sur Entrée

Dans le terminal, tapez :
```
pip install -r requirements.txt
```

> Cette commande télécharge et installe automatiquement toutes les bibliothèques.
> Cela peut prendre 5 à 15 minutes selon votre connexion internet.

---

### Étape 5 — Configurer la clé API Anthropic

La classification automatique par thèmes utilise l'API Anthropic (Claude Haiku).

1. Créez un compte sur [https://console.anthropic.com/](https://console.anthropic.com/)
2. Allez dans "API Keys" et créez une nouvelle clé
3. Dans le dossier VoiceNotes, copiez le fichier `.env.example` et renommez la copie en `.env`
4. Ouvrez `.env` avec le Bloc-notes
5. Remplacez `<votre-cle-api-anthropic-ici>` par votre vraie clé (qui commence par `sk-ant-`)
6. Sauvegardez et fermez le fichier

> **Coût estimé** : Claude Haiku est très économique. Classer 100 notes coûte
> environ $0.01 (moins d'un centime d'euro).

---

### Étape 6 — Lancer l'application

Dans le terminal ouvert dans le dossier VoiceNotes :
```
python main.py
```

> **Premier lancement** : Whisper téléchargera le modèle "base" (~150 Mo).
> Cette opération est automatique et ne se fait qu'une seule fois.

---

## Utilisation

### Enregistrer une note vocale

1. Cliquez sur le bouton rouge **"⏺ Enregistrer"**
2. Parlez dans votre microphone
3. Cliquez sur **"⏹ Arrêter"** quand vous avez terminé
4. Whisper transcrit automatiquement votre audio (quelques secondes)

### Classer la note

1. Une fois la transcription terminée, cliquez sur **"🤖 Classer automatiquement"**
2. Claude Haiku analyse le texte et propose un titre + des thèmes
3. Vous pouvez modifier manuellement les thèmes dans le champ texte
4. Cliquez sur **"💾 Sauvegarder"**

### Retrouver une note

- Utilisez le **filtre par thème** (menu déroulant en haut de la liste)
- Utilisez la **barre de recherche** pour chercher un mot dans les transcriptions
- Cliquez sur une note dans la liste pour l'afficher et la modifier

### Gérer les thèmes

- Menu **"Thèmes" → "Gérer les thèmes…"**
- Vous pouvez ajouter, renommer ou supprimer des thèmes

---

## Structure des données

```
data/
├── voicenotes.db        ← base de données SQLite (notes, thèmes)
└── recordings/          ← fichiers audio .wav
    ├── note_20241201_143022.wav
    └── ...
```

Les données sont stockées localement sur votre ordinateur.
Aucune donnée n'est envoyée dans le cloud, sauf le texte transcrit
envoyé à l'API Anthropic pour la classification des thèmes.

---

## Résolution des problèmes fréquents

| Problème | Solution |
|----------|----------|
| `ffmpeg not found` | Relancez le terminal après avoir modifié le PATH |
| Pas de son enregistré | Vérifiez que le microphone est autorisé dans les paramètres Windows (Confidentialité → Microphone) |
| Transcription très lente | Normal sur CPU sans GPU. Le modèle "tiny" est plus rapide (modifier `WHISPER_MODEL=tiny` dans `.env`) |
| Erreur clé API | Vérifiez que le fichier `.env` existe et contient bien `ANTHROPIC_API_KEY=sk-ant-...` |
| `ModuleNotFoundError` | Relancez `pip install -r requirements.txt` dans le bon dossier |

---

## Dépendances principales

| Bibliothèque | Rôle | Type |
|---|---|---|
| PyQt6 | Interface graphique | Local |
| sounddevice | Capture microphone | Local |
| openai-whisper | Transcription audio → texte | Local (modèle téléchargé 1× fois) |
| anthropic | Classification thèmes (Claude Haiku) | API cloud |
| python-dotenv | Lecture du fichier .env | Local |
