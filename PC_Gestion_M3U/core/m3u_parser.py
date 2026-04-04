import re

# Mots-clés pour détecter la qualité dans le nom ou le groupe
QUALITY_KEYWORDS = {
    "4K": ["4K", "4k", "UHD", "uhd", "2160"],
    "FHD": ["FHD", "fhd", "1080", "FULLHD", "FullHD", "Full HD"],
    "HD": ["HD", " HD", "720"],
    "SD": ["SD", "sd", "480", "360", "240"],
}

def detect_quality(name: str, group: str) -> str:
    """
    Détecte la qualité vidéo à partir du nom et du groupe.
    Retourne "4K", "FHD", "HD", "SD", ou "unknown".
    """
    text = (name + " " + group).upper()
    if any(k.upper() in text for k in ["4K", "UHD", "2160"]):
        return "4K"
    if any(k.upper() in text for k in ["FHD", "1080", "FULLHD", "FULL HD"]):
        return "FHD"
    if "HD" in text and "FHD" not in text:
        return "HD"
    if any(k.upper() in text for k in ["SD", "480P", "360P", "240P"]):
        return "SD"
    return "unknown"

def detect_content_type(url: str, group: str, name: str) -> str:
    """
    Détecte le type de contenu : "live", "vod" ou "series".
    Priorité 1 : analyse de l'URL (critère le plus fiable).
    Priorité 2 : mots-clés dans le nom du groupe.
    """
    url_lower = url.lower()
    if "/series/" in url_lower:
        return "series"
    if "/movie/" in url_lower:
        return "vod"
    return "live"

def parse_m3u(text: str) -> list:
    """
    Parse un texte M3U complet et retourne une liste de dictionnaires.
    Chaque dictionnaire représente une entrée (chaîne, film ou série).
    """
    entries = []
    lines = text.splitlines()
    current_info = {}

    for line in lines:
        line = line.strip()

        if line.startswith("#EXTINF:"):
            current_info = {}
            # Extraire tous les attributs clé="valeur"
            # Insensible à la casse pour tvg-ID vs tvg-id
            attrs_raw = re.findall(r'([\w-]+)\s*=\s*"([^"]*)"', line, re.IGNORECASE)
            attrs = {k.lower(): v for k, v in attrs_raw}

            # Nom affiché = tout ce qui est après la dernière virgule
            if "," in line:
                display_name = line.rsplit(",", 1)[-1].strip()
            else:
                display_name = attrs.get("tvg-name", "")

            current_info = {
                "name":         display_name,
                "tvg_id":       attrs.get("tvg-id", ""),
                "tvg_name":     attrs.get("tvg-name", display_name),
                "tvg_logo":     attrs.get("tvg-logo", ""),
                "group":        attrs.get("group-title", ""),
                "tvg_chno":     attrs.get("tvg-chno", ""),
                "rating":       attrs.get("rating", ""),
                "raw_extinf":   line,
                "url":          "",
                "content_type": "",
                "quality":      "",
            }

        elif line and not line.startswith("#") and current_info:
            current_info["url"] = line
            current_info["content_type"] = detect_content_type(
                line, current_info["group"], current_info["name"]
            )
            current_info["quality"] = detect_quality(
                current_info["name"], current_info["group"]
            )
            entries.append(current_info)
            current_info = {}

    return entries
