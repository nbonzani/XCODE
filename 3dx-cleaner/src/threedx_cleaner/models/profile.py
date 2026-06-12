"""Modele ``Profile`` — couple serveur + compte, sans secret.

Le profil porte la configuration **non sensible** (URL/tenant, login,
SecurityContext, options TLS). Le mot de passe n'y figure JAMAIS : il est
stocke a part dans le Windows Credential Manager via ``keyring`` (jalon 1),
et injecte au moment de batir un ``Settings`` (cf.
:mod:`threedx_cleaner.credentials.settings_builder`).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

DeploymentMode = Literal["on_prem", "cloud"]


class Profile(BaseModel):
    """Profil de connexion enregistre (serveur + compte, sans mot de passe).

    Exactement un mode doit etre renseigne :
    - ``on_prem`` : ``base_url`` requis (ex: https://3dx.univ-lorraine.fr).
    - ``cloud``   : ``tenant_id`` + ``platform_id`` requis.
    """

    name: str = Field(..., min_length=1, description="Nom affiche du profil (cle unique).")
    deployment: DeploymentMode = Field(..., description="Mode de deploiement cible.")
    username: str = Field(..., min_length=1, description="Email 3DPassport.")

    # On-prem
    base_url: str = Field(default="", description="URL racine on-prem (mode on_prem).")

    # Cloud
    tenant_id: str = Field(default="", description="Tenant cloud (mode cloud).")
    platform_id: str = Field(default="", description="Identifiant plateforme cloud (mode cloud).")

    # Partages
    security_context: str = Field(
        default="", description="ctx::<role>.<org>.<collabspace> (optionnel)."
    )
    verify_ssl: bool = Field(default=True, description="Verification TLS.")
    ca_bundle: str = Field(default="", description="Chemin d'un bundle CA custom (optionnel).")

    @model_validator(mode="after")
    def _check_mode_fields(self) -> "Profile":
        if self.deployment == "on_prem":
            if not self.base_url.strip():
                raise ValueError("Mode on_prem : 'base_url' est requis.")
            if self.tenant_id or self.platform_id:
                raise ValueError(
                    "Mode on_prem : 'tenant_id'/'platform_id' doivent etre vides."
                )
        else:  # cloud
            if not self.tenant_id.strip() or not self.platform_id.strip():
                raise ValueError(
                    "Mode cloud : 'tenant_id' et 'platform_id' sont requis."
                )
            if self.base_url:
                raise ValueError("Mode cloud : 'base_url' doit etre vide.")
        return self

    @property
    def target_label(self) -> str:
        """Libelle court de la cible (pour l'UI / les logs)."""
        return self.base_url if self.deployment == "on_prem" else self.tenant_id
