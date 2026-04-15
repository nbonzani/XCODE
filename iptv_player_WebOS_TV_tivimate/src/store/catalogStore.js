/**
 * src/store/catalogStore.js
 * Store Zustand — catalogue films, séries, catégories, filtres.
 *
 * Portage de l'état géré dans MainWindow._refresh() / _apply_filters().
 * Les données brutes (allMovies, allSeries) sont chargées depuis IndexedDB
 * via cacheService.js. Les données filtrées (filteredMovies, filteredSeries)
 * sont recalculées en mémoire à chaque changement de filtre.
 */

import { create } from 'zustand';

/**
 * Filtre un tableau d'items selon les critères actifs.
 * Portage direct de search_movies() / search_series() de cache_db.py.
 *
 * @param {Array}  items       - Tableau brut de films ou de séries
 * @param {string} query       - Texte recherché dans le nom
 * @param {string} categoryId  - ID de catégorie ("" = toutes)
 * @param {boolean} frenchOnly - Filtre FR uniquement
 * @param {Array}  frenchCategoryIds - IDs des catégories françaises (pré-calculé)
 * @returns {Array}
 */
function applyFilters(items, query, categoryId, frenchOnly, frenchCategoryIds, selectedCategoryIds) {
  let result = items;

  // Filtre catalogue (catégories sélectionnées par l'utilisateur dans le filtre)
  if (selectedCategoryIds && selectedCategoryIds.length > 0) {
    const selSet = new Set(selectedCategoryIds.map(String));
    result = result.filter((item) => selSet.has(String(item.category_id)));
  }

  // Filtre texte (insensible à la casse, insensible aux accents)
  if (query && query.trim()) {
    const q = query.trim().toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '');
    result = result.filter((item) => {
      const name = (item.name || '').toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '');
      return name.includes(q);
    });
  }

  // Filtre catégorie (sidebar)
  if (categoryId && categoryId !== '') {
    result = result.filter((item) => String(item.category_id) === String(categoryId));
  }

  // Filtre FR uniquement
  if (frenchOnly && frenchCategoryIds.length > 0) {
    const frSet = new Set(frenchCategoryIds.map(String));
    result = result.filter((item) => frSet.has(String(item.category_id)));
  }

  return result;
}

export const useCatalogStore = create((set, get) => ({
  // ── Données brutes (chargées depuis IndexedDB) ──────────────────────────
  allMovies: [],
  allSeries: [],

  // ── Catégories ──────────────────────────────────────────────────────────
  movieCategories: [],   // [{ category_id, category_name }]
  seriesCategories: [],  // [{ category_id, category_name }]

  // ── IDs des catégories françaises (calculé lors du chargement) ──────────
  frenchMovieCategoryIds: [],
  frenchSeriesCategoryIds: [],

  // ── Données filtrées (affichées dans ContentGrid) ───────────────────────
  filteredMovies: [],
  filteredSeries: [],

  // ── Filtres actifs ───────────────────────────────────────────────────────
  searchQuery: '',
  selectedCategoryId: '',

  // ── État de chargement ──────────────────────────────────────────────────
  isLoading: false,
  loadError: null,

  // ── Actions : chargement depuis le cache ────────────────────────────────

  /**
   * Charge le catalogue complet depuis IndexedDB.
   * Appelé au montage de HomeScreen et après une synchronisation réussie.
   * @param {Function} loadFromCache              - Fonction async de cacheService.js
   * @param {boolean}  frenchOnly                 - Filtre FR de la config
   * @param {string[]} selectedMovieCategories    - IDs catégories films sélectionnées ([] = toutes)
   * @param {string[]} selectedSeriesCategories   - IDs catégories séries sélectionnées ([] = toutes)
   */
  loadCatalog: async (loadFromCache, frenchOnly, selectedMovieCategories, selectedSeriesCategories) => {
    set({ isLoading: true, loadError: null });
    try {
      const { movies, series, movieCategories, seriesCategories } = await loadFromCache();

      // Détection des catégories françaises
      // Portage de la logique de cache_db.py : mots-clés FR dans le nom
      // Catégorie française = nom commençant par "FR" (insensible à la casse)
      const isFrench = (name) => {
        if (!name) return false;
        if (/(^|[^A-Za-z])FR(?![A-Za-z])/.test(name)) return true;
        if (/(^|[^A-Za-z])(?:FRENCH|FRANCE)(?![A-Za-z])/i.test(name)) return true;
        return false;
      };

      const frenchMovieCategoryIds = movieCategories
        .filter((c) => isFrench(c.category_name || ''))
        .map((c) => String(c.category_id));

      const frenchSeriesCategoryIds = seriesCategories
        .filter((c) => isFrench(c.category_name || ''))
        .map((c) => String(c.category_id));

      // Calcul initial des données filtrées
      const { searchQuery, selectedCategoryId } = get();
      const filteredMovies = applyFilters(
        movies, searchQuery, selectedCategoryId, frenchOnly, frenchMovieCategoryIds,
        selectedMovieCategories || []
      );
      const filteredSeries = applyFilters(
        series, searchQuery, selectedCategoryId, frenchOnly, frenchSeriesCategoryIds,
        selectedSeriesCategories || []
      );

      set({
        allMovies: movies,
        allSeries: series,
        movieCategories,
        seriesCategories,
        frenchMovieCategoryIds,
        frenchSeriesCategoryIds,
        filteredMovies,
        filteredSeries,
        isLoading: false,
      });
    } catch (error) {
      console.error('[CatalogStore] Erreur chargement catalogue:', error);
      set({ isLoading: false, loadError: error.message });
    }
  },

  // ── Actions : filtres ────────────────────────────────────────────────────

  /**
   * Met à jour le texte de recherche et recalcule les résultats filtrés.
   * @param {string}   query                    - Texte saisi dans SearchInput
   * @param {string}   activeTab                - 'movies' ou 'series'
   * @param {boolean}  frenchOnly
   * @param {string[]} selectedMovieCategories  - IDs catégories films ([] = toutes)
   * @param {string[]} selectedSeriesCategories - IDs catégories séries ([] = toutes)
   */
  setSearchQuery: (query, activeTab, frenchOnly, selectedMovieCategories, selectedSeriesCategories) => {
    const state = get();
    const { selectedCategoryId, allMovies, allSeries,
            frenchMovieCategoryIds, frenchSeriesCategoryIds } = state;

    const filteredMovies = activeTab === 'movies'
      ? applyFilters(allMovies, query, selectedCategoryId, frenchOnly, frenchMovieCategoryIds, selectedMovieCategories || [])
      : state.filteredMovies;

    const filteredSeries = activeTab === 'series'
      ? applyFilters(allSeries, query, selectedCategoryId, frenchOnly, frenchSeriesCategoryIds, selectedSeriesCategories || [])
      : state.filteredSeries;

    set({ searchQuery: query, filteredMovies, filteredSeries });
  },

  /**
   * Met à jour la catégorie sélectionnée et recalcule les résultats.
   * @param {string}   categoryId               - ID de catégorie ("" = toutes)
   * @param {string}   activeTab
   * @param {boolean}  frenchOnly
   * @param {string[]} selectedMovieCategories  - IDs catégories films ([] = toutes)
   * @param {string[]} selectedSeriesCategories - IDs catégories séries ([] = toutes)
   */
  setCategory: (categoryId, activeTab, frenchOnly, selectedMovieCategories, selectedSeriesCategories) => {
    const state = get();
    const { searchQuery, allMovies, allSeries,
            frenchMovieCategoryIds, frenchSeriesCategoryIds } = state;

    const filteredMovies = activeTab === 'movies'
      ? applyFilters(allMovies, searchQuery, categoryId, frenchOnly, frenchMovieCategoryIds, selectedMovieCategories || [])
      : state.filteredMovies;

    const filteredSeries = activeTab === 'series'
      ? applyFilters(allSeries, searchQuery, categoryId, frenchOnly, frenchSeriesCategoryIds, selectedSeriesCategories || [])
      : state.filteredSeries;

    set({ selectedCategoryId: categoryId, filteredMovies, filteredSeries });
  },

  /**
   * Réinitialise les filtres et recharge le catalogue filtré.
   * @param {string}  activeTab
   * @param {boolean} frenchOnly
   */
  resetFilters: (activeTab, frenchOnly) => {
    const state = get();
    const { allMovies, allSeries, frenchMovieCategoryIds, frenchSeriesCategoryIds } = state;

    set({
      searchQuery: '',
      selectedCategoryId: '',
      filteredMovies: applyFilters(allMovies, '', '', frenchOnly, frenchMovieCategoryIds),
      filteredSeries: applyFilters(allSeries, '', '', frenchOnly, frenchSeriesCategoryIds),
    });
  },

  /**
   * Injecte des données de test (mock) pour le développement sans serveur.
   * À appeler depuis HomeScreen si le catalogue est vide.
   */
  loadMockData: () => {
    const mockMovies = Array.from({ length: 48 }, (_, i) => ({
      stream_id: i + 1,
      name: `Film de test ${i + 1}`,
      category_id: String((i % 4) + 1),
      stream_icon: '',
      rating: (Math.random() * 4 + 6).toFixed(1),
      container_extension: 'mkv',
    }));

    const mockSeries = Array.from({ length: 30 }, (_, i) => ({
      series_id: i + 1,
      name: `Série de test ${i + 1}`,
      category_id: String((i % 3) + 1),
      cover: '',
      rating: (Math.random() * 4 + 6).toFixed(1),
    }));

    const mockMovieCategories = [
      { category_id: '1', category_name: 'Action FR' },
      { category_id: '2', category_name: 'Comédie VF' },
      { category_id: '3', category_name: 'Drame' },
      { category_id: '4', category_name: 'Science-Fiction' },
    ];

    const mockSeriesCategories = [
      { category_id: '1', category_name: 'Séries FR' },
      { category_id: '2', category_name: 'Séries VF' },
      { category_id: '3', category_name: 'Séries US' },
    ];

    set({
      allMovies: mockMovies,
      allSeries: mockSeries,
      movieCategories: mockMovieCategories,
      seriesCategories: mockSeriesCategories,
      frenchMovieCategoryIds: ['1', '2'],
      frenchSeriesCategoryIds: ['1', '2'],
      filteredMovies: mockMovies,
      filteredSeries: mockSeries,
      isLoading: false,
    });
  },
}));
