/**
 * ContentGrid.jsx — Layout TiviMate :
 *   - Hero (56% hauteur) : backdrop + gradient + métadonnées enrichies
 *   - Carrousel horizontal (44%) : rangée unique de cartes défilables
 *
 * Métadonnées dans le hero :
 *   - Séries   : plot/genre/release_date déjà présents dans le catalogue (pas d'appel API)
 *   - Films    : fetch debounced (400 ms) via getVodInfo + cache mémoire
 *
 * Navigation :
 *   ← depuis première carte  → onFocusLeft (ouvre sidebar)
 *   ↑ depuis la rangée       → onFocusUp (TabBar)
 *   → / ← dans la rangée    → déplace le focus + scroll automatique
 */

import React, { useState, useEffect, useCallback, useRef, useMemo } from 'react';
import ContentCard from './ContentCard.jsx';
import { KEY } from '../../constants/keyCodes.js';
import { createClientFromConfig } from '../../services/xtreamApi.js';
import { usePlayerStore } from '../../store/playerStore.js';

const PAGE_SIZE = 40;

// ── Cache mémoire global des détails film (partagé entre onglets) ─────────────
const vodDetailsCache = new Map();

// ── Hook : récupère les détails enrichis d'un item ───────────────────────────

function useItemDetails(item, type, config) {
  const [details, setDetails] = useState(null);
  const timerRef = useRef(null);
  const abortRef = useRef(null);

  useEffect(() => {
    if (!item) { setDetails(null); return; }

    const isSeries = type === 'series' || (type === 'mixed' && item.series_id && !item.stream_id);

    // ── Séries : métadonnées déjà dans le catalogue ──────────────────────────
    if (isSeries) {
      setDetails({
        plot:         item.plot         || '',
        genre:        item.genre        || '',
        release_date: item.release_date || '',
        cast:         '',
        director:     '',
        backdrop:     item.cover        || item.stream_icon || '',
        rating:       item.rating       || null,
      });
      return;
    }

    // ── Films : fetch debounced via getVodInfo ───────────────────────────────
    const vodId = item.stream_id;
    if (!vodId || !config) { setDetails(null); return; }

    // Cache hit
    if (vodDetailsCache.has(vodId)) {
      setDetails(vodDetailsCache.get(vodId));
      return;
    }

    // Debounce : attendre 400 ms que l'utilisateur se stabilise sur la carte
    clearTimeout(timerRef.current);
    setDetails(null); // vider pendant le chargement

    timerRef.current = setTimeout(async () => {
      // Annuler la requête précédente si elle est encore en cours
      if (abortRef.current) abortRef.current.abort();
      abortRef.current = new AbortController();

      try {
        const client = createClientFromConfig(config);
        const result = await client.getVodInfo(vodId);
        const info   = result?.info || {};

        const d = {
          plot:         info.plot         || info.description || '',
          genre:        info.genre        || '',
          release_date: info.release_date || info.releasedate || '',
          cast:         info.cast         || info.actors      || '',
          director:     info.director     || '',
          backdrop:     (Array.isArray(info.backdrop_path) ? info.backdrop_path[0] : info.backdrop_path)
                        || info.cover_big || item.stream_icon || '',
          rating:       info.rating       || item.rating      || null,
        };

        vodDetailsCache.set(vodId, d);
        setDetails(d);
      } catch (_) {
        // Échec silencieux : afficher les infos de base
        setDetails({ plot: '', genre: '', release_date: '', cast: '', director: '', backdrop: item.stream_icon || '', rating: item.rating || null });
      }
    }, 400);

    return () => {
      clearTimeout(timerRef.current);
    };
  }, [item, type, config]);

  return details;
}

// ── Extraction d'année depuis le titre ────────────────────────────────────────
// Cherche le nombre à 4 chiffres le plus à droite dans le nom (ex: "Film (2023)")

function extractYearFromName(name) {
  if (!name) return 0;
  const matches = String(name).match(/\b(19\d{2}|20[012]\d)\b/g);
  if (!matches) return 0;
  return parseInt(matches[matches.length - 1], 10); // le plus à droite
}

// ── Boutons de tri ────────────────────────────────────────────────────────────

const SORT_BTNS = [
  { key: 'alpha', label: 'A – Z' },
  { key: 'score', label: '⭐ Score' },
  { key: 'date',  label: '📅 Date' },
];

// sortState : null | { key: string, dir: 'asc'|'desc' }
function sortItems(items, sortState) {
  if (!sortState) return items;
  const { key, dir } = sortState;
  const f = dir === 'asc' ? 1 : -1;
  const arr = [...items];

  if (key === 'alpha') {
    arr.sort((a, b) => f * (a.name || '').localeCompare(b.name || '', 'fr', { sensitivity: 'base' }));
  } else if (key === 'score') {
    arr.sort((a, b) => f * ((parseFloat(a.rating) || 0) - (parseFloat(b.rating) || 0)));
  } else if (key === 'date') {
    arr.sort((a, b) => {
      // Priorité : release_date explicite → année extraite du nom → champ added (timestamp)
      const da = parseFloat(a.release_date || 0) || extractYearFromName(a.name) || parseFloat(a.added || 0);
      const db = parseFloat(b.release_date || 0) || extractYearFromName(b.name) || parseFloat(b.added || 0);
      return f * (da - db);
    });
  }
  return arr;
}

// ── Composant principal ───────────────────────────────────────────────────────

const ContentGrid = React.memo(function ContentGrid({
  items,
  type,
  onItemSelect,
  onToggleFavorite,
  favoritesSet,
  isActive,
  onFocusUp,
  onFocusLeft,
  config,
  categoryLabel = null,
  initialFocusIndex = 0,
}) {
  const [displayedCount, setDisplayedCount] = useState(PAGE_SIZE);
  const [focusedIndex,   setFocusedIndex]   = useState(initialFocusIndex);
  const [sortState,      setSortState]      = useState(null);       // null | {key, dir:'asc'|'desc'}
  const [zone,           setZone]           = useState('carousel'); // 'carousel' | 'header'
  const [headerIdx,      setHeaderIdx]      = useState(0);          // index bouton de tri focalisé

  // ── Confirmation suppression favori ──────────────────────────────────────
  const [favConfirm,    setFavConfirm]    = useState(null); // { item, effectiveType } | null
  const [favConfirmIdx, setFavConfirmIdx] = useState(0);    // 0=Annuler 1=Supprimer
  const favConfirmBtns = useRef([]);

  useEffect(() => {
    if (!favConfirm) return;
    const handler = (e) => {
      e.preventDefault(); e.stopPropagation();
      if (e.keyCode === KEY.LEFT || e.keyCode === KEY.RIGHT) {
        const next = favConfirmIdx === 0 ? 1 : 0;
        setFavConfirmIdx(next);
        favConfirmBtns.current[next]?.focus();
      } else if (e.keyCode === KEY.OK) {
        if (favConfirmIdx === 1) {
          // Supprimer : appliquer + focus première carte (liste mise à jour)
          onToggleFavorite(favConfirm.item, favConfirm.effectiveType);
          setTimeout(() => {
            const card = cardRefs.current[0];
            if (card) card.focus({ preventScroll: true });
            else onFocusUp?.();
          }, 80);
        } else {
          // Annuler : restaurer le focus sur la carte d'origine
          setTimeout(() => {
            const card = cardRefs.current[focusedIndex];
            if (card) card.focus({ preventScroll: true });
            else onFocusUp?.();
          }, 80);
        }
        setFavConfirm(null);
      } else if (e.keyCode === 461 || e.keyCode === 8) { // BACK
        setFavConfirm(null);
        setTimeout(() => {
          const card = cardRefs.current[focusedIndex];
          if (card) card.focus({ preventScroll: true });
          else onFocusUp?.();
        }, 80);
      }
    };
    document.addEventListener('keydown', handler, true);
    return () => document.removeEventListener('keydown', handler, true);
  }, [favConfirm, favConfirmIdx, focusedIndex, onToggleFavorite, onFocusUp]);

  const carouselRef  = useRef(null);
  const cardRefs     = useRef([]);
  const sortBtnRefs  = useRef([]);
  const restoredRef  = useRef(false); // empêche la restauration du focus après le 1er montage

  // ── Items triés ───────────────────────────────────────────────────────────
  const sortedItems = useMemo(() => sortItems(items, sortState), [items, sortState]);

  // Reset pagination + focus carrousel quand la liste change
  useEffect(() => {
    setDisplayedCount(PAGE_SIZE);
    setFocusedIndex(0);
    setZone('carousel');
  }, [items]);

  // Restauration du focus sur le dernier item joué (après retour du lecteur)
  // S'exécute après l'effet de reset ci-dessus (ordre de définition) → gagne la priorité
  useEffect(() => {
    if (restoredRef.current || items.length === 0) return;
    const lastItemId = usePlayerStore.getState().itemId;
    if (!lastItemId) { restoredRef.current = true; return; }
    const idx = sortedItems.findIndex(
      (item) => String(item.stream_id || item.series_id) === String(lastItemId)
    );
    if (idx < 0) { restoredRef.current = true; return; }
    restoredRef.current = true;
    if (idx >= PAGE_SIZE) setDisplayedCount(Math.ceil((idx + 1) / PAGE_SIZE) * PAGE_SIZE);
    setFocusedIndex(idx);
  }, [items]); // eslint-disable-line react-hooks/exhaustive-deps

  // ── Focus DOM ─────────────────────────────────────────────────────────────
  useEffect(() => {
    if (!isActive) return;
    if (zone === 'carousel') {
      const card = cardRefs.current[focusedIndex];
      if (card) {
        card.focus({ preventScroll: true });
        card.scrollIntoView({ behavior: 'smooth', block: 'nearest', inline: 'center' });
      }
    } else {
      sortBtnRefs.current[headerIdx]?.focus();
    }
  }, [focusedIndex, isActive, zone, headerIdx]);

  useEffect(() => {
    if (!isActive) return;
    if (zone === 'carousel') {
      cardRefs.current[focusedIndex]?.focus({ preventScroll: true });
    } else {
      sortBtnRefs.current[headerIdx]?.focus();
    }
  }, [isActive]);

  const visibleItems = useMemo(() => sortedItems.slice(0, displayedCount), [sortedItems, displayedCount]);
  const focusedItem  = visibleItems[focusedIndex] ?? null;

  // Détails enrichis de l'item focalisé
  const details = useItemDetails(focusedItem, type, config);

  const loadNextPage = useCallback(() => {
    if (displayedCount < sortedItems.length)
      setDisplayedCount((p) => Math.min(p + PAGE_SIZE, sortedItems.length));
  }, [displayedCount, sortedItems.length]);

  // ── Navigation clavier ────────────────────────────────────────────────────
  const handleKeyDown = useCallback((e) => {
    if (!isActive) return;

    // ── Zone : boutons de tri (header) ──────────────────────────────────────
    if (zone === 'header') {
      switch (e.keyCode) {
        case KEY.LEFT:
          e.preventDefault();
          if (headerIdx === 0) { onFocusLeft?.(); }
          else { setHeaderIdx((i) => i - 1); }
          break;
        case KEY.RIGHT:
          e.preventDefault();
          setHeaderIdx((i) => Math.min(i + 1, SORT_BTNS.length - 1));
          break;
        case KEY.UP:
          e.preventDefault();
          onFocusUp?.();
          break;
        case KEY.DOWN:
          e.preventDefault();
          setZone('carousel');
          break;
        case KEY.OK:
          e.preventDefault(); {
            const k = SORT_BTNS[headerIdx].key;
            setSortState((prev) => {
              if (!prev || prev.key !== k) return { key: k, dir: 'desc' };
              if (prev.dir === 'desc')     return { key: k, dir: 'asc' };
              return null;
            });
            setFocusedIndex(0);
          }
          break;
        default: break;
      }
      return;
    }

    // ── Zone : carrousel ────────────────────────────────────────────────────
    const total = visibleItems.length;
    switch (e.keyCode) {
      case KEY.RIGHT:
        e.preventDefault();
        if (focusedIndex + 1 < total) {
          const next = focusedIndex + 1;
          if (next >= displayedCount - 8) loadNextPage();
          setFocusedIndex(next);
        }
        break;
      case KEY.LEFT:
        e.preventDefault();
        if (focusedIndex === 0) { onFocusLeft?.(); return; }
        setFocusedIndex(focusedIndex - 1);
        break;
      case KEY.UP:
        e.preventDefault();
        // ↑ depuis le carrousel → boutons de tri
        setZone('header');
        break;
      case KEY.DOWN:
        e.preventDefault();
        // Dialog de suppression sur l'onglet favoris (type==='mixed')
        if (type === 'mixed' && focusedItem && onToggleFavorite) {
          const effectiveType = focusedItem.series_id && !focusedItem.stream_id ? 'series' : 'movie';
          setFavConfirmIdx(0);
          setFavConfirm({ item: focusedItem, effectiveType });
          setTimeout(() => favConfirmBtns.current[0]?.focus(), 50);
        } else if ((type === 'movie' || type === 'series') && focusedItem && onToggleFavorite) {
          // Toggle favori direct sur les onglets film/série
          onToggleFavorite(focusedItem, type);
        }
        break;
      default: return;
    }
  }, [isActive, zone, headerIdx, focusedIndex, visibleItems.length, displayedCount,
      focusedItem, type, onToggleFavorite,
      loadNextPage, onFocusUp, onFocusLeft]);

  // ── Données hero ──────────────────────────────────────────────────────────
  const heroTitle    = focusedItem?.name || '';
  const heroBackdrop = details?.backdrop || focusedItem?.stream_icon || focusedItem?.cover || '';
  const heroPlot     = details?.plot     || '';
  const heroGenre    = details?.genre    || '';
  const heroYear     = details?.release_date
    ? String(details.release_date).slice(0, 4)
    : (extractYearFromName(focusedItem?.name)
        ? String(extractYearFromName(focusedItem.name))
        : '');
  const heroCast     = details?.cast     || '';
  const heroDirector = details?.director || '';
  const heroRating   = details?.rating
    ? parseFloat(details.rating)
    : (focusedItem?.rating ? parseFloat(focusedItem.rating) : null);

  // Label carrousel : nom de catégorie si filtrée, sinon libellé par défaut
  const defaultLabel =
    type === 'movie'  ? 'Tous les films' :
    type === 'series' ? 'Toutes les séries' : 'Favoris';
  const carouselLabel = categoryLabel || defaultLabel;

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
    <div className="content-grid" onKeyDown={handleKeyDown} role="region">

      {/* ── Hero ─────────────────────────────────────────────────────────── */}
      <div className="content-hero">
        {heroBackdrop && (
          <div
            className="content-hero__backdrop"
            key={heroBackdrop}
            style={{ backgroundImage: `url(${heroBackdrop})` }}
          />
        )}
        <div className="content-hero__gradient" />
        <div className="content-hero__info">

          {/* Colonne gauche 40% */}
          <div className="content-hero__left">
            <h1 className="content-hero__title">{heroTitle}</h1>

            {(heroRating > 0 || heroYear || heroGenre) && (
              <div className="content-hero__meta">
                {heroRating > 0 && !isNaN(heroRating) && (
                  <span className="content-hero__rating">⭐ {heroRating.toFixed(1)}</span>
                )}
                {heroYear && <span className="content-hero__year">{heroYear}</span>}
                {heroGenre && <span className="content-hero__genre">{heroGenre}</span>}
              </div>
            )}

            {heroDirector && (
              <p className="content-hero__director">
                <span className="content-hero__label">Réalisateur : </span>{heroDirector}
              </p>
            )}
            {heroCast && (
              <p className="content-hero__cast">
                <span className="content-hero__label">Acteurs : </span>{heroCast}
              </p>
            )}
          </div>

          {/* Colonne droite 60% : synopsis */}
          {heroPlot && (
            <div className="content-hero__right">
              <p className="content-hero__plot">{heroPlot}</p>
            </div>
          )}
        </div>
      </div>

      {/* ── Carrousel ─────────────────────────────────────────────────────── */}
      <div className="content-carousel">
        <div className="content-carousel__header">
          {/* GAUCHE : label catégorie */}
          <span className="content-carousel__label">{carouselLabel}</span>

          {/* CENTRE : boutons de tri */}
          <div className="content-sort">
            {SORT_BTNS.map((btn, idx) => {
              const isActive  = sortState?.key === btn.key;
              const isFocused = zone === 'header' && headerIdx === idx;
              const arrow     = isActive ? (sortState.dir === 'asc' ? ' ▲' : ' ▼') : '';
              return (
                <button
                  key={btn.key}
                  ref={(el) => (sortBtnRefs.current[idx] = el)}
                  className={[
                    'content-sort__btn',
                    isActive  ? 'content-sort__btn--active'  : '',
                    isFocused ? 'content-sort__btn--focused' : '',
                  ].filter(Boolean).join(' ')}
                  tabIndex={isFocused ? 0 : -1}
                  onClick={() => {
                    setSortState((prev) => {
                      if (!prev || prev.key !== btn.key) return { key: btn.key, dir: 'desc' };
                      if (prev.dir === 'desc')           return { key: btn.key, dir: 'asc' };
                      return null;
                    });
                    setFocusedIndex(0);
                  }}
                >
                  {btn.label}{arrow}
                </button>
              );
            })}
          </div>

          {/* DROITE : compteur */}
          <span className="content-carousel__count">
            {focusedIndex + 1} / {sortedItems.length}
          </span>
        </div>

        <div className="content-carousel__track" ref={carouselRef}>
          {visibleItems.map((item, idx) => {
            const itemId = item.stream_id || item.series_id;
            return (
              <ContentCard
                key={item.stream_id || item.series_id || idx}
                item={item}
                type={type}
                isFocused={idx === focusedIndex && isActive && zone === 'carousel'}
                isFav={favoritesSet ? favoritesSet.has(String(itemId)) : false}
                onSelect={onItemSelect}
                tabIndex={idx === focusedIndex && zone === 'carousel' ? 0 : -1}
                cardRef={(el) => (cardRefs.current[idx] = el)}
              />
            );
          })}
        </div>
      </div>

      {/* ── Confirmation suppression favori ─────────────────────────────── */}
      {favConfirm && (
        <div className="fav-confirm-overlay">
          <div className="fav-confirm-box">
            <p className="fav-confirm-msg">
              Retirer <strong>{favConfirm.item.name}</strong> des favoris ?
            </p>
            <div className="fav-confirm-btns">
              <button
                ref={(el) => (favConfirmBtns.current[0] = el)}
                className={`fav-confirm-btn${favConfirmIdx === 0 ? ' fav-confirm-btn--focused' : ''}`}
                tabIndex={favConfirmIdx === 0 ? 0 : -1}
              >
                Annuler
              </button>
              <button
                ref={(el) => (favConfirmBtns.current[1] = el)}
                className={`fav-confirm-btn fav-confirm-btn--danger${favConfirmIdx === 1 ? ' fav-confirm-btn--focused' : ''}`}
                tabIndex={favConfirmIdx === 1 ? 0 : -1}
              >
                Supprimer
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
});

export default ContentGrid;
