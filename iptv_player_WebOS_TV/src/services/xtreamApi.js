/**
 * src/services/xtreamApi.js
 * Client JavaScript pour l'API Xtream Codes.
 *
 * Calqué sur la logique de xtream_client.py (PC_Gestion_M3U) :
 *   - Retry automatique (3 tentatives, backoff exponentiel 1 s → 2 s → 4 s)
 *   - Statuts retentés : 429 (rate limit) + 500-504 (erreurs serveur)
 *   - Vérification auth == 1 à l'authentification
 *   - Détection propre des erreurs JSON (réponse HTML inattendue)
 */

var RETRY_COUNT   = 3;
var RETRY_DELAYS  = [1000, 2000, 4000]; // backoff exponentiel
var RETRY_STATUSES = new Set([429, 500, 502, 503, 504]);

export class XtreamClient {
  constructor(serverUrl, port, username, password) {
    // Normalisation de l'URL — portage de xtream_client.py
    var base = (serverUrl || '').trim().replace(/\/+$/, '');
    if (base && !base.startsWith('http://') && !base.startsWith('https://')) {
      base = 'http://' + base;
    }

    // Port : ne pas ajouter si absent, "80" (http standard) ou "443" (https standard)
    var p = (port || '').trim();
    var skipPort = !p || p === '80' || p === '443';
    this.baseUrl = skipPort ? base : base + ':' + p;

    this.apiUrl   = this.baseUrl + '/player_api.php';
    this.username = username;
    this.password = password;
  }

  // ── Requête interne avec retry + backoff exponentiel ─────────────────────

  async _get(extraParams, timeoutMs) {
    var params = new URLSearchParams(
      Object.assign({ username: this.username, password: this.password }, extraParams || {})
    );
    var url = this.apiUrl + '?' + params.toString();
    var timeout = timeoutMs || 15000;

    var lastError = null;

    for (var attempt = 0; attempt < RETRY_COUNT; attempt++) {
      var controller = new AbortController();
      var timer = setTimeout(function() { controller.abort(); }, timeout);

      try {
        var response = await fetch(url, {
          signal: controller.signal,
          headers: { 'User-Agent': 'IPTVPlayer/1.0', 'Accept': 'application/json' },
        });
        clearTimeout(timer);

        // Retry sur rate-limit (429) et erreurs serveur (5xx)
        if (RETRY_STATUSES.has(response.status) && attempt < RETRY_COUNT - 1) {
          lastError = new Error('Erreur HTTP ' + response.status + ' — nouvelle tentative…');
          await _sleep(RETRY_DELAYS[attempt]);
          continue;
        }

        if (!response.ok) {
          throw new Error('Erreur HTTP ' + response.status + ' du serveur.');
        }

        // Parsing JSON — le serveur peut renvoyer du HTML en cas d'erreur de config
        var text = await response.text();
        try {
          return JSON.parse(text);
        } catch (_) {
          throw new Error(
            'Réponse serveur invalide (non-JSON). Vérifiez l\'URL du serveur.\n' +
            'Aperçu : ' + text.slice(0, 120)
          );
        }

      } catch (error) {
        clearTimeout(timer);
        lastError = _normalizeError(error, this.baseUrl, timeout);

        // Retry uniquement sur erreurs réseau ou timeout
        var isRetryable = error.name === 'AbortError' ||
          error.message.includes('Failed to fetch') ||
          error.message.includes('NetworkError') ||
          error.message.includes('network');

        if (isRetryable && attempt < RETRY_COUNT - 1) {
          await _sleep(RETRY_DELAYS[attempt]);
          continue;
        }

        throw lastError;
      }
    }

    throw lastError;
  }

  // ── API publique ──────────────────────────────────────────────────────────

  /**
   * Authentifie l'utilisateur.
   * Vérifie user_info.auth === 1 (portage de xtream_client.py).
   * @returns {Promise<object>} { user_info, server_info }
   */
  async authenticate() {
    var data = await this._get();

    if (!data || typeof data !== 'object') {
      throw new Error('Authentification échouée — réponse inattendue.');
    }

    var userInfo = data.user_info || {};

    // Vérification stricte : auth doit valoir 1 (0 = mauvais identifiants)
    if (userInfo.auth !== 1) {
      throw new Error('Identifiants incorrects. Vérifiez votre nom d\'utilisateur et mot de passe.');
    }

    // Vérification expiration du compte
    if (userInfo.status === 'Expired') {
      throw new Error('Votre abonnement a expiré.');
    }

    return data;
  }

  /** Catégories VOD */
  async getVodCategories() {
    var result = await this._get({ action: 'get_vod_categories' });
    return Array.isArray(result) ? result : [];
  }

  /**
   * Films VOD — optionnellement filtrés par catégorie.
   * timeout 30 s par catégorie, 120 s pour le catalogue complet.
   */
  async getVodStreams(categoryId) {
    var params = { action: 'get_vod_streams' };
    if (categoryId != null) params.category_id = String(categoryId);
    var result = await this._get(params, categoryId != null ? 30000 : 120000);
    return Array.isArray(result) ? result : [];
  }

  /** Métadonnées d'un film (synopsis, cast, affiche…) */
  async getVodInfo(vodId) {
    var result = await this._get({ action: 'get_vod_info', vod_id: vodId }, 20000);
    return result && typeof result === 'object' ? result : {};
  }

  /** Catégories de séries */
  async getSeriesCategories() {
    var result = await this._get({ action: 'get_series_categories' });
    return Array.isArray(result) ? result : [];
  }

  /**
   * Séries — optionnellement filtrées par catégorie.
   */
  async getSeries(categoryId) {
    var params = { action: 'get_series' };
    if (categoryId != null) params.category_id = String(categoryId);
    var result = await this._get(params, categoryId != null ? 30000 : 120000);
    return Array.isArray(result) ? result : [];
  }

  /** Épisodes + métadonnées d'une série */
  async getSeriesInfo(seriesId) {
    var result = await this._get({ action: 'get_series_info', series_id: seriesId }, 30000);
    return result && typeof result === 'object' ? result : {};
  }

  /** Catégories de chaînes live */
  async getLiveCategories() {
    var result = await this._get({ action: 'get_live_categories' });
    return Array.isArray(result) ? result : [];
  }

  /** Chaînes live — optionnellement filtrées par catégorie */
  async getLiveStreams(categoryId) {
    var params = { action: 'get_live_streams' };
    if (categoryId != null) params.category_id = String(categoryId);
    var result = await this._get(params, categoryId != null ? 30000 : 120000);
    return Array.isArray(result) ? result : [];
  }

  // ── Construction des URLs de flux ─────────────────────────────────────────

  /** URL d'un film VOD */
  getStreamUrl(streamId, containerExtension) {
    return this.baseUrl + '/movie/' + this.username + '/' + this.password + '/' + streamId + '.' + containerExtension;
  }

  /** URL d'un épisode de série */
  getEpisodeUrl(streamId, containerExtension) {
    return this.baseUrl + '/series/' + this.username + '/' + this.password + '/' + streamId + '.' + containerExtension;
  }

  /** URL d'un flux live */
  getLiveUrl(streamId, containerExtension) {
    var ext = containerExtension || 'ts';
    return this.baseUrl + '/live/' + this.username + '/' + this.password + '/' + streamId + '.' + ext;
  }
}

// ── Helpers internes ─────────────────────────────────────────────────────────

function _sleep(ms) {
  return new Promise(function(resolve) { setTimeout(resolve, ms); });
}

function _normalizeError(error, baseUrl, timeoutMs) {
  if (error.name === 'AbortError') {
    return new Error(
      'Le serveur n\'a pas répondu dans les délais impartis (' +
      Math.round(timeoutMs / 1000) + ' s).'
    );
  }
  if (error.message && (
    error.message.includes('Failed to fetch') ||
    error.message.includes('NetworkError') ||
    error.message.includes('network')
  )) {
    return new Error('Impossible de se connecter au serveur.\nVérifiez l\'URL : ' + baseUrl);
  }
  return error;
}

// ── Fabrique ─────────────────────────────────────────────────────────────────

export function createClientFromConfig(config) {
  return new XtreamClient(config.serverUrl, config.port, config.username, config.password);
}
