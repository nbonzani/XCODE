"""F3 — résolution de la taille de fichier d'un objet (jalon 2, architecture).

⚠️ **Contrat REST non capturé.** La taille n'est pas un prédicat de recherche
et n'est PAS retournée par ``search_advanced``. Elle doit être récupérée via les
métadonnées de fichier physique (FCS / ``GET .../modeler/documents/{id}/files``).
À ce jour cet endpoint n'a été capturé qu'à **vide** (aucun fichier attaché) :
le format exact d'un fichier présent (clé JSON de la taille) reste **inconnu**.
Tant qu'une capture HAR (cf. skill ``har-capture-3dx``) n'a pas confirmé le
contrat, on n'**invente pas** de clé : le résolveur par défaut renvoie ``None``.

Ce module fournit donc :
- :class:`SizeResolver` — protocole enfichable (un résolveur = ``resolve(rows)``).
- :class:`NullSizeResolver` — défaut neutre : laisse toutes les tailles à ``None``.
- :class:`ModelerFilesSizeResolver` — emplacement câblé sur l'endpoint connu,
  mais **désactivé** (lève :class:`SizeContractNotCaptured`) jusqu'à la capture.

L'UI affiche « — » pour une taille ``None`` ; la colonne existe pour être
alimentée sans refonte une fois le contrat validé (jalon 3).
"""

from __future__ import annotations

from typing import Protocol

from threedx_cleaner.core.document_query import ObjectRow


class SizeContractNotCaptured(NotImplementedError):
    """Levée par un résolveur dont le contrat REST n'est pas encore capturé."""


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
    """Résolveur FCS (``.../documents/{id}/files``) — **STUB, non activé**.

    Emplacement réservé pour le câblage réel une fois le contrat capturé. Ne
    PAS deviner la clé de taille : tant que la capture HAR n'a pas confirmé le
    format d'un fichier présent, ``resolve`` lève
    :class:`SizeContractNotCaptured` plutôt que de retourner une valeur fausse.

    Étapes d'activation (jalon 3) :
      1. capturer ``GET /resources/v1/modeler/documents/{id}/files`` sur un
         Document AVEC fichier (skill ``har-capture-3dx``) ;
      2. identifier la clé JSON exacte de la taille dans ``data[].dataelements`` ;
      3. implémenter l'appel par lot + cache ici ;
      4. router l'UI de :class:`NullSizeResolver` vers ce résolveur.
    """

    def __init__(self, client: object) -> None:
        self._client = client

    def resolve(self, rows: list[ObjectRow]) -> dict[str, int | None]:
        raise SizeContractNotCaptured(
            "Contrat REST de taille de fichier non capturé : exécuter la capture "
            "HAR (skill har-capture-3dx) sur un Document avec fichier avant "
            "d'activer ModelerFilesSizeResolver."
        )


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
