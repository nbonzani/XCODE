/**
 * src/services/watchHistoryService.js
 * Suivi de visionnage des épisodes.
 * Portage de mark_episode_watched / get_watched_episodes_set de cache_db.py.
 *
 * Stockage : localStorage (clé par série) — suffisant pour le périmètre webOS.
 * IndexedDB sera utilisé si le volume dépasse les limites du localStorage.
 *
 * Format de stockage :
 *   clé   : "watched_series_<series_id>"
 *   valeur: JSON.stringify({ "<episode_id>": "<iso_date>", ... })
 */

const KEY_PREFIX = 'watched_series_';
const LAST_WATCHED_KEY = 'iptv_last_watched_series';

/**
 * Marque un épisode comme visionné.
 * @param {number|string} episodeId
 * @param {number|string} seriesId
 */
export function markEpisodeWatched(episodeId, seriesId) {
  try {
    const key  = KEY_PREFIX + seriesId;
    const raw  = localStorage.getItem(key);
    const data = raw ? JSON.parse(raw) : {};
    data[String(episodeId)] = new Date().toISOString();
    localStorage.setItem(key, JSON.stringify(data));
  } catch {
    // localStorage plein ou inaccessible — non bloquant
  }
}

/**
 * Enregistre la dernière série/épisode visionné pour la reprise.
 * @param {number|string} seriesId
 * @param {string}        seriesName
 * @param {string}        episodeTitle
 * @param {number|string} episodeId   — ID de l'épisode (pour retrouver la position sauvegardée)
 * @param {string}        streamUrl   — URL du flux (pour relancer directement)
 */
export function setLastWatchedSeries(seriesId, seriesName, episodeTitle, episodeId, streamUrl) {
  try {
    localStorage.setItem(LAST_WATCHED_KEY, JSON.stringify({
      seriesId,
      seriesName,
      episodeTitle,
      episodeId:  episodeId  || null,
      streamUrl:  streamUrl  || null,
      date: new Date().toISOString(),
    }));
  } catch { /* non bloquant */ }
}

/**
 * Retourne la dernière série visionnée, ou null.
 * @returns {{ seriesId, seriesName, episodeTitle, episodeId, streamUrl, date }|null}
 */
export function getLastWatchedSeries() {
  try {
    const raw = localStorage.getItem(LAST_WATCHED_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch { return null; }
}

/**
 * Retourne l'ensemble des IDs d'épisodes visionnés pour une série.
 * @param {number|string} seriesId
 * @returns {Set<string>}
 */
export function getWatchedEpisodesSet(seriesId) {
  try {
    const raw = localStorage.getItem(KEY_PREFIX + seriesId);
    if (!raw) return new Set();
    return new Set(Object.keys(JSON.parse(raw)));
  } catch {
    return new Set();
  }
}
