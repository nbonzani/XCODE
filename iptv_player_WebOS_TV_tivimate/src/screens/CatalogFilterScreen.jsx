/**
 * CatalogFilterScreen.jsx
 * Permet à l'utilisateur de choisir les catégories à inclure dans le catalogue.
 * Affiché après la sélection d'une langue dans SettingsScreen.
 *
 * Navigation télécommande :
 *   Tab Films / Séries : ←→ entre onglets
 *   Liste catégories   : ↑↓ navigation (changement de page auto en haut/bas), OK pour cocher/décocher
 *   Boutons bas        : ↑↓ pour accéder / quitter, ←→ entre boutons
 */

import React, { useState, useEffect, useRef, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAppStore } from '../store/appStore.js';
import { KEY } from '../constants/keyCodes.js';
import './CatalogFilterScreen.css';

const PAGE_SIZE = 30; // 10 lignes × 3 colonnes

// Détecte si un nom de catégorie contient le code langue donné
function matchesOneLang(name, lang) {
  const n = name || '';
  if (lang === 'FR') return /(^|[^A-Za-z])FR(?![A-Za-z])/.test(n) || /(^|[^A-Za-z])(?:FRENCH|FRANCE|VF)(?![A-Za-z])/i.test(n);
  if (lang === 'IT') return /(^|[^A-Za-z])IT(?![A-Za-z])/.test(n) || /\b(?:ITALIAN|ITALIE|ITALIANO)\b/i.test(n);
  if (lang === 'EN') return /(^|[^A-Za-z])(?:EN|UK|US)(?![A-Za-z])/.test(n) || /\b(?:ENGLISH|ANGLAIS)\b/i.test(n);
  if (lang === 'DE') return /(^|[^A-Za-z])DE(?![A-Za-z])/.test(n) || /\b(?:GERMAN|DEUTSCH|ALLEMAND)\b/i.test(n);
  if (lang === 'ES') return /(^|[^A-Za-z])ES(?![A-Za-z])/.test(n) || /\b(?:SPANISH|ESPAGNOL|ESPAÑOL|ESPAÑA)\b/i.test(n);
  return false;
}

// Détecte si un nom de catégorie correspond à l'une des langues sélectionnées
function matchesLanguages(categoryName, langs) {
  if (!langs || langs.length === 0) return true;
  return langs.some((lang) => matchesOneLang(categoryName, lang));
}

export default function CatalogFilterScreen() {
  const navigate  = useNavigate();
  const { config, saveConfig, pendingCatalogFilter, setPendingCatalogFilter } = useAppStore();

  const { languages = [], movieCategories = [], seriesCategories = [] } = pendingCatalogFilter || {};

  // Filtrer les catégories par langues sélectionnées (pré-sélection)
  const filteredMovieCats  = movieCategories.filter((c) => matchesLanguages(c.category_name, languages));
  const filteredSeriesCats = seriesCategories.filter((c) => matchesLanguages(c.category_name, languages));

  // Si aucune catégorie ne correspond, afficher toutes
  const displayMovieCats  = filteredMovieCats.length  > 0 ? filteredMovieCats  : movieCategories;
  const displaySeriesCats = filteredSeriesCats.length > 0 ? filteredSeriesCats : seriesCategories;

  const [activeTab, setActiveTab] = useState('movies');  // 'movies' | 'series'

  // Pagination : une page par onglet
  const [moviePage,  setMoviePage]  = useState(0);
  const [seriesPage, setSeriesPage] = useState(0);

  // Sélection : par défaut toutes les catégories filtrées sont cochées
  const [selectedMovieIds,  setSelectedMovieIds]  = useState(
    () => new Set(displayMovieCats.map((c) => String(c.category_id)))
  );
  const [selectedSeriesIds, setSelectedSeriesIds] = useState(
    () => new Set(displaySeriesCats.map((c) => String(c.category_id)))
  );

  // Focus : area: 'tabs' | 'cats' | 'ctrl'
  const [focusArea,   setFocusArea]   = useState('cats');
  const [focusedTab,  setFocusedTab]  = useState(0);      // 0=films 1=séries
  const [focusedCat,  setFocusedCat]  = useState(0);      // index dans la page courante
  const [focusedCtrl, setFocusedCtrl] = useState(0);      // 0=selectAll 1=deselectAll 2=OK

  const tabFilmsRef    = useRef(null);
  const tabSeriesRef   = useRef(null);
  const catRefs        = useRef([]);
  const selectAllRef   = useRef(null);
  const deselectAllRef = useRef(null);
  const okRef          = useRef(null);

  const currentCats    = activeTab === 'movies' ? displayMovieCats  : displaySeriesCats;
  const currentSel     = activeTab === 'movies' ? selectedMovieIds   : selectedSeriesIds;
  const setCurrentSel  = activeTab === 'movies' ? setSelectedMovieIds : setSelectedSeriesIds;
  const currentPage    = activeTab === 'movies' ? moviePage  : seriesPage;
  const setCurrentPage = activeTab === 'movies' ? setMoviePage : setSeriesPage;

  const maxPages  = Math.max(1, Math.ceil(currentCats.length / PAGE_SIZE));
  const pagedCats = currentCats.slice(currentPage * PAGE_SIZE, (currentPage + 1) * PAGE_SIZE);

  // Focus initial : première catégorie
  useEffect(() => {
    setTimeout(() => {
      catRefs.current[0]?.focus();
      setFocusArea('cats');
      setFocusedCat(0);
    }, 100);
  }, []);

  // Quand on change d'onglet, recentrer sur la première cat de la première page
  useEffect(() => {
    if (focusArea === 'cats') {
      setFocusedCat(0);
      catRefs.current[0]?.focus();
    }
  }, [activeTab]);

  const toggleCategory = useCallback((id) => {
    const sid = String(id);
    setCurrentSel((prev) => {
      const next = new Set(prev);
      if (next.has(sid)) next.delete(sid);
      else next.add(sid);
      return next;
    });
  }, [setCurrentSel]);

  const selectAll = useCallback(() => {
    setCurrentSel(new Set(currentCats.map((c) => String(c.category_id))));
  }, [currentCats, setCurrentSel]);

  const deselectAll = useCallback(() => {
    setCurrentSel(new Set());
  }, [setCurrentSel]);

  const handleOk = useCallback(() => {
    const movIds = selectedMovieIds.size  > 0 ? [...selectedMovieIds]  : [];
    const serIds = selectedSeriesIds.size > 0 ? [...selectedSeriesIds] : [];
    saveConfig({
      ...config,
      filterLanguage: languages,
      selectedMovieCategories:  movIds,
      selectedSeriesCategories: serIds,
      catalogSetupDone: true,
    });
    setPendingCatalogFilter(null); // libérer la mémoire
    // needsFreshSync=true → HomeScreen vide le cache et resynchronise avec le nouveau filtre
    navigate('/', { state: { needsFreshSync: true } });
  }, [selectedMovieIds, selectedSeriesIds, config, languages, saveConfig, setPendingCatalogFilter, navigate]);

  // ── Navigation clavier ──────────────────────────────────────────────────
  useEffect(() => {
    const handler = (e) => {
      const COLS = 3;

      if (focusArea === 'tabs') {
        if (e.keyCode === KEY.LEFT) {
          e.preventDefault();
          if (focusedTab > 0) { setFocusedTab(0); setActiveTab('movies'); tabFilmsRef.current?.focus(); }
        } else if (e.keyCode === KEY.RIGHT) {
          e.preventDefault();
          if (focusedTab < 1) { setFocusedTab(1); setActiveTab('series'); tabSeriesRef.current?.focus(); }
        } else if (e.keyCode === KEY.DOWN) {
          e.preventDefault();
          setFocusArea('cats');
          setFocusedCat(0);
          catRefs.current[0]?.focus();
        } else if (e.keyCode === KEY.OK) {
          const el = document.activeElement;
          if (el && el.tagName === 'BUTTON') { e.preventDefault(); el.click(); }
        }

      } else if (focusArea === 'cats') {
        if (e.keyCode === KEY.UP) {
          e.preventDefault();
          const prevInPage = focusedCat - COLS;
          if (prevInPage >= 0) {
            // Remonter dans la page
            setFocusedCat(prevInPage);
            catRefs.current[prevInPage]?.focus({ preventScroll: false });
          } else if (currentPage > 0) {
            // Première ligne de la page → page précédente, dernière ligne
            const prevPage = currentPage - 1;
            setCurrentPage(prevPage);
            const prevPageSize = Math.min(PAGE_SIZE, currentCats.length - prevPage * PAGE_SIZE);
            // Trouver la dernière ligne : même colonne, dernière ligne disponible
            const col = focusedCat % COLS;
            const lastRow = Math.floor((prevPageSize - 1) / COLS);
            const target = Math.min(lastRow * COLS + col, prevPageSize - 1);
            setFocusedCat(target);
            setTimeout(() => catRefs.current[target]?.focus(), 0);
          } else {
            // Première page, première ligne → onglets
            setFocusArea('tabs');
            setFocusedTab(activeTab === 'movies' ? 0 : 1);
            (activeTab === 'movies' ? tabFilmsRef : tabSeriesRef).current?.focus();
          }

        } else if (e.keyCode === KEY.DOWN) {
          e.preventDefault();
          const nextInPage = focusedCat + COLS;
          if (nextInPage < pagedCats.length) {
            // Descendre dans la page
            setFocusedCat(nextInPage);
            catRefs.current[nextInPage]?.focus({ preventScroll: false });
          } else if (currentPage < maxPages - 1) {
            // Dernière ligne de la page → page suivante
            const nextPage = currentPage + 1;
            setCurrentPage(nextPage);
            const col = focusedCat % COLS;
            // Même colonne, première ligne de la page suivante
            const nextPageSize = Math.min(PAGE_SIZE, currentCats.length - nextPage * PAGE_SIZE);
            const target = Math.min(col, nextPageSize - 1);
            setFocusedCat(target);
            setTimeout(() => catRefs.current[target]?.focus(), 0);
          } else {
            // Dernière page, dernière ligne → boutons
            setFocusArea('ctrl');
            setFocusedCtrl(0);
            selectAllRef.current?.focus();
          }

        } else if (e.keyCode === KEY.LEFT) {
          e.preventDefault();
          if (focusedCat % COLS > 0) {
            const next = focusedCat - 1;
            setFocusedCat(next);
            catRefs.current[next]?.focus({ preventScroll: false });
          }
        } else if (e.keyCode === KEY.RIGHT) {
          e.preventDefault();
          if (focusedCat % COLS < COLS - 1 && focusedCat + 1 < pagedCats.length) {
            const next = focusedCat + 1;
            setFocusedCat(next);
            catRefs.current[next]?.focus({ preventScroll: false });
          }
        } else if (e.keyCode === KEY.OK) {
          e.preventDefault();
          const cat = pagedCats[focusedCat];
          if (cat) toggleCategory(cat.category_id);
        }

      } else if (focusArea === 'ctrl') {
        if (e.keyCode === KEY.UP) {
          e.preventDefault();
          if (focusedCtrl > 0) {
            const next = focusedCtrl - 1;
            setFocusedCtrl(next);
            [selectAllRef, deselectAllRef, okRef][next].current?.focus();
          } else {
            setFocusArea('cats');
            const last = Math.max(0, pagedCats.length - 1);
            setFocusedCat(last);
            catRefs.current[last]?.focus();
          }
        } else if (e.keyCode === KEY.DOWN) {
          e.preventDefault();
          const max = 2;
          if (focusedCtrl < max) {
            const next = focusedCtrl + 1;
            setFocusedCtrl(next);
            [selectAllRef, deselectAllRef, okRef][next].current?.focus();
          }
        } else if (e.keyCode === KEY.LEFT || e.keyCode === KEY.RIGHT) {
          e.preventDefault();
          const refs = [selectAllRef, deselectAllRef, okRef];
          const next = e.keyCode === KEY.RIGHT
            ? Math.min(2, focusedCtrl + 1)
            : Math.max(0, focusedCtrl - 1);
          setFocusedCtrl(next);
          refs[next].current?.focus();
        } else if (e.keyCode === KEY.OK) {
          const el = document.activeElement;
          if (el && el.tagName === 'BUTTON') { e.preventDefault(); el.click(); }
        }
      }
    };
    document.addEventListener('keydown', handler);
    return () => document.removeEventListener('keydown', handler);
  }, [focusArea, focusedTab, focusedCat, focusedCtrl, activeTab, currentCats, pagedCats, currentPage, maxPages, setCurrentPage, toggleCategory]);

  const fc = (area, idx) => focusArea === area && (idx === undefined || focusedCtrl === idx) ? 'focused' : '';

  return (
    <div className="catalog-filter-screen">
      <div className="catalog-filter-header">
        <h1 className="catalog-filter-title">Sélection des catégories</h1>
        <p className="catalog-filter-subtitle">
          Langues : <strong>{languages.length > 0 ? languages.join(', ') : 'Tout'}</strong> — Cochez les catégories à inclure dans votre catalogue
        </p>
      </div>

      {/* Tab bar + pagination */}
      <div className="catalog-filter-tabs">
        <button
          ref={tabFilmsRef}
          className={`catalog-filter-tab ${activeTab === 'movies' ? 'active' : ''} ${focusArea === 'tabs' && focusedTab === 0 ? 'focused' : ''}`}
          tabIndex={0}
          onFocus={() => { setFocusArea('tabs'); setFocusedTab(0); }}
          onClick={() => { setActiveTab('movies'); setFocusArea('cats'); setTimeout(() => catRefs.current[0]?.focus(), 50); }}
        >
          Films ({selectedMovieIds.size} / {displayMovieCats.length})
        </button>
        <button
          ref={tabSeriesRef}
          className={`catalog-filter-tab ${activeTab === 'series' ? 'active' : ''} ${focusArea === 'tabs' && focusedTab === 1 ? 'focused' : ''}`}
          tabIndex={0}
          onFocus={() => { setFocusArea('tabs'); setFocusedTab(1); }}
          onClick={() => { setActiveTab('series'); setFocusArea('cats'); setTimeout(() => catRefs.current[0]?.focus(), 50); }}
        >
          Séries ({selectedSeriesIds.size} / {displaySeriesCats.length})
        </button>

        {maxPages > 1 && (
          <div className="catalog-filter-page-indicator">
            Page {currentPage + 1} / {maxPages}
          </div>
        )}
      </div>

      {/* Liste des catégories */}
      <div className="catalog-filter-list">
        {pagedCats.map((cat, i) => {
          const id  = String(cat.category_id);
          const sel = currentSel.has(id);
          return (
            <div
              key={id}
              ref={(el) => { catRefs.current[i] = el; }}
              className={`catalog-filter-item ${sel ? 'selected' : ''} ${focusArea === 'cats' && focusedCat === i ? 'focused' : ''}`}
              tabIndex={0}
              role="checkbox"
              aria-checked={sel}
              onFocus={() => { setFocusArea('cats'); setFocusedCat(i); }}
              onClick={() => toggleCategory(id)}
            >
              <span className="catalog-filter-item__check">{sel ? '☑' : '☐'}</span>
              <span className="catalog-filter-item__name">{cat.category_name}</span>
            </div>
          );
        })}
      </div>

      {/* Boutons contrôle */}
      <div className="catalog-filter-controls">
        <button
          ref={selectAllRef}
          className={`catalog-filter-ctrl-btn ${fc('ctrl', 0)}`}
          tabIndex={0}
          onFocus={() => { setFocusArea('ctrl'); setFocusedCtrl(0); }}
          onClick={selectAll}
        >
          Tout sélectionner
        </button>
        <button
          ref={deselectAllRef}
          className={`catalog-filter-ctrl-btn ${fc('ctrl', 1)}`}
          tabIndex={0}
          onFocus={() => { setFocusArea('ctrl'); setFocusedCtrl(1); }}
          onClick={deselectAll}
        >
          Tout désélectionner
        </button>
        <button
          ref={okRef}
          className={`catalog-filter-ctrl-btn catalog-filter-ctrl-btn--ok ${fc('ctrl', 2)}`}
          tabIndex={0}
          onFocus={() => { setFocusArea('ctrl'); setFocusedCtrl(2); }}
          onClick={handleOk}
        >
          OK — Valider
        </button>
      </div>
    </div>
  );
}
