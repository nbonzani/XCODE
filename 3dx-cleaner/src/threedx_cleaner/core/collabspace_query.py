"""F3 — listing des collaborative spaces (lecture seule, jalon 2).

Câble ``endpoints.collabspaces.list_collabspaces`` pour alimenter le filtre
« collabspace » du panneau de recherche. Pagination suivie jusqu'à épuisement
(borne dure de sécurité).
"""

from __future__ import annotations

from threedx_mcp.client.endpoints import collabspaces
from threedx_mcp.client.session import ThreeDxClient

#: Borne dure du nombre de collabspaces rapatriés (garde-fou).
MAX_SPACES = 500


def list_space_names(client: ThreeDxClient, *, page_size: int = 50) -> list[str]:
    """Retourne les noms techniques des collabspaces accessibles (triés).

    Args:
        client: client 3DEXPERIENCE actif.
        page_size: taille de page serveur.

    Returns:
        Liste dédoublonnée et triée des ``name`` de collabspaces.

    Raises:
        threedx_mcp.client.errors.ThreeDxError: erreur d'auth/transport/métier.
    """
    names: list[str] = []
    seen: set[str] = set()
    page = 0
    while len(names) < MAX_SPACES:
        result = collabspaces.list_collabspaces(
            client, page=page, limit=page_size
        )
        for space in result.items:
            name = getattr(space, "name", None)
            if name and name not in seen:
                seen.add(name)
                names.append(name)
        nb_pages = getattr(result, "nb_pages", 0) or 0
        if page + 1 >= nb_pages or not result.items:
            break
        page += 1
    return sorted(names)
