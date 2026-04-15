/**
 * src/screens/PlayerScreen.jsx
 *
 * Navigation télécommande :
 *
 *  Mode LECTURE (défaut) :
 *    OK / Lecture-Pause → play/pause
 *    ←  / →            → −10 s / +10 s
 *    ⏪ / ⏩           → −5 min / +5 min
 *    ↓                 → descendre dans la barre de boutons
 *    ↑                 → volume +5
 *    🟢 Vert           → épisode suivant
 *    🟡 Jaune          → épisode précédent
 *    🔵 Bleu           → menu piste audio
 *    🔴 Rouge          → menu sous-titres
 *    BACK              → fermer le lecteur
 *
 *  Mode BOUTONS :
 *    ← / →             → naviguer entre les boutons
 *    OK                → activer le bouton sélectionné
 *    ↑ / BACK          → retour mode LECTURE
 *
 *  Menus audio / sous-titres :
 *    ↑ / ↓             → naviguer dans la liste
 *    OK                → sélectionner
 *    BACK / touche couleur → fermer
 */

import React, { useEffect, useRef, useCallback, useState, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import Hls from 'hls.js';
import { usePlayerStore } from '../store/playerStore.js';
import { KEY, isBackKey } from '../constants/keyCodes.js';
import { saveWatchPosition, clearWatchPosition } from '../services/watchPositionService.js';
import './PlayerScreen.css';

var CONTROLS_TIMEOUT = 3000;
var SEEK_SHORT_MS    = 10000;
var SEEK_LONG_MS     = 300000;

// ── Utilitaires temps ────────────────────────────────────────────────────────

function formatTime(seconds) {
  if (!seconds || isNaN(seconds) || seconds < 0) return '0:00';
  var h = Math.floor(seconds / 3600);
  var m = Math.floor((seconds % 3600) / 60);
  var s = Math.floor(seconds % 60);
  return h > 0
    ? h + ':' + String(m).padStart(2,'0') + ':' + String(s).padStart(2,'0')
    : m + ':' + String(s).padStart(2,'0');
}

// ── Piste audio ──────────────────────────────────────────────────────────────

function selectFrenchAudioTrack(video, hls) {
  if (hls && hls.audioTracks && hls.audioTracks.length > 1) {
    for (var i = 0; i < hls.audioTracks.length; i++) {
      var t = hls.audioTracks[i];
      var lang = (t.lang || '').toLowerCase();
      var name = (t.name || '').toLowerCase();
      if (lang === 'fr' || lang === 'fra' || lang === 'fre' ||
          lang.indexOf('french') !== -1 ||
          name.indexOf('franc') !== -1 || name.indexOf('french') !== -1) {
        hls.audioTrack = i; return;
      }
    }
  }
  if (video && video.audioTracks && video.audioTracks.length > 1) {
    for (var j = 0; j < video.audioTracks.length; j++) {
      var at    = video.audioTracks[j];
      var atLg  = (at.language || '').toLowerCase();
      var atLbl = (at.label   || '').toLowerCase();
      if (atLg === 'fr' || atLg === 'fra' || atLg === 'fre' ||
          atLbl.indexOf('franc') !== -1 || atLbl.indexOf('french') !== -1) {
        for (var k = 0; k < video.audioTracks.length; k++) video.audioTracks[k].enabled = false;
        at.enabled = true; return;
      }
    }
  }
}

function readAudioTracks(video, hls) {
  var tracks = [];
  if (hls && hls.audioTracks && hls.audioTracks.length > 0) {
    for (var i = 0; i < hls.audioTracks.length; i++) {
      var t = hls.audioTracks[i];
      var lang  = (t.lang || '').toLowerCase();
      var label = t.name || '';
      if (lang && label.toLowerCase().indexOf(lang) === -1)
        label = label ? label + ' (' + t.lang + ')' : t.lang;
      if (!label) label = 'Piste ' + (i + 1);
      tracks.push({ id: i, label: label, lang: lang });
    }
    return tracks;
  }
  if (video && video.audioTracks && video.audioTracks.length > 0) {
    for (var j = 0; j < video.audioTracks.length; j++) {
      var at = video.audioTracks[j];
      tracks.push({ id: j, label: at.label || at.language || ('Piste ' + (j + 1)), lang: (at.language || '').toLowerCase() });
    }
  }
  return tracks;
}

function applyAudioTrack(video, hls, trackId) {
  if (hls && hls.audioTracks && hls.audioTracks.length > trackId) { hls.audioTrack = trackId; return; }
  if (video && video.audioTracks) {
    for (var k = 0; k < video.audioTracks.length; k++) video.audioTracks[k].enabled = (k === trackId);
  }
}

function getActiveAudioId(video, hls) {
  if (hls && hls.audioTracks && hls.audioTracks.length > 0) return typeof hls.audioTrack === 'number' ? hls.audioTrack : 0;
  if (video && video.audioTracks) for (var i = 0; i < video.audioTracks.length; i++) if (video.audioTracks[i].enabled) return i;
  return 0;
}

// ── Sous-titres ──────────────────────────────────────────────────────────────

/**
 * Lit les pistes de sous-titres depuis HLS.js ou HTML5 TextTracks.
 * Chaque entrée : { id, label, lang, forced }
 *   forced = true  → piste partielle (passages étrangers seulement)
 *   forced = false → piste complète (transcription/traduction intégrale)
 */
function readSubtitleTracks(video, hls) {
  var tracks = [];

  // HLS.js : hls.subtitleTracks[i].forced est un booléen standard
  if (hls && hls.subtitleTracks && hls.subtitleTracks.length > 0) {
    for (var i = 0; i < hls.subtitleTracks.length; i++) {
      var t      = hls.subtitleTracks[i];
      var lang   = (t.lang || '').toLowerCase();
      var label  = t.name || '';
      var forced = t.forced === true;
      // Ajouter la langue si absente du nom
      if (lang && label.toLowerCase().indexOf(lang) === -1)
        label = label ? label + ' (' + t.lang + ')' : t.lang;
      if (!label) label = 'Sous-titres ' + (i + 1);
      tracks.push({ id: i, label: label, lang: lang, forced: forced });
    }
    return tracks;
  }

  // HTML5 TextTrackList
  if (video && video.textTracks && video.textTracks.length > 0) {
    for (var j = 0; j < video.textTracks.length; j++) {
      var tt     = video.textTracks[j];
      if (tt.kind !== 'subtitles' && tt.kind !== 'captions') continue;
      var lbl    = tt.label || tt.language || ('Sous-titres ' + (j + 1));
      var lang2  = (tt.language || '').toLowerCase();
      // Heuristique forced : certains encodeurs mettent "forced" dans le label
      var forced2 = tt.kind === 'forced' ||
                    lbl.toLowerCase().indexOf('forced') !== -1 ||
                    lbl.toLowerCase().indexOf('forcé')  !== -1;
      tracks.push({ id: j, label: lbl, lang: lang2, forced: forced2 });
    }
  }
  return tracks;
}

/**
 * Active une piste de sous-titres par son id, ou désactive tout (trackId = -1).
 */
function applySubtitleTrack(video, hls, trackId) {
  if (hls && hls.subtitleTracks && hls.subtitleTracks.length > 0) {
    hls.subtitleTrack = trackId; // -1 = off dans HLS.js
    return;
  }
  if (video && video.textTracks) {
    for (var k = 0; k < video.textTracks.length; k++) {
      var tt = video.textTracks[k];
      if (tt.kind !== 'subtitles' && tt.kind !== 'captions') continue;
      tt.mode = (k === trackId) ? 'showing' : 'hidden';
    }
  }
}

/**
 * Désactive tous les sous-titres (état initial).
 * Retourne l'id de la piste forcée FR si elle existe, -1 sinon.
 * Permet au code appelant de l'activer automatiquement.
 */
function disableAllSubtitles(video, hls) {
  if (hls && hls.subtitleTracks) { hls.subtitleTrack = -1; }
  if (video && video.textTracks) {
    for (var i = 0; i < video.textTracks.length; i++) {
      if (video.textTracks[i].kind === 'subtitles' || video.textTracks[i].kind === 'captions') {
        video.textTracks[i].mode = 'hidden';
      }
    }
  }
}

/**
 * Cherche et active automatiquement la piste de sous-titres forcée
 * correspondant à la langue audio active.
 * Logique : sous-titres forcés FR si l'audio est en français,
 *           ou sous-titres forcés de n'importe quelle langue si une seule piste forcée.
 * Retourne l'id activé, ou -1 si rien d'activé.
 */
function autoSelectForcedSubtitle(video, hls, tracks) {
  if (!tracks || tracks.length === 0) return -1;

  // Identifier la langue de la piste audio active
  var audioLang = '';
  if (hls && hls.audioTracks && hls.audioTracks.length > 0) {
    var aIdx = typeof hls.audioTrack === 'number' ? hls.audioTrack : 0;
    audioLang = ((hls.audioTracks[aIdx] && hls.audioTracks[aIdx].lang) || '').toLowerCase();
  } else if (video && video.audioTracks) {
    for (var i = 0; i < video.audioTracks.length; i++) {
      if (video.audioTracks[i].enabled) { audioLang = (video.audioTracks[i].language || '').toLowerCase(); break; }
    }
  }

  // Chercher une piste forcée dont la langue correspond à l'audio
  var matchedForced = -1;
  var anyForced     = -1;
  for (var j = 0; j < tracks.length; j++) {
    if (!tracks[j].forced) continue;
    if (anyForced === -1) anyForced = tracks[j].id;
    var tLang = tracks[j].lang;
    if (audioLang && (tLang === audioLang || audioLang.indexOf(tLang) === 0 || tLang.indexOf(audioLang) === 0)) {
      matchedForced = tracks[j].id;
      break;
    }
  }

  var chosen = matchedForced >= 0 ? matchedForced : anyForced;
  if (chosen >= 0) {
    applySubtitleTrack(video, hls, chosen);
    console.log('[Player] Sous-titres forcés activés automatiquement, id=' + chosen);
  }
  return chosen;
}

function shortLabel(track) {
  if (!track) return '---';
  if (track.lang) return track.lang.toUpperCase().slice(0, 3);
  return track.label.toUpperCase().slice(0, 3);
}

// ─────────────────────────────────────────────────────────────────────────────

export default function PlayerScreen() {
  var navigate = useNavigate();

  useEffect(function() {
    if (document.documentElement.requestFullscreen) document.documentElement.requestFullscreen().catch(function(){});
    return function() { if (document.exitFullscreen && document.fullscreenElement) document.exitFullscreen().catch(function(){}); };
  }, []);

  var store          = usePlayerStore();
  var streamUrl      = store.streamUrl;
  var title          = store.title;
  var playlist       = store.playlist;
  var playlistIndex  = store.playlistIndex;
  var nextInPlaylist = store.nextInPlaylist;
  var clearPlayer    = store.clearPlayer;
  var itemId         = store.itemId;
  var startTime      = store.startTime || 0;

  var videoRef     = useRef(null);
  var hlsRef       = useRef(null);
  var hideTimerRef = useRef(null);

  // Refs boutons barre
  var btnPrevRef  = useRef(null);
  var btnPlayRef  = useRef(null);
  var btnNextRef  = useRef(null);
  var btnAudioRef = useRef(null);
  var btnSubRef   = useRef(null);
  var btnMuteRef  = useRef(null);
  var btnCloseRef = useRef(null);

  var _sc  = useState(true),   showControls  = _sc[0],  setShowControls  = _sc[1];
  var _pl  = useState(false),  isPlaying     = _pl[0],  setIsPlaying     = _pl[1];
  var _mu  = useState(false),  isMuted       = _mu[0],  setIsMuted       = _mu[1];
  var _vo  = useState(100),    volume        = _vo[0],  setVolume        = _vo[1];
  var _ct  = useState(0),      currentTime   = _ct[0],  setCurrentTime   = _ct[1];
  var _du  = useState(0),      duration      = _du[0],  setDuration      = _du[1];
  var _pr  = useState(0),      progress      = _pr[0],  setProgress      = _pr[1];

  // Audio
  var _at  = useState([]),    audioTracks   = _at[0],  setAudioTracks   = _at[1];
  var _aid = useState(0),     activeAudioId = _aid[0], setActiveAudioId = _aid[1];
  var _sam = useState(false), showAudioMenu = _sam[0], setShowAudioMenu = _sam[1];
  var _ami = useState(0),     audioMenuIdx  = _ami[0], setAudioMenuIdx  = _ami[1];

  // Sous-titres
  var _st  = useState([]),    subTracks     = _st[0],  setSubTracks     = _st[1];
  var _sid = useState(-1),    activeSubId   = _sid[0], setActiveSubId   = _sid[1];  // -1 = off
  var _ssm = useState(false), showSubMenu   = _ssm[0], setShowSubMenu   = _ssm[1];
  var _smi = useState(-1),    subMenuIdx    = _smi[0], setSubMenuIdx    = _smi[1];

  // Mode boutons
  var _bm  = useState(false), btnMode       = _bm[0],  setBtnMode       = _bm[1];
  var _bfi = useState(0),     btnFocusIdx   = _bfi[0], setBtnFocusIdx   = _bfi[1];

  var hasPlaylist = playlist.length > 1;
  var hasPrev     = hasPlaylist && playlistIndex > 0;
  var hasNext     = hasPlaylist && playlistIndex < playlist.length - 1;
  var hasAudio    = audioTracks.length > 0;    // au moins une piste détectée
  var hasSubs     = subTracks.length > 0;
  var subsOn      = activeSubId >= 0;

  // Liste ordonnée des boutons visibles
  var availableBtns = useMemo(function() {
    var btns = [];
    if (hasPlaylist) btns.push({ id: 'prev',  ref: btnPrevRef  });
    btns.push(       { id: 'play',  ref: btnPlayRef  });
    if (hasPlaylist) btns.push({ id: 'next',  ref: btnNextRef  });
    if (hasAudio)    btns.push({ id: 'audio', ref: btnAudioRef });
    if (hasSubs)     btns.push({ id: 'sub',   ref: btnSubRef   });
    btns.push(         { id: 'mute',  ref: btnMuteRef  });
    btns.push(         { id: 'close', ref: btnCloseRef });
    return btns;
  }, [hasPlaylist, hasAudio, hasSubs]);

  // ── Timer contrôles ──────────────────────────────────────────────────────
  var showControlsTemporarily = useCallback(function(timeout) {
    setShowControls(true);
    clearTimeout(hideTimerRef.current);
    hideTimerRef.current = setTimeout(function() {
      setBtnMode(function(bm) { if (!bm) setShowControls(false); return bm; });
    }, timeout !== undefined ? timeout : CONTROLS_TIMEOUT);
  }, []);

  // ── Mode BOUTONS ─────────────────────────────────────────────────────────
  var enterBtnMode = useCallback(function() {
    setBtnMode(true);
    setShowControls(true);
    clearTimeout(hideTimerRef.current);
    var playIdx = 0;
    for (var i = 0; i < availableBtns.length; i++) { if (availableBtns[i].id === 'play') { playIdx = i; break; } }
    setBtnFocusIdx(playIdx);
  }, [availableBtns]);

  var exitBtnMode = useCallback(function() {
    setBtnMode(false);
    clearTimeout(hideTimerRef.current);
    setShowControls(false);
  }, []);

  useEffect(function() {
    if (!btnMode) return;
    var btn = availableBtns[btnFocusIdx];
    if (btn && btn.ref.current) btn.ref.current.focus();
  }, [btnMode, btnFocusIdx, availableBtns]);

  // Recalibrer l'index quand availableBtns change (ex. pistes audio/sous-titres
  // détectées 300 ms après le chargement du flux) pour éviter un index hors bornes.
  useEffect(function() {
    if (btnMode) {
      setBtnFocusIdx(function(i) { return Math.min(i, availableBtns.length - 1); });
    }
  }, [availableBtns, btnMode]);

  // ── Chargement flux ──────────────────────────────────────────────────────
  var loadStream = useCallback(function(url, seekTo) {
    var video = videoRef.current;
    if (!video || !url) return;
    if (hlsRef.current) { hlsRef.current.destroy(); hlsRef.current = null; }

    setCurrentTime(0); setDuration(0); setProgress(0); setIsPlaying(false);
    setAudioTracks([]); setActiveAudioId(0);
    setSubTracks([]); setActiveSubId(-1);
    setShowAudioMenu(false); setShowSubMenu(false); setBtnMode(false);

    var isHls = url.indexOf('.m3u8') !== -1;
    if (isHls && Hls.isSupported()) {
      var hls = new Hls({
        enableWorker: false,

        // ── Reprise au bon point ──────────────────────────────────────────
        startPosition: (seekTo && seekTo > 0) ? seekTo : -1,

        // ── Buffer : plus de marge pour absorber les pics de latence ─────
        maxBufferLength:    60,    // secondes de buffer cible (défaut : 30)
        maxMaxBufferLength: 120,   // plafond absolu (défaut : 600)
        maxBufferSize:      80 * 1024 * 1024, // 80 MB (défaut : 60 MB)
        maxBufferHole:      0.3,   // trou max toléré avant seek (défaut : 0.5)
        startFragPrefetch:  true,  // précharger le fragment suivant dès maintenant
        lowLatencyMode:     false, // IPTV ≠ live ultra-faible latence

        // ── Timeouts : réagir vite aux serveurs lents ────────────────────
        fragLoadingTimeOut:      8000,  // ms par fragment (défaut : 20 000)
        fragLoadingMaxRetry:     8,     // tentatives avant abandon (défaut : 6)
        fragLoadingRetryDelay:   500,   // délai entre retries (défaut : 1 000)
        manifestLoadingTimeOut:  8000,
        manifestLoadingMaxRetry: 3,
        levelLoadingTimeOut:     8000,
        levelLoadingMaxRetry:    3,

        // ── ABR : estimation bande passante adaptée IPTV ─────────────────
        testBandwidth: true,
      });

      hls.loadSource(url);
      hls.attachMedia(video);

      // ── Récupération automatique des erreurs ──────────────────────────
      hls.on(Hls.Events.ERROR, function(event, data) {
        if (!data.fatal) return;
        if (data.type === Hls.ErrorTypes.NETWORK_ERROR) {
          // Erreur réseau : relancer le chargement
          hls.startLoad();
        } else if (data.type === Hls.ErrorTypes.MEDIA_ERROR) {
          // Erreur média (MSE corrompu) : tenter une réparation
          hls.recoverMediaError();
        } else {
          // Erreur irrécupérable : détruire et recréer
          hls.destroy();
          hlsRef.current = null;
        }
      });

      // Fonction utilitaire : lit et applique les pistes après chargement
      function applyTracks() {
        selectFrenchAudioTrack(video, hls);
        var aTracks = readAudioTracks(video, hls);
        setAudioTracks(aTracks);
        setActiveAudioId(getActiveAudioId(video, hls));
        var sTracks = readSubtitleTracks(video, hls);
        setSubTracks(sTracks);
        var autoSub = autoSelectForcedSubtitle(video, hls, sTracks);
        setActiveSubId(autoSub);
      }

      hls.on(Hls.Events.MANIFEST_PARSED, function() {
        selectFrenchAudioTrack(video, hls);
        disableAllSubtitles(video, hls);
        video.play().catch(function(){});
        // Lecture initiale des pistes (peut être vide si flux HLS multi-pistes tardif)
        setTimeout(applyTracks, 400);
      });

      // AUDIO_TRACKS_UPDATED : certains serveurs IPTV n'exposent les pistes
      // audio qu'après cet événement (300-800 ms après MANIFEST_PARSED)
      hls.on(Hls.Events.AUDIO_TRACKS_UPDATED, function() {
        applyTracks();
      });

      // SUBTITLE_TRACKS_UPDATED : même logique pour les sous-titres
      hls.on(Hls.Events.SUBTITLE_TRACKS_UPDATED, function() {
        var sTracks = readSubtitleTracks(video, hls);
        setSubTracks(sTracks);
      });

      hlsRef.current = hls;
    } else {
      video.src = url;
      video.load();
      video.onloadedmetadata = function() {
        selectFrenchAudioTrack(video, null);
        disableAllSubtitles(video, null);
        if (seekTo && seekTo > 0) {
          video.currentTime = seekTo;
        }
        var aTracks = readAudioTracks(video, null);
        setAudioTracks(aTracks);
        setActiveAudioId(getActiveAudioId(video, null));
        var sTracks = readSubtitleTracks(video, null);
        setSubTracks(sTracks);
        var autoSub = autoSelectForcedSubtitle(video, null, sTracks);
        setActiveSubId(autoSub);
        // Lancer la lecture après le seek pour partir du bon point
        video.play().catch(function(){});
        // Écouter les changements de pistes audio sur les flux natifs
        // (utilise addEventListener + try/catch pour compatibilité webOS)
        if (video.audioTracks) {
          try {
            video.audioTracks.addEventListener('change', function() {
              setAudioTracks(readAudioTracks(video, null));
              setActiveAudioId(getActiveAudioId(video, null));
            });
            video.audioTracks.addEventListener('addtrack', function() {
              selectFrenchAudioTrack(video, null);
              setAudioTracks(readAudioTracks(video, null));
              setActiveAudioId(getActiveAudioId(video, null));
            });
          } catch (_) { /* non supporté sur ce navigateur */ }
        }
      };
    }
  }, []);

  useEffect(function() {
    if (!streamUrl) { navigate(-1); return; }
    loadStream(streamUrl, startTime);
    setShowControls(true); // affiche les contrôles sans démarrer le timer — le timer part sur onPlaying
    return function() { clearTimeout(hideTimerRef.current); if (hlsRef.current) hlsRef.current.destroy(); };
  }, [streamUrl]);

  useEffect(function() {
    var state = usePlayerStore.getState();
    if (state.streamUrl) loadStream(state.streamUrl, state.startTime || 0);
  }, [playlistIndex]);

  // ── Actions lecture ──────────────────────────────────────────────────────
  var togglePlay = useCallback(function() {
    var v = videoRef.current;
    if (!v) return;
    v.paused ? v.play().catch(function(){}) : v.pause();
    showControlsTemporarily();
  }, [showControlsTemporarily]);

  var toggleMute = useCallback(function() {
    var v = videoRef.current;
    if (!v) return;
    v.muted = !v.muted;
    setIsMuted(v.muted);
    showControlsTemporarily();
  }, [showControlsTemporarily]);

  var handleVolumeChange = useCallback(function(newVol) {
    var v = videoRef.current;
    if (!v) return;
    var vol = Math.max(0, Math.min(100, newVol));
    v.volume = vol / 100; setVolume(vol); setIsMuted(vol === 0);
    showControlsTemporarily();
  }, [showControlsTemporarily]);

  var seek = useCallback(function(deltaMs) {
    var v = videoRef.current;
    if (!v || !v.duration) return;
    v.currentTime = Math.max(0, Math.min(v.duration, v.currentTime + deltaMs / 1000));
    showControlsTemporarily();
  }, [showControlsTemporarily]);

  // ── Sélection piste audio ────────────────────────────────────────────────
  var selectAudioTrack = useCallback(function(trackId) {
    applyAudioTrack(videoRef.current, hlsRef.current, trackId);
    setActiveAudioId(trackId);
    setShowAudioMenu(false);
    showControlsTemporarily();
  }, [showControlsTemporarily]);

  var openAudioMenu = useCallback(function() {
    if (!hasAudio) return;
    setAudioMenuIdx(activeAudioId);
    setShowSubMenu(false);
    setShowAudioMenu(function(v) { return !v; });
  }, [hasAudio, activeAudioId]);

  // ── Sélection sous-titres ────────────────────────────────────────────────
  var selectSubtitle = useCallback(function(trackId) {
    // trackId = -1 → désactiver, ≥0 → activer cette piste
    applySubtitleTrack(videoRef.current, hlsRef.current, trackId);
    setActiveSubId(trackId);
    setShowSubMenu(false);
    showControlsTemporarily();
  }, [showControlsTemporarily]);

  var openSubMenu = useCallback(function() {
    if (!hasSubs) return;
    setSubMenuIdx(activeSubId);
    setShowAudioMenu(false);
    setShowSubMenu(function(v) { return !v; });
  }, [hasSubs, activeSubId]);

  // ── Navigation playlist ──────────────────────────────────────────────────
  var prevInPlaylist = useCallback(function() {
    if (!hasPrev) return;
    var prev = playlistIndex - 1;
    usePlayerStore.setState({ playlistIndex: prev, streamUrl: playlist[prev].url, title: playlist[prev].title, itemId: playlist[prev].episodeId || null });
    showControlsTemporarily();
  }, [hasPrev, playlistIndex, playlist, showControlsTemporarily]);

  var goNext = useCallback(function() {
    if (!hasNext) return;
    nextInPlaylist();
    showControlsTemporarily();
  }, [hasNext, nextInPlaylist, showControlsTemporarily]);

  var closePlayer = useCallback(function() {
    var v = videoRef.current;
    if (v) { saveWatchPosition(itemId, v.currentTime, v.duration); v.pause(); }
    clearPlayer();
    navigate(-1);
  }, [clearPlayer, navigate, itemId]);

  // ── Clavier ──────────────────────────────────────────────────────────────
  useEffect(function() {
    var handler = function(e) {

      // ── Menu audio ouvert ──
      if (showAudioMenu) {
        if (e.keyCode === KEY.DOWN) { e.preventDefault(); e.stopPropagation(); setAudioMenuIdx(function(i) { return Math.min(i + 1, audioTracks.length - 1); }); }
        else if (e.keyCode === KEY.UP)   { e.preventDefault(); e.stopPropagation(); setAudioMenuIdx(function(i) { return Math.max(i - 1, 0); }); }
        else if (e.keyCode === KEY.OK)   { e.preventDefault(); e.stopPropagation(); selectAudioTrack(audioMenuIdx); }
        else if (isBackKey(e.keyCode) || e.keyCode === KEY.BLUE) { e.preventDefault(); e.stopPropagation(); setShowAudioMenu(false); }
        return;
      }

      // ── Menu sous-titres ouvert ──
      if (showSubMenu) {
        // Liste : -1 (Désactivés) + indices 0..subTracks.length-1
        var subListLen = subTracks.length + 1; // +1 pour "Désactivés"
        if (e.keyCode === KEY.DOWN) { e.preventDefault(); e.stopPropagation(); setSubMenuIdx(function(i) { return Math.min(i + 1, subListLen - 2); }); }
        else if (e.keyCode === KEY.UP)   { e.preventDefault(); e.stopPropagation(); setSubMenuIdx(function(i) { return Math.max(i - 1, -1); }); }
        else if (e.keyCode === KEY.OK)   { e.preventDefault(); e.stopPropagation(); selectSubtitle(subMenuIdx); }
        else if (isBackKey(e.keyCode) || e.keyCode === KEY.RED) { e.preventDefault(); e.stopPropagation(); setShowSubMenu(false); }
        return;
      }

      // ── Mode BOUTONS ──
      if (btnMode) {
        if (e.keyCode === KEY.RIGHT) { e.preventDefault(); setBtnFocusIdx(function(i) { return Math.min(i + 1, availableBtns.length - 1); }); }
        else if (e.keyCode === KEY.LEFT) { e.preventDefault(); setBtnFocusIdx(function(i) { return Math.max(i - 1, 0); }); }
        else if (e.keyCode === KEY.OK) { e.preventDefault(); var btn = availableBtns[btnFocusIdx]; if (btn && btn.ref.current) btn.ref.current.click(); }
        else if (e.keyCode === KEY.UP || isBackKey(e.keyCode)) { e.preventDefault(); exitBtnMode(); }
        return;
      }

      // ── Mode LECTURE ──
      showControlsTemporarily();
      switch (e.keyCode) {
        case KEY.OK:
        case KEY.PLAY_PAUSE: e.preventDefault(); togglePlay(); break;
        case KEY.PLAY:   e.preventDefault(); videoRef.current && videoRef.current.play().catch(function(){}); break;
        case KEY.PAUSE:  e.preventDefault(); videoRef.current && videoRef.current.pause(); break;
        case KEY.RIGHT:  e.preventDefault(); seek(SEEK_SHORT_MS);  break;
        case KEY.LEFT:   e.preventDefault(); seek(-SEEK_SHORT_MS); break;
        case KEY.FF:     e.preventDefault(); seek(SEEK_LONG_MS);   break;
        case KEY.REW:    e.preventDefault(); seek(-SEEK_LONG_MS);  break;
        case KEY.DOWN:   e.preventDefault(); enterBtnMode();       break;
        case KEY.UP:     e.preventDefault(); handleVolumeChange(volume + 5); break;
        case KEY.GREEN:  e.preventDefault(); goNext();             break;
        case KEY.YELLOW: e.preventDefault(); prevInPlaylist();     break;
        case KEY.BLUE:   e.preventDefault(); openAudioMenu();      break;
        case KEY.RED:    e.preventDefault(); openSubMenu();        break;
        default: if (isBackKey(e.keyCode)) { e.preventDefault(); closePlayer(); }
      }
    };
    document.addEventListener('keydown', handler);
    return function() { document.removeEventListener('keydown', handler); };
  }, [
    showAudioMenu, audioTracks, audioMenuIdx, selectAudioTrack,
    showSubMenu,   subTracks,   subMenuIdx,   selectSubtitle,
    btnMode, availableBtns, btnFocusIdx, exitBtnMode, enterBtnMode,
    togglePlay, seek, handleVolumeChange, volume,
    goNext, prevInPlaylist, openAudioMenu, openSubMenu, closePlayer, showControlsTemporarily,
  ]);

  function isFocusedBtn(id) {
    return btnMode && btnFocusIdx === availableBtns.findIndex(function(b) { return b.id === id; });
  }

  var playlistLabel = hasPlaylist ? (playlistIndex + 1) + ' / ' + playlist.length : null;
  var activeAudioTrack = audioTracks[activeAudioId] || null;
  var activeSubTrack   = activeSubId >= 0 ? subTracks[activeSubId] : null;

  return (
    <div className="player-screen" onMouseMove={showControlsTemporarily}>
      <video
        ref={videoRef}
        className="player-video"
        onPlay={function()    { setIsPlaying(true);  }}
        onPlaying={function() { setIsPlaying(true); showControlsTemporarily(2000); }}
        onPause={function()   { setIsPlaying(false); }}
        onTimeUpdate={function() {
          var v = videoRef.current;
          if (!v) return;
          setCurrentTime(v.currentTime);
          setDuration(v.duration || 0);
          if (v.duration > 0) setProgress(Math.round((v.currentTime / v.duration) * 1000));
        }}
        onEnded={function() { clearWatchPosition(itemId); if (hasNext) goNext(); }}
        playsInline autoPlay
      />

      {/* ── Menu piste audio ── */}
      {showAudioMenu && hasAudio && (
        <div className="player-track-menu player-track-menu--left">
          <div className="player-track-menu__title">🎵 Piste audio</div>
          {audioTracks.map(function(track) {
            var isActive  = track.id === activeAudioId;
            var isCurrent = track.id === audioMenuIdx;
            return (
              <div key={track.id}
                className={'player-track-menu__item' + (isActive ? ' player-track-menu__item--active' : '') + (isCurrent ? ' player-track-menu__item--focused' : '')}
                onClick={function() { selectAudioTrack(track.id); }}
              >
                <span className="player-track-menu__check">{isActive ? '▶' : '\u00A0\u00A0'}</span>
                {track.label}
              </div>
            );
          })}
          <div className="player-track-menu__hint">↑↓ · OK · 🔵 Fermer</div>
        </div>
      )}

      {/* ── Menu sous-titres ── */}
      {showSubMenu && hasSubs && (
        <div className="player-track-menu player-track-menu--right">
          <div className="player-track-menu__title">🔤 Sous-titres</div>

          {/* Option : Désactivés */}
          <div
            className={'player-track-menu__item' + (activeSubId === -1 ? ' player-track-menu__item--active' : '') + (subMenuIdx === -1 ? ' player-track-menu__item--focused' : '')}
            onClick={function() { selectSubtitle(-1); }}
          >
            <span className="player-track-menu__check">{activeSubId === -1 ? '▶' : '\u00A0\u00A0'}</span>
            <span>Désactivés</span>
          </div>

          {subTracks.map(function(track) {
            var isActive  = track.id === activeSubId;
            var isCurrent = track.id === subMenuIdx;
            return (
              <div key={track.id}
                className={'player-track-menu__item' + (isActive ? ' player-track-menu__item--active' : '') + (isCurrent ? ' player-track-menu__item--focused' : '')}
                onClick={function() { selectSubtitle(track.id); }}
              >
                <span className="player-track-menu__check">{isActive ? '▶' : '\u00A0\u00A0'}</span>
                <span className="player-track-menu__item-label">
                  {track.label}
                  {track.forced
                    ? <span className="player-track-badge player-track-badge--forced" title="Passages en langue étrangère seulement">Forcés</span>
                    : <span className="player-track-badge player-track-badge--full"   title="Transcription/traduction intégrale">Complets</span>
                  }
                </span>
              </div>
            );
          })}
          <div className="player-track-menu__hint">↑↓ · OK · 🔴 Fermer</div>
        </div>
      )}

      {/* ── Barre de contrôles ── */}
      <div className={'player-controls ' + (showControls ? 'player-controls--visible' : '')}>

        {/* ── Ligne info : titre · temps · raccourcis ── */}
        <div className="player-info-row">
          <div className="player-info-row__left">
            <span className="player-title">
              {title}
              {playlistLabel && <span className="player-playlist-indicator"> — {playlistLabel}</span>}
            </span>
          </div>
          <div className="player-info-row__right">
            <span className="player-time">{formatTime(currentTime)} / {formatTime(duration)}</span>
            {(hasPrev || hasNext || hasAudio || hasSubs) && (
              <span className="player-color-hints">
                {hasPlaylist && hasPrev && <span className="player-color-hint">🟡 Préc.</span>}
                {hasPlaylist && hasNext && <span className="player-color-hint">🟢 Suiv.</span>}
                {hasAudio               && <span className="player-color-hint">🔵 Audio</span>}
                {hasSubs                && <span className="player-color-hint">🔴 Sous-titres</span>}
              </span>
            )}
          </div>
        </div>

        {/* ── Barre de progression ── */}
        <div className="player-progress" onClick={function(e) {
          var v = videoRef.current;
          if (!v || !v.duration) return;
          var rect = e.currentTarget.getBoundingClientRect();
          v.currentTime = ((e.clientX - rect.left) / rect.width) * v.duration;
        }}>
          <div className="player-progress__fill" style={{ width: (progress / 1000) * 100 + '%' }} />
          <div className="player-progress__thumb" style={{ left: (progress / 1000) * 100 + '%' }} />
        </div>

        {/* ── Ligne de boutons ── */}
        <div className={'player-btn-row' + (btnMode ? ' player-btn-row--active' : '')}>

          {/* Groupe gauche : navigation playlist + lecture */}
          <div className="player-btn-row__left">
            {hasPlaylist && (
              <button ref={btnPrevRef}
                className={'player-btn' + (!hasPrev ? ' player-btn--disabled' : '') + (isFocusedBtn('prev') ? ' player-btn--focused' : '')}
                tabIndex={0} onClick={prevInPlaylist} disabled={!hasPrev}>⏮</button>
            )}
            <button ref={btnPlayRef}
              className={'player-btn player-btn--play' + (isFocusedBtn('play') ? ' player-btn--focused' : '')}
              tabIndex={0} onClick={togglePlay}>
              {isPlaying ? '⏸' : '▶'}
            </button>
            {hasPlaylist && (
              <button ref={btnNextRef}
                className={'player-btn' + (!hasNext ? ' player-btn--disabled' : '') + (isFocusedBtn('next') ? ' player-btn--focused' : '')}
                tabIndex={0} onClick={goNext} disabled={!hasNext}>⏭</button>
            )}
          </div>

          {/* Groupe droit : pistes + son + fermer */}
          <div className="player-btn-row__right">
            {hasAudio && (
              <button ref={btnAudioRef}
                className={'player-btn player-btn--track' + (showAudioMenu ? ' player-btn--active' : '') + (isFocusedBtn('audio') ? ' player-btn--focused' : '')}
                tabIndex={0} onClick={openAudioMenu}>
                🎵 {shortLabel(activeAudioTrack)}
              </button>
            )}
            {hasSubs && (
              <button ref={btnSubRef}
                className={'player-btn player-btn--track' + (subsOn ? ' player-btn--track-on' : '') + (showSubMenu ? ' player-btn--active' : '') + (isFocusedBtn('sub') ? ' player-btn--focused' : '')}
                tabIndex={0} onClick={openSubMenu}>
                {subsOn ? ('🔤 ' + shortLabel(activeSubTrack)) : '🔤 OFF'}
              </button>
            )}
            <button ref={btnMuteRef}
              className={'player-btn' + (isMuted ? ' player-btn--muted' : '') + (isFocusedBtn('mute') ? ' player-btn--focused' : '')}
              tabIndex={0} onClick={toggleMute}>
              {isMuted ? '🔇' : '🔊'}
            </button>
            <button ref={btnCloseRef}
              className={'player-btn player-btn--close' + (isFocusedBtn('close') ? ' player-btn--focused' : '')}
              tabIndex={0} onClick={closePlayer}>✕</button>
          </div>
        </div>

        {/* Hint mode boutons */}
        {btnMode && (
          <div className="player-btn-mode-hint">
            ← → naviguer &nbsp;·&nbsp; OK activer &nbsp;·&nbsp; ↑ ou BACK reprendre la lecture
          </div>
        )}
      </div>
    </div>
  );
}
