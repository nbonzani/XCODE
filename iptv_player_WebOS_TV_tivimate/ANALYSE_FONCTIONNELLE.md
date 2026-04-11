J'ai maintenant une vue complète de l'application. Voici l'inventaire fonctionnel complet.

---

# Analyse fonctionnelle — WebOS IPTV Player

## 1. Liste des écrans / vues de l'application

L'application comporte **6 vues distinctes** :

| N° | Nom de la vue | Fichier source | Type |
|---|---|---|---|
| 1 | Fenêtre principale | `main_window.py` | Fenêtre principale |
| 2 | Dialogue Paramètres | `settings_dialog.py` | Dialogue modal |
| 3 | Dialogue Options de lecture (film) | `play_options_dialog.py` | Dialogue modal |
| 4 | Dialogue Détail série / épisodes | `series_dialog.py` | Dialogue modal |
| 5 | Lecteur vidéo plein écran | `player_window.py` | Fenêtre indépendante |
| 6 | Progression de téléchargement | `download_manager.py` | Dialogue modal |

---

## 2. Détail fonctionnel par écran

### Écran 1 — Fenêtre principale (`MainWindow`)

C'est l'écran central de l'application. Il est composé de trois onglets.

#### Barre d'outils (persistante, commune aux 3 onglets)
- Champ de recherche textuelle par titre (filtrage en temps réel)
- Filtre par catégorie (liste déroulante dynamique)
- Filtre par année de sortie
- Bouton bascule "FR uniquement" (filtre contenu français)
- Bouton "Synchroniser" (lancement manuel de la sync catalogue)
- Bouton "Paramètres" (ouvre le dialogue Paramètres)
- Spinner d'animation (actif pendant synchro et téléchargements)

#### Onglet 1 — Films (`grid_movies`)
- Grille de vignettes (poster + titre) des films
- Chargement progressif par pages (lazy loading au scroll)
- Chargement des posters : depuis le cache disque (priorité) ou réseau (pool de 8 threads)
- Clic sur une vignette → ouverture du dialogue Options de lecture
- Compteur de résultats affiché

#### Onglet 2 — Séries (`grid_series`)
- Grille de vignettes (poster + titre) des séries
- Mêmes mécanismes que l'onglet Films (lazy loading, cache posters)
- Clic sur une vignette → ouverture du dialogue Détail série / épisodes

#### Onglet 3 — Téléchargés
- Liste des fichiers téléchargés (base de données + scan disque fusionnés)
- Chaque ligne : icône, nom, taille en Mo, date de téléchargement, indicateur de fichier introuvable
- Bouton "▶ Lire" par ligne (lecture locale)
- Bouton "🗑 Supprimer" par ligne (suppression définitive du fichier)
- Double-clic sur une ligne → lecture du fichier local
- Menu contextuel clic droit : Lire / Voir dans l'explorateur / Supprimer de la liste / Supprimer liste + fichier
- Bouton "📁 Ouvrir le dossier" (explorateur Windows)
- Message vide si aucun téléchargement

#### Barre de statut (persistante)
- Affichage des messages d'état (progression sync, compteurs, erreurs)

#### Menu principal
- Menu **Fichier** : Paramètres, Quitter
- Menu **Catalogue** : Synchroniser, Vider le cache, Télécharger liste M3U complète, Télécharger liste M3U FR, Exporter catalogue CSV

---

### Écran 2 — Dialogue Paramètres (`SettingsDialog`)
- Champ URL du serveur Xtream
- Champ Port du serveur
- Champ Nom d'utilisateur
- Champ Mot de passe (masqué)
- Case à cocher "Afficher uniquement le contenu français"
- Bouton "Tester la connexion" (affiche statut du compte : expiration, connexions actives)
- Bouton "Enregistrer" (validation + sauvegarde)
- Bouton "Annuler"
- Ouverture automatique au premier lancement si non configuré

---

### Écran 3 — Dialogue Options de lecture (`PlayOptionsDialog`)
- Affiché uniquement pour les **films**
- En-tête : poster miniature + titre + catégorie + note
- Option "Voir sur ce PC" → lecture plein écran immédiate
- Option "Télécharger le film" → lancement du téléchargement local
- Bouton "Annuler"

---

### Écran 4 — Dialogue Détail série (`SeriesDialog`)
- En-tête : image de couverture + titre + genre + année + note + synopsis (280 caractères max)
- Arbre de navigation saisons / épisodes
  - Nœuds saison : nom, nombre d'épisodes, progression de visionnage (N/total vus, ✅ terminée)
  - Nœuds épisode : numéro, titre, état visionné (✅ vert)
  - Sélection automatique du premier épisode non visionné au chargement
- Bouton contextuel "▶ Lire l'épisode" ou "▶ Lire la saison (N épisodes)"
- Bouton contextuel "⬇️ Télécharger cet épisode" ou "⬇️ Télécharger la saison"
- Double-clic sur un épisode → lecture directe
- Marquage automatique comme visionné à la lecture

---

### Écran 5 — Lecteur vidéo (`PlayerWindow`)
- Lecture vidéo plein écran via VLC (`python-vlc`)
- Sélection de l'écran cible (principal ou secondaire si disponible)
- Barre de contrôles (affichage/masquage automatique après 3 s d'inactivité)
  - Bouton Lecture / Pause
  - Barre de progression (cliquable pour se repositionner)
  - Affichage temps écoulé / durée totale
  - Contrôle du volume (slider + valeur %)
  - Bouton Muet
  - Titre du contenu en cours
  - Bouton Fermer
- Raccourcis clavier : Espace (pause), Échap (fermer), ←/→ (±10s), PgPréc/PgSuiv (±5min), ↑/↓ (volume), M (muet)
- Lecture en mode playlist (séquence d'épisodes d'une saison)
- Overlay transparent pour capturer les événements souris par-dessus la fenêtre VLC native

---

### Écran 6 — Progression de téléchargement (`DownloadProgressDialog` / `SeasonDownloadDialog`)

**`DownloadProgressDialog`** (un seul fichier) :
- Titre du contenu en cours de téléchargement
- Barre de progression avec pourcentage
- Affichage vitesse de téléchargement (Ko/s ou Mo/s)
- Affichage ETA (temps restant estimé)
- Bouton "Annuler"

**`SeasonDownloadDialog`** (saison entière) :
- Progression globale de la saison (N épisodes / total)
- Progression individuelle de l'épisode en cours
- Affichage du nom de l'épisode en téléchargement
- Vitesse et ETA
- Bouton "Annuler"

---

## 3. Liste exhaustive de toutes les fonctionnalités

### Connexion et configuration
- Configuration des paramètres de connexion Xtream Codes (URL, port, identifiants)
- Test de connexion au serveur avec affichage des infos compte (statut, expiration, connexions actives)
- Sauvegarde de la configuration en JSON local (`AppData`)
- Filtre de langue configurable (français uniquement ou tout)

### Catalogue et synchronisation
- Synchronisation manuelle du catalogue depuis le serveur Xtream
- Synchronisation automatique au premier lancement
- Synchronisation automatique si catalogue > 30 jours
- Synchronisation silencieuse en arrière-plan pendant le visionnage si > 24h
- Stockage du catalogue en base SQLite locale (films + séries + catégories)
- Vidage manuel du cache

### Navigation et filtrage
- Affichage en grille (onglets Films / Séries)
- Recherche textuelle par titre (temps réel)
- Filtrage par catégorie
- Filtrage par année de sortie
- Filtrage "FR uniquement" (basé sur mots-clés dans les noms de catégories)
- Compteur de résultats
- Chargement progressif des vignettes (lazy loading, pages de N éléments)

### Gestion des posters / vignettes
- Chargement prioritaire depuis le cache disque local (instantané)
- Téléchargement réseau en fallback (pool de 8 threads max)
- Téléchargement en arrière-plan de toutes les vignettes manquantes après 4s d'inactivité
- Téléchargement à débit réduit pendant le visionnage (1 vignette/2s)
- Persistance sur le disque dans un dossier dédié (`AppData/thumbnails`)

### Lecture vidéo
- Lecture de films en streaming (flux réseau via URL Xtream)
- Lecture d'épisodes de séries en streaming
- Lecture en mode playlist (tous les épisodes d'une saison à la suite)
- Lecture de fichiers téléchargés localement
- Sélection de l'écran de lecture (principal ou secondaire)
- Contrôles complets : lecture/pause, navigation temporelle, volume, muet
- Masquage automatique des contrôles après 3s d'inactivité

### Suivi de visionnage
- Marquage automatique d'un épisode comme visionné à la lecture
- Marquage de tous les épisodes d'une saison comme visionnés (lecture saison entière)
- Affichage visuel de l'état de visionnage dans l'arbre des épisodes (✅ vert, N/total)
- Sélection automatique du premier épisode non visionné à l'ouverture d'une série

### Téléchargement local
- Téléchargement d'un film en local (dossier `Videos/IPTVPlayer/Films/`)
- Téléchargement d'un épisode en local (dossier `Videos/IPTVPlayer/<NomSérie>/`)
- Téléchargement d'une saison entière (séquentiel avec progression)
- Barre de progression avec vitesse et ETA
- Annulation de téléchargement
- Enregistrement des téléchargements en base SQLite
- Scan automatique du dossier disque (détection des fichiers non enregistrés en base)

### Gestion des téléchargements
- Liste unifiée (base de données + fichiers sur disque)
- Lecture d'un fichier téléchargé
- Suppression d'un fichier de la liste (sans supprimer le fichier)
- Suppression définitive d'un fichier (liste + disque)
- Accès au dossier dans l'explorateur Windows

### Export
- Export de la liste M3U complète (téléchargement depuis le serveur)
- Export de la liste M3U filtrée (FR uniquement, générée depuis le cache local)
- Export du catalogue complet en CSV (films + séries + chaînes live) compatible Excel

---

## 4. Dépendances Python utilisées

| Bibliothèque | Rôle dans l'application |
|---|---|
| **PyQt6** | Framework d'interface graphique : fenêtres, widgets, dialogues, threads Qt, signaux/slots |
| **python-vlc** | Lecture vidéo plein écran intégrant le moteur VLC (streaming réseau et fichiers locaux) |
| **requests** | Requêtes HTTP vers l'API Xtream (catalogue, posters, M3U), et téléchargement de fichiers |
| **sqlite3** | Base de données locale embarquée (standard Python) : cache catalogue, vignettes, téléchargements, historique de visionnage |
| **json** | Lecture et écriture de la configuration (`config.json`) |
| **pathlib** | Manipulation des chemins de fichiers (dossiers téléchargements, cache) |
| **hashlib** | Génération de noms de fichiers uniques pour les vignettes (hash de l'URL) |
| **threading** | Verrou (`Lock`) pour sécuriser les accès concurrents à la base SQLite |
| **re** | Nettoyage des noms de fichiers (suppression caractères interdits Windows) |
| **datetime** | Gestion des dates de synchronisation et d'expiration du compte |
| **csv** | Export du catalogue en fichier CSV |
| **os / subprocess** | Accès au système de fichiers, ouverture de l'explorateur Windows |
| **time** | Gestion des délais dans le thread de téléchargement des vignettes |