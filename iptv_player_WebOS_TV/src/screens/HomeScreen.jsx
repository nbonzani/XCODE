/**
 * HomeScreen.jsx
 *
 * Navigation télécommande :
 *
 * [Toolbar] Recherche → Catégorie → Synchroniser → Vider cache → Paramètres
 *               ↓                                                     ↑
 * [TabBar]  Films  →  Séries                                     ↑ depuis grille
 *               ↓↑
 * [Grille]  carte1 → carte2 → …
 *
 * Règles :
 * - Toolbar : ←/→ entre éléments, ↓ vers TabBar
 * - TabBar  : ←/→ entre onglets, ↑ vers Toolbar, ↓ vers grille
 * - Grille  : ←/→/↓ dans la grille, ↑ première ligne → TabBar
 */

import React, { useEffect, useCallback, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAppStore }     from '../store/appStore.js';
import { useCatalogStore } from '../store/catalogStore.js';
import { loadCatalog, loadCatalogFast, needsSync } from '../services/cacheService.js';
import { useSync }         from '../hooks/useSync.js';
import { usePlayerStore }  from '../store/playerStore.js';
import { createClientFromConfig } from '../services/xtreamApi.js';
import { getLastWatchedSeries } from '../services/watchHistoryService.js';
import { getFavorites, getFavoritesCount } from '../services/favoritesService.js';
import { getWatchPosition, formatPosition } from '../services/watchPositionService.js';
import { KEY } from '../constants/keyCodes.js';

import TabBar      from '../components/home/TabBar.jsx';
import Toolbar     from '../components/home/Toolbar.jsx';
import ContentGrid from '../components/home/ContentGrid.jsx';
import SyncScreen  from './SyncScreen.jsx';
import './HomeScreen.css';

export default function HomeScreen() {
  const navigate = useNavigate();

  const { config, activeTab, setActiveTab, syncStatus } = useAppStore();
  const {
    filteredMovies, filteredSeries,
    movieCategories, seriesCategories,
    searchQuery, selectedCategoryId,
    isLoading,
    setSearchQuery, setCategory,
    loadCatalog: loadCatalogStore,
  } = useCatalogStore();

  const { sync, syncFresh, isSyncing } = useSync();
  const { playSingle } = usePlayerStore();

  const toolbarRef = useRef(null);
  const tabBarRef  = useRef(null);
  const gridRef    = useRef(null);
  const resumeRef  = useRef(null);

  // ── Bandeau de reprise série ──────────────────────────────────────────
  const [lastWatched, setLastWatched] = useState(null);
  useEffect(() => {
    setLastWatched(getLastWatchedSeries());
  }, []);

  // ── Favoris ───────────────────────────────────────────────────────────
  const [favorites, setFavorites] = useState({ movies: [], series: [] });
  const [favCount, setFavCount] = useState(0);
  const refreshFavorites = useCallback(() => {
    setFavorites(getFavorites());
    setFavCount(getFavoritesCount());
  }, []);
  useEffect(() => { refreshFavorites(); }, [refreshFavorites]);
  // Rafraîchir les favoris quand on revient sur HomeScreen (retour du player/série)
  useEffect(() => {
    const onFocus = () => refreshFavorites();
    window.addEventListener('focus', onFocus);
    return () => window.removeEventListener('focus', onFocus);
  }, [refreshFavorites]);
  const favoriteItems = activeTab === 'favorites'
    ? [...favorites.movies, ...favorites.series]
    : [];

  // ── Chargement : rapide (60 items) puis complet ───────────────────────
  useEffect(() => {
    const alreadyLoaded = useCatalogStore.getState().allMovies.length > 0;
    if (alreadyLoaded) {
      // Déjà en mémoire → focus direct sur la grille
      setTimeout(() => tabBarRef.current?.focusActive(), 100);
      return;
    }

    // Étape 1 : affichage rapide des premiers items depuis IndexedDB
    loadCatalogStore(loadCatalogFast, config.frenchOnly).then(async () => {
      // Étape 2 : chargement complet en arrière-plan
      loadCatalogStore(loadCatalog, config.frenchOnly).then(async () => {
        const shouldSync = await needsSync(30);
        const isEmpty    = useCatalogStore.getState().allMovies.length === 0;
        if (shouldSync || isEmpty) sync();
      });
    });

    // Focus initial sur le TabBar après le premier rendu
    setTimeout(() => tabBarRef.current?.focusActive(), 300);
  }, []);

  // ── Callbacks de navigation inter-zones ──────────────────────────────

  // Toolbar ↓ → TabBar
  const handleToolbarDown = useCallback(() => {
    tabBarRef.current?.focusActive();
  }, []);

  // TabBar ↑ → Toolbar
  const handleTabBarUp = useCallback(() => {
    toolbarRef.current?.focusFirst();
  }, []);

  // Aller à la première carte de la grille
  const focusFirstCard = useCallback(() => {
    const first = document.querySelector('.content-grid .content-card[tabindex="0"]');
    if (first) first.focus();
    else document.querySelector('.content-card')?.focus();
  }, []);

  // TabBar ↓ → bandeau de reprise (si présent) → sinon grille
  const handleTabBarDown = useCallback(() => {
    if (lastWatched && resumeRef.current) {
      resumeRef.current.focus();
    } else {
      focusFirstCard();
    }
  }, [lastWatched, focusFirstCard]);

  // Bandeau de reprise ↑ → TabBar
  const handleResumeUp = useCallback(() => {
    tabBarRef.current?.focusActive();
  }, []);

  // Bandeau de reprise ↓ → grille
  const handleResumeDown = useCallback(() => {
    focusFirstCard();
  }, [focusFirstCard]);

  // Grille première ligne ↑ → bandeau de reprise (si présent) → sinon TabBar
  const handleGridUp = useCallback(() => {
    if (lastWatched && resumeRef.current) {
      resumeRef.current.focus();
    } else {
      tabBarRef.current?.focusActive();
    }
  }, [lastWatched]);

  // ── Sélection d'un item ───────────────────────────────────────────────
  const handleItemSelect = useCallback((item, type) => {
    const isSeries = type === 'series' || (type === 'mixed' && item.series_id && !item.stream_id);
    if (isSeries) {
      navigate(`/series/${item.series_id}`);
      return;
    }
    const client   = createClientFromConfig(config);
    const url      = client.getStreamUrl(item.stream_id, item.container_extension || 'mkv');
    const savedPos = getWatchPosition(item.stream_id);
    playSingle(url, item.name, 'movie', item.stream_id, savedPos);
    navigate('/player');
  }, [navigate, config, playSingle]);

  // ── Filtres ────────────────────────────────────────────────────────────
  const handleSearchChange   = useCallback((q)   => setSearchQuery(q, activeTab, config.frenchOnly),   [activeTab, config.frenchOnly, setSearchQuery]);
  const handleCategoryChange = useCallback((cat) => setCategory(cat, activeTab, config.frenchOnly),    [activeTab, config.frenchOnly, setCategory]);

  // Réinitialiser le filtre catégorie quand on change d'onglet
  const handleTabChange = useCallback((tab) => {
    setActiveTab(tab);
    setCategory('', tab, config.frenchOnly);
    setSearchQuery('', tab, config.frenchOnly);
  }, [setActiveTab, setCategory, setSearchQuery, config.frenchOnly]);

  const rawCategories    = activeTab === 'movies' ? movieCategories : seriesCategories;
  const frenchFiltered   = rawCategories.filter((c) => {
    const n = c.category_name || '';
    return /(^|[^A-Za-z])FR(?![A-Za-z])/.test(n) || /(^|[^A-Za-z])(?:FRENCH|FRANCE)(?![A-Za-z])/i.test(n);
  });
  // Si frenchOnly est actif mais qu'aucune catégorie FR n'existe sur ce serveur,
  // on affiche toutes les catégories (cohérent avec applyFilters qui ne filtre pas non plus)
  const activeCategories = config.frenchOnly && frenchFiltered.length > 0
    ? frenchFiltered
    : rawCategories;

  return (
    <div className="home-screen">

      <Toolbar
        ref={toolbarRef}
        searchQuery={searchQuery}
        onSearchChange={handleSearchChange}
        selectedCategoryId={selectedCategoryId}
        onCategoryChange={handleCategoryChange}
        categories={activeCategories}
        isSyncing={isSyncing}
        onSync={sync}
        onSyncFresh={syncFresh}
        onSettings={() => navigate('/settings')}
        onFocusDown={handleToolbarDown}
      />

      <TabBar
        ref={tabBarRef}
        activeTab={activeTab}
        onTabChange={handleTabChange}
        movieCount={filteredMovies.length}
        seriesCount={filteredSeries.length}
        favoritesCount={favCount}
        onFocusUp={handleTabBarUp}
        onFocusDown={handleTabBarDown}
      />

      {/* Bandeau de reprise série */}
      {lastWatched && (
        <div
          ref={resumeRef}
          className="home-screen__resume"
          tabIndex={0}
          role="button"
          onClick={() => {
            // Si on a l'URL de l'épisode → lancer directement au moment sauvegardé
            if (lastWatched.streamUrl && lastWatched.episodeId) {
              const pos = getWatchPosition(lastWatched.episodeId);
              playSingle(lastWatched.streamUrl, lastWatched.episodeTitle, 'episode', lastWatched.episodeId, pos);
              navigate('/player');
            } else {
              // Fallback : ouvrir la fiche de la série
              navigate(`/series/${lastWatched.seriesId}`);
            }
          }}
          onKeyDown={(e) => {
            if (e.keyCode === KEY.OK) {
              e.preventDefault();
              if (lastWatched.streamUrl && lastWatched.episodeId) {
                const pos = getWatchPosition(lastWatched.episodeId);
                playSingle(lastWatched.streamUrl, lastWatched.episodeTitle, 'episode', lastWatched.episodeId, pos);
                navigate('/player');
              } else {
                navigate(`/series/${lastWatched.seriesId}`);
              }
            }
            else if (e.keyCode === KEY.UP)   { e.preventDefault(); handleResumeUp(); }
            else if (e.keyCode === KEY.DOWN)  { e.preventDefault(); handleResumeDown(); }
          }}
        >
          <span className="home-screen__resume-icon">▶</span>
          <span className="home-screen__resume-text">
            Reprendre : <strong>{lastWatched.seriesName}</strong> — {lastWatched.episodeTitle}
            {lastWatched.episodeId && getWatchPosition(lastWatched.episodeId) > 0 && (
              <span className="home-screen__resume-pos"> ({formatPosition(getWatchPosition(lastWatched.episodeId))})</span>
            )}
          </span>
        </div>
      )}

      <div ref={gridRef} className="home-screen__content">
        {isLoading ? (
          <div className="home-screen__loading">
            <div className="spinner" />
            <p>Chargement du catalogue…</p>
          </div>
        ) : (
          <>
            {activeTab === 'movies' && (
              <ContentGrid
                items={filteredMovies}
                type="movie"
                onItemSelect={handleItemSelect}
                isActive={activeTab === 'movies'}
                onFocusUp={handleGridUp}
              />
            )}
            {activeTab === 'series' && (
              <ContentGrid
                items={filteredSeries}
                type="series"
                onItemSelect={handleItemSelect}
                isActive={activeTab === 'series'}
                onFocusUp={handleGridUp}
              />
            )}
            {activeTab === 'favorites' && (
              <ContentGrid
                items={favoriteItems}
                type="mixed"
                onItemSelect={handleItemSelect}
                isActive={activeTab === 'favorites'}
                onFocusUp={handleGridUp}
              />
            )}
          </>
        )}
      </div>

      {/* Écran de chargement plein écran pendant la synchronisation */}
      {isSyncing && <SyncScreen />}

      {/* StatusBar — message post-sync (succès / erreur) */}
      {!isSyncing && syncStatus ? (
        <div className="home-screen__statusbar">{syncStatus}</div>
      ) : null}

    </div>
  );
}
