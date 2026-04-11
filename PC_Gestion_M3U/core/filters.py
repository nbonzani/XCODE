import re as _re


# Langues européennes : code → liste de mots-clés (2 lettres en premier)
_LANG_CODES = {
    "FR": ["FR", "FRENCH", "FRANCE"],
    "EN": ["EN", "ENGLISH", "UK", "US", "GB"],
    "ES": ["ES", "SPANISH", "ESPANOL", "ESPAGNE"],
    "DE": ["DE", "GERMAN", "DEUTSCH", "ALLEMAND"],
    "IT": ["IT", "ITALIAN", "ITALIANO"],
    "PT": ["PT", "BR", "PORTUGUESE"],
    "NL": ["NL", "DUTCH", "HOLLAND"],
    "PL": ["PL", "POLISH", "POLOGNE"],
    "RO": ["RO", "ROMANIAN", "ROUMANIE"],
    "HU": ["HU", "HUNGARIAN", "HONGRIE"],
    "SE": ["SE", "SWEDISH", "SUEDE"],
    "NO": ["NO", "NORWEGIAN", "NORVEGE"],
    "DK": ["DK", "DANISH", "DANEMARK"],
    "FI": ["FI", "FINNISH", "FINLANDE"],
    "GR": ["GR", "GREEK", "GRECE"],
    "CZ": ["CZ", "CZECH", "TCHEQUE"],
    "BG": ["BG", "BULGARIAN", "BULGARIE"],
    "HR": ["HR", "CROATIAN", "CROATIE"],
    "SK": ["SK", "SLOVAK", "SLOVAQUIE"],
    "RS": ["RS", "SERBIAN", "SERBIE"],
    "AL": ["AL", "ALBANIAN", "ALBANIE"],
    "TR": ["TR", "TURKISH", "TURQUIE"],
    "RU": ["RU", "RUSSIAN", "RUSSIE"],
    "UA": ["UA", "UKRAINIAN", "UKRAINE"],
}


def _lang_keyword_matches(group_original: str, keyword: str) -> bool:
    """
    Vérifie si un mot-clé de langue correspond au groupe (texte original).

    Règles :
    - Code 2 lettres : les lettres doivent être en MAJUSCULES dans le texte
      original et ne pas toucher d'autre lettre (ni avant ni après).
    - Mot long (FRENCH, FRANCE…) : insensible à la casse, ne doit pas toucher
      d'autre lettre.
    """
    if len(keyword) <= 2:
        # Recherche sensible à la casse dans le texte original
        pattern = r'(?<![A-Za-z])' + _re.escape(keyword) + r'(?![A-Za-z])'
        return bool(_re.search(pattern, group_original))
    else:
        # Recherche insensible à la casse
        pattern = r'(?<![A-Za-z])' + _re.escape(keyword) + r'(?![A-Za-z])'
        return bool(_re.search(pattern, group_original, _re.IGNORECASE))


def apply_filters(entries: list, filter_config: dict) -> list:
    """
    Applique un ensemble de filtres sur la liste d'entrées.
    Retourne la liste filtrée.

    filter_config est un dictionnaire avec les clés optionnelles :
      - "content_types" : set de str parmi {"live", "vod", "series"}
                          Si vide ou absent, retourne liste vide.
      - "qualities"     : set de str parmi {"4K","FHD","HD","SD","unknown"}
                          Si vide ou absent, pas de filtre qualité.
      - "groups"        : set de str — catégories cochées (vide = toutes)
      - "lang_keywords" : list de str — mots-clés à chercher dans le group-title
                          pour filtrer par langue (ex: ["FR", "FRENCH", "FRANCE"])
      - "search_text"   : str — texte libre cherché dans le nom
    """
    content_types = filter_config.get("content_types", set())
    if not content_types:
        return []

    results = []
    qualities = filter_config.get("qualities", set())
    groups_filter = filter_config.get("groups", set())
    lang_keywords = filter_config.get("lang_keywords", [])
    search_text = filter_config.get("search_text", "").strip().lower()

    for entry in entries:
        # Filtre type de contenu
        if entry["content_type"] not in content_types:
            continue

        # Filtre qualité
        if qualities and entry["quality"] not in qualities:
            continue

        # Filtre catégories (multi-sélection)
        if groups_filter and entry["group"] not in groups_filter:
            continue

        # Filtre langue (texte original du groupe)
        if lang_keywords:
            group_orig = entry["group"]
            if not any(_lang_keyword_matches(group_orig, kw) for kw in lang_keywords):
                continue

        # Filtre texte libre sur le nom
        if search_text and search_text not in entry["name"].lower():
            continue

        results.append(entry)

    return results


def apply_filters_no_groups(entries: list, filter_config: dict) -> list:
    """Applique tous les filtres SAUF le filtre catégorie.
    Utile pour déterminer les catégories disponibles."""
    content_types = filter_config.get("content_types", set())
    if not content_types:
        return []

    results = []
    qualities = filter_config.get("qualities", set())
    lang_keywords = filter_config.get("lang_keywords", [])
    search_text = filter_config.get("search_text", "").strip().lower()

    for entry in entries:
        if entry["content_type"] not in content_types:
            continue
        if qualities and entry["quality"] not in qualities:
            continue
        if lang_keywords:
            group_orig = entry["group"]
            if not any(_lang_keyword_matches(group_orig, kw) for kw in lang_keywords):
                continue
        if search_text and search_text not in entry["name"].lower():
            continue
        results.append(entry)

    return results


def extract_groups(entries: list) -> list:
    """
    Extrait la liste triée de toutes les valeurs uniques de group-title.
    """
    return sorted(set(e["group"] for e in entries if e["group"]))


def extract_lang_keywords(entries: list) -> list:
    """
    Analyse les group-title pour détecter les langues européennes présentes.

    Règles :
    - Code 2 lettres : doit apparaître en MAJUSCULES dans le texte original
      du groupe, sans toucher d'autre lettre (ni avant ni après).
    - Mot long : insensible à la casse, sans lettre adjacente.

    Retourne la liste triée des codes trouvés.
    """
    found = set()
    unique_groups = set(e["group"] for e in entries if e["group"])

    for group in unique_groups:
        for code, keywords in _LANG_CODES.items():
            for kw in keywords:
                if _lang_keyword_matches(group, kw):
                    found.add(code)
                    break

    return sorted(found)
