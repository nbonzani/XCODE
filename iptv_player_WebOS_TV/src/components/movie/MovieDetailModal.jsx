/**
 * src/components/movie/MovieDetailModal.jsx
 * Modale superposée à HomeScreen — confirmation de lecture d'un film.
 * Portage de PlayOptionsDialog de play_options_dialog.py.
 *
 * Différences avec la version Python :
 * - Modale React (pas QDialog) : fond semi-transparent superposé
 * - Option "Télécharger" absente (hors périmètre webOS)
 * - Focus trap : les touches ←/→ restent dans la modale
 * - BACK/Échap → ferme la modale et redonne le focus à la carte déclenchante
 */

import React, { useEffect, useRef, useCallback, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAppStore }    from '../../store/appStore.js';
import { usePlayerStore } from '../../store/playerStore.js';
import { createClientFromConfig } from '../../services/xtreamApi.js';
import { KEY, isBackKey } from '../../constants/keyCodes.js';
import { isFavorite, toggleFavorite } from '../../services/favoritesService.js';
import PosterImage from '../home/PosterImage.jsx';
import './MovieDetailModal.css';

export default function MovieDetailModal() {
  const navigate   = useNavigate();
  const { config, selectedMovie, closeMovieDetail } = useAppStore();
  const { playSingle } = usePlayerStore();

  const playBtnRef   = useRef(null);
  const favBtnRef    = useRef(null);
  const cancelBtnRef = useRef(null);
  const btnRefs      = [playBtnRef, favBtnRef, cancelBtnRef];

  const [isFav, setIsFav] = useState(false);
  useEffect(() => {
    if (selectedMovie) setIsFav(isFavorite(selectedMovie.stream_id, 'movie'));
  }, [selectedMovie]);

  const handleToggleFav = useCallback(() => {
    if (!selectedMovie) return;
    const added = toggleFavorite(selectedMovie, 'movie');
    setIsFav(added);
  }, [selectedMovie]);

  // ── Focus initial sur "Lire" à l'ouverture ──────────────────────────────
  useEffect(() => {
    if (selectedMovie) {
      const t = setTimeout(() => playBtnRef.current?.focus(), 80);
      return () => clearTimeout(t);
    }
  }, [selectedMovie]);

  // ── Touche BACK → ferme la modale ───────────────────────────────────────
  useEffect(() => {
    if (!selectedMovie) return;
    const handler = (e) => {
      if (isBackKey(e.keyCode)) {
        e.preventDefault();
        closeMovieDetail();
      }
    };
    document.addEventListener('keydown', handler);
    return () => document.removeEventListener('keydown', handler);
  }, [selectedMovie, closeMovieDetail]);

  // ── Navigation ←/→ dans la modale (focus trap entre 3 boutons) ──────────
  const handleKeyDown = useCallback(
    (e) => {
      const active = document.activeElement;
      const idx = btnRefs.findIndex((r) => r.current === active);
      if (e.keyCode === KEY.RIGHT) {
        e.preventDefault();
        const next = idx < btnRefs.length - 1 ? idx + 1 : 0;
        btnRefs[next].current?.focus();
      } else if (e.keyCode === KEY.LEFT) {
        e.preventDefault();
        const prev = idx > 0 ? idx - 1 : btnRefs.length - 1;
        btnRefs[prev].current?.focus();
      }
    },
    []
  );

  // ── Lancement de la lecture ──────────────────────────────────────────────
  const handlePlay = useCallback(() => {
    if (!selectedMovie) return;

    const client = createClientFromConfig(config);
    const streamId  = selectedMovie.stream_id;
    const ext       = selectedMovie.container_extension || 'mkv';
    const streamUrl = client.getStreamUrl(streamId, ext);

    playSingle(streamUrl, selectedMovie.name, 'movie', streamId);
    closeMovieDetail();
    navigate('/player');
  }, [selectedMovie, config, playSingle, closeMovieDetail, navigate]);

  // ── Rendu conditionnel ───────────────────────────────────────────────────
  if (!selectedMovie) return null;

  const { name, stream_icon, category_name, rating } = selectedMovie;

  const metaParts = [];
  if (category_name) metaParts.push(category_name);
  if (rating) {
    const r = parseFloat(rating);
    if (!isNaN(r)) metaParts.push(`⭐ ${r.toFixed(1)}`);
  }

  return (
    <>
      {/* Fond semi-transparent */}
      <div className="modal-overlay" onClick={closeMovieDetail} />

      {/* Panneau de la modale */}
      <div
        className="movie-modal modal-container"
        role="dialog"
        aria-modal="true"
        aria-label={`Lire ${name}`}
        onKeyDown={handleKeyDown}
      >
        {/* ── En-tête : poster + infos ── */}
        <div className="movie-modal__header">
          <PosterImage
            url={stream_icon}
            alt={name}
            type="movie"
            width={80}
            height={112}
          />
          <div className="movie-modal__info">
            <h2 className="movie-modal__title">{name}</h2>
            {metaParts.length > 0 && (
              <p className="movie-modal__meta">{metaParts.join('  ·  ')}</p>
            )}
          </div>
        </div>

        <p className="movie-modal__prompt">Que souhaitez-vous faire ?</p>

        {/* ── Boutons ── */}
        <div className="movie-modal__actions">
          <button
            ref={playBtnRef}
            className="movie-modal__btn movie-modal__btn--play action-button"
            tabIndex={0}
            onClick={handlePlay}
          >
            <span className="movie-modal__btn-icon">▶</span>
            <span className="movie-modal__btn-text">
              <span className="movie-modal__btn-label">Lire</span>
              <span className="movie-modal__btn-desc">Lecture immédiate plein écran</span>
            </span>
          </button>

          <button
            ref={favBtnRef}
            className={`movie-modal__btn movie-modal__btn--fav action-button ${isFav ? 'movie-modal__btn--fav-active' : ''}`}
            tabIndex={0}
            onClick={handleToggleFav}
          >
            <span className="movie-modal__btn-icon">{isFav ? '★' : '☆'}</span>
            <span className="movie-modal__btn-text">
              <span className="movie-modal__btn-label">{isFav ? 'Retirer des favoris' : 'Ajouter aux favoris'}</span>
            </span>
          </button>

          <button
            ref={cancelBtnRef}
            className="movie-modal__btn movie-modal__btn--cancel action-button"
            tabIndex={0}
            onClick={closeMovieDetail}
          >
            <span className="movie-modal__btn-icon">✕</span>
            <span className="movie-modal__btn-text">
              <span className="movie-modal__btn-label">Annuler</span>
            </span>
          </button>
        </div>
      </div>
    </>
  );
}
