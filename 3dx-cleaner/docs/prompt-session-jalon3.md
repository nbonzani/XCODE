# Prompt de lancement — session jalon 3 (3dx-cleaner)

> À copier comme **premier message** d'une nouvelle session Claude Code ouverte
> dans `D:\CLAUDE\XCODE\3dx-cleaner`.

---

Tu reprends le développement de **`3dx-cleaner`** (GUI PyQt6 de purge contrôlée
de données 3DEXPERIENCE, usage pédagogique), couche GUI + orchestration batch
par-dessus le moteur `threedx_mcp` (`D:\CLAUDE\XCODE\3dx-mcp`, v0.6.0).

**Avant de coder, lis `HANDOFF.md`** (état complet : jalons 0-1-2 faits, F5
pré-vol lecture seule anticipé) **et `CLAUDE.md`**.

## ⚠️ Cette session entre en ZONE D'ÉCRITURE / SUPPRESSION

Le jalon 3 introduit les **premières opérations destructives**. Les garde-fous
sont **non négociables** :
- **dry-run / plan par défaut PARTOUT** ; aucune écriture sans confirmation UI
  explicite ;
- suppression 3DX **physique et irréversible** — l'UI doit le rappeler ;
- **valider avec moi** l'architecture de l'exécuteur et le gating de confirmation
  AVANT d'écrire le code qui exécute réellement ;
- tests sur objets **`MCP_` jetables** uniquement, jamais sur des données réelles ;
- `git push` / `commit -a` interdits sans accord.

## Contexte technique déjà en place (à réutiliser, pas réécrire)

- **F3 lecture seule** : `core/document_query.py` (recherche/pagination),
  `core/collabspace_query.py`, `ui/search_panel.py` (sélection → `selected_rows()`).
- **F5 pré-vol lecture seule** : `core/preflight.py` →
  `run_preflight(client, rows) -> list[PreflightVerdict]` (droit de suppression,
  logique vs physique, cascade `wholeStructure`, where-used). **Déjà testé**,
  pas encore branché à l'UI.
- **Taille** : `core/size_resolver.py` — `NullSizeResolver` par défaut ;
  `ModelerFilesSizeResolver` est un **STUB** tant que le contrat REST n'est pas
  capturé.
- Briques moteur destructives (couche endpoints) :
  `endpoints.lifecycle.reserve/unreserve`, `endpoints.lifecycle.change_maturity`
  (+ `preview_maturity`, `list_transitions`),
  `endpoints.lifecycle_delete.delete_objects` (+ `_cloud`, clé `wholeStructure`).

## Mission de cette session — JALON 3 (F4 + exécuteur + F6, + HAR taille)

1. **Capture HAR taille** (skill `har-capture-3dx`) sur un Document AVEC fichier
   physique → déterminer la clé JSON de taille dans
   `GET /resources/v1/modeler/documents/{id}/files` → **activer**
   `ModelerFilesSizeResolver` (appel par lot + cache) et router l'UI dessus.
2. **F4 `core/normalize.py`** : normalisation pré-suppression = `unreserve` +
   `demote` vers In Work. **Produire d'abord un PLAN** (dry-run, décrit les
   actions par objet) ; l'exécution réelle est une fonction distincte, gardée.
3. **`core/executor.py`** : exécuteur batch (worker Qt + pool borné), progression,
   agrégation d'erreurs typées (`client.errors.ThreeDxError`). **Dry-run par
   défaut** ; mode réel seulement après confirmation.
4. **F6 `core/report.py`** : rapport horodaté local par campagne (ce qui était
   prévu / fait / échoué, motif serveur exact par objet).
5. **UI** : brancher `run_preflight` sur la sélection F3 (écran de récap pré-vol
   avant toute action), avec rappel « suppression irréversible ».

**Critères de sortie** : taille réelle affichée dans le tableau F3 ; normalisation
+ pré-vol + rapport validés en **dry-run** puis sur objets `MCP_` jetables.

## Démarche

Commence par lire `HANDOFF.md` + `CLAUDE.md`, **propose le plan du jalon 3 et le
design de l'exécuteur/gating, et attends mon feu vert avant d'écrire le moindre
code destructif.** Réponds en français, ton technique. Travaille par sous-étapes,
rends compte en fin de cycle (10 lignes max).
