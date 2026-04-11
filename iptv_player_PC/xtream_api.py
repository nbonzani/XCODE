"""
xtream_api.py - Client pour l'API Xtream Codes.

L'API Xtream Codes est le protocole standard utilisé par la plupart
des serveurs IPTV. Ce module gère toutes les communications avec le serveur.

Documentation du protocole :
  Authentification : GET /player_api.php?username=X&password=Y
  Films            : GET /player_api.php?username=X&password=Y&action=get_vod_streams
  Séries           : GET /player_api.php?username=X&password=Y&action=get_series
"""

import requests
from typing import List, Dict, Any, Optional


class XtreamClient:
    """
    Client pour communiquer avec un serveur IPTV compatible Xtream Codes.

    Exemple d'utilisation :
        client = XtreamClient("http://monserveur.com", "8080", "user", "pass")
        info = client.authenticate()
        films = client.get_vod_streams()
    """

    def __init__(self, server_url: str, port: str, username: str, password: str):
        """
        Initialise le client.

        Args:
            server_url : URL du serveur, ex: "http://monserveur.com"
            port       : Port du serveur, ex: "8080" (laisser vide si inclus dans l'URL)
            username   : Nom d'utilisateur du compte Xtream
            password   : Mot de passe du compte Xtream
        """
        # Supprimer le slash final de l'URL si présent
        base = server_url.rstrip("/")

        # Construire l'URL de base en incluant le port si fourni
        if port and port.strip():
            self.base_url = f"{base}:{port.strip()}"
        else:
            self.base_url = base

        # URL de l'API Xtream
        self.api_url = f"{self.base_url}/player_api.php"

        self.username = username
        self.password = password
        self.timeout = 30  # Délai d'attente en secondes

    # ------------------------------------------------------------------ #
    #  Méthode privée : requête HTTP                                        #
    # ------------------------------------------------------------------ #

    def _get(self, extra_params: Dict = None) -> Optional[Any]:
        """
        Effectue une requête GET vers l'API Xtream.

        Ajoute automatiquement les identifiants (username/password)
        et les paramètres supplémentaires fournis.

        Args:
            extra_params : Paramètres additionnels (action, category_id, etc.)

        Returns:
            Données JSON désérialisées, ou lève une exception en cas d'erreur.
        """
        # Paramètres de base : identifiants
        params = {
            "username": self.username,
            "password": self.password
        }
        if extra_params:
            params.update(extra_params)

        try:
            response = requests.get(self.api_url, params=params, timeout=self.timeout)
            response.raise_for_status()
            return response.json()

        except requests.exceptions.ConnectionError:
            raise ConnectionError(
                f"Impossible de se connecter au serveur.\n"
                f"Vérifiez l'URL : {self.base_url}"
            )
        except requests.exceptions.Timeout:
            raise TimeoutError(
                "Le serveur n'a pas répondu dans les délais impartis (30s).\n"
                "Vérifiez votre connexion internet."
            )
        except requests.exceptions.HTTPError as e:
            raise ConnectionError(f"Erreur HTTP du serveur : {e}")
        except Exception as e:
            raise Exception(f"Erreur inattendue lors de la requête : {e}")

    # ------------------------------------------------------------------ #
    #  Authentification                                                     #
    # ------------------------------------------------------------------ #

    def authenticate(self) -> Dict:
        """
        Teste la connexion et récupère les informations du compte.

        Returns:
            Dictionnaire contenant "user_info" et "server_info".

        Raises:
            ConnectionError si l'authentification échoue.
        """
        data = self._get()
        if not data or "user_info" not in data:
            raise ConnectionError(
                "Authentification échouée.\n"
                "Vérifiez vos identifiants (username/password)."
            )
        return data

    # ------------------------------------------------------------------ #
    #  Films (VOD - Video On Demand)                                        #
    # ------------------------------------------------------------------ #

    def get_vod_categories(self) -> List[Dict]:
        """
        Récupère toutes les catégories de films disponibles sur le serveur.

        Returns:
            Liste de dicts : [{category_id, category_name, parent_id}, ...]
        """
        result = self._get({"action": "get_vod_categories"})
        return result if isinstance(result, list) else []

    def get_vod_streams(self, category_id: str = None) -> List[Dict]:
        """
        Récupère la liste de tous les films disponibles.

        Chaque film contient : stream_id, name, category_id,
        stream_icon (URL du poster), container_extension, rating, added.

        Args:
            category_id : Si fourni, filtre par catégorie (optionnel).

        Returns:
            Liste de dicts décrivant chaque film.
        """
        params = {"action": "get_vod_streams"}
        if category_id:
            params["category_id"] = str(category_id)
        result = self._get(params)
        return result if isinstance(result, list) else []

    def get_vod_info(self, vod_id: int) -> Dict:
        """
        Récupère les informations détaillées d'un film spécifique.

        Args:
            vod_id : Identifiant du film (stream_id).

        Returns:
            Dict avec les clés "info" et "movie_data".
        """
        result = self._get({"action": "get_vod_info", "vod_id": vod_id})
        return result if isinstance(result, dict) else {}

    # ------------------------------------------------------------------ #
    #  Séries                                                               #
    # ------------------------------------------------------------------ #

    def get_series_categories(self) -> List[Dict]:
        """
        Récupère toutes les catégories de séries.

        Returns:
            Liste de dicts : [{category_id, category_name, parent_id}, ...]
        """
        result = self._get({"action": "get_series_categories"})
        return result if isinstance(result, list) else []

    def get_series(self, category_id: str = None) -> List[Dict]:
        """
        Récupère la liste de toutes les séries disponibles.

        Args:
            category_id : Si fourni, filtre par catégorie (optionnel).

        Returns:
            Liste de dicts décrivant chaque série.
        """
        params = {"action": "get_series"}
        if category_id:
            params["category_id"] = str(category_id)
        result = self._get(params)
        return result if isinstance(result, list) else []

    def get_series_info(self, series_id: int) -> Dict:
        """
        Récupère les informations complètes d'une série,
        incluant toutes les saisons et tous les épisodes.

        Args:
            series_id : Identifiant de la série.

        Returns:
            Dict avec "info", "seasons" et "episodes".
        """
        result = self._get({"action": "get_series_info", "series_id": series_id})
        return result if isinstance(result, dict) else {}

    # ------------------------------------------------------------------ #
    #  Construction des URLs de streaming                                   #
    # ------------------------------------------------------------------ #

    def get_stream_url(self, stream_id: int, container_extension: str) -> str:
        """
        Construit l'URL de streaming pour un film.

        Format Xtream : http://serveur:port/movie/username/password/id.ext

        Args:
            stream_id           : Identifiant du flux VOD.
            container_extension : Extension du fichier vidéo (ex: "mkv", "mp4").

        Returns:
            URL complète prête à être lue par VLC.
        """
        return (
            f"{self.base_url}/movie/"
            f"{self.username}/{self.password}/"
            f"{stream_id}.{container_extension}"
        )

    def get_episode_url(self, stream_id: int, container_extension: str) -> str:
        """
        Construit l'URL de streaming pour un épisode de série.

        Format Xtream : http://serveur:port/series/username/password/id.ext

        Args:
            stream_id           : Identifiant du flux de l'épisode.
            container_extension : Extension du fichier vidéo.

        Returns:
            URL complète prête à être lue par VLC.
        """
        return (
            f"{self.base_url}/series/"
            f"{self.username}/{self.password}/"
            f"{stream_id}.{container_extension}"
        )

    # ------------------------------------------------------------------ #
    #  Chaînes TV en direct (Live)                                          #
    # ------------------------------------------------------------------ #

    def get_live_categories(self) -> List[Dict]:
        """
        Récupère toutes les catégories de chaînes live.

        Returns:
            Liste de dicts : [{category_id, category_name, parent_id}, ...]
        """
        result = self._get({"action": "get_live_categories"})
        return result if isinstance(result, list) else []

    def get_live_streams(self, category_id: str = None) -> List[Dict]:
        """
        Récupère la liste de toutes les chaînes TV en direct.

        Chaque chaîne contient : stream_id, name, category_id,
        stream_icon (logo), epg_channel_id.

        Args:
            category_id : Si fourni, filtre par catégorie (optionnel).

        Returns:
            Liste de dicts décrivant chaque chaîne.
        """
        params = {"action": "get_live_streams"}
        if category_id:
            params["category_id"] = str(category_id)
        result = self._get(params)
        return result if isinstance(result, list) else []

    def get_live_stream_url(self, stream_id: int, ext: str = "ts") -> str:
        """
        Construit l'URL de streaming d'une chaîne live.

        Format Xtream : http://serveur:port/live/username/password/id.ext

        Args:
            stream_id : Identifiant du flux live.
            ext       : Extension souhaitée ("ts" ou "m3u8").

        Returns:
            URL complète prête à être lue par VLC.
        """
        return (
            f"{self.base_url}/live/"
            f"{self.username}/{self.password}/"
            f"{stream_id}.{ext}"
        )
