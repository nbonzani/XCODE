# HANDOFF — 3dx-cleaner

> État de passation pour reprise en nouvelle session. Dernière mise à jour :
> 2026-06-13, **code des jalons 1 et 2 terminé** (validation live restante).

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

## 7. JALON 1 (F7) — CODE FAIT, validation live restante

Gestion des identifiants multi-comptes/multi-serveurs. Implémenté :
- `credentials/secret_store.py` : `set/get/delete/has_password` via `keyring`
  (service `3dx-cleaner`, username = `Profile.name`). Jamais de secret loggé.
- `credentials/profile_store.py` : CRUD TOML (`tomllib` + **`tomli-w`**, nouvelle
  dép. ajoutée à pyproject) sous `%APPDATA%/3dx-cleaner/profiles.toml`, dossier
  surchargé par `THREEDX_CONFIG_DIR` (testable). Écriture atomique. `delete`
  purge aussi le secret keyring.
- `ui/profile_dialog.py` : dialogue CRUD + **test de connexion** en `QThread`.
  Mot de passe masqué, jamais persisté en clair ; champ vide à l'édition =
  secret inchangé ; renommage migre le secret. Le **security_context est une
  liste déroulante** peuplée après le test de connexion (cf. `connection.probe`)
  — éditable (saisie libre préservée), tooltip = libellé du contexte.
- `core/connection.py` : `probe(settings)` (1 seul client → who_am_i +
  `list_security_contexts`, dédoublonné) ; échec des contextes non bloquant
  (`ConnectionProbe.contexts_error`, ex. cloud non porté). Câble
  `admin.list_security_contexts` (on-prem `getallctx`, fallback dgn/adm).
- `ui/main_window.py` : sélecteur de profil (combo) + bouton « Gérer les
  profils » ; le test bascule de l'env vers `build_settings(profil, keyring)`.
- Tests : `test_secret_store.py` + `test_profile_store.py` + `conftest.py`
  (backend keyring en mémoire `InMemoryKeyring`, isolation `config_dir`).

**Vérifié** : `pytest -q` → 23/23 ; UI s'instancie offscreen (MainWindow +
ProfileDialog). **NON vérifié** (= critère de sortie) : test de connexion live
réussi sur un profil **on-prem** ET un profil **cloud** depuis l'UI (nécessite
identifiants réels + réseau Polytech / accès cloud).

## 8. JALON 2 (F3 lecture seule) — CODE FAIT, validation live restante

Recherche filtrée + tableau à cases + pagination. Implémenté :
- `core/document_query.py` : `search_page` / `search_all` (énumération paginée
  bornée `MAX_ENUMERATION=5000`, anti-boucle sur curseur répété) câblé sur
  `endpoints.search.search_advanced`. Filtres : texte/UQL, types, owner,
  maturité, dates modifié, **collabspace** (clause `[ds6w:collabspace]` —
  prédicat ds6w standard, **à confirmer sur le tenant** au test live).
  Modèle `ObjectRow` (taille = `None` à ce stade).
- `core/collabspace_query.py` : `list_space_names` (pagination) pour alimenter
  le filtre collabspace.
- `core/size_resolver.py` : **architecture taille** — `SizeResolver` (protocole),
  `NullSizeResolver` (défaut, tout à `None`), `ModelerFilesSizeResolver` (**STUB
  qui lève `SizeContractNotCaptured`**). ⚠️ **Contrat REST de taille NON capturé**
  (endpoint `/files` vu seulement à vide) → à faire en J3 via skill
  `har-capture-3dx` sur un Document AVEC fichier, puis activer le résolveur.
  `format_size()` pour l'affichage (« — » si inconnue).
- `ui/search_panel.py` : `SearchPanel` (QWidget) — formulaire de filtres,
  `QTableWidget` à cases (colonnes Type/Identifiant/Titre/Rév/Statut/Propriétaire/
  Modifié/**Taille**), pagination « Charger la suite », « Tout énumérer »,
  cocher/décocher, récap sélection. **Lecture seule** (aucune action d'écriture).
  `selected_rows()` expose la sélection pour J3/J4. Recherche en `QThread`.
- `ui/main_window.py` : bouton « Explorer les objets… » → ouvre `SearchPanel`
  dans une fenêtre, à partir du profil sélectionné + secret keyring.

**Vérifié** : `pytest -q` → 47/47 ; panneau instancié offscreen (append/sélection/
format taille OK). **NON vérifié** (réseau requis) : recherche live, pertinence
du prédicat collabspace sur le tenant, format réel de la taille (non câblé).

Jalons suivants : J3 = F4+F5+F6 (normalisation, pré-vol, exécuteur batch,
rapport) sur objets `MCP_` jetables — **inclut la capture HAR taille** et
l'activation de `ModelerFilesSizeResolver` · J4 = F1+F2 (purges massives, double
confirmation) · J5 = packaging PyInstaller.
