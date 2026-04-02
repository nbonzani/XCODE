# M3U Manager — Spécification des fonctionnalités

> Document de référence du projet — avril 2026
> Version 1.1 — mise à jour après session de développement du 2 avril 2026

---

## Environnement technique

- OS : Windows 10 / 11
- Python : 3.12
- Interface graphique : PyQt6
- Bibliothèques : PyQt6 >= 6.6.0, requests >= 2.31.0

---

## Fonctionnalités détaillées

### F01 — Connexion au serveur Xtream Codes

- Boîte de dialogue au démarrage (LoginDialog) avec trois champs :
  - URL du serveur (ex : http://hmz.aurhost.com)
  - Nom d'utilisateur
  - Mot de passe (masqué)
- Bouton "Tester la connexion" :
  - Test dans un thread séparé (non bloquant)
  - Affichage du statut : "Connexion en cours..." (orange) → succès (vert) / échec (rouge)
  - Active le bouton "Se connecter" uniquement si le test réussit
- Sauvegarde automatique des identifiants en local (data/config.json)
- Pré-remplissage des champs au prochain démarrage
- Mécanisme robuste : 3 tentatives automatiques, timeout 15s (auth) / 60s (M3U)

### F02 — Téléchargement de la playlist

- Endpoint utilisé : GET /get.php?type=m3u_plus&output=ts
- Téléchargement du texte M3U complet en mémoire
- Alternative : chargement d'un fichier M3U local (menu Fichier → Ouvrir)

### F03 — Affichage liste brute

- Tableau affichant toutes les entrées sans filtre
- Colonnes : Nom, Groupe/Catégorie, Type, Pays, Langue, Qualité, URL
- Nombre total d'entrées affiché en barre de statut

### F04 — Filtres combinables

#### F04a — Filtre par type de contenu
Cases à cocher (sélection multiple) :
- [ ] Chaînes live
- [ ] Films VOD
- [ ] Séries TV

#### F04b — Filtre par qualité vidéo (chaînes live uniquement)
Cases à cocher :
- [ ] SD
- [ ] HD (720p)
- [ ] FHD (1080p)
- [ ] 4K / UHD
- [ ] Qualité non identifiée

Détection automatique de la qualité par analyse du nom de la chaîne
et de la catégorie (mots-clés : SD, HD, FHD, UHD, 4K).

#### F04c — Filtre Pays / Langue (multi-critères combinés)
- Champ texte libre : recherche dans group-title (nom de catégorie)
- Champ texte libre : recherche dans le nom de la chaîne/vidéo
- Liste déroulante : pays disponibles (extraits de tvg-country)
- Liste déroulante : langues disponibles (extraites de tvg-language)
- Cases à cocher de langue rapide : FR / EN / DE / ES / AR / autres
- Champ mots-clés exclus : termes à bannir des résultats

### F05 — Affichage liste filtrée

- Même structure de tableau que la liste brute
- Surlignage par type :
  - Chaînes live → bleu clair
  - Films VOD    → vert clair
  - Séries TV    → orange clair
- Nombre d'entrées filtrées affiché en barre de statut
- Sélection multiple (clic + Maj / Ctrl)

### F06 — Tris combinés et ordonnés

- Tri par clic sur en-tête de colonne
- Tris simultanés : tri primaire, secondaire, tertiaire
- Critères : Nom (A→Z), Catégorie, Année, Qualité, Évaluation
- Indicateur visuel de l'ordre de tri actif

### F07 — Menu Fichier

- Ouvrir un fichier M3U local
- Enregistrer sous → export M3U+ filtré
- Exporter CSV → fichier séparé par points-virgules (Nom ; URL)
- Quitter

### F08 — Téléchargement de vidéos

- Télécharge les entrées sélectionnées dans la liste filtrée
- Choix du dossier de destination via boîte de dialogue système
- Barre de progression par fichier + progression globale
- Nommage : [Nom_de_lentree].[extension]
- Nettoyage automatique des caractères interdits dans les noms Windows

### F09 — Lecture vidéo

- Double-clic sur une ligne → lecture plein écran via lecteur externe
- Priorité : VLC, puis mpv
- Message d'erreur si aucun lecteur détecté

---

## Contraintes permanentes

- Logique métier (core/) totalement séparée de l'interface (ui/)
- Aucune dépendance incompatible avec Android / webOS (évolutions futures)
- Pas de lecteur vidéo embarqué
- Encodage UTF-8 systématique
- Timeout systématique sur tous les appels réseau
- Identifiants stockés uniquement en local (data/config.json), jamais transmis
