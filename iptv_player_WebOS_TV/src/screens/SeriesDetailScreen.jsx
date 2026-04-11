/**
 * src/screens/SeriesDetailScreen.jsx
 * Écran détail série : couverture, synopsis, saisons, épisodes.
 * Portage de SeriesDialog de series_dialog.py.
 *
 * Mise en page deux colonnes :
 *   Gauche  : couverture + titre + synopsis
 *   Droite  : liste saisons | liste épisodes + barre d'actions
 *
 * Navigation télécommande :
 *   ↑/↓       → déplace le focus dans la liste active (saisons ou épisodes)
 *   ←/→       → bascule le focus entre les deux listes
 *   OK        → sélectionne la saison / lance l'épisode
 *   BACK      → retour à HomeScreen
 *   Vert (🟢) → lire toute la saison active
 */

import React, { useEffect, useState, useCallback, useRef } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useAppStore }    from '../store/appStore.js';
import { usePlayerStore } from '../store/playerStore.js';
import { createClientFromConfig } from '../services/xtreamApi.js';
import { markEpisodeWatched, getWatchedEpisodesSet, setLastWatchedSeries } from '../services/watchHistoryService.js';
import { getWatchPosition } from '../services/watchPositionService.js';
import { isFavorite, toggleFavorite } from '../services/favoritesService.js';
import { KEY, isBackKey } from '../constants/keyCodes.js';
import PosterImage from '../components/home/PosterImage.jsx';
import './SeriesDetailScreen.css';

// ── En-tête série (colonne gauche) ───────────────────────────────────────────

function SeriesHeader({ info, coverUrl, seriesName }) {
  const metaParts = [];
  if (info?.genre)        metaParts.push(info.genre);
  if (info?.release_date) metaParts.push(String(info.release_date).slice(0, 4));
  if (info?.rating) {
    const r = parseFloat(info.rating);
    if (!isNaN(r)) metaParts.push(`⭐ ${r.toFixed(1)}`);
  }
  const plot = info?.plot || '';

  return (
    <div className="series-header">
      <PosterImage url={coverUrl} alt={seriesName} type="series" width={180} height={260} />
      <div className="series-header__info">
        <h1 className="series-header__title">{seriesName}</h1>
        {metaParts.length > 0 && (
          <p className="series-header__meta">{metaParts.join('  |  ')}</p>
        )}
        {plot && (
          <p className="series-header__plot">
            {plot.length > 300 ? plot.slice(0, 300) + '…' : plot}
          </p>
        )}
      </div>
    </div>
  );
}

// ── Liste des saisons ─────────────────────────────────────────────────────────

const SeasonList = React.memo(function SeasonList({
  seasons, activeSeason, watchedSet,
  onSeasonSelect, isFocused, focusedIndex, listRef,
}) {
  return (
    <div ref={listRef} className={`season-list ${isFocused ? 'season-list--focused' : ''}`}
      role="listbox" aria-label="Saisons">
      <div className="list-title">Saisons</div>
      {seasons.map((season, idx) => {
        const eps        = season.episodes || [];
        const nWatched   = eps.filter((ep) => watchedSet.has(String(ep.id))).length;
        const isComplete = nWatched === eps.length && eps.length > 0;
        const isActive   = activeSeason === season.season_num;
        const isFocusedItem = isFocused && focusedIndex === idx;

        let suffix = `${eps.length} ép.`;
        if (isComplete)        suffix = '✅ terminée';
        else if (nWatched > 0) suffix = `${nWatched}/${eps.length} vus`;

        return (
          <div key={season.season_num}
            className={`season-item ${isActive ? 'season-item--active' : ''} ${isFocusedItem ? 'focused' : ''}`}
            tabIndex={isFocusedItem ? 0 : -1}
            role="option" aria-selected={isActive}
            onClick={() => onSeasonSelect(season.season_num)}
          >
            <span className="season-item__icon">📂</span>
            <span className="season-item__label">
              Saison {season.season_num}
              <span className="season-item__count"> — {suffix}</span>
            </span>
          </div>
        );
      })}
    </div>
  );
});

// ── Liste des épisodes ────────────────────────────────────────────────────────

const EpisodeList = React.memo(function EpisodeList({
  episodes, watchedSet, isFocused, focusedIndex, onEpisodeSelect, listRef,
}) {
  if (!episodes || episodes.length === 0) {
    return (
      <div className="episode-list episode-list--empty">
        <p>Sélectionnez une saison.</p>
      </div>
    );
  }
  return (
    <div ref={listRef} className={`episode-list ${isFocused ? 'episode-list--focused' : ''}`}
      role="listbox" aria-label="Épisodes">
      <div className="list-title">Épisodes</div>
      {episodes.map((ep, idx) => {
        const isWatched     = watchedSet.has(String(ep.id));
        const isFocusedItem = isFocused && focusedIndex === idx;
        const epTitle       = ep.title || `Épisode ${ep.episode_num}`;
        return (
          <div key={ep.id || idx}
            className={`episode-item ${isWatched ? 'episode-item--watched' : ''} ${isFocusedItem ? 'focused' : ''}`}
            tabIndex={isFocusedItem ? 0 : -1}
            role="option"
            onClick={() => onEpisodeSelect(ep)}
          >
            <span className="episode-item__num">Ép.{ep.episode_num}</span>
            <span className="episode-item__title">{epTitle}</span>
            {isWatched && <span className="episode-item__badge">✅</span>}
          </div>
        );
      })}
    </div>
  );
});

// ── Écran principal ───────────────────────────────────────────────────────────

export default function SeriesDetailScreen() {
  const { id }   = useParams();
  const navigate = useNavigate();
  const { config }                   = useAppStore();
  const { playSingle, playPlaylist } = usePlayerStore();

  const [seriesInfo,   setSeriesInfo]   = useState(null);
  const [seasons,      setSeasons]      = useState([]);
  const [activeSeason, setActiveSeason] = useState(null);
  const [watchedSet,   setWatchedSet]   = useState(new Set());
  const [isLoading,    setIsLoading]    = useState(true);
  const [loadError,    setLoadError]    = useState(null);
  const [isFav,        setIsFav]        = useState(false);

  // Panneaux de focus : 'left', 'seasons', 'episodes', 'actions'
  const [focusPanel,        setFocusPanel]        = useState('seasons');
  const [seasonFocusIndex,  setSeasonFocusIndex]  = useState(0);
  const [episodeFocusIndex, setEpisodeFocusIndex] = useState(0);
  const [leftFocusIndex,    setLeftFocusIndex]    = useState(0);  // 0=retour, 1=favoris
  const [actionFocusIndex,  setActionFocusIndex]  = useState(0);  // 0=lire épisode, 1=lire saison

  const seasonListRef  = useRef(null);
  const episodeListRef = useRef(null);
  const leftBtnRefs    = useRef([]);
  const actionBtnRefs  = useRef([]);

  const activeEpisodes = seasons.find((s) => s.season_num === activeSeason)?.episodes || [];

  // ── Chargement ────────────────────────────────────────────────────────
  useEffect(() => {
    if (!id) { navigate('/'); return; }
    const seriesId = parseInt(id, 10);
    setWatchedSet(getWatchedEpisodesSet(seriesId));
    setIsFav(isFavorite(seriesId, 'series'));

    createClientFromConfig(config)
      .getSeriesInfo(seriesId)
      .then((data) => {
        setSeriesInfo(data?.info || null);

        const rawEpisodes = data?.episodes || {};
        const seasonList  = Object.entries(rawEpisodes)
          .map(([num, eps]) => ({ season_num: num, episodes: Array.isArray(eps) ? eps : [] }))
          .sort((a, b) => (parseInt(a.season_num) || 0) - (parseInt(b.season_num) || 0));

        setSeasons(seasonList);

        // Premier épisode non visionné
        const watched = getWatchedEpisodesSet(seriesId);
        let firstSeason  = seasonList[0]?.season_num || null;
        let firstEpIdx   = 0;
        outer: for (const s of seasonList) {
          for (let i = 0; i < s.episodes.length; i++) {
            if (!watched.has(String(s.episodes[i].id))) {
              firstSeason = s.season_num;
              firstEpIdx  = i;
              break outer;
            }
          }
        }
        setActiveSeason(firstSeason);
        setEpisodeFocusIndex(firstEpIdx);
        setIsLoading(false);
      })
      .catch((err) => { setLoadError(err.message); setIsLoading(false); });
  }, [id, config, navigate]);

  // ── Actions ───────────────────────────────────────────────────────────
  const handleSeasonSelect = useCallback((seasonNum) => {
    setActiveSeason(seasonNum);
    setEpisodeFocusIndex(0);
    setFocusPanel('episodes');
  }, []);

  const launchEpisode = useCallback((ep) => {
    const client     = createClientFromConfig(config);
    const seriesId   = parseInt(id, 10);
    const seriesName = seriesInfo?.name || `Série #${id}`;

    // Construire la playlist de tous les épisodes de la saison active
    const allEps = activeEpisodes;
    const epIdx  = allEps.findIndex((e) => e.id === ep.id);
    const playlist = allEps.map((e) => ({
      url:       client.getEpisodeUrl(e.id, e.container_extension || 'mkv'),
      title:     `${seriesName} — ${e.title || `Épisode ${e.episode_num}`}`,
      episodeId: e.id,
    }));

    const epUrl      = client.getEpisodeUrl(ep.id, ep.container_extension || 'mkv');
    const epTitle    = ep.title || `Épisode ${ep.episode_num}`;
    // Position sauvegardée pour cet épisode (0 si nouveau)
    const savedPos   = getWatchPosition(ep.id);

    markEpisodeWatched(ep.id, seriesId);
    setLastWatchedSeries(seriesId, seriesName, epTitle, ep.id, epUrl);
    setWatchedSet(getWatchedEpisodesSet(seriesId));
    playPlaylist(playlist, epIdx >= 0 ? epIdx : 0, savedPos);
    navigate('/player');
  }, [config, id, seriesInfo, activeEpisodes, playPlaylist, navigate]);

  // ── Navigation télécommande ───────────────────────────────────────────
  //
  // Layout :  [Colonne gauche]  [Saisons]  [Épisodes]
  //           [Retour|Favoris]             [▶ Épisode | ▶ Saison]
  //
  //   left ←→ seasons ←→ episodes
  //   seasons ↓ (dernier) → actions
  //   episodes ↓ (dernier) → actions
  //   actions ↑ → episodes
  //   actions ←→ entre boutons
  //   left ↑/↓ entre retour et favoris
  //
  useEffect(() => {
    const handler = (e) => {
      if (isBackKey(e.keyCode)) { e.preventDefault(); navigate('/'); return; }

      if (focusPanel === 'left') {
        if      (e.keyCode === KEY.DOWN)  { e.preventDefault(); setLeftFocusIndex((i) => Math.min(i + 1, 1)); }
        else if (e.keyCode === KEY.UP)    { e.preventDefault(); setLeftFocusIndex((i) => Math.max(i - 1, 0)); }
        else if (e.keyCode === KEY.RIGHT) { e.preventDefault(); setFocusPanel('seasons'); }
        else if (e.keyCode === KEY.OK)    { e.preventDefault(); leftBtnRefs.current[leftFocusIndex]?.click(); }
      }
      else if (focusPanel === 'seasons') {
        if (e.keyCode === KEY.DOWN) {
          e.preventDefault();
          if (seasonFocusIndex >= seasons.length - 1) { setActionFocusIndex(0); setFocusPanel('actions'); }
          else setSeasonFocusIndex((i) => i + 1);
        }
        else if (e.keyCode === KEY.UP) {
          e.preventDefault();
          // ↑ en haut de la liste → panneau gauche (Retour / Favoris)
          if (seasonFocusIndex === 0) { setLeftFocusIndex(0); setFocusPanel('left'); }
          else setSeasonFocusIndex((i) => i - 1);
        }
        else if (e.keyCode === KEY.OK)    { e.preventDefault(); const s = seasons[seasonFocusIndex]; if (s) handleSeasonSelect(s.season_num); }
        else if (e.keyCode === KEY.RIGHT) { e.preventDefault(); setFocusPanel('episodes'); }
        else if (e.keyCode === KEY.LEFT)  { e.preventDefault(); setLeftFocusIndex(0); setFocusPanel('left'); }
      }
      else if (focusPanel === 'episodes') {
        if (e.keyCode === KEY.DOWN) {
          e.preventDefault();
          if (episodeFocusIndex >= activeEpisodes.length - 1) { setActionFocusIndex(0); setFocusPanel('actions'); }
          else setEpisodeFocusIndex((i) => i + 1);
        }
        else if (e.keyCode === KEY.UP)    { e.preventDefault(); setEpisodeFocusIndex((i) => Math.max(i - 1, 0)); }
        else if (e.keyCode === KEY.OK)    { e.preventDefault(); const ep = activeEpisodes[episodeFocusIndex]; if (ep) launchEpisode(ep); }
        else if (e.keyCode === KEY.LEFT)  { e.preventDefault(); setFocusPanel('seasons'); }
      }
      else if (focusPanel === 'actions') {
        if      (e.keyCode === KEY.UP)    { e.preventDefault(); setFocusPanel('episodes'); }
        else if (e.keyCode === KEY.OK)    { e.preventDefault(); actionBtnRefs.current[0]?.click(); }
      }
    };
    document.addEventListener('keydown', handler);
    return () => document.removeEventListener('keydown', handler);
  }, [focusPanel, seasons, seasonFocusIndex, activeEpisodes, episodeFocusIndex,
      leftFocusIndex, actionFocusIndex,
      handleSeasonSelect, launchEpisode, navigate]);

  // ── Scroll/focus automatique vers l'item focusé ────────────────────────
  useEffect(() => {
    if (focusPanel === 'seasons' || focusPanel === 'episodes') {
      const listRef = focusPanel === 'seasons' ? seasonListRef : episodeListRef;
      const idx     = focusPanel === 'seasons' ? seasonFocusIndex : episodeFocusIndex;
      const items   = listRef.current?.querySelectorAll('.season-item, .episode-item');
      if (items?.[idx]) {
        items[idx].scrollIntoView({ block: 'nearest', behavior: 'smooth' });
        items[idx].focus({ preventScroll: true });
      }
    } else if (focusPanel === 'left') {
      leftBtnRefs.current[leftFocusIndex]?.focus();
    } else if (focusPanel === 'actions') {
      actionBtnRefs.current[actionFocusIndex]?.focus();
    }
  }, [focusPanel, seasonFocusIndex, episodeFocusIndex, leftFocusIndex, actionFocusIndex]);

  // ── Rendu ──────────────────────────────────────────────────────────────
  const seriesName = seriesInfo?.name || `Série #${id}`;
  const coverUrl   = seriesInfo?.cover || seriesInfo?.backdrop_path || '';

  if (isLoading) return (
    <div className="series-screen series-screen--center">
      <div className="spinner" />
      <p style={{ color: 'var(--color-text-secondary)', marginTop: 'var(--space-3)' }}>
        Chargement des épisodes…
      </p>
    </div>
  );

  if (loadError) return (
    <div className="series-screen series-screen--center">
      <p style={{ color: 'var(--color-error)', fontSize: 'var(--font-size-lg)' }}>
        ❌ {loadError}
      </p>
      <button className="action-button" tabIndex={0} onClick={() => navigate('/')}
        style={{ marginTop: 'var(--space-4)', padding: 'var(--space-2) var(--space-5)',
                 background: 'var(--color-accent)', color: 'var(--color-text-inverse)',
                 border: 'none', borderRadius: 'var(--radius-md)', fontSize: 'var(--font-size-md)' }}>
        Retour
      </button>
    </div>
  );

  return (
    <div className="series-screen">

      {/* Colonne gauche */}
      <div className="series-screen__left">
        <SeriesHeader info={seriesInfo} coverUrl={coverUrl} seriesName={seriesName} />
        <div className="series-screen__left-actions">
          <button
            ref={(el) => (leftBtnRefs.current[0] = el)}
            className={`series-back-btn action-button ${focusPanel === 'left' && leftFocusIndex === 0 ? 'focused' : ''}`}
            tabIndex={focusPanel === 'left' && leftFocusIndex === 0 ? 0 : -1}
            onClick={() => navigate('/')}
          >
            ← Retour
          </button>
          <button
            ref={(el) => (leftBtnRefs.current[1] = el)}
            className={`series-fav-btn action-button ${isFav ? 'series-fav-btn--active' : ''} ${focusPanel === 'left' && leftFocusIndex === 1 ? 'focused' : ''}`}
            tabIndex={focusPanel === 'left' && leftFocusIndex === 1 ? 0 : -1}
            onClick={() => {
              const seriesData = { series_id: parseInt(id, 10), name: seriesName, cover: coverUrl, rating: seriesInfo?.rating, genre: seriesInfo?.genre };
              const added = toggleFavorite(seriesData, 'series');
              setIsFav(added);
            }}
          >
            {isFav ? '★ Retirer des favoris' : '☆ Ajouter aux favoris'}
          </button>
        </div>
      </div>

      {/* Colonne droite */}
      <div className="series-screen__right">
        <div className="series-screen__lists">
          <SeasonList
            seasons={seasons} activeSeason={activeSeason} watchedSet={watchedSet}
            onSeasonSelect={handleSeasonSelect}
            isFocused={focusPanel === 'seasons'}
            focusedIndex={seasonFocusIndex} listRef={seasonListRef}
          />
          <EpisodeList
            episodes={activeEpisodes} watchedSet={watchedSet}
            isFocused={focusPanel === 'episodes'}
            focusedIndex={episodeFocusIndex}
            onEpisodeSelect={launchEpisode} listRef={episodeListRef}
          />
        </div>

        <div className="series-action-bar">
          <button
            ref={(el) => (actionBtnRefs.current[0] = el)}
            className={`series-action-bar__btn series-action-bar__btn--episode action-button ${focusPanel === 'actions' ? 'focused' : ''}`}
            tabIndex={focusPanel === 'actions' ? 0 : -1}
            disabled={activeEpisodes.length === 0}
            onClick={() => { const ep = activeEpisodes[episodeFocusIndex]; if (ep) launchEpisode(ep); }}
          >
            ▶ Lire la saison ({activeEpisodes.length} ép.)
          </button>
        </div>
      </div>

    </div>
  );
}
