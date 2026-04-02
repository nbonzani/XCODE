# API Xtream Codes — Documentation de référence

> Sources : GitHub worldofiptvcom/xtream-codes-api-documentation, zaclimon/xipl wiki,
> xtream-masters.com, WorldOfIPTV forum
> Dernière mise à jour du document : avril 2026

---

## 1. Présentation générale

L'API Xtream Codes est l'interface standard des panels IPTV basés sur le logiciel
Xtream Codes (version 2.x). Elle expose plusieurs points d'entrée pour les clients
(lecteurs vidéo, applications mobiles, téléviseurs).

La version de référence documentée ici est **Xtream Codes v2.9.2**.

---

## 2. Architecture générale du système

Le système Xtream Codes implémente **8 composants API principaux** :

| Composant          | Endpoint              | Usage                                          |
|--------------------|-----------------------|------------------------------------------------|
| Player API         | `/player_api.php`     | Authentification et accès aux contenus client  |
| Panel API          | `/panel_api.php`      | Gestion du panel (côté admin)                  |
| Admin API          | `/api.php`            | Administration serveur (auth par IP)           |
| System API         | `/system_api.php`     | Communication inter-serveurs                   |
| MAG Portal         | `/portal.php`         | Support des décodeurs MAG STB                  |
| Enigma2            | `/enigma2.php`        | Compatibilité récepteurs Enigma2               |
| EPG/XMLTV          | `/xmltv.php`          | Guide des programmes (Electronic Program Guide)|
| Playlist Generator | `/get.php`            | Génération de playlists M3U                    |

---

## 3. URL de base

```
http://{host}:{port}/
```

Exemple : `http://monserveur.com:8080/`

---

## 4. Authentification

### 4.1 Méthode principale — Username / Password

Tous les appels à `player_api.php` nécessitent les paramètres `username` et `password` :

```
http://{host}:{port}/player_api.php?username={user}&password={pass}
```

**Sans paramètre `action`**, cet appel retourne les **informations utilisateur et serveur** :

```json
{
  "user_info": {
    "username": "testuser",
    "password": "testpass",
    "message": "",
    "auth": 1,
    "status": "Active",
    "exp_date": "1893456000",
    "is_trial": "0",
    "active_cons": "0",
    "created_at": "1609459200",
    "max_connections": "1",
    "allowed_output_formats": ["ts", "m3u8", "rtmpe"]
  },
  "server_info": {
    "url": "monserveur.com",
    "port": "8080",
    "https_port": "8443",
    "server_protocol": "http",
    "rtmp_port": "1935",
    "timezone": "Europe/Paris",
    "timestamp_now": 1700000000,
    "time_now": "2023-11-14 12:00:00"
  }
}
```

### 4.2 Autres méthodes d'authentification

| Méthode               | Usage                              |
|-----------------------|------------------------------------|
| Username / Password   | Clients standard (la plus courante)|
| Auth par IP           | Fonctions admin (`api.php`)        |
| Adresse MAC + Token   | Appareils MAG STB                  |
| Play Token            | Streaming sécurisé                 |

---

## 5. Génération de playlist M3U

```
http://{host}:{port}/get.php?username={user}&password={pass}&type=m3u_plus&output=ts
```

| Paramètre  | Valeurs possibles              | Description                        |
|------------|--------------------------------|------------------------------------|
| `type`     | `m3u`, `m3u_plus`              | `m3u_plus` inclut EPG et logos     |
| `output`   | `ts`, `m3u8`, `rtmp`           | Format de sortie des flux          |

---

## 6. Player API — Endpoints de contenu

Tous les endpoints suivent le pattern :
```
http://{host}:{port}/player_api.php?username={user}&password={pass}&action={action}
```

### 6.1 Catégories

| Action                    | Description                        |
|---------------------------|------------------------------------|
| `get_live_categories`     | Liste des catégories Live TV       |
| `get_vod_categories`      | Liste des catégories VOD (films)   |
| `get_series_categories`   | Liste des catégories Séries        |

**Exemple de réponse `get_live_categories` :**
```json
[
  {
    "category_id": "1",
    "category_name": "Généralistes FR",
    "parent_id": 0
  },
  {
    "category_id": "2",
    "category_name": "Sport",
    "parent_id": 0
  }
]
```

### 6.2 Flux Live

| Action                                          | Description                          |
|-------------------------------------------------|--------------------------------------|
| `get_live_streams`                              | Tous les flux live                   |
| `get_live_streams&category_id={id}`             | Flux live d'une catégorie            |

**Exemple de réponse `get_live_streams` (extrait) :**
```json
[
  {
    "num": 1,
    "name": "TF1 HD",
    "stream_type": "live",
    "stream_id": 1234,
    "stream_icon": "http://logos.com/tf1.png",
    "epg_channel_id": "TF1.fr",
    "added": "1609459200",
    "category_id": "1",
    "custom_sid": "",
    "tv_archive": 0,
    "direct_source": "",
    "tv_archive_duration": 0
  }
]
```

### 6.3 Flux VOD (films)

| Action                                     | Description                       |
|--------------------------------------------|-----------------------------------|
| `get_vod_streams`                          | Tous les films VOD                |
| `get_vod_streams&category_id={id}`         | Films d'une catégorie             |
| `get_vod_info&vod_id={id}`                 | Détails d'un film                 |

**Exemple de réponse `get_vod_info` :**
```json
{
  "info": {
    "kinopoisk_url": "",
    "tmdb_id": "12345",
    "name": "Titre du Film",
    "o_name": "Original Title",
    "cover_big": "http://image.tmdb.org/...",
    "movie_image": "http://image.tmdb.org/...",
    "releasedate": "2023-01-15",
    "episode_run_time": "120",
    "youtube_trailer": "dQw4w9WgXcQ",
    "director": "Nom Réalisateur",
    "actors": "Acteur 1, Acteur 2",
    "cast": "Acteur 1, Acteur 2",
    "description": "Description du film...",
    "plot": "Synopsis...",
    "age": "16",
    "country": "France",
    "genre": "Action, Thriller",
    "backdrop_path": ["http://..."],
    "duration_secs": 7200,
    "duration": "02:00:00",
    "rating": "7.5",
    "rating_count_kinopoisk": 0
  },
  "movie_data": {
    "stream_id": 5678,
    "name": "Titre du Film",
    "added": "1700000000",
    "category_id": "10",
    "container_extension": "mp4",
    "custom_sid": "",
    "direct_source": ""
  }
}
```

### 6.4 Séries TV

| Action                                        | Description                         |
|-----------------------------------------------|-------------------------------------|
| `get_series`                                  | Toutes les séries                   |
| `get_series&category_id={id}`                 | Séries d'une catégorie              |
| `get_series_info&series_id={id}`              | Détails + épisodes d'une série      |

**Exemple de réponse `get_series_info` (structure) :**
```json
{
  "info": {
    "name": "Nom de la Série",
    "cover": "http://...",
    "plot": "Synopsis...",
    "cast": "Acteurs...",
    "director": "Réalisateur",
    "genre": "Drama",
    "releaseDate": "2020",
    "rating": "8.2",
    "rating_5based": 4.1,
    "backdrop_path": ["http://..."],
    "youtube_trailer": "",
    "episode_run_time": "45",
    "category_id": "15"
  },
  "episodes": {
    "1": [
      {
        "id": "100",
        "episode_num": 1,
        "title": "Pilote",
        "container_extension": "mp4",
        "info": {
          "duration_secs": 2700,
          "duration": "00:45:00",
          "plot": "Description épisode...",
          "releasedate": "2020-01-05",
          "rating": "8.0"
        },
        "added": "1609459200",
        "season": 1,
        "direct_source": ""
      }
    ]
  },
  "seasons": [
    {
      "air_date": "2020-01-05",
      "episode_count": 10,
      "id": 1,
      "name": "Saison 1",
      "overview": "...",
      "season_number": 1,
      "cover": "http://..."
    }
  ]
}
```

### 6.5 EPG (Guide des programmes)

| Action                                             | Description                            |
|----------------------------------------------------|----------------------------------------|
| `get_short_epg&stream_id={id}&limit={n}`           | EPG court (n entrées, défaut toutes)   |
| `get_simple_data_table&stream_id={id}`             | EPG complet d'un flux                  |
| `xmltv.php?username={u}&password={p}`              | Guide complet au format XMLTV          |

---

## 7. URLs de streaming

### 7.1 Live TV

```
http://{host}:{port}/live/{username}/{password}/{stream_id}.{ext}
```

Extensions : `.ts` (recommandé), `.m3u8` (HLS)

### 7.2 VOD (films)

```
http://{host}:{port}/movie/{username}/{password}/{stream_id}.{ext}
```

Extensions courantes : `.mp4`, `.mkv`, `.avi`

### 7.3 Séries (épisodes)

```
http://{host}:{port}/series/{username}/{password}/{stream_id}.{ext}
```

### 7.4 Timeshift / Replay

```
http://{host}:{port}/timeshift/{username}/{password}/{duration}/{start}/{stream_id}.ts
```

Paramètres :
- `{duration}` : durée en minutes
- `{start}` : date/heure de début au format `YYYY-MM-DD:HH-MM`

### 7.5 HLS Segments

```
http://{host}:{port}/hls/{username}/{password}/{stream_id}/{segment}.ts
```

---

## 8. Formats de réponse

| Format       | Usage                                |
|--------------|--------------------------------------|
| JSON         | Player API, Panel API                |
| XML          | Enigma2, XMLTV (EPG)                 |
| Transport Stream (TS) | Flux live et VOD             |
| HLS (M3U8)   | Streaming adaptatif                  |
| MP4, MKV, AVI, FLV, WMV, MOV, 3GP | VOD selon fournisseur |

---

## 9. Sécurité et limitations

| Mécanisme             | Description                                      |
|-----------------------|--------------------------------------------------|
| GeoIP                 | Restriction par zone géographique                |
| ISP Locking           | Restriction par fournisseur d'accès              |
| IP Whitelisting       | Accès autorisé seulement depuis certaines IPs    |
| User Agent Filtering  | Filtrage par type de client                      |
| Rate Limiting         | 20 requêtes/seconde maximum                      |
| Flood Protection      | Protection anti-abus                             |
| Connection Limits     | Nombre max de connexions simultanées par compte  |

---

## 10. Exemple d'utilisation complète en Python

```python
import requests

BASE_URL = "http://monserveur.com:8080"
USERNAME = "monuser"
PASSWORD = "monpass"

def get_user_info():
    url = f"{BASE_URL}/player_api.php"
    params = {"username": USERNAME, "password": PASSWORD}
    response = requests.get(url, params=params, timeout=10)
    return response.json()

def get_live_categories():
    url = f"{BASE_URL}/player_api.php"
    params = {
        "username": USERNAME,
        "password": PASSWORD,
        "action": "get_live_categories"
    }
    response = requests.get(url, params=params, timeout=10)
    return response.json()

def get_live_streams(category_id=None):
    url = f"{BASE_URL}/player_api.php"
    params = {
        "username": USERNAME,
        "password": PASSWORD,
        "action": "get_live_streams"
    }
    if category_id:
        params["category_id"] = category_id
    response = requests.get(url, params=params, timeout=10)
    return response.json()

def get_vod_info(vod_id):
    url = f"{BASE_URL}/player_api.php"
    params = {
        "username": USERNAME,
        "password": PASSWORD,
        "action": "get_vod_info",
        "vod_id": vod_id
    }
    response = requests.get(url, params=params, timeout=10)
    return response.json()

def build_stream_url(stream_id, stream_type="live", ext="ts"):
    return f"{BASE_URL}/{stream_type}/{USERNAME}/{PASSWORD}/{stream_id}.{ext}"

def download_m3u_playlist():
    url = f"{BASE_URL}/get.php"
    params = {
        "username": USERNAME,
        "password": PASSWORD,
        "type": "m3u_plus",
        "output": "ts"
    }
    response = requests.get(url, params=params, timeout=30)
    return response.text  # Contenu M3U complet
```

---

*Document généré automatiquement à partir de sources publiques — structure JSON indicative,
peut varier selon le fournisseur et la version du panel.*
