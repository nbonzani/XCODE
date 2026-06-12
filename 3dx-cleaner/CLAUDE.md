# CLAUDE.md — projet 3dx-cleaner

> Contexte permanent lu par Claude Code CLI. Court par construction.

## Identité

**Nom** : `3dx-cleaner` (repo + distribution). **Module Python** :
`threedx_cleaner`. **Binaire** : `3dx-cleaner` (gui-script, pas de console).

**Mission** : GUI Windows (PyQt6) pour administrer et **purger des données
3DEXPERIENCE** en contexte pédagogique, de façon contrôlée et traçable.
Couche **GUI + orchestration batch** par-dessus le moteur `threedx_mcp`.

## Socle : moteur threedx_mcp (repo voisin)

`D:\CLAUDE\XCODE\3dx-mcp` (distribution `3dx-mcp` v0.6.0+, module
`threedx_mcp`). Fournit auth (CAS on-prem + OAuth2/PKCE cloud auto-détectée),
dispatch `Settings.deployment_mode`, écriture contrôlée (delete, lifecycle,
reserve). **Installer en editable en dev** : `pip install -e D:\CLAUDE\XCODE\3dx-mcp`.

### Câblage : couche ENDPOINTS, pas tools
On câble `threedx_mcp.client.endpoints.*` + `ThreeDxClient` / `Settings`,
**jamais** les wrappers MCP `tools/*` (qui aplatissent en `{ok,data,summary}`
pour le LLM). Primitives utiles :
- `client.session.ThreeDxClient(settings)` — point HTTP unique.
- `client.endpoints.admin.get_current_user(client)` — who_am_i.
- `endpoints.lifecycle_delete` : `get_delete_options`, `check_delete_access`,
  `delete_objects` (+ variantes `_cloud`). `whole_structure` = cascade BOM.
- `endpoints.lifecycle` : change_maturity, reserve/unreserve.
- `endpoints.search`, `collabspaces`, `documents`, `navigation`, `change`.
- Erreurs typées : hiérarchie `client.errors.ThreeDxError` (motif serveur
  exact par objet → F6).

### Settings en mémoire (linchpin F7)
`Settings` (pydantic-settings) est instanciable par kwargs :
`Settings(_env_file=None, base_url=..., username=..., password=...)`.
Permet de bâtir un client depuis un profil + secret keyring **sans .env sur
disque**. Mode auto-détecté : `base_url` → on_prem ; `tenant_id` → cloud
(exactement un des deux). **Interdiction de réimplémenter une couche HTTP/auth.**

## Périmètre fonctionnel (cf. docs/3dx-cleaner-prompt.md)

F1 purge d'un 3DSpace · F2 purge par propriétaires · F3 sélection fine
(tableau à cases, filtres, **taille**) · F4 normalisation auto pré-suppression
(unreserve + demote In Work) · F5 pré-vol (checkDeleteAccess, locks, where-used,
change control) · F6 rapport post-vol · F7 profils + secrets keyring ·
F8 multi-cible on-prem/cloud.

## Garde-fous (non négociables)

- **Dry-run par défaut** partout ; aucune suppression sans confirm explicite UI.
- **Double confirmation** F1/F2 (récap chiffré + retaper le nom).
- **Jamais de secret en clair** (log, profil, capture). Mot de passe → keyring.
- Suppression 3DX **physique et irréversible** — l'UI doit le rappeler.
- **Traçabilité** : chaque campagne → log horodaté local.

## Conventions code

Python 3.12+, `from __future__ import annotations`, type hints partout,
`pydantic` v2, `requests` (hérité moteur — synchrone ; concurrence via worker
Qt + pool borné), `rich` pour logs. pytest (+ pytest-qt). Mêmes conventions
que `3dx-mcp`.

## Jalons

- **J0** squelette + Settings en mémoire + fenêtre PyQt6 + smoke who_am_i. ← *en cours*
- **J1** F7 (profils %APPDATA% + secrets keyring) + test connexion on-prem/cloud.
- **J2** F3 lecture seule (recherche filtrée + tableau à cases + tailles).
- **J3** F4+F5+F6 sur sélection F3, validés sur objets `MCP_` jetables.
- **J4** F1+F2 (purges massives, double confirmation).
- **J5** packaging PyInstaller + test exécutable autonome.

## Interdits sans permission

`git push`, `git commit -a` · afficher secrets (password, tokens, CASTGC,
csrf, Authorization) · installer un paquet hors `pyproject.toml`.
