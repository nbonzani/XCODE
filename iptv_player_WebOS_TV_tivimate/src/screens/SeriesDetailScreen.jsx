/**
 * src/screens/SeriesDetailScreen.jsx
 *
 * Layout deux colonnes :
 *   [Gauche élargi : affiche + infos + 3 boutons]   [Saisons | Épisodes]
 *
 * Boutons panneau gauche (navigation ←/→) :
 *   idx 0 : ← Retour
 *   idx 1 : ☆ Favoris
 *   idx 2 : ▶ Lire épisode
 *
 * Navigation complète (focusPanel) :
 *   'left'     ←→ entre boutons  ↓ → 'seasons'  → (depuis btn2) → 'seasons'
 *   'seasons'  ← → 'left'        ↑(0) → 'left'  → → 'episodes'  ↑↓ dans liste
 *   'episodes' ← → 'seasons'     ↑(0) → 'left'  ↑↓ dans liste
 *   BACK → accueil depuis tout panneau
 */

import React, { useEffect, useState, useCallback, useRef } from 'react';
import { useNavigate, useParams, useLocation } from 'react-router-dom';
import { useAppStore }    from '../store/appStore.js';
import { useWakeLock }    from '../hooks/useWakeLock.js';
import { usePlayerStore } from '../store/playerStore.js';
import { createClientFromConfig } from '../services/xtreamApi.js';
import { markEpisodeWatched, getWatchedEpisodesSet, setLastWatchedSeries } from '../services/watchHistoryService.js';
import { getWatchPosition } from '../services/watchPositionService.js';
import { isFavorite, toggleFavorite } from '../services/favoritesService.js';
import { KEY, isBackKey } from '../constants/keyCodes.js';
import PosterImage from '../components/home/PosterImage.jsx';
import './SeriesDetailScreen.css';

// ── Nombre de boutons dans le panneau gauche ──────────────────────────────────
const LEFT_BTN_COUNT = 3; // 0=Retour  1=Favoris  2=Lire épisode

// ── En-tête série ─────────────────────────────────────────────────────────────

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
      <PosterImage url={coverUrl} alt={seriesName} type="series" width={200} height={290} />
      <div className="series-header__info">
        <h1 className="series-header__title">{seriesName}</h1>
        {metaParts.length > 0 && (
          <p className="series-header__meta">{metaParts.join('  ·  ')}</p>
        )}
        {plot && (
          <p className="series-header__plot">
            {plot.length > 350 ? plot.slice(0, 350) + '…' : plot}
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
    <div ref={listRef}
      className={`season-list ${isFocused ? 'season-list--focused' : ''}`}
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
    <div ref={listRef}
      className={`episode-list ${isFocused ? 'episode-list--focused' : ''}`}
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
  const { id }        = useParams();
  const navigate      = useNavigate();
  const { state: locationState } = useLocation();
  const { config }                   = useAppStore();
  useWakeLock();
  const { playPlaylist } = usePlayerStore();

  const [seriesInfo,   setSeriesInfo]   = useState(null);
  const [seasons,      setSeasons]      = useState([]);
  const [activeSeason, setActiveSeason] = useState(null);
  const [watchedSet,   setWatchedSet]   = useState(new Set());
  const [isLoading,    setIsLoading]    = useState(true);
  const [loadError,    setLoadError]    = useState(null);
  const [isFav,        setIsFav]        = useState(false);

  // focusPanel : 'left' | 'seasons' | 'episodes'
  const [focusPanel,        setFocusPanel]        = useState('seasons');
  const [seasonFocusIndex,  setSeasonFocusIndex]  = useState(0);
  const [episodeFocusIndex, setEpisodeFocusIndex] = useState(0);
  const [leftFocusIndex,    setLeftFocusIndex]    = useState(0); // 0=Retour 1=Favoris 2=Lire

  const seasonListRef  = useRef(null);
  const episodeListRef = useRef(null);
  const leftBtnRefs    = useRef([]);

  const activeEpisodes = seasons.find((s) => s.season_num === activeSeason)?.episodes || [];
  const focusedEpisode = activeEpisodes[episodeFocusIndex] ?? null;

  // ── Refs miroirs (évite les closures périmées) ────────────────────────────
  const focusPanelRef        = useRef(focusPanel);
  const seasonFocusIdxRef    = useRef(seasonFocusIndex);
  const episodeFocusIdxRef   = useRef(episodeFocusIndex);
  const leftFocusIdxRef      = useRef(leftFocusIndex);

  useEffect(() => { focusPanelRef.current = focusPanel; },          [focusPanel]);
  useEffect(() => { seasonFocusIdxRef.current = seasonFocusIndex; }, [seasonFocusIndex]);
  useEffect(() => { episodeFocusIdxRef.current = episodeFocusIndex; },[episodeFocusIndex]);
  useEffect(() => { leftFocusIdxRef.current = leftFocusIndex; },    [leftFocusIndex]);

  // ── Focus DOM helper ──────────────────────────────────────────────────────
  const applyFocus = useCallback(() => {
    requestAnimationFrame(() => {
      const panel = focusPanelRef.current;
      if (panel === 'seasons') {
        const items = seasonListRef.current?.querySelectorAll('.season-item');
        const el = items?.[seasonFocusIdxRef.current];
        el?.focus({ preventScroll: true });
        el?.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
      } else if (panel === 'episodes') {
        const items = episodeListRef.current?.querySelectorAll('.episode-item');
        const el = items?.[episodeFocusIdxRef.current];
        el?.focus({ preventScroll: true });
        el?.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
      } else if (panel === 'left') {
        leftBtnRefs.current[leftFocusIdxRef.current]?.focus();
      }
    });
  }, []);

  useEffect(() => {
    if (!isLoading) applyFocus();
  }, [focusPanel, seasonFocusIndex, episodeFocusIndex, leftFocusIndex, isLoading, applyFocus]);

  // ── Chargement ────────────────────────────────────────────────────────────
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

        const focusEpisodeId = locationState?.focusEpisodeId;
        let targetSeason = seasonList[0]?.season_num || null;
        let targetEpIdx  = 0;

        if (focusEpisodeId) {
          // Reprendre : chercher l'épisode exact par son ID
          outer: for (const s of seasonList) {
            for (let i = 0; i < s.episodes.length; i++) {
              if (String(s.episodes[i].id) === String(focusEpisodeId)) {
                targetSeason = s.season_num;
                targetEpIdx  = i;
                break outer;
              }
            }
          }
        } else {
          // Comportement par défaut : premier épisode non visionné
          const watched = getWatchedEpisodesSet(seriesId);
          outer: for (const s of seasonList) {
            for (let i = 0; i < s.episodes.length; i++) {
              if (!watched.has(String(s.episodes[i].id))) {
                targetSeason = s.season_num;
                targetEpIdx  = i;
                break outer;
              }
            }
          }
        }

        setActiveSeason(targetSeason);
        setEpisodeFocusIndex(targetEpIdx);
        // Reprendre → focus direct sur les épisodes ; sinon seulement si 1 saison
        if (focusEpisodeId || seasonList.length <= 1) setFocusPanel('episodes');
        setIsLoading(false);
      })
      .catch((err) => { setLoadError(err.message); setIsLoading(false); });
  }, [id, config, navigate]);

  // Focus après chargement
  useEffect(() => {
    if (isLoading || loadError) return;
    const t = setTimeout(applyFocus, 100);
    return () => clearTimeout(t);
  }, [isLoading, loadError, applyFocus]);

  // ── Actions ───────────────────────────────────────────────────────────────
  const handleSeasonSelect = useCallback((seasonNum) => {
    setActiveSeason(seasonNum);
    setEpisodeFocusIndex(0);
    setFocusPanel('episodes');
  }, []);

  const launchEpisode = useCallback((ep) => {
    if (!ep) return;
    const client      = createClientFromConfig(config);
    const seriesId    = parseInt(id, 10);
    const seriesName  = seriesInfo?.name || `Série #${id}`;
    const allEps      = activeEpisodes;
    const epIdx       = allEps.findIndex((e) => e.id === ep.id);
    const playlist    = allEps.map((e) => ({
      url:       client.getEpisodeUrl(e.id, e.container_extension || 'mkv'),
      title:     `${seriesName} — ${e.title || `Épisode ${e.episode_num}`}`,
      episodeId: e.id,
    }));
    markEpisodeWatched(ep.id, seriesId);
    setLastWatchedSeries(
      seriesId, seriesName,
      ep.title || `Épisode ${ep.episode_num}`,
      ep.id,
      client.getEpisodeUrl(ep.id, ep.container_extension || 'mkv'),
    );
    setWatchedSet(getWatchedEpisodesSet(seriesId));
    playPlaylist(playlist, epIdx >= 0 ? epIdx : 0, getWatchPosition(ep.id));
    navigate('/player');
  }, [config, id, seriesInfo, activeEpisodes, playPlaylist, navigate]);

  const handleToggleFav = useCallback(() => {
    const seriesId   = parseInt(id, 10);
    const seriesName = seriesInfo?.name || `Série #${id}`;
    const coverUrl   = seriesInfo?.cover || '';
    const data = { series_id: seriesId, name: seriesName, cover: coverUrl,
                   rating: seriesInfo?.rating, genre: seriesInfo?.genre };
    setIsFav(toggleFavorite(data, 'series'));
  }, [id, seriesInfo]);

  // ── Navigation télécommande ───────────────────────────────────────────────
  useEffect(() => {
    const handler = (e) => {
      if (isBackKey(e.keyCode)) { e.preventDefault(); navigate('/'); return; }
      const kc = e.keyCode;

      // ── Panneau gauche (3 boutons horizontaux) ──
      if (focusPanel === 'left') {
        if (kc === KEY.LEFT) {
          e.preventDefault();
          setLeftFocusIndex((i) => Math.max(i - 1, 0));
        } else if (kc === KEY.RIGHT) {
          e.preventDefault();
          if (leftFocusIndex < LEFT_BTN_COUNT - 1) {
            setLeftFocusIndex((i) => i + 1);
          } else {
            // dernier bouton → aller vers saisons
            setFocusPanel('seasons');
          }
        } else if (kc === KEY.DOWN) {
          e.preventDefault();
          setFocusPanel('seasons');
        } else if (kc === KEY.OK) {
          e.preventDefault();
          leftBtnRefs.current[leftFocusIndex]?.click();
        }

      // ── Saisons ──
      } else if (focusPanel === 'seasons') {
        if (kc === KEY.UP) {
          e.preventDefault();
          if (seasonFocusIndex === 0) {
            setLeftFocusIndex(0);
            setFocusPanel('left');
          } else {
            setSeasonFocusIndex((i) => i - 1);
          }
        } else if (kc === KEY.DOWN) {
          e.preventDefault();
          if (seasonFocusIndex < seasons.length - 1)
            setSeasonFocusIndex((i) => i + 1);
        } else if (kc === KEY.LEFT) {
          e.preventDefault();
          setLeftFocusIndex(0);
          setFocusPanel('left');
        } else if (kc === KEY.RIGHT) {
          e.preventDefault();
          setFocusPanel('episodes');
        } else if (kc === KEY.OK) {
          e.preventDefault();
          const s = seasons[seasonFocusIndex];
          if (s) handleSeasonSelect(s.season_num);
        }

      // ── Épisodes ──
      } else if (focusPanel === 'episodes') {
        if (kc === KEY.UP) {
          e.preventDefault();
          if (episodeFocusIndex === 0) {
            setLeftFocusIndex(2); // focus sur "Lire épisode"
            setFocusPanel('left');
          } else {
            setEpisodeFocusIndex((i) => i - 1);
          }
        } else if (kc === KEY.DOWN) {
          e.preventDefault();
          if (episodeFocusIndex < activeEpisodes.length - 1)
            setEpisodeFocusIndex((i) => i + 1);
        } else if (kc === KEY.LEFT) {
          e.preventDefault();
          setFocusPanel('seasons');
        } else if (kc === KEY.OK) {
          e.preventDefault();
          launchEpisode(activeEpisodes[episodeFocusIndex]);
        }
      }
    };

    document.addEventListener('keydown', handler);
    return () => document.removeEventListener('keydown', handler);
  }, [
    focusPanel, seasons, seasonFocusIndex,
    activeEpisodes, episodeFocusIndex, leftFocusIndex,
    handleSeasonSelect, launchEpisode, navigate,
  ]);

  // ── Rendu ──────────────────────────────────────────────────────────────────
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
      <p style={{ color: 'var(--color-error)', fontSize: 'var(--font-size-lg)' }}>❌ {loadError}</p>
      <button className="action-button" tabIndex={0} onClick={() => navigate('/')}
        style={{ marginTop: 'var(--space-4)', padding: 'var(--space-2) var(--space-5)',
                 background: 'var(--color-accent)', color: '#fff',
                 border: 'none', borderRadius: 'var(--radius-md)', fontSize: 'var(--font-size-md)' }}>
        Retour
      </button>
    </div>
  );

  const epLabel = focusedEpisode
    ? `▶  Épisode ${focusedEpisode.episode_num}`
    : '▶  Lire';

  return (
    <div className="series-screen">

      {/* ── Colonne gauche ── */}
      <div className="series-screen__left">
        <SeriesHeader info={seriesInfo} coverUrl={coverUrl} seriesName={seriesName} />

        {/* 3 boutons horizontaux navigués avec ←/→ */}
        <div className="series-screen__actions">
          {/* 0 — Retour */}
          <button
            ref={(el) => (leftBtnRefs.current[0] = el)}
            className={`series-action-btn ${focusPanel === 'left' && leftFocusIndex === 0 ? 'focused' : ''}`}
            tabIndex={focusPanel === 'left' && leftFocusIndex === 0 ? 0 : -1}
            onClick={() => navigate('/')}
          >
            ← Retour
          </button>

          {/* 1 — Favoris */}
          <button
            ref={(el) => (leftBtnRefs.current[1] = el)}
            className={`series-action-btn ${isFav ? 'series-action-btn--fav-active' : ''} ${focusPanel === 'left' && leftFocusIndex === 1 ? 'focused' : ''}`}
            tabIndex={focusPanel === 'left' && leftFocusIndex === 1 ? 0 : -1}
            onClick={handleToggleFav}
          >
            {isFav ? '★ Favoris' : '☆ Favoris'}
          </button>

          {/* 2 — Lire épisode */}
          <button
            ref={(el) => (leftBtnRefs.current[2] = el)}
            className={`series-action-btn series-action-btn--play ${focusPanel === 'left' && leftFocusIndex === 2 ? 'focused' : ''}`}
            tabIndex={focusPanel === 'left' && leftFocusIndex === 2 ? 0 : -1}
            disabled={!focusedEpisode}
            onClick={() => launchEpisode(focusedEpisode)}
          >
            {epLabel}
          </button>
        </div>
      </div>

      {/* ── Colonne droite (saisons + épisodes) ── */}
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
      </div>

    </div>
  );
}
