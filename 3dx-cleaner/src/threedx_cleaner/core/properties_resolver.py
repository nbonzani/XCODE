"""F3 — résolution des propriétés riches d'un objet (maturité + verrouillage).

La **maturité** (état du cycle de vie) et l'état de **verrouillage** (réservation)
ne sont pas toujours fiables via la recherche fédérée (``ds6w:status`` peut ne
pas remonter selon le tenant). On les récupère de façon robuste via les attributs
riches ``collabServices/attributes/op/read`` (``read_attributes``, **appel par
lot** : un seul appel pour toute la page) :

- **maturité** ← ``basicData.current`` (NLS, ex. « En traitement », « Validé ») —
  source documentée et fiable côté moteur ;
- **verrouillage** ← attributs candidats (``reserved`` / ``reservedby`` /
  ``locker`` / ``ds6w:reservedby``), sondés défensivement. ⚠️ Présence selon le
  tenant ; si absent → ``None`` (« — »), **sans rien inventer**.

Sémantique de :class:`PropInfo.lock` → ``locker | "" | None`` :
- chaîne non vide  → réservé (login/nom du verrouilleur, sinon ``"?"``) ;
- ``""``            → confirmé non réservé (libre) ;
- ``None`` / absent → inconnu (champ non exposé / erreur / non sondé).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from threedx_cleaner.core.document_query import ObjectRow

#: Nom d'attribut ``basicData`` portant la maturité (état lifecycle courant).
_MATURITY_NAMES = ("current",)
#: Noms d'attributs candidats portant l'état de réservation (sondés en lecture).
_RESERVED_FLAG_NAMES = ("reserved",)
_LOCKER_NAMES = ("reservedby", "ds6w:reservedby", "locker", "reservedBy")


@dataclass(frozen=True)
class PropInfo:
    """Propriétés résolues d'un objet (maturité + verrouillage)."""

    maturity: str | None = None
    lock: str | None = None


class PropertiesResolver(Protocol):
    """Résout maturité + verrouillage d'un lot de lignes.

    Retourne ``{row.key: PropInfo}``. Doit tolérer les erreurs partielles
    (un objet → ``PropInfo()`` vide, jamais d'exception propagée).
    """

    def resolve(self, rows: list[ObjectRow]) -> dict[str, PropInfo]:
        ...


class NullPropertiesResolver:
    """Résolveur neutre : maturité et verrouillage inconnus pour tout le monde."""

    def resolve(self, rows: list[ObjectRow]) -> dict[str, PropInfo]:
        return {row.key: PropInfo() for row in rows if row.key}


def _truthy(value: str) -> bool:
    return value.strip().lower() in {"true", "1", "yes", "oui"}


class ReadAttributesPropertiesResolver:
    """Résolveur réel : maturité + verrouillage via ``read_attributes`` (par lot).

    Un seul appel réseau pour l'ensemble des ``physical_id`` d'une page, puis
    extraction par objet. Résultat **mis en cache** par clé de ligne.
    """

    def __init__(self, client: object) -> None:
        self._client = client
        self._cache: dict[str, PropInfo] = {}

    @staticmethod
    def _values(obj: object, names: tuple[str, ...]) -> list[str] | None:
        """Cherche un attribut (basicData puis data) parmi ``names``."""
        for name in names:
            for getter_name in ("basic_by_name", "attribute_by_name"):
                getter = getattr(obj, getter_name, None)
                if callable(getter):
                    entry = getter(name)
                    if entry is not None:
                        return list(getattr(entry, "value", []) or [])
        return None

    @classmethod
    def _maturity(cls, obj: object) -> str | None:
        vals = cls._values(obj, _MATURITY_NAMES)
        if vals:
            first = vals[0].strip()
            return first or None
        return None

    @classmethod
    def _lock(cls, obj: object) -> str | None:
        locker_vals = cls._values(obj, _LOCKER_NAMES)
        flag_vals = cls._values(obj, _RESERVED_FLAG_NAMES)
        if locker_vals is None and flag_vals is None:
            return None  # champ non exposé → inconnu
        if locker_vals:
            first = locker_vals[0].strip()
            if first:
                return first
        if flag_vals:
            return "?" if _truthy(flag_vals[0]) else ""
        return ""  # liste verrouilleur présente mais vide → libre

    def _resolve_batch(self, ids: list[str]) -> dict[str, PropInfo]:
        from threedx_mcp.client.endpoints import attributes

        try:
            result = attributes.read_attributes(self._client, ids)
        except Exception:  # noqa: BLE001 — best-effort, jamais bloquant
            return {i: PropInfo() for i in ids}
        out: dict[str, PropInfo] = {i: PropInfo() for i in ids}
        for obj in getattr(result, "results", []) or []:
            pid = getattr(obj, "physical_id", None)
            if pid:
                out[pid] = PropInfo(maturity=self._maturity(obj), lock=self._lock(obj))
        return out

    def resolve(self, rows: list[ObjectRow]) -> dict[str, PropInfo]:
        out: dict[str, PropInfo] = {}
        to_fetch: list[str] = []
        key_by_pid: dict[str, str] = {}
        for row in rows:
            key = row.key
            if not key:
                continue
            if key in self._cache:
                out[key] = self._cache[key]
            elif row.physical_id:
                to_fetch.append(row.physical_id)
                key_by_pid[row.physical_id] = key
            else:
                self._cache[key] = PropInfo()
                out[key] = PropInfo()

        if to_fetch:
            resolved = self._resolve_batch(to_fetch)
            for pid, info in resolved.items():
                key = key_by_pid.get(pid, pid)
                self._cache[key] = info
                out[key] = info
        return out


def format_lock(state: str | None) -> str:
    """Formate l'état de verrouillage pour l'affichage."""
    if state is None:
        return "—"
    if state == "":
        return "Libre"
    if state == "?":
        return "Verrouillé"
    return f"Verrouillé — {state}"
