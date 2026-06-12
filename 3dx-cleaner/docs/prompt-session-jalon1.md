# Prompt de lancement — session jalon 1 (3dx-cleaner)

> À copier comme **premier message** d'une nouvelle session Claude Code ouverte
> dans `D:\CLAUDE\XCODE\3dx-cleaner`.

---

Tu reprends le développement de **`3dx-cleaner`** (GUI PyQt6 de purge contrôlée
de données 3DEXPERIENCE, usage pédagogique), couche GUI + orchestration batch
par-dessus le moteur `threedx_mcp` (`D:\CLAUDE\XCODE\3dx-mcp`, v0.6.0).

**Avant de coder, lis `HANDOFF.md` à la racine du projet** : il contient l'état
complet (jalon 0 fait), les décisions d'architecture arrêtées, l'environnement
de dev, les briques moteur repérées et les garde-fous. Lis aussi `CLAUDE.md`.

## Contexte essentiel (résumé — détails dans HANDOFF.md)

- **Câblage couche endpoints** du moteur (`threedx_mcp.client.endpoints.*` +
  `ThreeDxClient` / `Settings`), jamais les wrappers MCP `tools/*`.
- **Env** : `.venv` interne au projet, moteur local editable dedans. Activer
  `.\.venv\Scripts\Activate.ps1`. Jalon 0 : 10 tests verts.
- **Pivot déjà en place** : `credentials/settings_builder.build_settings(profile,
  password)` construit un `Settings` en mémoire (aucun secret sur disque).
- **Garde-fous** : dry-run par défaut, jamais de secret en clair, suppression
  3DX irréversible, traçabilité. `git push`/`commit -a` interdits sans accord.

## Mission de cette session — JALON 1 (besoin F7)

Gestion des identifiants multi-comptes / multi-serveurs (on-prem **et** cloud) :

1. `credentials/profile_store.py` — CRUD de `Profile` en **TOML** sous
   `%APPDATA%/3dx-cleaner/profiles.toml` (config NON sensible uniquement, jamais
   de mot de passe). Utiliser `tomllib` (lecture) + `tomli_w` ou écriture
   manuelle (à toi de proposer ; si nouvelle dépendance, demande validation).
2. `credentials/secret_store.py` — mot de passe via **`keyring`** (déjà
   installé) : service `3dx-cleaner`, username = `Profile.name`. set/get/delete.
   Jamais de secret en clair (ni log).
3. `ui/profile_dialog.py` — dialogue PyQt6 : ajout / édition / suppression /
   **test de connexion** d'un profil (réutilise `core.connection.who_am_i` +
   `build_settings`, en `QThread` worker comme dans `main_window.py`).
4. `ui/main_window.py` — sélecteur de profil au lancement + accès au dialogue.
5. `models/` — si besoin, modèle `ProfileRef`/état ; rester pydantic v2.
6. **Tests** : `profile_store` (round-trip TOML, isolation via
   `THREEDX_CONFIG_DIR`/`tmp_path`), `secret_store` (keyring mocké), dialogue si
   pertinent (pytest-qt). Tout doit passer sans réseau.

**Critère de sortie** : test de connexion réussi sur un profil **on-prem** et
un profil **cloud** depuis l'UI.

## Démarche

Travaille en autonomie par sous-étapes, rends compte en fin de cycle (10 lignes
max). Demande validation uniquement sur : nouvelle dépendance, choix structurant,
action irréversible. Réponds en français, ton technique. Commence par lire
`HANDOFF.md` + `CLAUDE.md`, puis propose le plan du jalon 1 et attends mon feu
vert avant de coder.
