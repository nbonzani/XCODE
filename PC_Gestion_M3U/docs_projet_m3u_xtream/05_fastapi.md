# Framework FastAPI (Python) — Documentation de référence

> Source : fastapi.tiangolo.com — Tutorial officiel (First Steps, Path Params,
> Query Params, Request Body)
> Dernière mise à jour du document : avril 2026

---

## 1. Présentation

FastAPI est un framework web Python moderne et très performant pour créer des APIs.
Ses caractéristiques principales :

- **Rapide** : performances comparables à Node.js et Go (basé sur Starlette et Pydantic)
- **Validation automatique** : types Python → validation des données sans code supplémentaire
- **Documentation automatique** : génère une interface Swagger UI interactive
- **Standards ouverts** : basé sur OpenAPI et JSON Schema
- **Typage Python** : utilise les annotations de type Python 3.10+

---

## 2. Installation

```bash
pip install fastapi
```

Pour le serveur de développement :

```bash
pip install "fastapi[standard]"
```

---

## 3. Application minimale

**Fichier `main.py` :**

```python
from fastapi import FastAPI

app = FastAPI()

@app.get("/")
async def root():
    return {"message": "Hello World"}
```

**Lancement du serveur de développement :**

```bash
fastapi dev main.py
```

Ou avec uvicorn directement :

```bash
uvicorn main:app --reload
```

L'application est accessible à `http://127.0.0.1:8000`

---

## 4. Documentation interactive automatique

FastAPI génère automatiquement deux interfaces de documentation :

| Interface     | URL                                  | Description                       |
|---------------|--------------------------------------|-----------------------------------|
| Swagger UI    | `http://127.0.0.1:8000/docs`         | Interface interactive (test live) |
| ReDoc         | `http://127.0.0.1:8000/redoc`        | Documentation alternative         |
| OpenAPI JSON  | `http://127.0.0.1:8000/openapi.json` | Schéma brut OpenAPI               |

---

## 5. Structure d'un endpoint FastAPI

Chaque endpoint combine :
1. Un **décorateur** indiquant la méthode HTTP et le chemin
2. Une **fonction** (synchrone ou asynchrone)
3. Une **valeur de retour** (dict, liste, modèle Pydantic...)

```python
@app.get("/items/")          # Méthode HTTP + chemin
async def read_items():      # Fonction async ou def normale
    return [{"id": 1}]       # Valeur retournée (convertie en JSON)
```

**Méthodes HTTP disponibles :**

```python
@app.get("/items/")      # Lire / lister
@app.post("/items/")     # Créer
@app.put("/items/{id}")  # Mettre à jour (complet)
@app.patch("/items/{id}")# Mettre à jour (partiel)
@app.delete("/items/{id}")# Supprimer
```

---

## 6. Paramètres de chemin (Path Parameters)

Les paramètres de chemin sont déclarés entre accolades `{nom}` dans l'URL.

### 6.1 Exemple basique

```python
@app.get("/items/{item_id}")
async def read_item(item_id):
    return {"item_id": item_id}

# GET /items/foo → {"item_id": "foo"}
```

### 6.2 Avec type Python (validation automatique)

```python
@app.get("/items/{item_id}")
async def read_item(item_id: int):
    return {"item_id": item_id}

# GET /items/3   → {"item_id": 3}         (converti en int)
# GET /items/foo → Erreur 422 (pas un entier)
```

### 6.3 Valeurs prédéfinies (Enum)

```python
from enum import Enum
from fastapi import FastAPI

class TypeFlux(str, Enum):
    live = "live"
    vod = "vod"
    series = "series"

app = FastAPI()

@app.get("/streams/{type_flux}")
async def get_streams(type_flux: TypeFlux):
    return {"type": type_flux, "streams": []}

# GET /streams/live   → {"type": "live", "streams": []}
# GET /streams/autre  → Erreur 422 (valeur non autorisée)
```

### 6.4 Paramètre contenant un chemin

```python
@app.get("/files/{file_path:path}")
async def read_file(file_path: str):
    return {"file_path": file_path}

# GET /files/dossier/sous-dossier/fichier.m3u
# → {"file_path": "dossier/sous-dossier/fichier.m3u"}
```

---

## 7. Paramètres de requête (Query Parameters)

Tout paramètre de fonction **qui n'est pas dans le chemin URL** est automatiquement
un paramètre de requête (après le `?` dans l'URL).

### 7.1 Avec valeur par défaut (optionnel)

```python
@app.get("/items/")
async def list_items(skip: int = 0, limit: int = 10):
    return {"skip": skip, "limit": limit}

# GET /items/          → {"skip": 0, "limit": 10}
# GET /items/?skip=5   → {"skip": 5, "limit": 10}
# GET /items/?skip=5&limit=20 → {"skip": 5, "limit": 20}
```

### 7.2 Paramètre optionnel (None par défaut)

```python
@app.get("/items/{item_id}")
async def read_item(item_id: str, q: str | None = None):
    if q:
        return {"item_id": item_id, "q": q}
    return {"item_id": item_id}

# GET /items/abc        → {"item_id": "abc"}
# GET /items/abc?q=test → {"item_id": "abc", "q": "test"}
```

### 7.3 Paramètre obligatoire (sans valeur par défaut)

```python
@app.get("/search/")
async def search(q: str):    # Obligatoire — pas de valeur par défaut
    return {"query": q}

# GET /search/       → Erreur 422 : champ "q" requis
# GET /search/?q=python → {"query": "python"}
```

### 7.4 Type booléen

```python
@app.get("/items/{item_id}")
async def read_item(item_id: str, active: bool = True):
    return {"item_id": item_id, "active": active}

# Valeurs acceptées pour True  : 1, true, True, on, yes
# Valeurs acceptées pour False : 0, false, False, off, no
```

### 7.5 Combinaison path + query

```python
@app.get("/users/{user_id}/streams/{stream_id}")
async def read_stream(
    user_id: int,
    stream_id: int,
    q: str | None = None,
    format: str = "ts"
):
    result = {"user_id": user_id, "stream_id": stream_id, "format": format}
    if q:
        result["q"] = q
    return result
```

---

## 8. Corps de requête (Request Body) avec Pydantic

Pour les requêtes POST/PUT, on envoie des données JSON dans le corps de la requête.
FastAPI utilise **Pydantic** pour déclarer et valider ces données.

### 8.1 Définir un modèle

```python
from fastapi import FastAPI
from pydantic import BaseModel

class Channel(BaseModel):
    name: str                        # Requis
    group: str                       # Requis
    url: str                         # Requis
    logo: str | None = None          # Optionnel (défaut None)
    active: bool = True              # Optionnel (défaut True)

app = FastAPI()
```

### 8.2 Utiliser le modèle dans un endpoint POST

```python
@app.post("/channels/")
async def create_channel(channel: Channel):
    return channel

# Corps JSON attendu :
# {
#   "name": "TF1 HD",
#   "group": "Généralistes",
#   "url": "http://serveur:8080/live/user/pass/1234.ts",
#   "logo": "http://logos.com/tf1.png"
# }
```

FastAPI gère automatiquement :
- La lecture du corps JSON
- La validation des types
- Le retour d'erreurs claires si les données sont invalides
- La conversion vers le modèle Pydantic
- La documentation dans Swagger UI

### 8.3 Accéder aux données du modèle

```python
@app.post("/channels/")
async def create_channel(channel: Channel):
    channel_dict = channel.model_dump()      # Convertir en dictionnaire

    if channel.logo:
        channel_dict["has_logo"] = True

    return channel_dict
```

### 8.4 Combiner path + query + body

```python
@app.put("/channels/{channel_id}")
async def update_channel(
    channel_id: int,        # Paramètre de chemin
    channel: Channel,       # Corps de requête (Pydantic)
    notify: bool = False    # Paramètre de requête
):
    return {
        "channel_id": channel_id,
        "updated": channel.model_dump(),
        "notification_sent": notify
    }
```

**Règle de reconnaissance automatique :**
- `{param}` dans l'URL → **paramètre de chemin**
- Type Pydantic (BaseModel) → **corps de requête**
- Autre → **paramètre de requête**

---

## 9. Retour de données et codes de statut

```python
from fastapi import FastAPI, HTTPException

app = FastAPI()

channels_db = {1: {"name": "TF1", "group": "FR"}}

@app.get("/channels/{channel_id}")
async def get_channel(channel_id: int):
    if channel_id not in channels_db:
        raise HTTPException(status_code=404, detail="Chaîne non trouvée")
    return channels_db[channel_id]

@app.post("/channels/", status_code=201)
async def create_channel(channel: Channel):
    return channel
```

---

## 10. Exemple complet — API FastAPI pour gestion M3U/Xtream

```python
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel
from typing import Optional, List

app = FastAPI(
    title="API Gestion M3U",
    description="Gestion de playlists M3U et interaction Xtream Codes",
    version="1.0.0"
)

# --- Modèles Pydantic ---

class Channel(BaseModel):
    name: str
    group: str
    url: str
    logo: Optional[str] = None
    epg_id: Optional[str] = None
    active: bool = True

class ChannelOut(Channel):
    id: int

# --- Données en mémoire ---
channels_db: dict[int, dict] = {}
next_id = 1

# --- Endpoints ---

@app.get("/")
async def root():
    return {"message": "API M3U Gestion - Bienvenue"}

@app.get("/channels/", response_model=List[ChannelOut])
async def list_channels(
    group: Optional[str] = Query(None, description="Filtrer par groupe"),
    active: Optional[bool] = Query(None, description="Filtrer par statut"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, le=500)
):
    results = list(channels_db.values())
    if group:
        results = [c for c in results if c["group"] == group]
    if active is not None:
        results = [c for c in results if c["active"] == active]
    return results[skip : skip + limit]

@app.get("/channels/{channel_id}", response_model=ChannelOut)
async def get_channel(channel_id: int):
    if channel_id not in channels_db:
        raise HTTPException(status_code=404, detail="Chaîne introuvable")
    return channels_db[channel_id]

@app.post("/channels/", response_model=ChannelOut, status_code=201)
async def create_channel(channel: Channel):
    global next_id
    new_channel = {"id": next_id, **channel.model_dump()}
    channels_db[next_id] = new_channel
    next_id += 1
    return new_channel

@app.delete("/channels/{channel_id}")
async def delete_channel(channel_id: int):
    if channel_id not in channels_db:
        raise HTTPException(status_code=404, detail="Chaîne introuvable")
    del channels_db[channel_id]
    return {"message": f"Chaîne {channel_id} supprimée"}
```

---

## 11. Comparaison Flask vs FastAPI

| Critère                   | Flask                      | FastAPI                        |
|---------------------------|----------------------------|--------------------------------|
| Courbe d'apprentissage    | Très douce                 | Douce (nécessite typage Python)|
| Performances              | Correctes                  | Très élevées (async natif)     |
| Validation automatique    | Non (manuel)               | Oui (Pydantic intégré)         |
| Documentation auto        | Non (extension requise)    | Oui (Swagger UI intégré)       |
| Support async/await       | Partiel                    | Natif                          |
| Maturité / Communauté     | Très mature (2010)         | Jeune mais populaire (2018)    |
| Recommandé pour           | Prototypes, apps simples   | APIs REST modernes, production |

**Recommandation pour ce projet :** FastAPI est recommandé si vous souhaitez une API
REST robuste avec documentation automatique. Flask est préférable pour un démarrage
très rapide ou si vous préférez la simplicité.

---

*Document généré automatiquement à partir de sources publiques.*
