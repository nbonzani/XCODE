/**
 * Toolbar.jsx
 *
 * Navigation télécommande :
 *   ←/→ : se déplacer entre les éléments (Recherche, Catégorie, Sync, Vider, Paramètres)
 *   ↓   : descendre vers TabBar (sauf si liste catégories ouverte → naviguer dans la liste)
 *   OK  : activer l'élément
 *
 * Champ Recherche :
 *   - OK ouvre le clavier virtuel
 *   - BACK ou OK ferme le clavier et revient au bouton
 *   - ←/→ fonctionnent après fermeture du clavier
 *
 * Champ Catégorie :
 *   - Focus → halo autour du bouton
 *   - OK → déplie la liste des catégories
 *   - ↑/↓ → navigue dans la liste dépliée
 *   - OK → valide la catégorie et referme la liste
 *   - BACK → referme sans changer
 *   - Le filtre n'est appliqué que quand OK valide
 */

import React, { useState, useCallback, useRef, useImperativeHandle } from 'react';
import { KEY } from '../../constants/keyCodes.js';

function isBackKey(kc) { return kc === 461 || kc === 8; }

const Toolbar = React.forwardRef(function Toolbar({
  searchQuery, onSearchChange, selectedCategoryId, onCategoryChange,
  categories, isSyncing, onSync, onSyncFresh, onSettings, onFocusDown,
}, ref) {
  const [searchOpen, setSearchOpen] = useState(false);
  const [localQuery, setLocalQuery] = useState(searchQuery || '');

  // Synchroniser localQuery quand searchQuery change depuis l'extérieur (changement d'onglet, etc.)
  React.useEffect(function() {
    setLocalQuery(searchQuery || '');
  }, [searchQuery]);

  // Catégorie : liste dépliée
  const [catOpen, setCatOpen]       = useState(false);
  const [catBrowseIdx, setCatBrowseIdx] = useState(0);

  const searchBtnRef   = useRef(null);
  const searchInputRef = useRef(null);
  const categoryRef    = useRef(null);
  const syncRef        = useRef(null);
  const clearRef       = useRef(null);
  const settingsRef    = useRef(null);
  const catListRef     = useRef(null);

  const navRefs = [searchBtnRef, categoryRef, syncRef, clearRef, settingsRef];

  useImperativeHandle(ref, () => ({
    focusFirst: () => searchBtnRef.current?.focus(),
  }));

  // ── Recherche ─────────────────────────────────────────────────────────
  const openSearch = useCallback(() => {
    setSearchOpen(true);
    setTimeout(() => searchInputRef.current?.focus(), 50);
  }, []);

  const closeSearch = useCallback(() => {
    setSearchOpen(false);
    onSearchChange(localQuery);
    setTimeout(() => searchBtnRef.current?.focus(), 50);
  }, [localQuery, onSearchChange]);

  // ── Catégorie ─────────────────────────────────────────────────────────
  const allCats = [{ category_id: '', category_name: 'Toutes' }].concat(categories);

  const openCatList = useCallback(() => {
    const curIdx = allCats.findIndex(function(c) { return String(c.category_id) === String(selectedCategoryId); });
    setCatBrowseIdx(curIdx >= 0 ? curIdx : 0);
    setCatOpen(true);
  }, [allCats, selectedCategoryId]);

  const closeCatList = useCallback((apply) => {
    if (apply) {
      onCategoryChange(allCats[catBrowseIdx]?.category_id || '');
    }
    setCatOpen(false);
    setTimeout(() => categoryRef.current?.focus(), 50);
  }, [allCats, catBrowseIdx, onCategoryChange]);

  // ── Navigation globale toolbar ────────────────────────────────────────
  const navigateTo = useCallback((idx) => {
    const clamped = Math.max(0, Math.min(idx, navRefs.length - 1));
    navRefs[clamped].current?.focus();
  }, []);

  const getActiveIndex = useCallback(() => {
    const active = document.activeElement;
    return navRefs.findIndex((r) => r.current === active);
  }, []);

  const handleNavKeyDown = useCallback((e) => {
    // Input recherche ouvert : seuls OK et BACK le ferment
    if (searchOpen) {
      if (e.keyCode === KEY.OK || isBackKey(e.keyCode)) {
        e.preventDefault();
        e.stopPropagation();
        closeSearch();
      }
      // Bloquer ←/→/↓ pendant l'édition du champ recherche
      if (e.keyCode === KEY.LEFT || e.keyCode === KEY.RIGHT || e.keyCode === KEY.DOWN || e.keyCode === KEY.UP) {
        e.stopPropagation();
      }
      return;
    }

    // Liste catégories ouverte : ↑/↓ navigue, OK valide, BACK annule
    if (catOpen) {
      if (e.keyCode === KEY.DOWN) {
        e.preventDefault(); e.stopPropagation();
        setCatBrowseIdx(function(i) { return Math.min(i + 1, allCats.length - 1); });
      } else if (e.keyCode === KEY.UP) {
        e.preventDefault(); e.stopPropagation();
        setCatBrowseIdx(function(i) { return Math.max(i - 1, 0); });
      } else if (e.keyCode === KEY.OK) {
        e.preventDefault(); e.stopPropagation();
        closeCatList(true);
      } else if (isBackKey(e.keyCode)) {
        e.preventDefault(); e.stopPropagation();
        closeCatList(false);
      }
      // Bloquer toute autre touche pendant la liste ouverte
      e.stopPropagation();
      return;
    }

    // Navigation normale dans la toolbar
    const idx = getActiveIndex();
    if (idx === -1) return;

    if (e.keyCode === KEY.RIGHT) {
      e.preventDefault(); e.stopPropagation();
      navigateTo(idx + 1);
    } else if (e.keyCode === KEY.LEFT) {
      e.preventDefault(); e.stopPropagation();
      navigateTo(idx - 1);
    } else if (e.keyCode === KEY.DOWN) {
      e.preventDefault();
      onFocusDown?.();
    } else if (e.keyCode === KEY.OK) {
      // OK sur le bouton catégorie → ouvrir la liste
      if (idx === 1) {
        e.preventDefault(); e.stopPropagation();
        openCatList();
      }
    }
  }, [searchOpen, catOpen, allCats, getActiveIndex, navigateTo, onFocusDown, closeSearch, closeCatList, openCatList]);

  // Scroll la liste catégorie vers l'item browsé
  React.useEffect(() => {
    if (catOpen && catListRef.current) {
      var items = catListRef.current.querySelectorAll('.toolbar__cat-item');
      if (items[catBrowseIdx]) {
        items[catBrowseIdx].scrollIntoView({ block: 'nearest', behavior: 'smooth' });
      }
    }
  }, [catOpen, catBrowseIdx]);

  const selectedCatName = (categories.find(function(c) { return String(c.category_id) === String(selectedCategoryId); }) || {}).category_name || 'Toutes';

  return (
    <div className="toolbar" onKeyDown={handleNavKeyDown}>

      {/* ── Recherche ── */}
      <div className="toolbar__search">
        <span className="toolbar__search-icon">🔍</span>
        {searchOpen ? (
          <input
            ref={searchInputRef}
            type="text"
            className="toolbar__search-input focusable-input"
            placeholder="Rechercher par titre…"
            value={localQuery}
            onChange={(e) => {
              setLocalQuery(e.target.value);
              onSearchChange(e.target.value);
            }}
            autoComplete="off"
            spellCheck={false}
          />
        ) : (
          <button
            ref={searchBtnRef}
            className="toolbar__search-btn action-button"
            tabIndex={0}
            onClick={openSearch}
          >
            {localQuery ? localQuery : 'Rechercher…'}
          </button>
        )}
      </div>

      <div className="toolbar__sep" aria-hidden="true" />

      {/* ── Catégorie : bouton + liste dépliable ── */}
      <label className="toolbar__label">Catégorie :</label>
      <div className="toolbar__cat-wrapper">
        <button
          ref={categoryRef}
          className="toolbar__select category-selector action-button"
          tabIndex={0}
          onClick={openCatList}
        >
          {selectedCatName} ▾
        </button>

        {catOpen && (
          <div ref={catListRef} className="toolbar__cat-dropdown">
            {allCats.map(function(cat, idx) {
              var isActive = idx === catBrowseIdx;
              return (
                <div
                  key={cat.category_id || '__all__'}
                  className={'toolbar__cat-item' + (isActive ? ' toolbar__cat-item--active' : '')}
                  onClick={function() { setCatBrowseIdx(idx); closeCatList(true); }}
                >
                  {cat.category_name}
                </div>
              );
            })}
          </div>
        )}
      </div>

      <div className="toolbar__spacer" />

      <button ref={syncRef} className="toolbar__btn toolbar__btn--sync action-button" tabIndex={0} onClick={onSync} disabled={isSyncing}>
        {isSyncing ? '⏳ Sync…' : '🔄 Synchroniser'}
      </button>
      <button ref={clearRef} className="toolbar__btn toolbar__btn--clear action-button" tabIndex={0} onClick={onSyncFresh} disabled={isSyncing}>
        🗑 Vider le cache
      </button>
      <button ref={settingsRef} className="toolbar__btn toolbar__btn--settings action-button" tabIndex={0} onClick={onSettings}>
        ⚙ Paramètres
      </button>

      {isSyncing && <div className="toolbar__spinner"><div className="spinner" /></div>}
    </div>
  );
});

export default Toolbar;
