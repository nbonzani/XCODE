"""Construction d'un ``Settings`` threedx_mcp **en memoire**.

C'est le pivot technique de F7 : batir un client 3DEXPERIENCE depuis un
profil enregistre + un mot de passe (lu du keyring), **sans ecrire de .env
sur disque** et sans dependre des variables d'environnement ambiantes.

``Settings`` (pydantic-settings) accepte des kwargs d'init prioritaires sur
le .env et l'environnement. On passe ``_env_file=None`` pour neutraliser la
lecture du .env, et on fournit explicitement TOUS les champs discriminant le
mode (``base_url`` / ``tenant_id`` / ``platform_id``) — meme vides — pour
qu'une variable ``THREEDX_*`` ambiante de l'autre mode ne cree pas une
configuration ambigue.
"""

from __future__ import annotations

import os

from threedx_mcp.config import Settings

from threedx_cleaner.models.profile import Profile


def build_settings(profile: Profile, password: str) -> Settings:
    """Construit un ``Settings`` threedx_mcp depuis un profil + mot de passe.

    Args:
        profile: profil de connexion (config non sensible, sans secret).
        password: mot de passe 3DPassport (jamais persiste en clair ;
            provient du keyring ou d'une saisie volatile).

    Returns:
        Un ``Settings`` valide, pret a alimenter ``ThreeDxClient``.

    Raises:
        threedx_mcp.client.errors.ConfigurationError | ValueError:
            si la configuration resultante est invalide.
    """
    if not password:
        raise ValueError("Le mot de passe est requis pour construire un Settings.")

    # Tous les champs de mode sont fournis explicitement (vides si non utilises)
    # pour neutraliser toute variable d'environnement ambiante de l'autre mode.
    kwargs: dict[str, object] = {
        "username": profile.username,
        "password": password,
        "base_url": profile.base_url,
        "tenant_id": profile.tenant_id,
        "platform_id": profile.platform_id,
        "security_context": profile.security_context,
        "verify_ssl": profile.verify_ssl,
        "ca_bundle": profile.ca_bundle,
    }
    # _env_file=None : ne lit aucun .env (secrets jamais sur disque).
    return Settings(_env_file=None, **kwargs)  # type: ignore[arg-type]


def build_settings_from_env() -> Settings:
    """Construit un ``Settings`` depuis les variables d'environnement (smoke jalon 0).

    Lit ``THREEDX_BASE_URL`` (on-prem) ou ``THREEDX_TENANT_ID`` +
    ``THREEDX_PLATFORM_ID`` (cloud), plus ``THREEDX_USERNAME`` /
    ``THREEDX_PASSWORD`` et options. Passe par un :class:`Profile` pour
    valider la coherence du mode, puis reutilise :func:`build_settings`.

    Returns:
        ``Settings`` valide.

    Raises:
        ValueError: variables manquantes ou mode indetermine/ambigu.
    """
    base_url = os.environ.get("THREEDX_BASE_URL", "").strip()
    tenant_id = os.environ.get("THREEDX_TENANT_ID", "").strip()
    platform_id = os.environ.get("THREEDX_PLATFORM_ID", "").strip()
    username = os.environ.get("THREEDX_USERNAME", "").strip()
    password = os.environ.get("THREEDX_PASSWORD", "")

    if not username or not password:
        raise ValueError(
            "THREEDX_USERNAME et THREEDX_PASSWORD doivent etre renseignes "
            "dans l'environnement pour le smoke test."
        )
    if bool(base_url) == bool(tenant_id):
        raise ValueError(
            "Renseigner exactement un mode : THREEDX_BASE_URL (on-prem) OU "
            "THREEDX_TENANT_ID + THREEDX_PLATFORM_ID (cloud)."
        )

    if base_url:
        profile = Profile(
            name="env",
            deployment="on_prem",
            username=username,
            base_url=base_url,
            security_context=os.environ.get("THREEDX_SECURITY_CONTEXT", "").strip(),
        )
    else:
        profile = Profile(
            name="env",
            deployment="cloud",
            username=username,
            tenant_id=tenant_id,
            platform_id=platform_id,
            security_context=os.environ.get("THREEDX_SECURITY_CONTEXT", "").strip(),
        )
    return build_settings(profile, password)
