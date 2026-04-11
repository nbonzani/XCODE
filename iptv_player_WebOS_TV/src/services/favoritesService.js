/**
 * src/services/favoritesService.js
 * Gestion des favoris — stockage localStorage.
 *
 * Format :
 *   clé   : "iptv_favorites"
 *   valeur : { movies: [{ stream_id, name, stream_icon, ... }], series: [{ series_id, name, cover, ... }] }
 */

const FAVORITES_KEY = 'iptv_favorites';

function readFavorites() {
  try {
    const raw = localStorage.getItem(FAVORITES_KEY);
    if (!raw) return { movies: [], series: [] };
    const data = JSON.parse(raw);
    return {
      movies: Array.isArray(data.movies) ? data.movies : [],
      series: Array.isArray(data.series) ? data.series : [],
    };
  } catch {
    return { movies: [], series: [] };
  }
}

function writeFavorites(data) {
  try {
    localStorage.setItem(FAVORITES_KEY, JSON.stringify(data));
  } catch { /* localStorage plein — non bloquant */ }
}

/**
 * Ajoute un item aux favoris.
 * @param {Object} item - L'objet film ou série complet
 * @param {'movie'|'series'} type
 */
export function addFavorite(item, type) {
  const data = readFavorites();
  if (type === 'movie' || type === 'movies') {
    if (!data.movies.some((m) => m.stream_id === item.stream_id)) {
      data.movies.unshift(item);
    }
  } else {
    if (!data.series.some((s) => s.series_id === item.series_id)) {
      data.series.unshift(item);
    }
  }
  writeFavorites(data);
}

/**
 * Retire un item des favoris.
 * @param {number|string} itemId
 * @param {'movie'|'series'} type
 */
export function removeFavorite(itemId, type) {
  const data = readFavorites();
  if (type === 'movie' || type === 'movies') {
    data.movies = data.movies.filter((m) => m.stream_id !== itemId);
  } else {
    data.series = data.series.filter((s) => s.series_id !== itemId);
  }
  writeFavorites(data);
}

/**
 * Bascule un item dans les favoris (ajoute si absent, retire si présent).
 * @returns {boolean} true si ajouté, false si retiré
 */
export function toggleFavorite(item, type) {
  if (isFavorite(type === 'movie' || type === 'movies' ? item.stream_id : item.series_id, type)) {
    removeFavorite(type === 'movie' || type === 'movies' ? item.stream_id : item.series_id, type);
    return false;
  }
  addFavorite(item, type);
  return true;
}

/**
 * Vérifie si un item est dans les favoris.
 * @param {number|string} itemId
 * @param {'movie'|'series'} type
 * @returns {boolean}
 */
export function isFavorite(itemId, type) {
  const data = readFavorites();
  if (type === 'movie' || type === 'movies') {
    return data.movies.some((m) => m.stream_id === itemId);
  }
  return data.series.some((s) => s.series_id === itemId);
}

/**
 * Retourne tous les favoris.
 * @returns {{ movies: Array, series: Array }}
 */
export function getFavorites() {
  return readFavorites();
}

/**
 * Retourne le nombre total de favoris.
 * @returns {number}
 */
export function getFavoritesCount() {
  const data = readFavorites();
  return data.movies.length + data.series.length;
}
