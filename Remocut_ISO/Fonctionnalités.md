# Fonctionnalités — Remocut ISO Generator

## Fonctionnalités essentielles (MVP)

### F1 — Import de fichiers DXF
- Description : ouverture d'un ou plusieurs fichiers DXF contenant les profils à découper
- Entrée : fichiers .dxf (AutoCAD 2000 à 2024, entités LINE, ARC, LWPOLYLINE, CIRCLE, SPLINE)
- Sortie : liste des contours détectés, affichés dans le viewer 2D
- Contraintes : les contours doivent être fermés (tolérance de fermeture configurable)

### F2 — Paramétrage de la découpe
- Description : saisie de tous les paramètres nécessaires à la génération GCode
- Paramètres :
  - Matériau (acier / inox / aluminium) avec valeurs par défaut associées
  - Épaisseur tôle (mm)
  - Vitesse de découpe F (mm/min)
  - Kerf (mm) — largeur de trait plasma
  - Délai piercing G04 (ms)
  - Longueur lead-in (mm) et type (linéaire / arc)
  - Longueur lead-out (mm)
  - Côté de compensation (G41 gauche / G42 droite)
  - Format tôle (largeur × hauteur en mm)
  - Vitesse rapide G00 (mm/min)

### F3 — Nesting (imbrication des pièces)
- Description : placement automatique des pièces importées sur le format de tôle défini
- Entrée : liste des contours + format de tôle + marge entre pièces
- Sortie : positions XY de chaque pièce sur la tôle, visualisation nesting
- Contraintes V1 : placement en rangées successives (gauche→droite, bas→haut), pas de rotation

### F4 — Calcul de trajectoire
- Description : calcul de l'ordre et du chemin de découpe pour toutes les pièces
- Règles :
  - Les contours intérieurs (trous) sont découpés avant les contours extérieurs
  - Lead-in sur chaque contour avant allumage torche
  - Lead-out sur chaque contour après extinction torche
  - Déplacement rapide G00 entre les contours

### F5 — Génération GCode ISO ECP1000
- Description : export du programme GCode conforme au contrôleur Eurosoft ECP1000
- Entrée : trajectoires calculées + paramètres de découpe
- Sortie : fichier GCode (extension et format conformes aux exemples du dossier doc/)
- Structure obligatoire : en-tête commenté → initialisation → séquence par contour (G00 + M03 + G41/42 + contour + G40 + M05) → M30
- Compensation de kerf : G41 D1 pour contours extérieurs, G42 D1 pour contours intérieurs

### F6 — Prévisualisation trajectoire
- Description : affichage graphique du parcours outil calculé (déplacements rapides en pointillés, trajectoires de découpe en trait plein, lead-in/out en couleur distincte)
- Entrée : trajectoires calculées
- Sortie : rendu 2D dans l'interface

### F7 — Export fichier GCode
- Description : sauvegarde du GCode dans un fichier sur disque
- Répertoire par défaut : output/ (relatif au projet) ou chemin personnalisé
- Nom de fichier : auto-généré à partir du nom DXF + date + heure

## Fonctionnalités secondaires (V2)

### F8 — Base de données matériaux
- Édition des paramètres par défaut par matériau/épaisseur depuis l'interface

### F9 — Nesting optimisé
- Algorithme de placement avec rotation des pièces pour minimiser les chutes

### F10 — Import multi-DXF
- Glisser-déposer de plusieurs fichiers DXF simultanément

### F11 — Mode simulation à blanc
- Génération d'un GCode sans M03/M05 (déplacements torche éteinte) pour test machine

### F12 — Historique des programmes
- Liste des derniers fichiers GCode générés avec leurs paramètres

## Fonctionnalités exclues du périmètre
- Pas de dessin/édition de géométrie (l'application lit des DXF, ne les crée pas)
- Pas de connexion directe à la machine (pas d'envoi réseau/USB du GCode)
- Pas de simulation 3D
- Pas de gestion multi-utilisateurs
- Pas de découpe biseau (torche droite uniquement)
- Pas de découpe tube

## Cas limites à gérer
- Contour DXF non fermé → avertissement avec tolérance de fermeture configurable
- Pièce trop grande pour la tôle → message d'erreur explicite
- Pièces se chevauchant après nesting → détection et alerte
- Fichier DXF vide ou corrompu → message d'erreur sans crash
- Entités DXF non supportées (3DFACE, MESH…) → ignorées avec avertissement
- Contour avec segments trop courts pour lead-in → réduction automatique du lead-in
