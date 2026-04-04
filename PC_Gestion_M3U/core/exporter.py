import csv


def export_m3u(entries: list, filepath: str):
    """Exporte une liste d'entrées au format M3U dans le fichier spécifié."""
    with open(filepath, "w", encoding="utf-8") as f:
        f.write("#EXTM3U\n")
        for entry in entries:
            f.write(entry.get("raw_extinf", "") + "\n")
            f.write(entry.get("url", "") + "\n")


def append_m3u(entries: list, filepath: str):
    """Ajoute une liste d'entrées à la fin d'un fichier M3U existant.
    Si le fichier n'existe pas encore, le crée avec l'entête #EXTM3U."""
    import os
    file_exists = os.path.exists(filepath)
    with open(filepath, "a", encoding="utf-8") as f:
        if not file_exists:
            f.write("#EXTM3U\n")
        for entry in entries:
            f.write(entry.get("raw_extinf", "") + "\n")
            f.write(entry.get("url", "") + "\n")


def export_csv(entries: list, filepath: str):
    """Exporte une liste d'entrées au format CSV (séparateur point-virgule)."""
    with open(filepath, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, delimiter=";")
        writer.writerow(["Nom", "URL"])
        for entry in entries:
            writer.writerow([
                entry.get("name", ""),
                entry.get("url", ""),
            ])
