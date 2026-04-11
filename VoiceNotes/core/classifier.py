"""
core/classifier.py
------------------
Classification automatique d'une note dans un ou plusieurs thèmes.

Deux modes disponibles :
  1. API Anthropic (Claude Haiku) — automatique, nécessite une clé dans .env
  2. Export markdown — génère un fichier .md à coller manuellement dans claude.ai,
     puis l'utilisateur importe la réponse via un dialogue de collage.

Comportement commun :
  - Si le texte correspond à un ou plusieurs thèmes existants → les retourne
  - Si aucun thème ne correspond → propose un nouveau thème inventé par Claude
  - Toujours retourner une liste Python de chaînes de caractères
"""

import re
import os
from datetime import datetime
from pathlib import Path
from utils.config import ANTHROPIC_API_KEY, CLAUDE_MODEL, DATA_DIR


def classifier_note(texte: str, themes_disponibles: list[str]) -> list[str]:
    """
    Envoie le texte à Claude Haiku et retourne une liste de thèmes appropriés.

    Paramètres :
        texte               : transcription de la note vocale
        themes_disponibles  : liste des noms de thèmes existants en base

    Retourne :
        Liste de strings (noms de thèmes). Peut contenir un nouveau thème
        si aucun existant ne convient.

    Lève :
        ValueError si la clé API est absente.
        anthropic.APIError en cas de problème réseau ou de quota.
    """
    if not ANTHROPIC_API_KEY:
        raise ValueError(
            "Clé API Anthropic manquante.\n"
            "Ajoutez ANTHROPIC_API_KEY=sk-ant-... dans votre fichier .env"
        )

    try:
        import anthropic
    except ImportError:
        raise ImportError(
            "Le module 'anthropic' n'est pas installé.\n"
            "Exécutez : pip install anthropic"
        )

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    # Construction du prompt de classification
    themes_str = "\n".join(f"- {t}" for t in themes_disponibles)

    prompt = f"""Tu es un assistant qui classe des notes vocales dans des thèmes.

Voici la liste des thèmes disponibles :
{themes_str}

Note à classifier :
\"\"\"
{texte}
\"\"\"

Instructions :
1. Sélectionne un ou plusieurs thèmes de la liste ci-dessus qui correspondent le mieux à la note.
2. Si aucun thème ne convient vraiment, invente un nouveau thème court et descriptif (2-4 mots max).
3. Réponds UNIQUEMENT avec les noms des thèmes choisis, séparés par des virgules.
4. Ne donne aucune explication, aucun commentaire, juste les thèmes.
5. Utilise exactement l'orthographe des thèmes existants si tu les utilises.

Exemple de réponse valide : Réunion, Action à faire
Exemple de réponse valide : Idée projet innovation"""

    message = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=100,
        messages=[{"role": "user", "content": prompt}],
    )

    # Extraction de la réponse textuelle
    reponse = message.content[0].text.strip()
    print(f"[Classifier] Réponse Claude : {reponse}")

    # Parsing : découpage par virgule, nettoyage des espaces
    themes_proposes = [t.strip() for t in reponse.split(",") if t.strip()]

    # Validation : on accepte tous les thèmes retournés
    # (Claude peut proposer des thèmes existants ou en créer de nouveaux)
    if not themes_proposes:
        themes_proposes = ["Divers"]

    return themes_proposes


def classifier_note_avec_contexte(texte: str,
                                   themes_disponibles: list[str],
                                   titre_suggestion: str = None) -> tuple[list[str], str]:
    """
    Version étendue qui retourne aussi un titre suggéré pour la note.

    Retourne :
        (themes: list[str], titre: str)
    """
    if not ANTHROPIC_API_KEY:
        raise ValueError("Clé API Anthropic manquante dans .env")

    try:
        import anthropic
    except ImportError:
        raise ImportError("pip install anthropic")

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    themes_str = "\n".join(f"- {t}" for t in themes_disponibles)

    prompt = f"""Tu es un assistant qui analyse des notes vocales transcrites.

Thèmes disponibles :
{themes_str}

Note à analyser :
\"\"\"
{texte}
\"\"\"

Réponds avec exactement deux lignes :
LIGNE 1 — TITRE: un titre court et descriptif (5-8 mots maximum)
LIGNE 2 — THEMES: les thèmes séparés par des virgules (utilise les thèmes existants si possible, sinon invente-en un)

Exemple :
TITRE: Réunion projet Urbanloop capsule
THEMES: Réunion, Travail"""

    message = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=150,
        messages=[{"role": "user", "content": prompt}],
    )

    reponse = message.content[0].text.strip()
    print(f"[Classifier] Réponse étendue : {reponse}")

    titre = ""
    themes_proposes = []

    for ligne in reponse.split("\n"):
        ligne = ligne.strip()
        if ligne.upper().startswith("TITRE:"):
            titre = ligne[6:].strip()
        elif ligne.upper().startswith("THEMES:"):
            themes_str_ret = ligne[7:].strip()
            themes_proposes = [t.strip() for t in themes_str_ret.split(",") if t.strip()]

    if not themes_proposes:
        themes_proposes = ["Divers"]
    if not titre:
        titre = texte[:50] + "…" if len(texte) > 50 else texte

    return themes_proposes, titre


# ---------------------------------------------------------------------------
# Mode sans clé API — Export / Import markdown
# ---------------------------------------------------------------------------

def generer_prompt_markdown(texte: str, themes_disponibles: list[str],
                             titre_note: str = "") -> tuple[str, str]:
    """
    Génère un fichier markdown contenant le prompt prêt à coller dans claude.ai.

    Retourne :
        (contenu_markdown: str, chemin_fichier: str)
        Le fichier est sauvegardé dans DATA_DIR/exports/
    """
    themes_str = "\n".join(f"- {t}" for t in themes_disponibles)
    horodatage = datetime.now().strftime("%Y%m%d_%H%M%S")

    contenu = f"""# Demande de classification — VoiceNotes

> Copiez l'intégralité de ce fichier et collez-le dans claude.ai pour obtenir la classification.

---

## Thèmes disponibles

{themes_str}

---

## Note à classifier

{texte}

---

## Instructions pour Claude

Analyse la note ci-dessus et réponds avec **exactement deux lignes**, sans rien d'autre :

```
TITRE: un titre court et descriptif (5 à 8 mots)
THEMES: Thème1, Thème2
```

Règles :
1. Utilise les thèmes existants de la liste si possible (orthographe identique).
2. Si aucun thème ne convient, invente un nouveau thème court (2-4 mots).
3. Tu peux associer plusieurs thèmes séparés par des virgules.
4. Ne donne **aucune explication**, uniquement les deux lignes demandées.

Exemple de réponse attendue :
```
TITRE: Réunion projet Urbanloop capsule
THEMES: Réunion, Travail
```
"""

    # Sauvegarde dans DATA_DIR/exports/
    dossier_exports = Path(DATA_DIR) / "exports"
    dossier_exports.mkdir(parents=True, exist_ok=True)
    nom_fichier = f"classification_{horodatage}.md"
    chemin = str(dossier_exports / nom_fichier)

    with open(chemin, "w", encoding="utf-8") as f:
        f.write(contenu)

    print(f"[Classifier] Prompt exporté : {chemin}")
    return contenu, chemin


def parser_reponse_claude(reponse: str) -> tuple[list[str], str]:
    """
    Analyse la réponse collée par l'utilisateur depuis claude.ai.
    Tolère les variations de formatage (majuscules, espaces, tirets…).

    Retourne :
        (themes: list[str], titre: str)
        Si le parsing échoue, retourne (["Divers"], "")
    """
    titre = ""
    themes_proposes = []

    for ligne in reponse.strip().split("\n"):
        ligne_propre = ligne.strip()
        # Supprime les backticks éventuels (si l'utilisateur a copié le bloc code)
        ligne_propre = ligne_propre.strip("`").strip()

        cle = ligne_propre.upper()
        if cle.startswith("TITRE:"):
            titre = ligne_propre[6:].strip()
        elif cle.startswith("THEMES:") or cle.startswith("THÈMES:"):
            # Cherche le ":" dans la ligne originale pour extraire après
            idx = ligne_propre.index(":") + 1
            themes_str = ligne_propre[idx:].strip()
            themes_proposes = [t.strip() for t in themes_str.split(",") if t.strip()]

    if not themes_proposes:
        themes_proposes = ["Divers"]
    if not titre:
        titre = ""

    print(f"[Classifier] Réponse parsée — titre: '{titre}', thèmes: {themes_proposes}")
    return themes_proposes, titre
