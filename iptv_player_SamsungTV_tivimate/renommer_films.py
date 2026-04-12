import os

# ============================================================
# CONFIGURATION - Modifiez uniquement cette ligne si nécessaire
# ============================================================
DOSSIER = r"E:\Films\Films Cultes FR"
FICHIER_LISTE = os.path.join(DOSSIER, "Liste.txt")
# ============================================================

print("=" * 60)
print("  Script de renommage de fichiers")
print("=" * 60)
print(f"Dossier       : {DOSSIER}")
print(f"Fichier liste : {FICHIER_LISTE}")
print()

# Vérification que le dossier existe
if not os.path.isdir(DOSSIER):
    print(f"ERREUR : Le dossier '{DOSSIER}' est introuvable.")
    input("\nAppuyez sur Entrée pour quitter...")
    exit()

# Vérification que Liste.txt existe
if not os.path.isfile(FICHIER_LISTE):
    print(f"ERREUR : Le fichier 'Liste.txt' est introuvable dans le dossier.")
    input("\nAppuyez sur Entrée pour quitter...")
    exit()

# Lecture du fichier Liste.txt
with open(FICHIER_LISTE, "r", encoding="utf-8") as f:
    lignes = f.readlines()

nb_ok = 0
nb_erreur = 0
nb_ignore = 0

for numero_ligne, ligne in enumerate(lignes, start=1):
    ligne = ligne.strip()

    # Ignorer les lignes vides
    if not ligne:
        nb_ignore += 1
        continue

    # Vérification du format attendu : "Nom du film - Année ; http://.../.../1234567.mkv"
    if ";" not in ligne:
        print(f"  [IGNORÉ] Ligne {numero_ligne} : format non reconnu → '{ligne}'")
        nb_ignore += 1
        continue

    # Découpage de la ligne en deux parties
    parties = ligne.split(";", 1)
    nouveau_nom_base = parties[0].strip()   # Ex : "Fantômas - 1964"
    url = parties[1].strip()                # Ex : "http://.../.../1544327.mkv"

    # Extraction du nom de fichier actuel depuis la fin de l'URL
    # Ex : "1544327.mkv"
    nom_fichier_actuel = url.split("/")[-1].strip()

    if not nom_fichier_actuel:
        print(f"  [IGNORÉ] Ligne {numero_ligne} : impossible d'extraire le nom de fichier depuis l'URL")
        nb_ignore += 1
        continue

    # Récupération de l'extension (ex : ".mkv" ou ".avi")
    _, extension = os.path.splitext(nom_fichier_actuel)

    # Construction du nouveau nom avec extension
    # Remplacement des caractères interdits dans les noms de fichiers Windows
    nouveau_nom = nouveau_nom_base + extension
    for char in ['\\', '/', ':', '*', '?', '"', '<', '>', '|']:
        nouveau_nom = nouveau_nom.replace(char, '-')

    ancien_chemin = os.path.join(DOSSIER, nom_fichier_actuel)
    nouveau_chemin = os.path.join(DOSSIER, nouveau_nom)

    # Vérification que le fichier source existe
    if not os.path.isfile(ancien_chemin):
        print(f"  [INTROUVABLE] '{nom_fichier_actuel}' → fichier absent du dossier")
        nb_erreur += 1
        continue

    # Vérification que le fichier de destination n'existe pas déjà
    if os.path.exists(nouveau_chemin):
        print(f"  [DÉJÀ EXISTANT] '{nouveau_nom}' existe déjà, renommage ignoré")
        nb_ignore += 1
        continue

    # Renommage
    try:
        os.rename(ancien_chemin, nouveau_chemin)
        print(f"  [OK] '{nom_fichier_actuel}' → '{nouveau_nom}'")
        nb_ok += 1
    except Exception as e:
        print(f"  [ERREUR] '{nom_fichier_actuel}' → '{nouveau_nom}' : {e}")
        nb_erreur += 1

# Résumé final
print()
print("=" * 60)
print(f"  Résultat : {nb_ok} fichier(s) renommé(s) avec succès")
if nb_erreur > 0:
    print(f"             {nb_erreur} fichier(s) introuvable(s) ou erreur(s)")
if nb_ignore > 0:
    print(f"             {nb_ignore} ligne(s) ignorée(s)")
print("=" * 60)
input("\nAppuyez sur Entrée pour fermer...")
