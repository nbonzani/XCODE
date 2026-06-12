"""F5 — pré-vol de suppression (LECTURE SEULE, jalon 2/3).

Avant toute purge, on agrège par objet des informations **non destructives** :
- droit de suppression (``check_delete_access``) ;
- options de suppression : suppression logique vs **physique irréversible**,
  disponibilité de la cascade structure/BOM (``get_delete_options``) ;
- nombre d'utilisations amont / where-used (``get_relation_count``).

⚠️ **Aucun appel d'écriture ici.** Tous les endpoints câblés sont des lectures.
Le résultat (:class:`PreflightVerdict`) alimente l'UI de confirmation (J3/J4) :
il NE déclenche aucune suppression. Le dispatch on-prem/cloud suit
``Settings.deployment_mode`` (variantes ``*_cloud`` du moteur).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from threedx_mcp.client.endpoints import lifecycle_delete, navigation
from threedx_mcp.client.session import ThreeDxClient
from threedx_mcp.models.navigation import NavigationItem

from threedx_cleaner.core.document_query import ObjectRow


@dataclass(frozen=True)
class PreflightVerdict:
    """Synthèse pré-vol d'un objet (lecture seule)."""

    key: str
    type: str | None = None
    has_delete_access: bool | None = None
    logical_delete: bool | None = None
    cascade_available: bool = False
    where_used_count: int | None = None
    notes: list[str] = field(default_factory=list)

    @property
    def deletable(self) -> bool:
        """Vrai si le serveur accorde le droit de suppression."""
        return bool(self.has_delete_access)

    @property
    def physical_delete(self) -> bool:
        """Vrai si la suppression serait **physique/irréversible**."""
        return self.logical_delete is False

    @property
    def has_dependents(self) -> bool:
        """Vrai si l'objet a des utilisations amont (where-used > 0)."""
        return bool(self.where_used_count)


def _is_cloud(client: ThreeDxClient) -> bool:
    return getattr(client.settings, "deployment_mode", None) == "cloud"


def _delete_access(client: ThreeDxClient, ids: list[str]) -> dict[str, bool]:
    if _is_cloud(client):
        return lifecycle_delete.check_delete_access_cloud(ids)
    return lifecycle_delete.check_delete_access(client, ids)


def _delete_options(client: ThreeDxClient, ids: list[str]) -> list[dict]:
    if _is_cloud(client):
        return lifecycle_delete.get_delete_options_cloud(client, ids)
    return lifecycle_delete.get_delete_options(client, ids)


def _cascade_available(options_entry: dict) -> bool:
    for opt in options_entry.get("available_options") or []:
        if isinstance(opt, dict) and opt.get("key") == "wholeStructure":
            return True
    return False


def _where_used(client: ThreeDxClient, row: ObjectRow) -> tuple[int | None, str | None]:
    """Compte les relations entrantes d'un objet. Retourne (count, note_erreur)."""
    if not row.physical_id or not row.type:
        return None, "where-used ignoré : type ou physical_id manquant."
    try:
        item = NavigationItem.for_object(row.physical_id, row.type)
        result = navigation.get_relation_count(client, [item])
        return result.where_used_count(), None
    except Exception as exc:  # noqa: BLE001 — non bloquant : info best-effort
        return None, f"where-used indisponible : {type(exc).__name__}: {exc}"


def run_preflight(
    client: ThreeDxClient,
    rows: list[ObjectRow],
    *,
    with_where_used: bool = True,
) -> list[PreflightVerdict]:
    """Exécute le pré-vol (lecture seule) sur un lot d'objets sélectionnés.

    Args:
        client: client 3DEXPERIENCE actif.
        rows: objets sélectionnés (issus de F3).
        with_where_used: si vrai, interroge aussi le where-used (1 appel/objet).

    Returns:
        Un :class:`PreflightVerdict` par objet (ordre d'entrée préservé).
        Les erreurs partielles (accès/options/where-used) sont consignées en
        ``notes`` plutôt que levées — le pré-vol reste informatif et complet.
    """
    verdicts: list[PreflightVerdict] = []
    ids = [r.physical_id for r in rows if r.physical_id]

    # Lectures groupées : droits + options.
    access: dict[str, bool] = {}
    options_by_id: dict[str, dict] = {}
    global_notes: list[str] = []
    if ids:
        try:
            access = _delete_access(client, ids)
        except Exception as exc:  # noqa: BLE001
            global_notes.append(f"checkDeleteAccess indisponible : {type(exc).__name__}: {exc}")
        try:
            for entry in _delete_options(client, ids):
                pid = entry.get("physicalid")
                if pid:
                    options_by_id[pid] = entry
        except Exception as exc:  # noqa: BLE001
            global_notes.append(f"getDeleteOptions indisponible : {type(exc).__name__}: {exc}")

    for row in rows:
        notes = list(global_notes)
        key = row.key
        pid = row.physical_id
        opt = options_by_id.get(pid or "", {})

        wu_count: int | None = None
        if with_where_used:
            wu_count, wu_note = _where_used(client, row)
            if wu_note:
                notes.append(wu_note)

        if pid is None:
            notes.append("Objet sans physical_id : suppression impossible.")

        verdicts.append(
            PreflightVerdict(
                key=key,
                type=row.type or opt.get("type"),
                has_delete_access=access.get(pid) if pid else None,
                logical_delete=opt.get("logical_delete"),
                cascade_available=_cascade_available(opt),
                where_used_count=wu_count,
                notes=notes,
            )
        )
    return verdicts
