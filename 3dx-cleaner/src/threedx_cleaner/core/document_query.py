"""F3 — recherche filtrée d'objets 3DEXPERIENCE (lecture seule, jalon 2).

Câble la couche **endpoints** du moteur (``endpoints.search.search_advanced``)
pour produire des lignes normalisées affichables dans un tableau à cases. Gère
la pagination (un *batch* à la fois) et l'énumération exhaustive bornée.

La **taille de fichier** n'est PAS un prédicat de recherche et n'est pas
retournée par ``search_advanced`` : elle est laissée à ``None`` ici et résolue
séparément, à la demande, par un :class:`~threedx_cleaner.core.size_resolver.SizeResolver`
(contrat REST ``/files`` capturé — cf. ``size_resolver`` et
``docs/captures/size-files/analysis.md``).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from threedx_mcp.client.endpoints import search
from threedx_mcp.client.session import ThreeDxClient

#: Borne dure de l'énumération exhaustive (garde-fou anti-emballement).
MAX_ENUMERATION = 5000

#: Prédicat 3DSearch standard pour le collaborative space (filtre optionnel).
#: Attribut ds6w standard ; à confirmer sur le tenant cible lors du test live.
_COLLABSPACE_PREDICATE = "ds6w:collabspace"


@dataclass(frozen=True)
class ObjectRow:
    """Ligne normalisée d'un objet PLM pour le tableau de sélection (F3).

    ``size_bytes`` vaut ``None`` tant qu'aucun :class:`SizeResolver` ne l'a
    renseignée (contrat REST de taille non encore câblé — cf. module).
    """

    physical_id: str | None
    identifier: str | None
    type: str | None
    title: str | None
    revision: str | None
    status: str | None
    owner: str | None
    modified: str | None
    organization: str | None
    project: str | None
    size_bytes: int | None = None

    @property
    def key(self) -> str:
        """Clé d'identification stable (physical_id sinon identifier)."""
        return self.physical_id or self.identifier or ""


def _quote(value: str) -> str:
    """Échappe une valeur pour une clause UQL entre guillemets."""
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _or_clause(predicate: str, values: list[str] | None) -> list[str]:
    """Construit ``[('[pred]:"a" OR [pred]:"b")')]`` pour une multi-sélection."""
    vals = [v for v in (values or []) if v]
    if not vals:
        return []
    terms = " OR ".join(f'[{predicate}]:"{_quote(v)}"' for v in vals)
    return [f"({terms})" if len(vals) > 1 else terms]


@dataclass(frozen=True)
class SearchFilters:
    """Critères de recherche F3 (tous optionnels, combinés en AND côté moteur).

    ``types`` / ``owners`` / ``maturities`` / ``collabspaces`` acceptent
    **plusieurs valeurs** (multi-sélection) : chacune est étendue en groupe
    ``OR`` ; les groupes sont combinés en ``AND``.
    """

    query: str = "*"
    types: list[str] | None = None
    owners: list[str] | None = None
    maturities: list[str] | None = None
    collabspaces: list[str] | None = None
    modified_after: str | None = None
    modified_before: str | None = None
    page_size: int = 50

    def _extra_clauses(self) -> list[str] | None:
        clauses: list[str] = []
        clauses += _or_clause("owner", self.owners)
        clauses += _or_clause("ds6w:status", self.maturities)
        clauses += _or_clause(_COLLABSPACE_PREDICATE, self.collabspaces)
        return clauses or None


@dataclass(frozen=True)
class SearchPage:
    """Un *batch* de résultats + curseur de pagination."""

    rows: list[ObjectRow] = field(default_factory=list)
    nmatches: int = 0
    next_start: str | None = None
    truncated: bool = False
    query: str = ""


def _row_from_hit(hit: object) -> ObjectRow:
    """Convertit un ``AdvancedSearchHit`` en :class:`ObjectRow`."""
    g = lambda name: getattr(hit, name, None)  # noqa: E731 — accès défensif court
    return ObjectRow(
        physical_id=g("physical_id"),
        identifier=g("identifier"),
        type=g("type"),
        title=g("title"),
        revision=g("revision"),
        status=g("status"),
        owner=g("owner"),
        modified=g("modified"),
        organization=g("organization"),
        project=g("project"),
    )


def search_page(
    client: ThreeDxClient,
    filters: SearchFilters,
    *,
    start: int | str = 0,
) -> SearchPage:
    """Exécute un *batch* de recherche filtrée et retourne une page normalisée.

    Args:
        client: client 3DEXPERIENCE actif (couche endpoints).
        filters: critères F3.
        start: offset (0) ou curseur opaque ``next_start`` d'une page précédente.

    Returns:
        Un :class:`SearchPage` (lignes + curseur + total serveur).

    Raises:
        threedx_mcp.client.errors.ThreeDxError: erreur d'auth/transport/métier.
    """
    # owner / maturity / collabspace multi-valeurs passent par extra_clauses
    # (groupes OR) ; types reste géré nativement par search_advanced.
    result = search.search_advanced(
        client,
        query=filters.query or "*",
        types=filters.types,
        owner=None,
        maturity=None,
        modified_after=filters.modified_after,
        modified_before=filters.modified_before,
        extra_clauses=filters._extra_clauses(),
        limit=filters.page_size,
        start=start,  # type: ignore[arg-type] — le moteur sérialise le curseur opaque
    )
    rows = [_row_from_hit(h) for h in result.hits]
    return SearchPage(
        rows=rows,
        nmatches=result.nmatches,
        next_start=result.next_start,
        truncated=result.truncated,
        query=result.query,
    )


def search_all(
    client: ThreeDxClient,
    filters: SearchFilters,
    *,
    max_objects: int = MAX_ENUMERATION,
) -> SearchPage:
    """Énumère **toutes** les pages jusqu'à épuisement ou borne ``max_objects``.

    Suit le curseur ``next_start`` tant qu'il progresse. S'arrête à
    ``max_objects`` (garde-fou) en marquant ``truncated=True`` si le serveur
    annonce davantage de matches.

    Args:
        client: client 3DEXPERIENCE actif.
        filters: critères F3.
        max_objects: nombre maximal d'objets à rapatrier (borne dure).

    Returns:
        Un :class:`SearchPage` agrégé (curseur final éventuel conservé).
    """
    all_rows: list[ObjectRow] = []
    seen_cursors: set[str] = set()
    cursor: int | str = 0
    nmatches = 0
    last_cursor: str | None = None

    while len(all_rows) < max_objects:
        page = search_page(client, filters, start=cursor)
        nmatches = page.nmatches
        all_rows.extend(page.rows)
        last_cursor = page.next_start
        # Fin : pas de curseur, curseur inchangé, ou batch vide.
        if not page.next_start or page.next_start in seen_cursors or not page.rows:
            last_cursor = None
            break
        seen_cursors.add(page.next_start)
        cursor = page.next_start

    truncated = len(all_rows) < nmatches
    return SearchPage(
        rows=all_rows[:max_objects],
        nmatches=nmatches,
        next_start=last_cursor,
        truncated=truncated,
        query=filters.query or "*",
    )
