/**
 * src/components/home/ContentCard.jsx
 * Corrections :
 * - Ratio poster 2:3 (600x900) → objectFit: contain (pas cover)
 * - Score affiché sous le titre
 * - Clic sur film → lecture directe sans popup
 */

import React, { useCallback } from 'react';
import PosterImage from './PosterImage.jsx';
import { KEY } from '../../constants/keyCodes.js';
import { isFavorite } from '../../services/favoritesService.js';

const ContentCard = React.memo(function ContentCard({
  item,
  type,
  isFocused,
  onSelect,
  tabIndex,
  cardRef,
}) {
  const name     = item.name || '';
  const imageUrl = item.stream_icon || item.cover || '';
  const itemId   = item.stream_id || item.series_id;
  const rating   = item.rating ? parseFloat(item.rating) : null;
  // Pour le type "mixed" (favoris), détecter le vrai type
  const effectiveType = type === 'mixed' ? (item.series_id && !item.stream_id ? 'series' : 'movie') : type;
  const showFavBadge = isFavorite(itemId, effectiveType);

  const handleKeyDown = useCallback((e) => {
    if (e.keyCode === KEY.OK) { e.preventDefault(); onSelect(item, effectiveType); }
  }, [item, effectiveType, onSelect]);

  return (
    <div
      ref={cardRef}
      className={`content-card ${isFocused ? 'focused' : ''}`}
      tabIndex={tabIndex}
      role="button"
      aria-label={name}
      onKeyDown={handleKeyDown}
      onClick={() => onSelect(item, effectiveType)}
      data-item-id={itemId}
    >
      <div className="content-card__poster-wrap">
        <PosterImage url={imageUrl} alt={name} type={effectiveType} />
        {showFavBadge && <span className="content-card__fav-badge">★</span>}
      </div>
      <div className="content-card__info">
        <div className="content-card__title text-clamp-2">{name}</div>
        {rating !== null && !isNaN(rating) && rating > 0 && (
          <div className="content-card__rating">⭐ {rating.toFixed(1)}</div>
        )}
      </div>
    </div>
  );
});

export default ContentCard;
