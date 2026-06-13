"""F3 — résolution de la taille de fichier d'un objet (jalon 3).

La taille n'est pas un prédicat de recherche et n'est PAS retournée par
``search_advanced``. Elle est récupérée via les métadonnées de fichier physique
``GET /resources/v1/modeler/documents/{id}/files`` : chaque entrée ``data[]`` est
un fichier dont ``dataelements.fileSize`` porte la taille en octets (chaîne).

Contrat **capturé live** le 2026-06-13 contre le tenant Polytech R2026x
(cf. ``docs/captures/size-files/analysis.md``). L'endpoint typé côté moteur est
``threedx_mcp.client.endpoints.documents.list_document_files``.

Ce module fournit :
- :class:`SizeResolver` — protocole enfichable (un résolveur = ``resolve(rows)``).
- :class:`NullSizeResolver` — défaut neutre : laisse toutes les tailles à ``None``.
- :class:`ModelerFilesSizeResolver` — résolveur réel câblé sur l'endpoint
  ``files`` (appel par lot + cache, somme des fichiers par Document).

L'UI affiche « — » pour une taille ``None`` (objet sans fichier, type non
documentaire, ou résolution non encore demandée).
"""

from __future__ import annotations

from typing import Protocol

from threedx_cleaner.core.document_query import ObjectRow


class SizeContractNotCaptured(NotImplementedError):
    """Conservée pour compat ascendante (contrat désormais capturé, plus levée)."""


class SizeResolver(Protocol):
    """Résout la taille (octets) d'un lot de lignes.

    Implémentation attendue : retourner un dict ``{row.key: size_bytes|None}``
    pour les clés résolues. Doit être tolérant aux erreurs partielles (un objet
    sans fichier → ``None``, pas une exception).
    """

    def resolve(self, rows: list[ObjectRow]) -> dict[str, int | None]:
        ...


class NullSizeResolver:
    """Résolveur par défaut : ne résout rien (toutes tailles à ``None``).

    Utilisé tant que le contrat REST de taille n'est pas capturé. Permet à l'UI
    d'afficher la colonne « Taille » avec « — » sans appel réseau.
    """

    def resolve(self, rows: list[ObjectRow]) -> dict[str, int | None]:
        return {row.key: None for row in rows if row.key}


class ModelerFilesSizeResolver:
    """Résolveur réel : taille = somme des fichiers physiques d'un Document.

    Appelle ``documents.list_document_files`` (endpoint
    ``GET .../documents/{id}/files``) pour chaque ligne *documentaire* du lot,
    somme les ``size_bytes`` de ses fichiers, et **met en cache** le résultat
    par clé de ligne pour ne pas refaire l'appel entre deux ``resolve``.

    Tolérance aux erreurs : un objet sans fichier (``data[]`` vide), d'un type
    non documentaire, ou dont l'appel échoue → ``None`` (jamais d'exception
    propagée). Seules les lignes dont le type ressemble à un Document sont
    sondées, pour éviter des appels inutiles sur des Parts/Représentations.
    """

    def __init__(self, client: object) -> None:
        self._client = client
        self._cache: dict[str, int | None] = {}

    @staticmethod
    def _is_document(row: ObjectRow) -> bool:
        """Heuristique : ne sonder que les lignes au type documentaire."""
        t = (row.type or "").lower()
        # Type vide → on tente (rare ; l'appel échouera proprement sinon).
        return not t or "document" in t or "drawing" in t

    def _resolve_one(self, physical_id: str) -> int | None:
        """Taille totale (octets) des fichiers d'un Document, ou ``None``."""
        from threedx_mcp.client.endpoints import documents

        try:
            files = documents.list_document_files(self._client, physical_id)
        except Exception:  # noqa: BLE001 — résolution best-effort, jamais bloquante
            return None
        sizes = [f.size_bytes for f in files if f.size_bytes is not None]
        if not sizes:
            return None
        return sum(sizes)

    def resolve(self, rows: list[ObjectRow]) -> dict[str, int | None]:
        out: dict[str, int | None] = {}
        for row in rows:
            key = row.key
            if not key:
                continue
            if key in self._cache:
                out[key] = self._cache[key]
                continue
            if not row.physical_id or not self._is_document(row):
                self._cache[key] = None
                out[key] = None
                continue
            size = self._resolve_one(row.physical_id)
            self._cache[key] = size
            out[key] = size
        return out


def format_size(size_bytes: int | None) -> str:
    """Formate une taille en octets pour l'affichage (« — » si inconnue)."""
    if size_bytes is None:
        return "—"
    if size_bytes < 0:
        return "—"
    units = ("o", "Ko", "Mo", "Go", "To")
    value = float(size_bytes)
    idx = 0
    while value >= 1024 and idx < len(units) - 1:
        value /= 1024
        idx += 1
    if idx == 0:
        return f"{int(value)} {units[idx]}"
    return f"{value:.1f} {units[idx]}"
