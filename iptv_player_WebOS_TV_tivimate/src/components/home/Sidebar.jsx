/**
 * Sidebar.jsx
 *
 * Panneau latéral gauche (280px) — style TiviMate
 *
 * Zones de focus :
 *   'tabs'     — onglets Films / Séries / Favoris
 *   'cats'     — liste de catégories (défilable)
 *   'settings' — bouton Paramètres en bas
 *
 * Navigation télécommande :
 *   ↑/↓ : naviguer entre onglets puis catégories puis settings
 *   →   : aller vers la zone de contenu (onFocusRight)
 *   OK  : sélectionner l'onglet ou la catégorie
 */

import React, { useRef, useCallback, useImperativeHandle, useState, useEffect } from 'react';
import { KEY } from '../../constants/keyCodes.js';
import './Sidebar.css';

const TABS = [
  { id: 'movies',    label: 'Films' },
  { id: 'series',    label: 'Séries' },
  { id: 'favorites', label: 'Favoris' },
];

const Sidebar = React.forwardRef(function Sidebar(
  {
    isOpen,
    activeTab,
    onTabChange,
    categories,
    selectedCategoryId,
    onCategoryChange,
    movieCount,
    seriesCount,
    favoritesCount,
    onSettings,
    onFocusRight,
  },
  ref
) {
  const tabRefs     = useRef([]);
  const catRefs     = useRef([]);
  const settingsRef = useRef(null);
  const catListRef  = useRef(null);

  const [focusArea,     setFocusArea]     = useState('tabs');
  const [focusedTabIdx, setFocusedTabIdx] = useState(() => TABS.findIndex(t => t.id === activeTab) || 0);
  const [focusedCatIdx, setFocusedCatIdx] = useState(0);

  const allCats = [{ category_id: '', category_name: 'Toutes' }, ...categories];

  // Quand l'onglet actif change depuis l'extérieur → mettre à jour l'index focalisé
  useEffect(() => {
    const idx = TABS.findIndex(t => t.id === activeTab);
    setFocusedTabIdx(idx >= 0 ? idx : 0);
    // Remettre la sélection de catégorie à "Toutes" quand on change d'onglet
    setFocusedCatIdx(0);
  }, [activeTab]);

  // Quand selectedCategoryId change → synchroniser l'index
  useEffect(() => {
    const idx = allCats.findIndex(c => String(c.category_id) === String(selectedCategoryId));
    setFocusedCatIdx(idx >= 0 ? idx : 0);
  }, [selectedCategoryId, categories]);

  // Scroll l'item catégorie actif dans la vue
  useEffect(() => {
    if (catListRef.current) {
      const items = catListRef.current.querySelectorAll('.sidebar__cat-item');
      if (items[focusedCatIdx]) {
        items[focusedCatIdx].scrollIntoView({ block: 'nearest', behavior: 'smooth' });
      }
    }
  }, [focusedCatIdx]);

  useImperativeHandle(ref, () => ({
    focusActiveTab: () => {
      const idx = TABS.findIndex(t => t.id === activeTab);
      const target = idx >= 0 ? idx : 0;
      setFocusArea('tabs');
      setFocusedTabIdx(target);
      setTimeout(() => tabRefs.current[target]?.focus(), 0);
    },
    focusSettings: () => {
      setFocusArea('settings');
      setTimeout(() => settingsRef.current?.focus(), 0);
    },
  }));

  const getTabLabel = (tab) => {
    if (tab.id === 'movies'    && movieCount    !== undefined) return `🎬 Films (${movieCount})`;
    if (tab.id === 'series'    && seriesCount   !== undefined) return `📺 Séries (${seriesCount})`;
    if (tab.id === 'favorites' && favoritesCount !== undefined) return `⭐ Favoris (${favoritesCount})`;
    return tab.label;
  };

  // ── Navigation des onglets ──────────────────────────────────────────────
  const handleTabKeyDown = useCallback((e, tabId, tabIdx) => {
    switch (e.keyCode) {
      case KEY.DOWN:
        e.preventDefault();
        if (tabIdx < TABS.length - 1) {
          const next = tabIdx + 1;
          setFocusedTabIdx(next);
          tabRefs.current[next]?.focus();
        } else {
          setFocusArea('cats');
          setFocusedCatIdx(0);
          setTimeout(() => catRefs.current[0]?.focus(), 0);
        }
        break;
      case KEY.UP:
        e.preventDefault();
        if (tabIdx > 0) {
          const prev = tabIdx - 1;
          setFocusedTabIdx(prev);
          tabRefs.current[prev]?.focus();
        }
        break;
      case KEY.RIGHT:
        e.preventDefault();
        onFocusRight?.();
        break;
      case KEY.OK:
        e.preventDefault();
        onTabChange(tabId);
        break;
      default:
        break;
    }
  }, [onTabChange, onFocusRight]);

  // ── Navigation des catégories ───────────────────────────────────────────
  const handleCatKeyDown = useCallback((e, catIdx) => {
    switch (e.keyCode) {
      case KEY.DOWN:
        e.preventDefault();
        if (catIdx < allCats.length - 1) {
          const next = catIdx + 1;
          setFocusedCatIdx(next);
          catRefs.current[next]?.focus();
        } else {
          setFocusArea('settings');
          settingsRef.current?.focus();
        }
        break;
      case KEY.UP:
        e.preventDefault();
        if (catIdx > 0) {
          const prev = catIdx - 1;
          setFocusedCatIdx(prev);
          catRefs.current[prev]?.focus();
        } else {
          const tabIdx = TABS.findIndex(t => t.id === activeTab);
          const target = tabIdx >= 0 ? tabIdx : 0;
          setFocusArea('tabs');
          setFocusedTabIdx(target);
          tabRefs.current[target]?.focus();
        }
        break;
      case KEY.RIGHT:
        e.preventDefault();
        onFocusRight?.();
        break;
      case KEY.OK:
        e.preventDefault();
        onCategoryChange(allCats[catIdx]?.category_id ?? '');
        break;
      default:
        break;
    }
  }, [allCats, activeTab, onCategoryChange, onFocusRight]);

  // ── Navigation du bouton Paramètres ────────────────────────────────────
  const handleSettingsKeyDown = useCallback((e) => {
    switch (e.keyCode) {
      case KEY.UP: {
        e.preventDefault();
        setFocusArea('cats');
        const lastIdx = allCats.length - 1;
        setFocusedCatIdx(lastIdx);
        catRefs.current[lastIdx]?.focus();
        break;
      }
      case KEY.RIGHT:
        e.preventDefault();
        onFocusRight?.();
        break;
      case KEY.OK:
        e.preventDefault();
        onSettings?.();
        break;
      default:
        break;
    }
  }, [allCats, onFocusRight, onSettings]);

  return (
    <div className={`sidebar${isOpen ? ' sidebar--open' : ''}`}>

      {/* ── Logo ── */}
      <div className="sidebar__logo">
        <span className="sidebar__logo-icon">📺</span>
        <span className="sidebar__logo-text">IPTV</span>
      </div>

      {/* ── Onglets ── */}
      <div className="sidebar__tabs">
        {TABS.map((tab, idx) => (
          <button
            key={tab.id}
            ref={(el) => (tabRefs.current[idx] = el)}
            className={`sidebar__tab${activeTab === tab.id ? ' sidebar__tab--active' : ''}`}
            tabIndex={focusArea === 'tabs' && focusedTabIdx === idx ? 0 : -1}
            onClick={() => onTabChange(tab.id)}
            onKeyDown={(e) => handleTabKeyDown(e, tab.id, idx)}
          >
            {getTabLabel(tab)}
          </button>
        ))}
      </div>

      <div className="sidebar__divider" />

      {/* ── Liste des catégories ── */}
      <div ref={catListRef} className="sidebar__cats">
        {allCats.map((cat, idx) => {
          const isSelected = String(cat.category_id) === String(selectedCategoryId);
          return (
            <button
              key={cat.category_id || '__all__'}
              ref={(el) => (catRefs.current[idx] = el)}
              className={`sidebar__cat-item${isSelected ? ' sidebar__cat-item--selected' : ''}`}
              tabIndex={focusArea === 'cats' && focusedCatIdx === idx ? 0 : -1}
              onClick={() => onCategoryChange(cat.category_id ?? '')}
              onKeyDown={(e) => handleCatKeyDown(e, idx)}
            >
              {cat.category_name}
            </button>
          );
        })}
      </div>

      {/* ── Pied : bouton Paramètres ── */}
      <div className="sidebar__footer">
        <button
          ref={settingsRef}
          className="sidebar__settings"
          tabIndex={focusArea === 'settings' ? 0 : -1}
          onClick={onSettings}
          onKeyDown={handleSettingsKeyDown}
        >
          ⚙ Paramètres
        </button>
      </div>

    </div>
  );
});

export default Sidebar;
