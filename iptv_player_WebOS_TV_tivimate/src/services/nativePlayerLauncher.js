/**
 * src/services/nativePlayerLauncher.js
 *
 * Lance le lecteur natif LG pour les fichiers XVID/DivX/AVI non décodables
 * par le <video> HTML5 de webOS 6.
 *
 * Flow :
 *   1. luna://com.webos.applicationManager/launch
 *        → com.webos.app.mediadiscovery (webOS 6)
 *        → com.webos.app.photovideo     (webOS 3–5, fallback)
 *   2. Souscription getForegroundAppInfo pour détecter la fermeture du player
 *        → callback onClosed()
 */

var APP_MEDIADISCOVERY = 'com.webos.app.mediadiscovery';
var APP_PHOTOVIDEO     = 'com.webos.app.photovideo';

/**
 * Lance le lecteur vidéo natif LG.
 *
 * @param {object} opts
 *   url             {string}   URL HTTP du flux vidéo
 *   fileName        {string}   Nom affiché dans le player LG
 *   lastPlayPosition{number}   Position de départ en secondes (0 = début)
 *   onLaunched      {function} Appelé si le lancement réussit
 *   onError         {function} Appelé si le lancement échoue (msg)
 *   onClosed        {function} Appelé quand le player LG se ferme
 */
export function launchNativePlayer(opts) {
  var url              = opts.url              || '';
  var fileName         = opts.fileName         || url.split('/').pop().split('?')[0];
  var lastPlayPosition = opts.lastPlayPosition || 0;
  var onLaunched       = opts.onLaunched       || function() {};
  var onError          = opts.onError          || function() {};
  var onClosed         = opts.onClosed         || null;

  if (typeof PalmServiceBridge === 'undefined') {
    onError('PalmServiceBridge non disponible');
    return;
  }

  _launchWithId(APP_MEDIADISCOVERY, url, fileName, lastPlayPosition, onLaunched, onClosed,
    function fallback(err) {
      console.warn('[NativePlayer] mediadiscovery échoué (' + err + '), retry photovideo...');
      _launchWithId(APP_PHOTOVIDEO, url, fileName, lastPlayPosition, onLaunched, onClosed, onError);
    }
  );
}

// ── Helpers internes ──────────────────────────────────────────────────────────

function _buildPayload(url, fileName, lastPlayPosition) {
  return {
    fullPath:         url,
    fileName:         fileName,
    mediaType:        'VIDEO',
    deviceType:       'DMR',
    lastPlayPosition: lastPlayPosition > 0 ? Math.floor(lastPlayPosition * 1000) : -1,
    artist:           '',
    album:            '',
    subtitle:         '',
    thumbnail:        '',
    dlnaInfo: {
      flagVal:       4096,
      cleartextSize: '-1',
      contentLength: '-1',
      opVal:         1,
      duration:      0,
      // Wildcard MIME pour laisser le player auto-détecter (évite refus sur certains firmwares)
      protocolInfo: 'http-get:*:*:DLNA.ORG_OP=01;DLNA.ORG_CI=0;DLNA.ORG_FLAGS=01700000000000000000000000000000'
    }
  };
}

function _launchWithId(appId, url, fileName, lastPlayPosition, onLaunched, onClosed, onError) {
  var params = JSON.stringify({
    id:     appId,
    params: { payload: [_buildPayload(url, fileName, lastPlayPosition)] }
  });

  console.warn('[NativePlayer] launch', appId, 'url=', url);

  var b = new PalmServiceBridge();
  b.onservicecallback = function(msg) {
    try {
      var r = JSON.parse(msg);
      if (r.returnValue === false) {
        console.warn('[NativePlayer] launch ERREUR:', r.errorText);
        onError(r.errorText || 'launch failed');
      } else {
        console.warn('[NativePlayer] lancé :', appId);
        onLaunched(appId);
        if (onClosed) _monitorForeground(appId, onClosed);
      }
    } catch (e) {
      onError('parse error');
    }
  };
  b.call('luna://com.webos.applicationManager/launch', params);
}

function _monitorForeground(playerAppId, onClosed) {
  if (typeof PalmServiceBridge === 'undefined') return;

  var bridge   = new PalmServiceBridge();
  var launched = false;

  bridge.onservicecallback = function(msg) {
    try {
      var data = JSON.parse(msg);
      if (data.returnValue === false) {
        console.warn('[NativePlayer] getForegroundAppInfo non disponible');
        bridge.cancel();
        return;
      }

      var appId = '';
      if (data.foregroundAppInfo && data.foregroundAppInfo[0]) {
        appId = data.foregroundAppInfo[0].appId || '';
      } else if (data.appId) {
        appId = data.appId;
      }

      if (!launched) {
        if (appId === playerAppId) launched = true;
      } else {
        if (appId && appId !== playerAppId) {
          console.warn('[NativePlayer] player fermé, app courante :', appId);
          bridge.cancel();
          onClosed();
        }
      }
    } catch (e) {}
  };

  bridge.call(
    'luna://com.webos.applicationManager/getForegroundAppInfo',
    JSON.stringify({ subscribe: true })
  );
}
