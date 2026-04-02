# Documentation Projet — Gestion M3U & API Xtream Codes

> Dossier de référence technique généré le 2 avril 2026
> Projet : Application Python de gestion de fichiers M3U et d'interaction avec l'API Xtream Codes

---

## Contenu du dossier

| Fichier                    | Sujet                              | Sources principales                                        |
|----------------------------|------------------------------------|------------------------------------------------------------|
| `01_format_m3u.md`         | Format M3U / M3U+ (IPTV)          | Wikipedia EN — M3U                                        |
| `02_api_xtream.md`         | API Xtream Codes complète          | GitHub worldofiptvcom, zaclimon/xipl, xtream-masters.com  |
| `03_python_requests.md`    | Librairie Python `requests`        | Real Python — "Python's Requests Library (Guide)"         |
| `04_flask.md`              | Framework Flask                    | flask.palletsprojects.com, ImaginaryCloud, Mega-Tutorial   |
| `05_fastapi.md`            | Framework FastAPI                  | fastapi.tiangolo.com — Tutorial officiel                   |

---

## Synthèse des sujets couverts

### 01 — Format M3U / M3U+
- Structure d'un fichier M3U de base et étendu
- En-tête `#EXTM3U`, directive `#EXTINF`
- Attributs IPTV : `tvg-id`, `tvg-name`, `tvg-logo`, `group-title`, `tvg-chno`, `tvg-country`
- Exemple de fichier IPTV complet
- Types de flux : Live, VOD, Séries, Timeshift
- Format HLS / M3U8 (Apple, RFC 8216)
- Exemple de parsing en Python

### 02 — API Xtream Codes
- Architecture du système (8 composants API)
- Authentification username/password
- Endpoint `get.php` : téléchargement de playlist M3U
- Endpoints `player_api.php` : catégories, live, VOD, séries, EPG
- Structure des réponses JSON (exemples détaillés)
- URLs de streaming live, VOD, séries, timeshift, HLS
- Sécurité : GeoIP, rate limiting, IP whitelisting
- Exemple d'utilisation complète en Python

### 03 — Librairie Python `requests`
- Installation et importation
- Méthodes GET, POST, PUT, DELETE
- Paramètres d'URL (`params`), headers personnalisés
- Lecture des réponses : `text`, `content`, `json()`
- Authentification Basic et Bearer Token
- Gestion des erreurs et codes de statut
- Timeouts (simple et dual)
- Sessions persistantes
- Retries automatiques
- Exemple complet d'appel à l'API Xtream Codes

### 04 — Flask
- Installation et application minimale
- Routage avec `@app.route` et variables de chemin
- Méthodes HTTP (GET, POST, PUT, DELETE)
- Retour JSON avec `jsonify`
- Lecture des paramètres de requête et du corps JSON
- Codes de statut HTTP
- Gestion des erreurs personnalisée
- Templates Jinja2
- Blueprints pour modulariser le code
- Structure de projet recommandée
- Exemple d'API Flask pour gestion M3U

### 05 — FastAPI
- Installation et application minimale
- Documentation interactive automatique (Swagger UI)
- Paramètres de chemin (path parameters) avec types
- Paramètres de requête (query parameters) — optionnels, obligatoires, booléens
- Corps de requête avec modèles Pydantic (BaseModel)
- Gestion des erreurs (HTTPException)
- Codes de statut HTTP personnalisés
- Exemple d'API FastAPI complète pour gestion M3U
- Comparaison Flask vs FastAPI

---

## Architecture recommandée pour le projet

```
mon_projet_m3u/
├── main.py                 ← Point d'entrée (Flask ou FastAPI)
├── parser_m3u.py           ← Parsing et génération des fichiers M3U
├── client_xtream.py        ← Interaction avec l'API Xtream Codes (requests)
├── models.py               ← Structures de données (Pydantic ou dataclasses)
├── routes/
│   ├── channels.py         ← Endpoints pour les chaînes live
│   ├── vod.py              ← Endpoints pour les films VOD
│   └── series.py           ← Endpoints pour les séries
├── requirements.txt        ← Dépendances Python
└── docs_projet_m3u_xtream/ ← Ce dossier de documentation
```

**Dépendances minimales (`requirements.txt`) :**
```
requests>=2.31.0
fastapi>=0.110.0
uvicorn[standard]>=0.27.0
pydantic>=2.6.0
```

Ou avec Flask :
```
requests>=2.31.0
Flask>=3.0.0
```

---

## Points d'attention pour le développement

1. **Encoding M3U** : toujours ouvrir les fichiers M3U avec `encoding='utf-8'`
2. **Timeout API Xtream** : toujours spécifier `timeout=10` dans les appels `requests`
3. **Rate limiting Xtream** : l'API impose 20 req/s — utiliser des pauses si besoin
4. **Durée -1 en IPTV** : dans M3U+, la durée `-1` signifie flux continu (live)
5. **Attributs sensibles à la casse** : `group-title` ≠ `Group-Title` dans M3U

---

*Documentation de référence — à compléter selon l'évolution du projet.*
