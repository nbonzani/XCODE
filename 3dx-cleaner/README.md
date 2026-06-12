# 3dx-cleaner

Application de bureau Windows (PyQt6) pour **administrer et purger des données
sur 3DEXPERIENCE** dans un cadre pédagogique, de façon contrôlée et traçable.

`3dx-cleaner` est une **couche GUI + orchestration batch** par-dessus le moteur
[`3dx-mcp`](../3dx-mcp) (package Python `threedx_mcp`), qui fournit
l'authentification (CAS on-prem + OAuth2/PKCE cloud, auto-détectée), le dispatch
on-prem/cloud et les opérations d'écriture contrôlée. **Aucune couche
HTTP/auth n'est réimplémentée ici.**

## Architecture (résumé)

`3dx-cleaner` câble la **couche endpoints** du moteur
(`threedx_mcp.client.endpoints.*` + `ThreeDxClient` / `Settings`), pas les
wrappers MCP `tools/*` — pour disposer d'objets pydantic typés, du motif
serveur exact par objet (erreurs `ThreeDxError`) et d'un gating dry-run/confirm
piloté par l'UI.

```
src/threedx_cleaner/
├── core/          # orchestration batch (purge, normalisation, pré-vol, rapport)
├── credentials/   # profils (%APPDATA%) + secrets (Windows Credential Manager)
├── models/        # pydantic v2 : Profile, DocRow, Job, Outcome
└── ui/            # PyQt6
```

## Installation (développement)

Environnement isolé dans `.venv` **interne au projet**. Le moteur n'est pas
publié sur un index : l'installer en editable **avant** ce projet.

```powershell
cd D:\CLAUDE\XCODE\3dx-cleaner
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e D:\CLAUDE\XCODE\3dx-mcp   # moteur (prérequis)
pip install -e .[dev]                    # 3dx-cleaner + outils de test
```

## Lancement

```powershell
3dx-cleaner
# ou
python -m threedx_cleaner
```

## Smoke test (jalon 0)

Le bouton « Tester la connexion » lit les variables d'environnement, construit
un `Settings` **en mémoire** (aucun secret sur disque) et affiche l'utilisateur
connecté (`who_am_i`).

```powershell
$env:THREEDX_BASE_URL  = "https://3dexperience2025.univ-lorraine.fr"   # on-prem
$env:THREEDX_USERNAME  = "prenom.nom@univ-lorraine.fr"
$env:THREEDX_PASSWORD  = "..."
3dx-cleaner
```

## Garde-fous (non négociables)

- **Dry-run par défaut** partout ; aucune suppression sans confirmation explicite.
- **Double confirmation** pour les purges massives (F1/F2).
- **Jamais de secret en clair** (ni log, ni fichier de profil) — mots de passe
  dans le Windows Credential Manager via `keyring`.
- La suppression 3DX est **physique et irréversible** (pas de corbeille).
- **Traçabilité** : chaque campagne produit un log horodaté local.
