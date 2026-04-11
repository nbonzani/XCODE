import React, { useState, useEffect, useCallback, useRef, useMemo } from 'react';
import ContentCard from './ContentCard.jsx';
import { KEY } from '../../constants/keyCodes.js';

const PAGE_SIZE = 30;
const COLS = { movie: 6, series: 5, mixed: 6 };

const ContentGrid = React.memo(function ContentGrid({
  items,
  type,
  onItemSelect,
  isActive,
  onFocusUp,     // callback → remonte vers TabBar depuis la première ligne
  initialFocusIndex = 0,
}) {
  const [displayedCount, setDisplayedCount] = useState(PAGE_SIZE);
  const [focusedIndex,   setFocusedIndex]   = useState(initialFocusIndex);
  const gridRef  = useRef(null);
  const cardRefs = useRef([]);
  const cols     = COLS[type] || 6;

  useEffect(() => {
    setDisplayedCount(PAGE_SIZE);
    setFocusedIndex(0);
    if (gridRef.current) gridRef.current.scrollTop = 0;
  }, [items]);

  useEffect(() => {
    if (isActive && cardRefs.current[focusedIndex]) {
      cardRefs.current[focusedIndex].focus({ preventScroll: false });
    }
  }, [focusedIndex, isActive]);

  useEffect(() => {
    if (isActive && cardRefs.current[focusedIndex]) {
      cardRefs.current[focusedIndex].focus({ preventScroll: false });
    }
  }, [isActive]);

  const visibleItems = useMemo(() => items.slice(0, displayedCount), [items, displayedCount]);

  const loadNextPage = useCallback(() => {
    if (displayedCount < items.length)
      setDisplayedCount((prev) => Math.min(prev + PAGE_SIZE, items.length));
  }, [displayedCount, items.length]);

  const handleScroll = useCallback(() => {
    const el = gridRef.current;
    if (!el) return;
    if ((el.scrollTop + el.clientHeight) / el.scrollHeight >= 0.8) loadNextPage();
  }, [loadNextPage]);

  const handleKeyDown = useCallback((e) => {
    if (!isActive) return;
    const total = visibleItems.length;
    let next = focusedIndex;

    switch (e.keyCode) {
      case KEY.RIGHT:
        e.preventDefault();
        next = focusedIndex + 1 < total ? focusedIndex + 1 : focusedIndex;
        if (next >= displayedCount - cols && displayedCount < items.length) loadNextPage();
        break;
      case KEY.LEFT:
        e.preventDefault();
        next = focusedIndex - 1 >= 0 ? focusedIndex - 1 : focusedIndex;
        break;
      case KEY.DOWN:
        e.preventDefault();
        next = focusedIndex + cols < total ? focusedIndex + cols : focusedIndex;
        if (next >= displayedCount - cols && displayedCount < items.length) loadNextPage();
        break;
      case KEY.UP:
        e.preventDefault();
        if (focusedIndex < cols) {
          // Première ligne → remonter vers TabBar
          onFocusUp?.();
          return;
        }
        next = focusedIndex - cols;
        break;
      default:
        return;
    }
    setFocusedIndex(next);
  }, [isActive, focusedIndex, visibleItems.length, displayedCount, items.length, cols, loadNextPage, onFocusUp]);

  if (items.length === 0) {
    return (
      <div className="content-grid content-grid--empty">
        <p className="content-grid__empty-msg">
          Aucun contenu disponible.<br />
          Lancez une synchronisation depuis la barre d'outils.
        </p>
      </div>
    );
  }

  return (
    <div
      ref={gridRef}
      className={`content-grid content-grid--${type}`}
      onScroll={handleScroll}
      onKeyDown={handleKeyDown}
      role="grid"
    >
      <div className="content-grid__inner" style={{ '--grid-cols': cols }}>
        {visibleItems.map((item, idx) => (
          <ContentCard
            key={item.stream_id || item.series_id || idx}
            item={item}
            type={type}
            isFocused={idx === focusedIndex && isActive}
            onSelect={onItemSelect}
            tabIndex={idx === focusedIndex ? 0 : -1}
            cardRef={(el) => (cardRefs.current[idx] = el)}
          />
        ))}
      </div>
      <div className="content-grid__status">
        {displayedCount < items.length
          ? `${displayedCount} / ${items.length} — continuez à défiler`
          : `${items.length} résultat${items.length > 1 ? 's' : ''}`}
      </div>
    </div>
  );
});

export default ContentGrid;
