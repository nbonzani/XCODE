/**
 * src/services/cacheService.js
 * Cache local IndexedDB — portage de cache_db.py (SQLite → IndexedDB).
 *
 * Schéma IndexedDB :
 *   DB name    : "iptv_cache"
 *   Version    : 1
 *   Stores     :
 *     "movies"            → films          (keyPath: stream_id)
 *     "series"            → séries         (keyPath: series_id)
 *     "vod_categories"    → catég. films   (keyPath: category_id)
 *     "series_categories" → catég. séries  (keyPath: category_id)
 *     "sync_meta"         → métadonnées    (keyPath: key)
 *
 * Mots-clés FR (portage de FRENCH_KEYWORDS de cache_db.py)
 */

import { openDB } from 'idb';

// ── Constantes ───────────────────────────────────────────────────────────────

const DB_NAME    = 'iptv_cache';
const DB_VERSION = 1;

// Une catégorie est française si son nom commence par "FR" (insensible à la casse).

// ── Ouverture / initialisation de la base ────────────────────────────────────

let _db = null;

async function getDB() {
  if (_db) return _db;

  _db = await openDB(DB_NAME, DB_VERSION, {
    upgrade(db) {
      // movies
      if (!db.objectStoreNames.contains('movies')) {
        const ms = db.createObjectStore('movies', { keyPath: 'stream_id' });
        ms.createIndex('by_category', 'category_id');
        ms.createIndex('by_name',     'name');
        ms.createIndex('by_french',   'is_french');
      }
      // series
      if (!db.objectStoreNames.contains('series')) {
        const ss = db.createObjectStore('series', { keyPath: 'series_id' });
        ss.createIndex('by_category', 'category_id');
        ss.createIndex('by_name',     'name');
        ss.createIndex('by_french',   'is_french');
      }
      // vod_categories
      if (!db.objectStoreNames.contains('vod_categories')) {
        const vc = db.createObjectStore('vod_categories', { keyPath: 'category_id' });
        vc.createIndex('by_french', 'is_french');
      }
      // series_categories
      if (!db.objectStoreNames.contains('series_categories')) {
        const sc = db.createObjectStore('series_categories', { keyPath: 'category_id' });
        sc.createIndex('by_french', 'is_french');
      }
      // sync_meta
      if (!db.objectStoreNames.contains('sync_meta')) {
        db.createObjectStore('sync_meta', { keyPath: 'key' });
      }
    },
  });

  return _db;
}

// ── Utilitaires ───────────────────────────────────────────────────────────────

/**
 * Détecte si un nom de catégorie est français.
 * Portage de _lang_keyword_matches() de PC_Gestion_M3U/core/filters.py.
 *
 * Règles :
 * - "FR" (2 lettres) : doit être en MAJUSCULES dans le texte original,
 *   sans lettre adjacente (ni avant ni après).
 *   Matche : "VOD | FR - Action", "FR Movies", "|FR|"
 *   Ne matche pas : "AFRICA", "French", "fr"
 * - "FRENCH", "FRANCE" : insensible à la casse, sans lettre adjacente.
 *   Matche : "French Movies", "FRANCE VOD"
 *   Ne matche pas : "FRENCHFRIES"
 *
 * Note : pas de lookbehind (?<!) pour compatibilité ES2015 / webOS.
 */
export function isFrench(categoryName) {
  if (!categoryName) return false;
  // Code 2 lettres FR — sensible à la casse, sans lettre adjacente
  if (/(^|[^A-Za-z])FR(?![A-Za-z])/.test(categoryName)) return true;
  // Mots longs — insensible à la casse, sans lettre adjacente
  if (/(^|[^A-Za-z])(?:FRENCH|FRANCE)(?![A-Za-z])/i.test(categoryName)) return true;
  return false;
}

function safeFloat(value) {
  const f = parseFloat(value);
  return isNaN(f) ? 0 : f;
}

// ── Sauvegarde — catégories films ─────────────────────────────────────────────

/**
 * Sauvegarde toutes les catégories de films (remplace les existantes).
 * Portage de save_vod_categories() de cache_db.py.
 * @param {Array} categories
 */
export async function saveVodCategories(categories) {
  const db = await getDB();
  const tx = db.transaction('vod_categories', 'readwrite');
  await tx.store.clear();
  for (const cat of categories) {
    await tx.store.put({
      category_id:   String(cat.category_id ?? ''),
      category_name: cat.category_name ?? '',
      parent_id:     String(cat.parent_id ?? ''),
      is_french:     isFrench(cat.category_name) ? 1 : 0,
    });
  }
  await tx.done;
}

// ── Sauvegarde — films ────────────────────────────────────────────────────────

/**
 * Sauvegarde la liste complète des films.
 * Portage de save_movies() de cache_db.py.
 * @param {Array}  movies
 * @param {Object} categoriesMap - { category_id: category_name }
 */
export async function saveMovies(movies, categoriesMap) {
  const db = await getDB();

  // Récupérer les IDs des catégories françaises
  const frenchCatIds = new Set();
  const allVodCats   = await db.getAll('vod_categories');
  for (const cat of allVodCats) {
    if (cat.is_french) frenchCatIds.add(cat.category_id);
  }

  const cachedAt = new Date().toISOString();
  const tx       = db.transaction('movies', 'readwrite');
  await tx.store.clear();

  for (const movie of movies) {
    const catId = String(movie.category_id ?? '');
    await tx.store.put({
      stream_id:           movie.stream_id,
      name:                movie.name ?? '',
      category_id:         catId,
      category_name:       categoriesMap[catId] ?? '',
      stream_icon:         movie.stream_icon ?? '',
      container_extension: movie.container_extension ?? 'mkv',
      rating:              safeFloat(movie.rating),
      added:               movie.added ?? '',
      cached_at:           cachedAt,
      is_french:           frenchCatIds.has(catId) ? 1 : 0,
    });
  }
  await tx.done;
}

// ── Sauvegarde — catégories séries ────────────────────────────────────────────

/**
 * Portage de save_series_categories() de cache_db.py.
 * @param {Array} categories
 */
export async function saveSeriesCategories(categories) {
  const db = await getDB();
  const tx = db.transaction('series_categories', 'readwrite');
  await tx.store.clear();
  for (const cat of categories) {
    await tx.store.put({
      category_id:   String(cat.category_id ?? ''),
      category_name: cat.category_name ?? '',
      parent_id:     String(cat.parent_id ?? ''),
      is_french:     isFrench(cat.category_name) ? 1 : 0,
    });
  }
  await tx.done;
}

// ── Sauvegarde — séries ───────────────────────────────────────────────────────

/**
 * Portage de save_series_list() de cache_db.py.
 * @param {Array}  seriesList
 * @param {Object} categoriesMap
 */
export async function saveSeriesList(seriesList, categoriesMap) {
  const db = await getDB();

  const frenchCatIds = new Set();
  const allSeriesCats = await db.getAll('series_categories');
  for (const cat of allSeriesCats) {
    if (cat.is_french) frenchCatIds.add(cat.category_id);
  }

  const cachedAt = new Date().toISOString();
  const tx       = db.transaction('series', 'readwrite');
  await tx.store.clear();

  for (const s of seriesList) {
    const catId = String(s.category_id ?? '');
    await tx.store.put({
      series_id:     s.series_id,
      name:          s.name ?? '',
      category_id:   catId,
      category_name: categoriesMap[catId] ?? '',
      cover:         s.cover ?? '',
      rating:        safeFloat(s.rating),
      genre:         s.genre ?? '',
      release_date:  s.release_date ?? '',
      plot:          s.plot ?? '',
      cached_at:     cachedAt,
      is_french:     frenchCatIds.has(catId) ? 1 : 0,
    });
  }
  await tx.done;
}

// ── Lecture — catalogue complet ───────────────────────────────────────────────

/**
 * Charge tout le catalogue depuis IndexedDB.
 * Appelé par catalogStore.loadCatalog().
 * @returns {{ movies, series, movieCategories, seriesCategories }}
 */
export async function loadCatalog() {
  const db = await getDB();
  const [movies, series, movieCategories, seriesCategories] = await Promise.all([
    db.getAll('movies'),
    db.getAll('series'),
    db.getAll('vod_categories'),
    db.getAll('series_categories'),
  ]);
  return { movies, series, movieCategories, seriesCategories };
}

/**
 * Charge un sous-ensemble rapide du catalogue (60 premiers items par store).
 * Permet un premier affichage quasi-instantané avant le chargement complet.
 * @returns {{ movies, series, movieCategories, seriesCategories }}
 */
export async function loadCatalogFast() {
  const FAST_LIMIT = 60;
  const db = await getDB();
  const tx = db.transaction(['movies', 'series', 'vod_categories', 'series_categories'], 'readonly');

  const movies = [];
  const series = [];
  let cursor;

  cursor = await tx.objectStore('movies').openCursor();
  while (cursor && movies.length < FAST_LIMIT) {
    movies.push(cursor.value);
    cursor = await cursor.continue();
  }

  cursor = await tx.objectStore('series').openCursor();
  while (cursor && series.length < FAST_LIMIT) {
    series.push(cursor.value);
    cursor = await cursor.continue();
  }

  const [movieCategories, seriesCategories] = await Promise.all([
    tx.objectStore('vod_categories').getAll(),
    tx.objectStore('series_categories').getAll(),
  ]);

  return { movies, series, movieCategories, seriesCategories };
}

// ── Compteurs ─────────────────────────────────────────────────────────────────

export async function getMovieCount(frenchOnly = true) {
  const db    = await getDB();
  const items = await db.getAll('movies');
  return frenchOnly ? items.filter((m) => m.is_french).length : items.length;
}

export async function getSeriesCount(frenchOnly = true) {
  const db    = await getDB();
  const items = await db.getAll('series');
  return frenchOnly ? items.filter((s) => s.is_french).length : items.length;
}

// ── Métadonnées de synchronisation ────────────────────────────────────────────

/**
 * Enregistre la date de la dernière synchronisation réussie.
 * Portage de set_last_sync_date() de cache_db.py.
 */
export async function setLastSyncDate() {
  const db = await getDB();
  await db.put('sync_meta', { key: 'last_sync', value: new Date().toISOString() });
}

/**
 * Lit la date de la dernière synchronisation.
 * @returns {string|null} ISO date string ou null
 */
export async function getLastSyncDate() {
  const db  = await getDB();
  const row = await db.get('sync_meta', 'last_sync');
  return row?.value ?? null;
}

/**
 * Vérifie si une synchronisation est nécessaire.
 * Portage de needs_sync() de cache_db.py.
 * @param {number} maxAgeDays
 * @returns {Promise<boolean>}
 */
export async function needsSync(maxAgeDays = 30) {
  const lastSync = await getLastSyncDate();
  if (!lastSync) return true;
  const ageMs   = Date.now() - new Date(lastSync).getTime();
  const ageDays = ageMs / (1000 * 60 * 60 * 24);
  return ageDays >= maxAgeDays;
}

/**
 * Vide entièrement le cache (films + séries + catégories).
 * Portage de clear_cache() de cache_db.py.
 */
export async function clearCache() {
  const db = await getDB();
  const tx = db.transaction(
    ['movies', 'series', 'vod_categories', 'series_categories'],
    'readwrite'
  );
  await Promise.all([
    tx.objectStore('movies').clear(),
    tx.objectStore('series').clear(),
    tx.objectStore('vod_categories').clear(),
    tx.objectStore('series_categories').clear(),
  ]);
  await tx.done;
}
