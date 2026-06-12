"""Test de connexion et identite (jalon 0).

Cable la couche **endpoints** du moteur : ``ThreeDxClient`` + ``admin``.
Aucune reimplementation HTTP/auth.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from threedx_mcp.client.endpoints import admin
from threedx_mcp.client.session import ThreeDxClient
from threedx_mcp.config import Settings


@dataclass(frozen=True)
class SecurityContextOption:
    """Un SecurityContext proposable a l'utilisateur (liste deroulante F7).

    ``name`` est l'identifiant brut ``<role>.<org>.<collabspace>`` (sans
    prefixe ``ctx::``, que le moteur ajoute automatiquement). ``title`` est
    le libelle lisible pour l'affichage.
    """

    name: str
    title: str

    def label(self) -> str:
        """Texte d'affichage : titre si present, sinon identifiant brut."""
        return self.title or self.name


@dataclass(frozen=True)
class ConnectionProbe:
    """Resultat d'un test de connexion enrichi : identite + contextes.

    ``contexts_error`` est non nul si la connexion a reussi mais que la
    recuperation des SecurityContexts a echoue (ex. mode cloud non porte) :
    l'UI peut alors confirmer la connexion tout en signalant la liste vide.
    """

    who: WhoAmI
    contexts: list[SecurityContextOption] = field(default_factory=list)
    contexts_error: str | None = None


@dataclass(frozen=True)
class WhoAmI:
    """Resultat lisible d'un test de connexion."""

    login: str
    internal_id: str
    full_name: str
    email: str
    super_user: bool
    enabled: bool
    deployment_mode: str

    def one_line(self) -> str:
        flags = []
        if self.super_user:
            flags.append("super-user")
        if not self.enabled:
            flags.append("DESACTIVE")
        flag_str = f" [{', '.join(flags)}]" if flags else ""
        name = f" ({self.full_name})" if self.full_name and self.full_name != self.login else ""
        email = f", {self.email}" if self.email else ""
        return (
            f"Connecte en tant que '{self.login or '<inconnu>'}'{name} "
            f"(id {self.internal_id or 'N/A'}{email}) sur {self.deployment_mode}{flag_str}."
        )


def _who_am_i_from_client(client: ThreeDxClient, settings: Settings) -> WhoAmI:
    """Construit un :class:`WhoAmI` depuis un client deja authentifie."""
    user = admin.get_current_user(client)
    return WhoAmI(
        login=user.login or "",
        internal_id=str(user.id) if user.id is not None else "",
        full_name=user.full_name or "",
        email=user.email or "",
        super_user=bool(user.super_user),
        enabled=bool(user.enabled),
        deployment_mode=settings.deployment_mode,
    )


def _contexts_from_client(client: ThreeDxClient) -> list[SecurityContextOption]:
    """Recupere et normalise les SecurityContexts disponibles."""
    result = admin.list_security_contexts(client)
    options = [
        SecurityContextOption(name=ctx.name, title=ctx.title or ctx.name)
        for ctx in result.contexts
        if ctx.name
    ]
    # Dedoublonnage en preservant l'ordre serveur.
    seen: set[str] = set()
    unique: list[SecurityContextOption] = []
    for opt in options:
        if opt.name not in seen:
            seen.add(opt.name)
            unique.append(opt)
    return unique


def who_am_i(settings: Settings) -> WhoAmI:
    """Authentifie et retourne l'identite de l'utilisateur courant.

    Args:
        settings: configuration de connexion (cf. settings_builder).

    Returns:
        Un :class:`WhoAmI` decrivant l'utilisateur connecte.

    Raises:
        threedx_mcp.client.errors.ThreeDxError: en cas d'echec d'auth ou reseau.
    """
    client = ThreeDxClient(settings)
    return _who_am_i_from_client(client, settings)


def list_security_contexts(settings: Settings) -> list[SecurityContextOption]:
    """Liste les SecurityContexts visibles par l'utilisateur (apres auth)."""
    client = ThreeDxClient(settings)
    return _contexts_from_client(client)


def probe(settings: Settings) -> ConnectionProbe:
    """Teste la connexion et recupere identite + SecurityContexts.

    Un **seul** :class:`ThreeDxClient` est cree (une seule authentification)
    pour enchainer who_am_i puis la liste des contextes. Si la connexion
    reussit mais que la recuperation des contextes echoue, on retourne quand
    meme l'identite avec ``contexts_error`` renseigne (liste vide) — l'echec
    d'auth/reseau, lui, se propage en exception.

    Args:
        settings: configuration de connexion.

    Returns:
        Un :class:`ConnectionProbe` (identite + contextes + erreur eventuelle).

    Raises:
        threedx_mcp.client.errors.ThreeDxError: echec d'auth ou reseau.
    """
    client = ThreeDxClient(settings)
    who = _who_am_i_from_client(client, settings)
    try:
        contexts = _contexts_from_client(client)
        return ConnectionProbe(who=who, contexts=contexts)
    except Exception as exc:  # noqa: BLE001 — non bloquant : connexion deja OK
        return ConnectionProbe(
            who=who, contexts=[], contexts_error=f"{type(exc).__name__}: {exc}"
        )
