# Framework Flask (Python) — Documentation de référence

> Sources : Flask Official Documentation (flask.palletsprojects.com),
> ImaginaryCloud Flask REST API Guide, Flask Mega-Tutorial
> Dernière mise à jour du document : avril 2026

---

## 1. Présentation

Flask est un **micro-framework web Python** léger et extensible. Il fournit les briques
fondamentales d'une application web (routage, gestion des requêtes/réponses, templates)
sans imposer de structure ni d'outils particuliers. Il est idéal pour créer des APIs REST.

**Philosophie :** "easy-to-extend" — vous choisissez vos propres outils.

---

## 2. Installation

```bash
pip install Flask
```

Avec un environnement virtuel (recommandé) :

```bash
python -m venv venv
source venv/bin/activate     # Linux / macOS
venv\Scripts\activate        # Windows
pip install Flask
```

---

## 3. Application Flask minimale

```python
from flask import Flask

app = Flask(__name__)

@app.route("/")
def hello():
    return "Hello, World!"

if __name__ == "__main__":
    app.run(debug=True)
```

Lancer l'application :

```bash
python app.py
```

Ou avec la commande Flask CLI :

```bash
flask --app app run --debug
```

L'application est accessible à `http://127.0.0.1:5000`

---

## 4. Routage — Le décorateur `@app.route`

Le décorateur `@app.route` associe une URL à une **fonction de vue** (view function).

```python
@app.route("/")
def index():
    return "Page d'accueil"

@app.route("/a-propos")
def about():
    return "À propos"

@app.route("/contact")
def contact():
    return "Contact"
```

---

## 5. Variables de route (paramètres de chemin)

On peut déclarer des **variables dynamiques** dans l'URL avec des chevrons `<variable>`.

```python
@app.route("/user/<username>")
def user_profile(username):
    return f"Profil de : {username}"

@app.route("/post/<int:post_id>")
def show_post(post_id):
    return f"Article numéro : {post_id}"

@app.route("/path/<path:subpath>")
def show_subpath(subpath):
    return f"Sous-chemin : {subpath}"
```

**Convertisseurs disponibles :**

| Convertisseur | Type Python | Exemple              |
|---------------|-------------|----------------------|
| `string`      | `str`       | `<string:name>`      |
| `int`         | `int`       | `<int:id>`           |
| `float`       | `float`     | `<float:value>`      |
| `path`        | `str`       | `<path:filepath>`    |
| `uuid`        | `UUID`      | `<uuid:token>`       |

---

## 6. Méthodes HTTP (GET, POST, PUT, DELETE)

Par défaut, une route n'accepte que les requêtes **GET**. Pour spécifier les méthodes :

```python
from flask import Flask, request

app = Flask(__name__)

@app.route("/items", methods=["GET", "POST"])
def items():
    if request.method == "GET":
        return "Liste des items"
    elif request.method == "POST":
        data = request.get_json()
        return f"Item créé : {data}"

@app.route("/items/<int:item_id>", methods=["GET", "PUT", "DELETE"])
def item(item_id):
    if request.method == "GET":
        return f"Item {item_id}"
    elif request.method == "PUT":
        data = request.get_json()
        return f"Item {item_id} mis à jour"
    elif request.method == "DELETE":
        return f"Item {item_id} supprimé"
```

---

## 7. Retour JSON avec `jsonify`

Flask fournit la fonction `jsonify` pour retourner des réponses JSON avec le bon
`Content-Type` (`application/json`) automatiquement.

```python
from flask import Flask, jsonify

app = Flask(__name__)

@app.route("/api/data")
def get_data():
    data = {
        "nom": "Alice",
        "age": 30,
        "ville": "Nancy"
    }
    return jsonify(data)

@app.route("/api/items")
def get_items():
    items = [
        {"id": 1, "name": "Item 1"},
        {"id": 2, "name": "Item 2"}
    ]
    return jsonify(items)
```

> **Note :** Depuis Flask 2.2+, retourner directement un `dict` ou une `list`
> déclenche automatiquement `jsonify`. Les deux formes sont équivalentes.

---

## 8. Lire les données d'une requête

### 8.1 Paramètres d'URL (query string)

URL : `http://localhost:5000/search?q=python&page=2`

```python
from flask import request

@app.route("/search")
def search():
    query = request.args.get("q", "")       # Valeur par défaut ""
    page = request.args.get("page", 1, type=int)
    return jsonify({"query": query, "page": page})
```

### 8.2 Corps JSON d'une requête POST

```python
@app.route("/api/users", methods=["POST"])
def create_user():
    data = request.get_json()
    if not data:
        return jsonify({"error": "Données JSON manquantes"}), 400

    nom = data.get("nom")
    age = data.get("age")

    return jsonify({"message": "Utilisateur créé", "nom": nom}), 201
```

### 8.3 Données de formulaire HTML

```python
@app.route("/login", methods=["POST"])
def login():
    username = request.form.get("username")
    password = request.form.get("password")
    return jsonify({"user": username})
```

---

## 9. Codes de statut HTTP

Flask retourne `200 OK` par défaut. Pour spécifier un autre code :

```python
@app.route("/api/users", methods=["POST"])
def create_user():
    data = request.get_json()
    # Créer l'utilisateur...
    return jsonify({"message": "Créé"}), 201   # 201 Created

@app.route("/api/items/<int:id>")
def get_item(id):
    item = trouver_item(id)
    if item is None:
        return jsonify({"error": "Non trouvé"}), 404
    return jsonify(item)
```

**Codes courants :**

| Code | Signification         | Usage                              |
|------|-----------------------|------------------------------------|
| 200  | OK                    | Succès standard                    |
| 201  | Created               | Ressource créée avec succès        |
| 400  | Bad Request           | Données invalides envoyées         |
| 401  | Unauthorized          | Authentification requise           |
| 403  | Forbidden             | Accès refusé                       |
| 404  | Not Found             | Ressource introuvable              |
| 500  | Internal Server Error | Erreur serveur                     |

---

## 10. Gestion des erreurs

```python
from flask import jsonify

@app.errorhandler(400)
def bad_request(error):
    return jsonify({"error": "Requête invalide"}), 400

@app.errorhandler(404)
def not_found(error):
    return jsonify({"error": "Ressource introuvable"}), 404

@app.errorhandler(500)
def internal_error(error):
    return jsonify({"error": "Erreur serveur interne"}), 500
```

---

## 11. Templates Jinja2

Pour les réponses HTML, Flask configure automatiquement le moteur de templates Jinja2.
Les templates sont placés dans un dossier `templates/`.

**Fichier `templates/index.html` :**
```html
<!DOCTYPE html>
<html>
<body>
  <h1>Bonjour, {{ nom }} !</h1>
  <ul>
    {% for item in items %}
      <li>{{ item }}</li>
    {% endfor %}
  </ul>
</body>
</html>
```

**Vue Flask :**
```python
from flask import render_template

@app.route("/accueil")
def accueil():
    return render_template("index.html", nom="Alice", items=["A", "B", "C"])
```

---

## 12. Blueprints — Organisation modulaire

Pour les projets de taille moyenne/grande, les **Blueprints** permettent de regrouper
les routes par thème :

```python
# fichier routes/channels.py
from flask import Blueprint, jsonify

channels_bp = Blueprint("channels", __name__, url_prefix="/api/channels")

@channels_bp.route("/")
def list_channels():
    return jsonify([])

@channels_bp.route("/<int:channel_id>")
def get_channel(channel_id):
    return jsonify({"id": channel_id})
```

```python
# fichier app.py
from flask import Flask
from routes.channels import channels_bp

app = Flask(__name__)
app.register_blueprint(channels_bp)
```

---

## 13. Structure recommandée d'un projet Flask

**Projet simple :**
```
mon_projet/
├── app.py              ← Application principale
├── models.py           ← Structures de données
├── routes.py           ← Routes / endpoints
└── requirements.txt    ← Dépendances
```

**Projet structuré :**
```
mon_projet/
├── app/
│   ├── __init__.py     ← Création de l'app Flask
│   ├── routes/
│   │   ├── channels.py
│   │   └── vod.py
│   └── models/
│       └── channel.py
├── requirements.txt
└── run.py              ← Point d'entrée
```

---

## 14. Exemple complet — API Flask pour gestion M3U

```python
from flask import Flask, jsonify, request

app = Flask(__name__)

# Données en mémoire (exemple)
channels = [
    {"id": 1, "name": "TF1 HD", "group": "Généralistes", "url": "http://..."},
    {"id": 2, "name": "France 2", "group": "Généralistes", "url": "http://..."},
]

@app.route("/api/channels", methods=["GET"])
def get_channels():
    group = request.args.get("group")
    if group:
        filtered = [c for c in channels if c["group"] == group]
        return jsonify(filtered)
    return jsonify(channels)

@app.route("/api/channels/<int:channel_id>", methods=["GET"])
def get_channel(channel_id):
    channel = next((c for c in channels if c["id"] == channel_id), None)
    if channel is None:
        return jsonify({"error": "Chaîne non trouvée"}), 404
    return jsonify(channel)

@app.route("/api/channels", methods=["POST"])
def add_channel():
    data = request.get_json()
    if not data or "name" not in data:
        return jsonify({"error": "Données invalides"}), 400
    new_channel = {
        "id": len(channels) + 1,
        "name": data["name"],
        "group": data.get("group", ""),
        "url": data.get("url", "")
    }
    channels.append(new_channel)
    return jsonify(new_channel), 201

@app.errorhandler(404)
def not_found(e):
    return jsonify({"error": "Non trouvé"}), 404

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
```

---

*Document généré automatiquement à partir de sources publiques.*
