# Librairie Python `requests` — Documentation de référence

> Source : Real Python — "Python's Requests Library (Guide)", realpython.com
> Dernière mise à jour du document : avril 2026

---

## 1. Présentation

La librairie `requests` est la référence pour effectuer des appels HTTP en Python.
Elle n'est **pas** incluse dans la bibliothèque standard Python et doit être installée.
Elle simplifie radicalement les requêtes GET, POST, PUT, DELETE, la gestion des
réponses JSON, l'authentification et les sessions persistantes.

---

## 2. Installation

```bash
pip install requests
```

En environnement virtuel (recommandé) :

```bash
python -m venv venv
source venv/bin/activate        # Linux / macOS
venv\Scripts\activate           # Windows
pip install requests
```

---

## 3. Importation

```python
import requests
```

---

## 4. Méthodes HTTP disponibles

| Méthode                           | Correspondance HTTP | Usage courant              |
|-----------------------------------|---------------------|----------------------------|
| `requests.get(url)`               | GET                 | Lire des données           |
| `requests.post(url, data=...)`    | POST                | Créer une ressource        |
| `requests.put(url, data=...)`     | PUT                 | Mettre à jour              |
| `requests.delete(url)`            | DELETE              | Supprimer                  |
| `requests.head(url)`              | HEAD                | Vérifier sans corps        |
| `requests.patch(url, data=...)`   | PATCH               | Mise à jour partielle      |
| `requests.options(url)`           | OPTIONS             | Méthodes autorisées        |

---

## 5. Requête GET

### 5.1 Requête simple

```python
response = requests.get("https://api.exemple.com/data")
```

### 5.2 Avec paramètres d'URL (query string)

```python
response = requests.get(
    "https://api.exemple.com/search",
    params={"q": "python", "sort": "stars", "page": 1}
)

# URL générée : https://api.exemple.com/search?q=python&sort=stars&page=1
print(response.url)  # Vérification de l'URL réelle
```

Le paramètre `params` accepte :
- Un dictionnaire `{"clé": "valeur"}`
- Une liste de tuples `[("clé", "valeur")]`
- Une chaîne encodée `"clé=valeur"`

---

## 6. Inspection de la réponse

```python
response = requests.get("https://api.exemple.com/data")

# Code de statut HTTP
print(response.status_code)   # 200, 404, 500...

# Contenu textuel (décodé)
print(response.text)           # Chaîne de caractères UTF-8

# Contenu brut (bytes)
print(response.content)        # bytes bruts (utile pour images, fichiers)

# Réponse JSON → dictionnaire Python
data = response.json()         # Désérialise automatiquement

# Headers de réponse
print(response.headers["Content-Type"])
print(response.headers["content-type"])  # Insensible à la casse
```

---

## 7. Vérification du code de statut

### 7.1 Comparaison directe

```python
if response.status_code == 200:
    print("Succès !")
elif response.status_code == 404:
    print("Ressource non trouvée")
elif response.status_code == 401:
    print("Non autorisé — vérifiez les identifiants")
```

### 7.2 Évaluation booléenne

```python
if response:   # True si statut < 400
    data = response.json()
else:
    raise Exception(f"Erreur HTTP : {response.status_code}")
```

### 7.3 Lever une exception automatiquement

```python
from requests.exceptions import HTTPError

try:
    response.raise_for_status()   # Lève HTTPError si >= 400
    data = response.json()
except HTTPError as err:
    print(f"Erreur HTTP : {err}")
```

---

## 8. Headers personnalisés

```python
headers = {
    "Accept": "application/json",
    "User-Agent": "MonApplication/1.0"
}

response = requests.get("https://api.exemple.com/data", headers=headers)
```

---

## 9. Requête POST

### 9.1 Envoi de données de formulaire

```python
response = requests.post(
    "https://api.exemple.com/login",
    data={"username": "monuser", "password": "monpass"}
)
```

### 9.2 Envoi de données JSON (recommandé pour les API REST)

```python
payload = {"nom": "Alice", "age": 30, "ville": "Nancy"}

response = requests.post(
    "https://api.exemple.com/users",
    json=payload   # Sérialise en JSON + ajoute Content-Type: application/json
)

print(response.json())  # Réponse de l'API
```

---

## 10. Authentification

### 10.1 Basic Authentication (username / password)

```python
response = requests.get(
    "https://api.exemple.com/protected",
    auth=("monuser", "monpass")
)
# Encodé automatiquement en Base64 dans l'header Authorization
```

### 10.2 Bearer Token (JWT, OAuth2)

```python
token = "eyJhbGciOiJIUzI1NiIs..."

headers = {"Authorization": f"Bearer {token}"}

response = requests.get(
    "https://api.exemple.com/protected",
    headers=headers
)
```

### 10.3 Authentification personnalisée (classe AuthBase)

```python
from requests.auth import AuthBase

class TokenAuth(AuthBase):
    def __init__(self, token):
        self.token = token

    def __call__(self, request):
        request.headers["Authorization"] = f"Bearer {self.token}"
        return request

response = requests.get("https://api.exemple.com/data", auth=TokenAuth("mon_token"))
```

---

## 11. Timeouts

Sans timeout, une requête peut bloquer indéfiniment si le serveur ne répond pas.
**Toujours spécifier un timeout en production.**

```python
# Timeout simple : 5 secondes pour connexion ET lecture
response = requests.get("https://api.exemple.com/data", timeout=5)

# Timeout dual : 3s pour la connexion, 10s pour la lecture
response = requests.get("https://api.exemple.com/data", timeout=(3, 10))
```

Exceptions levées :
- `requests.exceptions.ConnectTimeout` — connexion trop lente
- `requests.exceptions.ReadTimeout` — réponse trop lente

---

## 12. Sessions (connexions persistantes)

Une session réutilise la connexion TCP et peut partager des paramètres communs
(headers, auth, cookies) entre plusieurs requêtes.

```python
with requests.Session() as session:
    # Paramètres communs à toutes les requêtes de la session
    session.headers.update({"User-Agent": "MonApp/1.0"})
    session.auth = ("monuser", "monpass")

    # Ces requêtes partagent la même connexion et les mêmes headers
    info = session.get("https://api.exemple.com/user")
    data = session.get("https://api.exemple.com/data")
```

---

## 13. Gestion des retries automatiques

```python
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

retry_strategy = Retry(
    total=3,                           # Nombre de tentatives max
    status_forcelist=[429, 500, 502, 503, 504]  # Codes à rejouer
)
adapter = HTTPAdapter(max_retries=retry_strategy)

session = requests.Session()
session.mount("https://", adapter)

response = session.get("https://api.exemple.com/data", timeout=5)
```

---

## 14. Certificats SSL / TLS

```python
# Vérification normale (par défaut — recommandé)
response = requests.get("https://api.exemple.com/data")

# Certificat CA personnalisé (entreprise)
response = requests.get("https://api.intranet.fr", verify="/chemin/vers/ca.pem")

# Désactiver la vérification (DÉCONSEILLÉ en production)
response = requests.get("https://api.exemple.com/data", verify=False)
```

---

## 15. Exemple complet — Interaction avec l'API Xtream Codes

```python
import requests
from requests.exceptions import HTTPError, ConnectionError, Timeout

BASE_URL = "http://monserveur.com:8080"
USERNAME = "monuser"
PASSWORD = "monpass"

def appeler_api(action, params_suppl=None):
    """Appel générique à l'API Xtream Codes."""
    params = {
        "username": USERNAME,
        "password": PASSWORD,
        "action": action
    }
    if params_suppl:
        params.update(params_suppl)

    try:
        response = requests.get(
            f"{BASE_URL}/player_api.php",
            params=params,
            timeout=10
        )
        response.raise_for_status()
        return response.json()

    except Timeout:
        print("Erreur : le serveur ne répond pas (timeout)")
    except ConnectionError:
        print("Erreur : impossible de se connecter au serveur")
    except HTTPError as e:
        print(f"Erreur HTTP : {e.response.status_code}")

    return None

# Utilisation
categories = appeler_api("get_live_categories")
streams = appeler_api("get_live_streams", {"category_id": "1"})
```

---

## 16. Récapitulatif des bonnes pratiques

| Bonne pratique                          | Raison                                         |
|-----------------------------------------|------------------------------------------------|
| Toujours spécifier `timeout`            | Évite les blocages infinis                     |
| Utiliser `response.raise_for_status()`  | Détecte automatiquement les erreurs HTTP       |
| Utiliser `json=` (et non `data=`)       | Sérialise proprement pour les API REST         |
| Utiliser une `Session` pour répéter     | Performances + partage des paramètres          |
| Ne jamais mettre `verify=False`         | Risque de sécurité (man-in-the-middle)         |
| Capturer les exceptions spécifiques     | Gestion d'erreur précise et robuste            |

---

*Document généré automatiquement à partir de sources publiques.*
