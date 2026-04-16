/**
 * src/services/webosMedia.js
 *
 * Pipeline média natif webOS via PalmServiceBridge → luna://com.webos.media
 * + webosgavplugin pour le rendu vidéo hardware.
 *
 * Formats ciblés : AVI (DivX/Xvid), WMV, FLV, MKV avec codec ancien, etc.
 *
 * Architecture :
 *   1. luna://com.webos.media/load  → obtient un mediaId
 *   2. webosgavplugin.requestMediaLayer(mediaId, 0)
 *        → déclenche onCreatedMediaLayer(mediaId, windowId)
 *   3. webosgavplugin.updateMediaLayerBounds(mediaId, 0,0,1920,1080, 0,0,1920,1080)
 *   4. webosgavplugin.setMediaLayerZOrder(mediaId, 999)   ← force au-dessus du DOM
 *   5. luna://com.webos.media/play  (appelé DANS le callback, après les bounds)
 *
 * Débogage : tous les événements critiques sont loggés via console.warn
 * avec le préfixe [GAV] ou [LUNA] pour filtrage facile dans CDP.
 */

var MEDIA_SVC = 'luna://com.webos.media';

// ── Détection format ─────────────────────────────────────────────────────────

var MIME_MAP = {
  mp4:  'video/mp4',
  m4v:  'video/mp4',
  ts:   'video/mp2t',
  mkv:  'video/x-matroska',
  webm: 'video/webm',
  avi:  'video/x-msvideo',
  wmv:  'video/x-ms-wmv',
  flv:  'video/x-flv',
  mpg:  'video/mpeg',
  mpeg: 'video/mpeg',
  mov:  'video/quicktime',
};

export function canPlayNatively(url) {
  var ext = (url.split('?')[0].split('.').pop() || '').toLowerCase();
  var mime = MIME_MAP[ext];
  if (!mime) return true;
  var r = document.createElement('video').canPlayType(mime);
  console.warn('[GAV] canPlayType(' + mime + ') =', JSON.stringify(r));
  return r !== '';
}

// ── Introspection webosgavplugin ─────────────────────────────────────────────

function logGavMethods() {
  if (typeof webosgavplugin === 'undefined') {
    console.warn('[GAV] webosgavplugin NON DISPONIBLE');
    return;
  }
  try {
    var methods = [];
    var obj = webosgavplugin;
    do {
      Object.getOwnPropertyNames(obj).forEach(function(n) {
        if (methods.indexOf(n) === -1) methods.push(n);
      });
    } while ((obj = Object.getPrototypeOf(obj)) && obj !== Object.prototype);
    console.warn('[GAV] méthodes disponibles:', methods.join(', '));
  } catch (e) {
    console.warn('[GAV] introspection échouée:', e.message);
  }
}

// Appel unique au chargement du module
if (typeof webosgavplugin !== 'undefined') logGavMethods();

// ── Pipeline natif ───────────────────────────────────────────────────────────

class WebOSMediaPipeline {

  static isAvailable() {
    return typeof PalmServiceBridge !== 'undefined';
  }

  constructor() {
    this._mediaId    = null;
    this._seekTo     = 0;
    this._subBridge  = null;
    this._pollTimer  = null;
    this._destroyed  = false;
    this._layerReady = false;
    this._cbs        = {};
  }

  /**
   * Charge et démarre la lecture d'un flux.
   * @param {string}  url    URL du flux (http://)
   * @param {number}  seekTo Position de départ en secondes
   * @param {object}  cbs    Callbacks : onLoaded, onTimeUpdate, onPlayStateChange,
   *                                     onEnded, onError, onCodecError
   */
  load(url, seekTo, cbs) {
    this._cbs       = cbs || {};
    this._seekTo    = seekTo || 0;
    this._destroyed = false;
    this._layerReady = false;
    this._cleanup();

    console.warn('[GAV] load() url=', url, 'seekTo=', seekTo);

    var self = this;

    // ── Lecture directe sans GAV ──────────────────────────────────────────────
    // On ne demande pas de couche d'affichage via webosgavplugin :
    // le système routera peut-être la vidéo vers la surface par défaut de l'app.
    // (webosgavplugin crée une fenêtre native déconnectée du compositor web —
    //  cette approche teste si Luna seule suffit pour l'affichage.)

    var bridge = new PalmServiceBridge();
    bridge.onservicecallback = function(msg) {
      if (self._destroyed) return;
      try {
        var data = JSON.parse(msg);
        console.warn('[LUNA] /load réponse:', JSON.stringify(data));

        if (data.returnValue === false) {
          console.error('[LUNA] /load ERREUR:', data.errorText || data.errorCode);
          if (self._cbs.onError) self._cbs.onError(data.errorText || 'load failed');
          return;
        }

        if (data.mediaId) {
          self._mediaId = data.mediaId;
          self._layerReady = true;
          console.warn('[LUNA] mediaId obtenu:', data.mediaId);

          self._startSubscription();
          self._startPolling();

          // Lecture directe — pas de GAV
          if (self._seekTo > 0) self._fire('/seek', { mediaId: data.mediaId, position: Math.floor(self._seekTo * 1000) });
          self._fire('/play', { mediaId: data.mediaId });
          if (self._cbs.onLoaded) self._cbs.onLoaded();
        }
      } catch (e) {
        console.warn('[LUNA] parse error:', e.message);
      }
    };

    // Payload avec option pour aider le décodeur
    var payload = {
      uri:  url,
      type: 'media',
      option: {
        adaptiveStreaming: {
          useUnsupportedResolution: true
        }
      }
    };
    console.warn('[LUNA] /load payload:', JSON.stringify(payload));
    bridge.call(MEDIA_SVC + '/load', JSON.stringify(payload));
  }

  play() {
    if (this._mediaId && this._layerReady)
      this._fire('/play', { mediaId: this._mediaId });
  }

  pause() {
    if (this._mediaId)
      this._fire('/pause', { mediaId: this._mediaId });
  }

  seek(seconds) {
    if (this._mediaId)
      this._fire('/seek', { mediaId: this._mediaId, position: Math.floor(seconds * 1000) });
  }

  unload() {
    console.warn('[GAV] unload()');
    this._destroyed = true;
    if (this._mediaId && typeof webosgavplugin !== 'undefined') {
      try { webosgavplugin.destroyMediaLayer(this._mediaId); } catch (e) {}
    }
    this._cleanup();
  }

  // ── Méthodes internes ──────────────────────────────────────────────────────

  _fire(method, params) {
    var b = new PalmServiceBridge();
    b.onservicecallback = function(msg) {
      try {
        var d = JSON.parse(msg);
        console.warn('[LUNA]', method, 'réponse:', JSON.stringify(d));
      } catch(e) {}
    };
    b.call(MEDIA_SVC + method, JSON.stringify(params));
  }

  _handleStatus(data) {
    if (!data || this._destroyed) return;

    // ── Position courante ────────────────────────────────────────────────────
    // webOS envoie currentTime comme objet imbriqué :
    //   { currentTime: { currentTime: 86948, mediaId: "..." } }  ← ms
    // bufferRange.endTime est en secondes et représente la fin du buffer,
    // pas la position de lecture → ne pas l'utiliser comme position affichée.
    var time = null;
    var dur  = null;

    if (data.currentTime && typeof data.currentTime.currentTime === 'number') {
      time = data.currentTime.currentTime / 1000; // ms → secondes
    }

    if (typeof data.duration === 'number' && data.duration > 0) {
      dur = data.duration / 1000;
    } else if (data.currentTime && typeof data.currentTime.duration === 'number' && data.currentTime.duration > 0) {
      dur = data.currentTime.duration / 1000;
    }

    if (time !== null && this._cbs.onTimeUpdate) {
      this._cbs.onTimeUpdate(time, dur || 0);
    }

    // ── État de lecture ──────────────────────────────────────────────────────
    if (data.playState !== undefined) {
      var st      = String(data.playState).toLowerCase();
      var playing = st === 'playing';
      var ended   = st === 'endofstream' || st === 'ended';
      console.warn('[LUNA] playState=', st);
      if (this._cbs.onPlayStateChange) this._cbs.onPlayStateChange(playing);
      if (ended && this._cbs.onEnded)   this._cbs.onEnded();
    }

    // ── Erreurs ──────────────────────────────────────────────────────────────
    if (data.error) {
      var code = data.error.errorCode || 0;
      console.warn('[LUNA] erreur pipeline code=', code, 'text=', data.error.errorText);
      if (code === 100) {
        // "Playing error" = codec refusé par le hardware decoder.
        // Notifier l'appelant via onCodecError pour qu'il puisse tenter un fallback.
        if (this._cbs.onCodecError) this._cbs.onCodecError(data.error.errorText || 'codec not supported');
      } else {
        if (this._cbs.onError) this._cbs.onError(data.error.errorText || code);
      }
    }
  }

  _startSubscription() {
    var self = this;
    this._subBridge = new PalmServiceBridge();
    this._subBridge.onservicecallback = function(msg) {
      if (self._destroyed) return;
      try {
        var d = JSON.parse(msg);
        console.warn('[LUNA] subscription event:', JSON.stringify(d));
        self._handleStatus(d);
      } catch (e) {}
    };
    this._subBridge.call(MEDIA_SVC + '/subscribe', JSON.stringify({
      mediaId:   this._mediaId,
      subscribe: true
    }));
  }

  _startPolling() {
    var self = this;
    this._pollTimer = setInterval(function() {
      if (!self._mediaId || self._destroyed) {
        clearInterval(self._pollTimer);
        self._pollTimer = null;
        return;
      }
      var b = new PalmServiceBridge();
      b.onservicecallback = function(msg) {
        try { self._handleStatus(JSON.parse(msg)); } catch (e) {}
      };
      b.call(MEDIA_SVC + '/getMediaPlayState', JSON.stringify({ mediaId: self._mediaId }));
    }, 1000);
  }

  _cleanup() {
    clearInterval(this._pollTimer);
    this._pollTimer = null;

    if (this._subBridge) {
      try { this._subBridge.cancel(); } catch (e) {}
      this._subBridge = null;
    }

    if (this._mediaId) {
      var mediaId = this._mediaId;
      this._mediaId = null;
      var b = new PalmServiceBridge();
      b.onservicecallback = function() {};
      b.call(MEDIA_SVC + '/unload', JSON.stringify({ mediaId: mediaId }));
    }
  }
}

export default WebOSMediaPipeline;
