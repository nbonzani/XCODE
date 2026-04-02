# Format M3U et M3U+ (Extended M3U) — Documentation de référence

> Source : Wikipedia EN — M3U, consolidation technique
> Dernière mise à jour du document : avril 2026

---

## 1. Présentation générale

Le format M3U est un fichier texte brut servant à référencer l'emplacement de fichiers médias
(musique, vidéo, flux IPTV). Il en existe deux variantes :

- `.m3u` — encodage non-Unicode (codepage système)
- `.m3u8` — encodage UTF-8 obligatoire (recommandé pour l'IPTV et le streaming international)

Chaque entrée se termine par un saut de ligne. Le standard CRLF (`\r\n`) est recommandé
pour la compatibilité maximale avec les appareils.

---

## 2. Structure de base (M3U simple)

Un fichier M3U minimal peut référencer :

- Des chemins absolus locaux : `C:\Musique\fichier.mp3`
- Des chemins relatifs au fichier M3U
- Des URLs complètes : `http://exemple.com/flux.mp3`

**Exemple minimal :**
```
Alice_in_Chains_01_Rotten_Apple.mp3
Alice_in_Chains_02_Nutshell.mp3
```

---

## 3. Format M3U étendu (Extended M3U / M3U+)

### 3.1 En-tête obligatoire

```
#EXTM3U
```

La première ligne **doit** être `#EXTM3U`. Les lignes commençant par `#` sont soit
des commentaires, soit des directives étendues (suivies de `:`).

### 3.2 Tags étendus

| Directive       | Description                            | Exemple                                      |
|-----------------|----------------------------------------|----------------------------------------------|
| `#EXTINF:`      | Durée en secondes + titre optionnel    | `#EXTINF:419,Artist – Title`                 |
| `#EXTALB:`      | Titre de l'album                       | `#EXTALB:Album Title (2009)`                 |
| `#EXTART:`      | Artiste de l'album                     | `#EXTART:Various Artists`                    |
| `#EXTGENRE:`    | Genre musical                          | `#EXTGENRE:Jazz Fusion`                      |

**Exemple M3U+ pour musique :**
```
#EXTM3U
#EXTINF:419,Alice in Chains - Rotten Apple
Alice_in_Chains_01_Rotten_Apple.mp3
#EXTINF:260,Alice in Chains - Nutshell
Alice_in_Chains_02_Nutshell.mp3
```

---

## 4. Format IPTV (M3U+ pour la télévision IP)

Pour les flux IPTV/streaming continus, la durée est conventionnellement fixée à `-1`
(flux sans fin déterminée). Les attributs IPTV sont placés **sur la même ligne** que
la directive `#EXTINF`.

### 4.1 Syntaxe générale

```
#EXTINF:-1 attribut1="valeur1" attribut2="valeur2", Nom affiché
http://serveur:port/chemin/vers/flux
```

### 4.2 Attributs IPTV courants

| Attribut        | Rôle                                     | Exemple                              |
|-----------------|------------------------------------------|--------------------------------------|
| `tvg-id`        | Identifiant unique (liaison EPG/XMLTV)   | `tvg-id="TF1.fr"`                   |
| `tvg-name`      | Nom du canal                             | `tvg-name="TF1"`                    |
| `tvg-logo`      | URL du logo de la chaîne                 | `tvg-logo="http://logos.com/tf1.png"`|
| `group-title`   | Catégorie / groupe thématique            | `group-title="Généralistes FR"`     |
| `tvg-chno`      | Numéro de canal (TNT, etc.)              | `tvg-chno="1"`                      |
| `tvg-country`   | Code pays ISO 3166                       | `tvg-country="FR"`                  |
| `tvg-language`  | Langue ISO 639                           | `tvg-language="French"`             |
| `tvg-shift`     | Décalage EPG en heures                   | `tvg-shift="+1"`                    |

### 4.3 Exemple complet d'un fichier M3U IPTV

```
#EXTM3U url-tvg="http://epg.provider.com/guide.xml" tvg-url="http://epg.provider.com/guide.xml"

#EXTINF:-1 tvg-id="TF1.fr" tvg-name="TF1" tvg-logo="http://logos.com/tf1.png" group-title="Généralistes FR",TF1
http://monserveur.com:8080/live/user/pass/1234.ts

#EXTINF:-1 tvg-id="France2.fr" tvg-name="France 2" tvg-logo="http://logos.com/france2.png" group-title="Généralistes FR",France 2
http://monserveur.com:8080/live/user/pass/1235.ts

#EXTINF:-1 tvg-id="" tvg-name="Film Action" tvg-logo="" group-title="VOD",Film Action HD
http://monserveur.com:8080/movie/user/pass/5678.mp4
```

### 4.4 Attribut de l'en-tête `#EXTM3U`

L'en-tête peut lui-même porter des attributs globaux :

| Attribut    | Rôle                                        |
|-------------|---------------------------------------------|
| `url-tvg`   | URL du guide EPG au format XMLTV            |
| `tvg-url`   | Alternative à `url-tvg`                     |
| `x-tvg-url` | Variante utilisée par certains fournisseurs |

---

## 5. Types de flux IPTV

| Type      | Extension courante | Description                                   |
|-----------|--------------------|-----------------------------------------------|
| Live      | `.ts`, `.m3u8`     | Diffusion en direct (télévision)               |
| VOD       | `.mp4`, `.mkv`     | Vidéo à la demande (films, documentaires)      |
| Séries    | `.mp4`, `.mkv`     | Séries TV, organisées en saisons et épisodes   |
| Timeshift | `/timeshift/...`   | Replay / rattrapage TV                         |

---

## 6. Format HLS (HTTP Live Streaming — Apple)

Apple a étendu M3U/M3U8 pour le streaming adaptatif (RFC 8216). Les directives
commencent par `#EXT-X-` :

| Directive                 | Rôle                                    |
|---------------------------|-----------------------------------------|
| `#EXT-X-VERSION:`         | Version du format HLS                   |
| `#EXT-X-TARGETDURATION:`  | Durée maximale d'un segment (secondes)  |
| `#EXT-X-MEDIA-SEQUENCE:`  | Numéro du premier segment               |
| `#EXT-X-PLAYLIST-TYPE:`   | `VOD` ou `EVENT`                        |
| `#EXT-X-KEY:`             | Méthode de chiffrement des segments     |
| `#EXT-X-ENDLIST`          | Signal de fin de playlist               |

---

## 7. Types MIME associés

| Type MIME                          | Usage                          |
|------------------------------------|--------------------------------|
| `application/vnd.apple.mpegurl`   | HLS — enregistré IANA          |
| `application/x-mpegurl`           | Usage commun                   |
| `audio/mpegurl`                   | Flux audio                     |

---

## 8. Considérations pratiques pour le développement Python

- Lire un fichier M3U : utiliser `open()` avec encodage `utf-8`
- Analyser les lignes : tester si la ligne commence par `#EXTINF` pour extraire les attributs
- Extraire les attributs IPTV : utiliser des expressions régulières (`re` module)
- Les URLs de flux suivent immédiatement la ligne `#EXTINF` correspondante
- Les lignes vides ou les lignes `#EXTM3U` doivent être ignorées lors du parsing

**Exemple de parsing minimal en Python :**
```python
def parse_m3u(filepath):
    channels = []
    current_info = {}

    with open(filepath, encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line.startswith('#EXTINF:'):
                # Extraire les attributs
                import re
                attrs = re.findall(r'(\w[\w-]*)="([^"]*)"', line)
                current_info = dict(attrs)
                # Extraire le nom affiché (après la dernière virgule)
                current_info['display_name'] = line.rsplit(',', 1)[-1].strip()
            elif line and not line.startswith('#'):
                current_info['url'] = line
                channels.append(current_info)
                current_info = {}

    return channels
```

---

*Document généré automatiquement à partir de sources publiques — à compléter selon les besoins du projet.*
