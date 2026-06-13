# Contrat REST — taille de fichier d'un Document (endpoint `files`)

> Capturé **live** le 2026-06-13 contre le tenant Polytech on-prem
> **R2026x** (`<deployment-host>/3dspace`), via probe authentifié direct
> (`scripts/probe_files_size.py`, profil keyring `UL on premise 2026X`).
> Méthode retenue au lieu de la capture HAR : l'auth moteur étant déjà
> opérationnelle, un GET direct reproduit fidèlement l'appel nu du client
> web (`/files?SecurityContext=…`, sans `mask`/`$fields`) et expose le même
> corps de réponse. Le contrat antérieur n'avait été observé **qu'à vide**.

## Endpoint

```
GET /3dspace/resources/v1/modeler/documents/{physical_id}/files
    ?tenant=OnPremise        (param ajouté par le moteur ; SecurityContext via header)
```

- Header `SecurityContext` auto-injecté par `ThreeDxClient` (couche session).
- **Lecture seule.** Un Document **sans** fichier physique renvoie
  `data: []` (HTTP 200) — ce n'est pas une erreur.
- Chaque entrée `data[]` décrit **un** fichier ; un Document peut en porter
  plusieurs → la taille « objet » est la **somme** des `fileSize`.

## Forme de la réponse (fichier présent)

```json
{
  "success": true,
  "statusCode": 200,
  "csrf": { "name": "ENO_CSRF_TOKEN", "value": "<REDACTED>" },
  "items": 1,
  "data": [
    {
      "id": "56A5898500000BFC6A26DC9F0001DBEC",
      "type": "Document",
      "cestamp": "56A5898500000BFC6A26DC9F0001DBEA",
      "dataelements": {
        "title": "Skateboard -In Work -1.1 (1).3dxml",
        "name": "221780931743603",
        "fileType": " ",
        "length": "0.0",
        "revision": "1",
        "originated": "2026-06-08T15:15:43.000Z",
        "modified": "2026-06-08T15:15:43.000Z",
        "fileSize": "133575",
        "fileChecksum": "{MD5}d6283f1fe52c400eab80c11f79daeb3f",
        "format": "generic",
        "image": "https://…/I_CDM_Document108x144.png"
      },
      "relateddata": { "ownerInfo": [ … ], "lockerInfo": [ … ] }
    }
  ],
  "masks": [], "definitions": []
}
```

## Clé de la taille — **`data[].dataelements.fileSize`**

| Clé serveur     | Exemple                              | Sens                                   |
|-----------------|--------------------------------------|----------------------------------------|
| **`fileSize`**  | `"133575"`                           | **Taille en octets** (chaîne) ← cible  |
| `title`         | `"…1.1 (1).3dxml"`                    | Nom de fichier réel                    |
| `name`          | `"221780931743603"`                  | Identifiant FCS du store (≠ nom)       |
| `fileChecksum`  | `"{MD5}d6283f1f…"`                    | Empreinte d'intégrité                  |
| `format`        | `"generic"`                          | Format déclaré                         |
| `fileType`      | `" "`                                | Attribut géométrique — **pas** la taille |
| `length`        | `"0.0"`                              | Attribut géométrique — **pas** la taille |
| `revision`      | `"1"`                                | Révision du fichier                    |

> ⚠️ Ne pas confondre `fileSize` (octets) avec `length`/`fileType` (attributs
> géométriques). `fileSize` est une **chaîne** → parser en `int` (via `float`
> pour tolérer un `"0.0"` éventuel).

## Implémentation

- **Moteur** `threedx_mcp` (couche endpoints, réutilisable par futurs tools) :
  - `models/documents.py` → `DocumentFile` (champs typés, `size_bytes: int|None`).
  - `client/endpoints/documents.py` → `list_document_files(client, physical_id)
    -> list[DocumentFile]` (GET + parse `fileSize` en `int`, `data:[]` → `[]`).
- **Cleaner** `threedx_cleaner` :
  - `core/size_resolver.py` → `ModelerFilesSizeResolver.resolve(rows)` : pour
    chaque ligne **documentaire**, somme des `size_bytes` ; **cache** par clé ;
    tolérant (objet sans fichier / type non-doc / erreur réseau → `None`).
  - `ui/search_panel.py` → worker Qt `_SizeWorker` qui résout chaque page hors
    thread UI et remplit la colonne « Taille ».

## Limites / à confirmer

- **Cloud (3DEXPERIENCE SaaS)** : contrat non re-capturé ici. `space_url` vaut
  `…/enovia` au lieu de `/3dspace` ; le path applicatif `/resources/v1/modeler/
  documents/{id}/files` devrait être identique. À vérifier sur un tenant cloud.
- Types non documentaires (Part `VPMReference`, Representation) : pas couverts
  par cet endpoint — la taille reste `None` (le résolveur ne les sonde pas).
- Document multi-fichiers : sommé. Non observé en live (1 seul fichier sur
  l'échantillon `DOC-0000030`), mais la sémantique `data[]` = liste le permet.
