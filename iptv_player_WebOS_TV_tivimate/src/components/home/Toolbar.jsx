/**
 * Toolbar.jsx — barre de recherche + actions
 *
 * Navigation télécommande :
 *   ←   depuis Recherche (idx 0) → aller à la Sidebar (onFocusLeft)
 *   ←/→ : se déplacer entre Recherche, Sync, Paramètres
 *   ↓   : descendre vers TabBar (onFocusDown)
 *   OK  : activer l'élément
 *
 * Champ Recherche :
 *   - OK ouvre le clavier virtuel
 *   - BACK ou OK ferme le clavier et revient au bouton
 */

import React, { useState, useCallback, useRef, useImperativeHandle } from 'react';
import { KEY } from '../../constants/keyCodes.js';

function isBackKey(kc) { return kc === 461 || kc === 8; }

const Toolbar = React.forwardRef(function Toolbar({
  searchQuery, onSearchChange,
  isSyncing, onSync, onSyncFresh, onSettings,
  onFocusDown, onFocusLeft,
}, ref) {
  const [searchOpen, setSearchOpen] = useState(false);
  const [localQuery, setLocalQuery] = useState(searchQuery || '');

  React.useEffect(function () {
    setLocalQuery(searchQuery || '');
  }, [searchQuery]);

  const searchBtnRef = useRef(null);
  const searchInputRef = useRef(null);
  const syncRef      = useRef(null);
  const settingsRef  = useRef(null);

  const navRefs = [searchBtnRef, syncRef, settingsRef];

  useImperativeHandle(ref, () => ({
    // Si l'input est ouvert → focus dessus ; sinon → focus sur le bouton
    focusFirst: () => {
      if (searchOpen) searchInputRef.current?.focus();
      else            searchBtnRef.current?.focus();
    },
  }), [searchOpen]);

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

  // ── Navigation globale ────────────────────────────────────────────────
  const navigateTo = useCallback((idx) => {
    const clamped = Math.max(0, Math.min(idx, navRefs.length - 1));
    navRefs[clamped].current?.focus();
  }, []);

  const getActiveIndex = useCallback(() => {
    const active = document.activeElement;
    return navRefs.findIndex((r) => r.current === active);
  }, []);

  const handleNavKeyDown = useCallback((e) => {
    // Input recherche ouvert
    if (searchOpen) {
      if (e.keyCode === KEY.OK) {
        // OK → ferme le champ
        e.preventDefault();
        e.stopPropagation();
        closeSearch();
      } else if (e.keyCode === 461) {
        // BACK télécommande → sort du clavier, retourne au bouton recherche
        e.preventDefault();
        e.stopPropagation();
        closeSearch();
      } else if (e.keyCode === 8) {
        // Touche ⌫ du clavier virtuel → efface le dernier caractère (rien si vide)
        e.preventDefault();
        e.stopPropagation();
        if (localQuery.length > 0) {
          const newVal = localQuery.slice(0, -1);
          setLocalQuery(newVal);
          onSearchChange(newVal);
        }
      } else if (e.keyCode === KEY.LEFT || e.keyCode === KEY.RIGHT) {
        // Laisser les flèches ←/→ déplacer le curseur dans l'input
        e.stopPropagation();
      } else if (e.keyCode === KEY.UP) {
        // ↑ depuis le champ : fermer et remonter
        e.preventDefault();
        e.stopPropagation();
        closeSearch();
      } else if (e.keyCode === KEY.DOWN) {
        // ↓ depuis le champ : fermer et descendre vers le TabBar
        e.preventDefault();
        e.stopPropagation();
        closeSearch();
        setTimeout(() => onFocusDown?.(), 60);
      }
      return;
    }

    const idx = getActiveIndex();
    if (idx === -1) return;

    if (e.keyCode === KEY.RIGHT) {
      e.preventDefault(); e.stopPropagation();
      navigateTo(idx + 1);
    } else if (e.keyCode === KEY.LEFT) {
      e.preventDefault(); e.stopPropagation();
      if (idx === 0) {
        // Premier élément → aller à la Sidebar
        onFocusLeft?.();
      } else {
        navigateTo(idx - 1);
      }
    } else if (e.keyCode === KEY.DOWN) {
      e.preventDefault();
      onFocusDown?.();
    }
  }, [searchOpen, getActiveIndex, navigateTo, onFocusDown, onFocusLeft, closeSearch]);

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

      <div className="toolbar__spacer" />

      <button ref={syncRef} className="toolbar__btn toolbar__btn--sync action-button" tabIndex={0} onClick={onSync} disabled={isSyncing}>
        {isSyncing ? '⏳ Sync…' : '🔄 Synchroniser'}
      </button>
      <button ref={settingsRef} className="toolbar__btn toolbar__btn--settings action-button" tabIndex={0} onClick={onSettings}>
        ⚙ Paramètres
      </button>

      {isSyncing && <div className="toolbar__spinner"><div className="spinner" /></div>}
    </div>
  );
});

export default Toolbar;
