/**
 * src/store/playerStore.js
 * Store Zustand — état du lecteur vidéo.
 *
 * Les paramètres de lecture sont transmis via ce store (pas via l'URL)
 * pour éviter d'exposer les credentials Xtream dans l'historique du navigateur.
 */

import { create } from 'zustand';

export const usePlayerStore = create((set) => ({
  // ── Lecture courante ────────────────────────────────────────────────────
  streamUrl: null,   // URL du flux à lire
  playKey: null,     // Timestamp unique — force le remontage du PlayerScreen
  title: '',         // Titre affiché dans le lecteur
  contentType: null, // 'movie' | 'episode'
  itemId: null,      // stream_id ou episode id (pour le suivi de visionnage)
  startTime: 0,      // Position de départ en secondes (reprise de lecture)

  // ── Mode playlist (séries — lecture automatique des épisodes) ───────────
  playlist: [],      // [{ url, title, episodeId }]
  playlistIndex: 0,

  // ── Actions ─────────────────────────────────────────────────────────────

  /** Lance la lecture d'un film ou d'un épisode unique. */
  playSingle: (streamUrl, title, contentType = 'movie', itemId = null, startTime = 0) =>
    set({
      streamUrl,
      title,
      contentType,
      itemId,
      startTime,
      playlist: [],
      playlistIndex: 0,
      playKey: Date.now(),
    }),

  /** Lance la lecture d'une playlist d'épisodes. */
  playPlaylist: (playlist, startIndex = 0, startTime = 0) =>
    set({
      streamUrl: playlist[startIndex]?.url ?? null,
      title: playlist[startIndex]?.title ?? '',
      contentType: 'episode',
      itemId: playlist[startIndex]?.episodeId ?? null,
      startTime,
      playlist,
      playlistIndex: startIndex,
      playKey: Date.now(),
    }),

  /** Passe à l'épisode suivant dans la playlist. */
  nextInPlaylist: () =>
    set((state) => {
      const next = state.playlistIndex + 1;
      if (next >= state.playlist.length) return state;
      return {
        playlistIndex: next,
        streamUrl: state.playlist[next].url,
        title: state.playlist[next].title,
        itemId: state.playlist[next].episodeId ?? null,
        startTime: 0,  // Nouvel épisode → toujours depuis le début
      };
    }),

  /** Réinitialise le store (appelé à la fermeture du lecteur). */
  clearPlayer: () =>
    set({
      streamUrl: null,
      title: '',
      contentType: null,
      itemId: null,
      startTime: 0,
      playlist: [],
      playlistIndex: 0,
      playKey: null,
    }),
}));
