# HANDOFF — 3dx-cleaner

> État de passation pour reprise en nouvelle session. Dernière mise à jour :
> 2026-06-13, fin du **jalon 0**.

## 1. Ce qu'est le projet

GUI Windows **PyQt6** pour **purger des données 3DEXPERIENCE** en contexte
pédagogique, de façon contrôlée et traçable. Couche **GUI + orchestration
batch** par-dessus le moteur `threedx_mcp`. Cahier des charges complet
(F1–F8) : `D:\CLAUDE\XCODE\3dx-mcp\docs\3dx-cleaner-prompt.md`.

- Module Python : `threedx_cleaner` · distribution : `3dx-cleaner` ·
  binaire : `3dx-cleaner` (gui-script, pas de console).
- Repo : `D:\CLAUDE\XCODE\3dx-cleaner` (git, branche `main`, **0 commit** —
  rien n'est encore commité).

## 2. Décisions d'architecture arrêtées (ne pas rediscuter)

1. **Câblage sur la couche ENDPOINTS du moteur**, pas les wrappers MCP
   `tools/*`. On appelle `threedx_mcp.client.endpoints.*` +
   `ThreeDxClient` / `Settings`. Raison : objets pydantic typés, motif
   serveur exact par objet (erreurs `ThreeDxError`), gating dry-run/confirm
   piloté par l'UI. Les `tools/*` aplatissent en `{ok,data,summary}` pour le
   LLM — inadaptés à un batch GUI.
2. **Moteur = prérequis editable, PAS une dépendance pip.** Son nom de
   distribution varie selon le clone (`3dx-mcp` / `threedx-mcp-gdt` /
   `threedx-mcp-gdt-cloud`) et n'est sur aucun index. Présence vérifiée à
   l'import (`__main__.main`). PyInstaller l'embarquera (jalon 5).
3. **Env de dev = `.venv` interne au projet** (`D:\CLAUDE\XCODE\3dx-cleaner\.venv`,
   gitignoré), avec le moteur local `D:\CLAUDE\XCODE\3dx-mcp` (v0.6.0)
   installé editable dedans. But : projet autonome + ne PAS écraser les
   entry points MCP de l'env global utilisés par Claude Desktop/Code.
   *(Un venv ne se déplace pas — le recréer si besoin.)*
4. **Pivot technique F7** : `Settings` construit **en mémoire** par kwargs
   (`Settings(_env_file=None, ...)`), tous les champs de mode fournis
   explicitement pour neutraliser un `THREEDX_*` ambiant. Aucun secret sur
   disque ; mot de passe via `keyring` (à venir, jalon 1).
5. Stack : Python 3.12+, `from __future__ import annotations`, type hints
   partout, pydantic v2, `requests` (hérité moteur, synchrone → concurrence
   via worker Qt + pool borné), `rich`. pytest + pytest-qt.

## 3. Briques moteur déjà repérées (à câbler, pas réécrire)

| Besoin | Endpoint `threedx_mcp` |
|---|---|
| Identité / who_am_i | `client.endpoints.admin.get_current_user(client)` |
| Recherche filtrée (owner, status, dates, project) | `endpoints.search` (`dx_advanced_search` côté tools) |
| Lister spaces / metadata | `endpoints.collabspaces` |
| Lister documents / drawings | `endpoints.documents` |
| Suppression (cascade BOM) | `endpoints.lifecycle_delete` : `get_delete_options`, `check_delete_access`, `delete_objects` (+ `_cloud`), clé `wholeStructure` |
| Normalisation (unreserve, demote) | `endpoints.lifecycle` (change_maturity, reserve/unreserve) |
| Pré-vol where-used / change control | `endpoints.navigation`, `endpoints.change` |
| Attributs riches | `endpoints.attributes` / `read_attributes` |
| Erreurs typées | `client.errors.ThreeDxError` (Auth/Authorization/Validation/Conflict/NotFound/Server…) |

Écarts à instrumenter (n'existent pas tels quels dans le moteur, cf. prompt §
« Points à instrumenter ») : **taille des fichiers** (pas un prédicat de
recherche → FCS / `documents/{id}/files`, service `DocumentSizeResolver` à
créer, vérifier le contrat REST / capture HAR via skill `har-capture-3dx`),
**énumération exhaustive paginée d'un space**, **orchestrateur batch**,
**pré-vol where-used/change-control**.

## 4. État du code (jalon 0 — FAIT)

```
3dx-cleaner/
├── pyproject.toml          # deps PyQt6/keyring/pydantic/rich ; moteur en commentaire (prérequis)
├── .gitignore              # secrets, .venv, profiles.toml, logs de purge
├── README.md  CLAUDE.md  HANDOFF.md
├── src/threedx_cleaner/
│   ├── __init__.py         # __version__
│   ├── __main__.py         # main() : garde import moteur + lance QApplication
│   ├── models/profile.py   # Profile (pydantic) : mode on_prem/cloud validé
│   ├── credentials/
│   │   ├── settings_builder.py   # build_settings(profile, pwd) + build_settings_from_env()  ← PIVOT
│   │   ├── profile_store.py      # STUB jalon 1 (profils %APPDATA%)
│   │   └── secret_store.py       # STUB jalon 1 (keyring)
│   ├── core/connection.py  # who_am_i(settings) -> WhoAmI (couche endpoints)
│   └── ui/main_window.py   # fenêtre + bouton « Tester la connexion » en QThread worker
└── tests/                  # test_profile.py, test_settings_builder.py — 10 tests verts
```

`core/` contient aussi des stubs prévus pour les jalons suivants (cf.
`core/__init__.py` : document_query, normalize, preflight, executor, report,
space_purge, owner_purge).

**Vérifié** : `pytest -q` → 10/10 ; import chain OK ; fenêtre s'instancie
(offscreen) ; moteur résolu sur `D:\CLAUDE\XCODE\3dx-mcp\src\threedx_mcp`.
**NON vérifié** : smoke test d'**auth live** (nécessite identifiants réels +
réseau Polytech où le tenant on-prem résout).

## 5. Lancer / tester

```powershell
cd D:\CLAUDE\XCODE\3dx-cleaner
.\.venv\Scripts\Activate.ps1
pytest -q                                   # tests unitaires

# Smoke test connexion live (à faire) :
$env:THREEDX_BASE_URL = "https://3dexperience2025.univ-lorraine.fr"
$env:THREEDX_USERNAME = "prenom.nom@univ-lorraine.fr"
$env:THREEDX_PASSWORD = "..."
3dx-cleaner                                  # → bouton « Tester la connexion »
```

## 6. Garde-fous (non négociables)

- **Dry-run par défaut** partout ; aucune suppression sans confirm explicite UI.
- **Double confirmation** F1/F2 (récap chiffré + retaper le nom du space).
- **Jamais de secret en clair** (log, profil, capture) → mot de passe keyring.
- Suppression 3DX **physique et irréversible** (pas de corbeille) — l'UI doit
  le rappeler sans ambiguïté.
- **Traçabilité** : chaque campagne de purge → log horodaté local.
- Interdits sans permission : `git push`, `git commit -a`, afficher des
  secrets, installer un paquet hors `pyproject.toml`.

## 7. Prochaine étape — JALON 1 (F7)

Gestion des identifiants multi-comptes/multi-serveurs :
- `credentials/profile_store.py` : CRUD de profils `Profile` en TOML sous
  `%APPDATA%/3dx-cleaner/profiles.toml` (config NON sensible uniquement).
- `credentials/secret_store.py` : mot de passe via `keyring` (service
  `3dx-cleaner`, username = `Profile.name`). Jamais en clair.
- `ui/profile_dialog.py` : ajout/édition/suppression/**test de connexion**
  d'un profil (réutilise `core.connection.who_am_i` + `build_settings`).
- `ui/main_window.py` : sélecteur de profil au lancement.
- Tests : profile_store (round-trip TOML), secret_store (keyring mocké).
- Critère de sortie : test de connexion OK sur un profil **on-prem** et un
  profil **cloud**.

Jalons suivants : J2 = F3 (recherche filtrée + tableau à cases + tailles,
lecture seule) · J3 = F4+F5+F6 (normalisation, pré-vol, exécuteur batch,
rapport) sur objets `MCP_` jetables · J4 = F1+F2 (purges massives, double
confirmation) · J5 = packaging PyInstaller.
