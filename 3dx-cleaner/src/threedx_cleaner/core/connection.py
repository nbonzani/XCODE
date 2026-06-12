"""Test de connexion et identite (jalon 0).

Cable la couche **endpoints** du moteur : ``ThreeDxClient`` + ``admin``.
Aucune reimplementation HTTP/auth.
"""

from __future__ import annotations

from dataclasses import dataclass

from threedx_mcp.client.endpoints import admin
from threedx_mcp.client.session import ThreeDxClient
from threedx_mcp.config import Settings


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
    user = admin.get_current_user(client)
    return WhoAmI(
        login=user.login or "",
        internal_id=user.id or "",
        full_name=user.full_name or "",
        email=user.email or "",
        super_user=bool(user.super_user),
        enabled=bool(user.enabled),
        deployment_mode=settings.deployment_mode,
    )
