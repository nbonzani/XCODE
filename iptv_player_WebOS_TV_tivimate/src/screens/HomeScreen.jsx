/**
 * HomeScreen.jsx — Layout TiviMate
 *
 * Navigation :
 *   ← depuis colonne 0 de la grille → ouvre la Sidebar (overlay)
 *   ← depuis Toolbar (idx 0) ou TabBar (tab 0) → ouvre la Sidebar
 *   Dans la Sidebar : ↑↓ navigue, → ou BACK ferme + retour grille
 *   Clic sur le backdrop → ferme la Sidebar
 */

import React, { useEffect, useCallback, useRef, useState } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { useAppStore }     from '../store/appStore.js';
import { useCatalogStore } from '../store/catalogStore.js';
import { loadCatalog, loadCatalogFast, needsSync } from '../services/cacheService.js';
import { useSync }         from '../hooks/useSync.js';
import { useWakeLock }     from '../hooks/useWakeLock.js';
import { usePlayerStore }  from '../store/playerStore.js';
import { createClientFromConfig } from '../services/xtreamApi.js';
import { getLastWatchedSeries } from '../services/watchHistoryService.js';
import { getFavorites, getFavoritesCount, toggleFavorite } from '../services/favoritesService.js';
import { getWatchPosition, formatPosition } from '../services/watchPositionService.js';
import { KEY } from '../constants/keyCodes.js';

import Sidebar     from '../components/home/Sidebar.jsx';
import TabBar      from '../components/home/TabBar.jsx';
import Toolbar     from '../components/home/Toolbar.jsx';
import ContentGrid from '../components/home/ContentGrid.jsx';
import SyncScreen  from './SyncScreen.jsx';
import './HomeScreen.css';

function isBackKey(kc) { return kc === 461 || kc === 8; }

export default function HomeScreen() {
  const navigate = useNavigate();
  const location = useLocation();

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
  useWakeLock();
  const { playSingle } = usePlayerStore();

  const sidebarRef = useRef(null);
  const toolbarRef = useRef(null);
  const tabBarRef  = useRef(null);
  const gridRef    = useRef(null);
  const resumeRef  = useRef(null);

  // ── État de la sidebar (overlay) ──────────────────────────────────────
  const [sidebarOpen, setSidebarOpen] = useState(false);

  const openSidebar = useCallback(() => {
    setSidebarOpen(true);
    setTimeout(() => sidebarRef.current?.focusToutesCategory(), 80);
  }, []);

  const closeSidebar = useCallback(() => {
    setSidebarOpen(false);
  }, []);

  // Touche BACK ferme la sidebar si elle est ouverte
  useEffect(() => {
    if (!sidebarOpen) return;
    const handler = (e) => {
      if (isBackKey(e.keyCode)) {
        e.preventDefault();
        e.stopPropagation();
        closeSidebar();
        setTimeout(focusFirstCard, 50);
      }
    };
    document.addEventListener('keydown', handler, true);
    return () => document.removeEventListener('keydown', handler, true);
  }, [sidebarOpen, closeSidebar]);

  // ── Bandeau de reprise série ──────────────────────────────────────────
  const [lastWatched, setLastWatched] = useState(null);
  useEffect(() => { setLastWatched(getLastWatchedSeries()); }, []);

  // ── Favoris ───────────────────────────────────────────────────────────
  const [favorites, setFavorites] = useState({ movies: [], series: [] });
  const [favCount, setFavCount]   = useState(0);
  const refreshFavorites = useCallback(() => {
    setFavorites(getFavorites());
    setFavCount(getFavoritesCount());
  }, []);

  const handleToggleFavorite = useCallback((item, type) => {
    toggleFavorite(item, type);
    refreshFavorites();
  }, [refreshFavorites]);
  useEffect(() => { refreshFavorites(); }, [refreshFavorites]);
  useEffect(() => {
    const onFocus = () => refreshFavorites();
    window.addEventListener('focus', onFocus);
    return () => window.removeEventListener('focus', onFocus);
  }, [refreshFavorites]);
  const favoriteItems = activeTab === 'favorites'
    ? [...favorites.movies, ...favorites.series]
    : [];

  const favoritesSet = React.useMemo(() => {
    const s = new Set();
    favorites.movies.forEach((m) => s.add(String(m.stream_id)));
    favorites.series.forEach((sr) => s.add(String(sr.series_id)));
    return s;
  }, [favorites]);

  // ── Chargement catalogue ──────────────────────────────────────────────
  useEffect(() => {
    const selMovCats = config.selectedMovieCategories  || [];
    const selSerCats = config.selectedSeriesCategories || [];

    // Retour depuis CatalogFilterScreen → vider le cache et resynchroniser
    if (location.state?.needsFreshSync) {
      // Remplacer l'état de navigation pour ne pas re-déclencher au prochain montage
      navigate('/', { replace: true, state: {} });
      syncFresh();
      return;
    }

    const alreadyLoaded = useCatalogStore.getState().allMovies.length > 0;
    if (alreadyLoaded) {
      setTimeout(focusFirstCard, 100);
      return;
    }
    loadCatalogStore(loadCatalogFast, config.frenchOnly, selMovCats, selSerCats).then(async () => {
      loadCatalogStore(loadCatalog, config.frenchOnly, selMovCats, selSerCats).then(async () => {
        const shouldSync = await needsSync(30);
        const isEmpty    = useCatalogStore.getState().allMovies.length === 0;
        if (shouldSync || isEmpty) sync();
      });
    });
    setTimeout(focusFirstCard, 400);
  }, []);

  // ── Catégories filtrées ────────────────────────────────────────────────
  const rawCategories   = activeTab === 'movies' ? movieCategories : seriesCategories;
  const frenchFiltered  = rawCategories.filter((c) => {
    const n = c.category_name || '';
    return /(^|[^A-Za-z])FR(?![A-Za-z])/.test(n) || /(^|[^A-Za-z])(?:FRENCH|FRANCE)(?![A-Za-z])/i.test(n);
  });
  const activeCategories = config.frenchOnly && frenchFiltered.length > 0
    ? frenchFiltered
    : rawCategories;

  // ── Filtres ────────────────────────────────────────────────────────────
  const selMovCats = config.selectedMovieCategories  || [];
  const selSerCats = config.selectedSeriesCategories || [];

  const handleSearchChange = useCallback(
    (q) => setSearchQuery(q, activeTab, config.frenchOnly, selMovCats, selSerCats),
    [activeTab, config.frenchOnly, setSearchQuery, selMovCats, selSerCats]
  );

  // Sélection catégorie depuis la sidebar → ferme la sidebar
  const handleCategoryChange = useCallback((cat) => {
    setCategory(cat, activeTab, config.frenchOnly, selMovCats, selSerCats);
    closeSidebar();
    setTimeout(focusFirstCard, 80);
  }, [activeTab, config.frenchOnly, setCategory, closeSidebar, selMovCats, selSerCats]);

  const handleTabChange = useCallback((tab) => {
    setActiveTab(tab);
    setCategory('', tab, config.frenchOnly, selMovCats, selSerCats);
    setSearchQuery('', tab, config.frenchOnly, selMovCats, selSerCats);
    closeSidebar();
  }, [setActiveTab, setCategory, setSearchQuery, config.frenchOnly, closeSidebar, selMovCats, selSerCats]);

  // ── Fonctions de focus ─────────────────────────────────────────────────
  const focusFirstCard = useCallback(() => {
    const first = document.querySelector('.content-grid .content-card[tabindex="0"]');
    if (first) first.focus();
    else document.querySelector('.content-card')?.focus();
  }, []);

  // ── Navigation inter-zones ─────────────────────────────────────────────

  // Sidebar → (ferme) → retour grille
  const handleSidebarRight = useCallback(() => {
    closeSidebar();
    setTimeout(focusFirstCard, 80);
  }, [closeSidebar, focusFirstCard]);

  // Toolbar ↓ → TabBar
  const handleToolbarDown = useCallback(() => {
    tabBarRef.current?.focusActive();
  }, []);

  // Toolbar ← → ouvre sidebar
  const handleToolbarLeft = useCallback(() => {
    openSidebar();
  }, [openSidebar]);

  // TabBar ← → ouvre sidebar
  const handleTabBarLeft = useCallback(() => {
    openSidebar();
  }, [openSidebar]);

  // TabBar ↑ → Toolbar
  const handleTabBarUp = useCallback(() => {
    toolbarRef.current?.focusFirst();
  }, []);

  // TabBar ↓ → bandeau de reprise ou grille
  const handleTabBarDown = useCallback(() => {
    if (lastWatched && resumeRef.current) resumeRef.current.focus();
    else focusFirstCard();
  }, [lastWatched, focusFirstCard]);

  const handleResumeUp   = useCallback(() => { tabBarRef.current?.focusActive(); }, []);
  const handleResumeDown = useCallback(() => { focusFirstCard(); }, [focusFirstCard]);

  // Grille ↑ depuis première ligne
  const handleGridUp = useCallback(() => {
    if (lastWatched && resumeRef.current) resumeRef.current.focus();
    else tabBarRef.current?.focusActive();
  }, [lastWatched]);

  // Grille ← depuis colonne 0 → ouvre sidebar
  const handleGridLeft = useCallback(() => {
    openSidebar();
  }, [openSidebar]);

  // ── Sélection d'un item ───────────────────────────────────────────────
  const handleItemSelect = useCallback((item, type) => {
    const isSeries = type === 'series' || (type === 'mixed' && item.series_id && !item.stream_id);
    if (isSeries) { navigate(`/series/${item.series_id}`); return; }
    const client   = createClientFromConfig(config);
    const url      = client.getStreamUrl(item.stream_id, item.container_extension || 'mkv');
    const savedPos = getWatchPosition(item.stream_id);
    playSingle(url, item.name, 'movie', item.stream_id, savedPos);
    navigate('/player');
  }, [navigate, config, playSingle]);

  return (
    <div className="home-screen">

      {/* ── Backdrop sidebar ── */}
      {sidebarOpen && (
        <div className="sidebar-backdrop" onClick={() => { closeSidebar(); setTimeout(focusFirstCard, 50); }} />
      )}

      {/* ── Sidebar (overlay depuis gauche) ── */}
      <Sidebar
        ref={sidebarRef}
        isOpen={sidebarOpen}
        activeTab={activeTab}
        onTabChange={handleTabChange}
        categories={activeCategories}
        selectedCategoryId={selectedCategoryId}
        onCategoryChange={handleCategoryChange}
        movieCount={filteredMovies.length}
        seriesCount={filteredSeries.length}
        favoritesCount={favCount}
        onSettings={() => { closeSidebar(); navigate('/settings'); }}
        onFocusRight={handleSidebarRight}
      />

      {/* ── Toolbar ── */}
      <Toolbar
        ref={toolbarRef}
        searchQuery={searchQuery}
        onSearchChange={handleSearchChange}
        isSyncing={isSyncing}
        onSync={sync}
        onSyncFresh={syncFresh}
        onSettings={() => navigate('/settings')}
        onFocusDown={handleToolbarDown}
        onFocusLeft={handleToolbarLeft}
      />

      {/* ── TabBar ── */}
      <TabBar
        ref={tabBarRef}
        activeTab={activeTab}
        onTabChange={handleTabChange}
        movieCount={filteredMovies.length}
        seriesCount={filteredSeries.length}
        favoritesCount={favCount}
        onFocusUp={handleTabBarUp}
        onFocusDown={handleTabBarDown}
        onFocusLeft={handleTabBarLeft}
      />

      {/* ── Bandeau de reprise série ── */}
      {lastWatched && (
        <div
          ref={resumeRef}
          className="home-screen__resume"
          tabIndex={0}
          role="button"
          onClick={() => {
            if (lastWatched.streamUrl && lastWatched.episodeId) {
              const pos = getWatchPosition(lastWatched.episodeId);
              playSingle(lastWatched.streamUrl, lastWatched.episodeTitle, 'episode', lastWatched.episodeId, pos);
              navigate('/player');
            } else {
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
            else if (e.keyCode === KEY.UP)  { e.preventDefault(); handleResumeUp();   }
            else if (e.keyCode === KEY.DOWN) { e.preventDefault(); handleResumeDown(); }
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

      {/* ── Grille de contenu (pleine largeur) ── */}
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
                items={filteredMovies} type="movie" onItemSelect={handleItemSelect}
                onToggleFavorite={handleToggleFavorite} favoritesSet={favoritesSet}
                isActive={activeTab === 'movies'} onFocusUp={handleGridUp} onFocusLeft={handleGridLeft}
                config={config}
                categoryLabel={selectedCategoryId ? activeCategories.find(c => String(c.category_id) === String(selectedCategoryId))?.category_name || null : null}
              />
            )}
            {activeTab === 'series' && (
              <ContentGrid
                items={filteredSeries} type="series" onItemSelect={handleItemSelect}
                onToggleFavorite={handleToggleFavorite} favoritesSet={favoritesSet}
                isActive={activeTab === 'series'} onFocusUp={handleGridUp} onFocusLeft={handleGridLeft}
                config={config}
                categoryLabel={selectedCategoryId ? activeCategories.find(c => String(c.category_id) === String(selectedCategoryId))?.category_name || null : null}
              />
            )}
            {activeTab === 'favorites' && (
              <ContentGrid
                items={favoriteItems} type="mixed" onItemSelect={handleItemSelect}
                onToggleFavorite={handleToggleFavorite} favoritesSet={favoritesSet}
                isActive={activeTab === 'favorites'} onFocusUp={handleGridUp} onFocusLeft={handleGridLeft}
                config={config}
              />
            )}
          </>
        )}
      </div>

      {/* StatusBar */}
      {!isSyncing && syncStatus ? (
        <div className="home-screen__statusbar">{syncStatus}</div>
      ) : null}

      {/* Écran de synchronisation */}
      {isSyncing && <SyncScreen />}

    </div>
  );
}
