/**
 * src/services/watchPositionService.js
 * Sauvegarde de la position de lecture pour chaque film/épisode.
 *
 * Stockage : localStorage, clé = "iptv_pos_<itemId>"
 *
 * Règles :
 *   - Position sauvegardée seulement entre 2 % et 90 % de la durée.
 *   - En dessous de 2 % → ignoré (début, pas utile).
 *   - Au-dessus de 90 % → position effacée (considéré comme terminé).
 *   - Durée < 30 s → ignoré (contenu trop court).
 */

const KEY_PREFIX = 'iptv_pos_';

/**
 * Sauvegarde la position de lecture.
 * @param {number|string} itemId   stream_id ou episode id
 * @param {number}        position Temps en secondes
 * @param {number}        duration Durée totale en secondes
 */
export function saveWatchPosition(itemId, position, duration) {
  if (!itemId || !duration || isNaN(duration) || duration < 30) return;
  const pct = position / duration;
  if (pct > 0.90) {
    // Terminé → effacer la position résiduelle
    clearWatchPosition(itemId);
    return;
  }
  if (pct < 0.02) return; // Trop au début, ne pas sauvegarder
  try {
    localStorage.setItem(KEY_PREFIX + String(itemId), JSON.stringify({
      position: Math.floor(position),
      duration: Math.floor(duration),
      savedAt:  Date.now(),
    }));
  } catch { /* localStorage plein — non bloquant */ }
}

/**
 * Retourne la position sauvegardée en secondes (0 si absente ou expirée).
 * @param {number|string} itemId
 * @returns {number}
 */
export function getWatchPosition(itemId) {
  if (!itemId) return 0;
  try {
    const raw = localStorage.getItem(KEY_PREFIX + String(itemId));
    if (!raw) return 0;
    const data = JSON.parse(raw);
    return data.position || 0;
  } catch { return 0; }
}

/**
 * Efface la position sauvegardée (lecture terminée, ou reset manuel).
 * @param {number|string} itemId
 */
export function clearWatchPosition(itemId) {
  if (!itemId) return;
  try { localStorage.removeItem(KEY_PREFIX + String(itemId)); } catch {}
}

/**
 * Formate une position en mm:ss ou h:mm:ss pour l'affichage.
 * @param {number} seconds
 * @returns {string}
 */
export function formatPosition(seconds) {
  if (!seconds || seconds < 1) return '';
  var h = Math.floor(seconds / 3600);
  var m = Math.floor((seconds % 3600) / 60);
  var s = Math.floor(seconds % 60);
  if (h > 0) return h + 'h' + String(m).padStart(2,'0') + 'm';
  return m + 'min ' + String(s).padStart(2,'0') + 's';
}
