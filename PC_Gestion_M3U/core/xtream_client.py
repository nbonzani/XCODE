import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


class XtreamClient:
    """Client pour l'API Xtream Codes."""

    def __init__(self, base_url: str, username: str, password: str):
        # Nettoyage de l'URL
        base_url = base_url.strip().rstrip("/")
        if not base_url.startswith(("http://", "https://")):
            base_url = "http://" + base_url

        self.base_url = base_url
        self.username = username
        self.password = password

        # Configuration de la session avec retry automatique
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "M3UManager/1.0"})

        retry_strategy = Retry(
            total=3,
            status_forcelist=[429, 500, 502, 503, 504],
            backoff_factor=1,
            allowed_methods=["GET"],
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

    def authenticate(self) -> dict:
        """Authentifie l'utilisateur auprès du serveur Xtream Codes.

        Returns:
            dict contenant user_info et server_info.

        Raises:
            ValueError: identifiants incorrects ou réponse invalide.
            ConnectionError: problème de connexion réseau.
        """
        url = f"{self.base_url}/player_api.php"
        params = {"username": self.username, "password": self.password}

        try:
            response = self.session.get(url, params=params, timeout=15)
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            raise ConnectionError(f"Impossible de se connecter au serveur : {e}") from e

        try:
            data = response.json()
        except ValueError as e:
            raise ValueError("Réponse serveur invalide") from e

        user_info = data.get("user_info", {})
        if user_info.get("auth") == 1:
            return data
        else:
            raise ValueError("Identifiants incorrects")

    def download_m3u(self, progress_callback=None) -> str:
        """Télécharge la playlist M3U complète.

        Args:
            progress_callback: optionnel, callable(bytes_received, bytes_total)
                appelé à chaque bloc téléchargé. bytes_total vaut 0 si inconnu.

        Returns:
            Le contenu texte brut de la playlist M3U.

        Raises:
            RuntimeError: en cas d'erreur réseau ou serveur.
        """
        url = f"{self.base_url}/get.php"
        params = {
            "username": self.username,
            "password": self.password,
            "type": "m3u_plus",
            "output": "ts",
        }

        try:
            # Streaming + timeout large pour les playlists volumineuses (>200 Mo)
            response = self.session.get(
                url, params=params, timeout=(15, 600), stream=True
            )
            response.raise_for_status()

            # Taille totale (peut être absente ou 0)
            total = int(response.headers.get("Content-Length", 0))

            # Lecture brute par blocs via urllib3 (contourne IncompleteRead)
            # decode_content=True gère le gzip/deflate éventuel
            raw = response.raw
            raw.decode_content = True
            chunks = []
            received = 0
            while True:
                chunk = raw.read(1024 * 256)
                if not chunk:
                    break
                chunks.append(chunk)
                received += len(chunk)
                if progress_callback:
                    progress_callback(received, total)
            data = b"".join(chunks)
            return data.decode("utf-8", errors="replace")
        except requests.exceptions.Timeout as e:
            raise RuntimeError("Délai d'attente dépassé lors du téléchargement M3U") from e
        except requests.exceptions.ConnectionError as e:
            raise RuntimeError(f"Erreur de connexion : {e}") from e
        except requests.exceptions.HTTPError as e:
            raise RuntimeError(f"Erreur serveur : {e}") from e

    def get_vod_streams(self) -> list:
        """Récupère la liste de tous les films VOD avec leurs métadonnées (rating, etc.)."""
        return self._get_streams("get_vod_streams")

    def get_series_list(self) -> list:
        """Récupère la liste de toutes les séries avec leurs métadonnées (rating, etc.)."""
        return self._get_streams("get_series")

    def _get_streams(self, action: str) -> list:
        """Appel générique pour récupérer des listes de flux."""
        url = f"{self.base_url}/player_api.php"
        params = {
            "username": self.username,
            "password": self.password,
            "action": action,
        }
        try:
            response = self.session.get(url, params=params, timeout=(15, 120))
            response.raise_for_status()
            data = response.json()
            return data if isinstance(data, list) else []
        except Exception:
            return []

    def get_live_categories(self) -> list:
        """Récupère la liste des catégories de chaînes live."""
        return self._get_categories("get_live_categories")

    def get_vod_categories(self) -> list:
        """Récupère la liste des catégories VOD."""
        return self._get_categories("get_vod_categories")

    def get_series_categories(self) -> list:
        """Récupère la liste des catégories de séries."""
        return self._get_categories("get_series_categories")

    def _get_categories(self, action: str) -> list:
        """Appel générique pour récupérer des catégories."""
        url = f"{self.base_url}/player_api.php"
        params = {
            "username": self.username,
            "password": self.password,
            "action": action,
        }

        try:
            response = self.session.get(url, params=params, timeout=15)
            response.raise_for_status()
            return response.json()
        except Exception:
            return []
