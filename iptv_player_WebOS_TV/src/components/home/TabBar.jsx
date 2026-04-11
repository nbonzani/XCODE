/**
 * TabBar.jsx
 * Navigation :
 *   ←/→ : basculer entre Films et Séries
 *   ↑   : remonter vers Toolbar
 *   ↓   : descendre vers la grille
 *   OK  : sélectionner l'onglet (déjà actif = pas d'effet)
 */

import React, { useRef, useCallback, useImperativeHandle } from 'react';
import { KEY } from '../../constants/keyCodes.js';

const TABS = [
  { id: 'movies', label: '🎬 Films' },
  { id: 'series', label: '📺 Séries' },
  { id: 'favorites', label: '⭐ Favoris' },
];

const TabBar = React.forwardRef(function TabBar(
  { activeTab, onTabChange, movieCount, seriesCount, favoritesCount, onFocusUp, onFocusDown },
  ref
) {
  const tabRefs = useRef([]);

  useImperativeHandle(ref, () => ({
    focusActive: () => {
      const idx = TABS.findIndex((t) => t.id === activeTab);
      tabRefs.current[idx]?.focus();
    },
  }));

  const handleKeyDown = useCallback((e, tabId) => {
    const currentIdx = TABS.findIndex((t) => t.id === tabId);

    switch (e.keyCode) {
      case KEY.RIGHT:
        e.preventDefault();
        if (currentIdx < TABS.length - 1) {
          onTabChange(TABS[currentIdx + 1].id);
          setTimeout(() => tabRefs.current[currentIdx + 1]?.focus(), 0);
        }
        break;
      case KEY.LEFT:
        e.preventDefault();
        if (currentIdx > 0) {
          onTabChange(TABS[currentIdx - 1].id);
          setTimeout(() => tabRefs.current[currentIdx - 1]?.focus(), 0);
        }
        break;
      case KEY.UP:
        e.preventDefault();
        onFocusUp?.();
        break;
      case KEY.DOWN:
        e.preventDefault();
        onFocusDown?.();
        break;
      case KEY.OK:
        e.preventDefault();
        onTabChange(tabId);
        break;
      default:
        break;
    }
  }, [onTabChange, onFocusUp, onFocusDown]);

  const getLabel = (tab) => {
    if (tab.id === 'movies' && movieCount !== undefined) return `🎬 Films (${movieCount})`;
    if (tab.id === 'series' && seriesCount !== undefined) return `📺 Séries (${seriesCount})`;
    if (tab.id === 'favorites' && favoritesCount !== undefined) return `⭐ Favoris (${favoritesCount})`;
    return tab.label;
  };

  return (
    <div className="tab-bar" role="tablist">
      {TABS.map((tab, idx) => (
        <button
          key={tab.id}
          ref={(el) => (tabRefs.current[idx] = el)}
          role="tab"
          aria-selected={activeTab === tab.id}
          className={`tab-item ${activeTab === tab.id ? 'active' : ''}`}
          tabIndex={0}
          onClick={() => onTabChange(tab.id)}
          onKeyDown={(e) => handleKeyDown(e, tab.id)}
        >
          {getLabel(tab)}
        </button>
      ))}
    </div>
  );
});

export default TabBar;
