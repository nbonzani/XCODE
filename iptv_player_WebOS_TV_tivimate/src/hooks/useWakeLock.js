/**
 * src/hooks/useWakeLock.js
 * Empêche la mise en veille de la TV webOS pendant la navigation dans l'app.
 *
 * Deux mécanismes combinés :
 *   1. Luna subscribe sur getPowerState → réveille l'écran si il part en veille
 *   2. Ping Luna setSystemSettings toutes les 60s (signal d'activité)
 *   3. AudioContext silencieux (fallback Chromium, maintient la page "active")
 */

import { useEffect } from 'react';

export function useWakeLock() {
  useEffect(function() {
    var cleanups = [];

    // ── Méthode 1 : Luna subscribe getPowerState ──────────────────────────
    // S'abonner à un service Luna maintient l'app "active" côté système.
    try {
      if (typeof webOS !== 'undefined' && webOS.service) {
        var req = webOS.service.request('luna://com.webos.service.tvpower/power', {
          method: 'getPowerState',
          subscribe: true,
          onSuccess: function(res) {
            if (res && res.state && res.state.toLowerCase().indexOf('sleep') !== -1) {
              webOS.service.request('luna://com.webos.service.tvpower/power', {
                method: 'wakeUpScreen',
                parameters: {},
                onSuccess: function() {},
                onFailure: function() {},
              });
            }
          },
          onFailure: function() {},
        });
        cleanups.push(function() { if (req && req.cancel) req.cancel(); });
      }
    } catch (e) { /* non webOS */ }

    // ── Méthode 2 : Ping Luna toutes les 60s ─────────────────────────────
    // setSystemSettings avec screenSaverTimeout=0 désactive le screensaver.
    // L'appel périodique maintient le réglage actif sans perturber l'usage normal.
    try {
      if (typeof webOS !== 'undefined' && webOS.service) {
        var pingInterval = setInterval(function() {
          try {
            webOS.service.request('luna://com.webos.settingsservice', {
              method: 'setSystemSettings',
              parameters: { category: 'picture', settings: { screenSaverTimeout: 0 } },
              onSuccess: function() {},
              onFailure: function() {},
            });
          } catch (e2) {}
        }, 60000);
        cleanups.push(function() { clearInterval(pingInterval); });
      }
    } catch (e) { /* non webOS */ }

    // ── Méthode 3 : AudioContext silencieux (fallback) ────────────────────
    try {
      var AudioCtx = window.AudioContext || window.webkitAudioContext;
      if (AudioCtx) {
        var ctx  = new AudioCtx();
        var osc  = ctx.createOscillator();
        var gain = ctx.createGain();
        gain.gain.value = 0;
        osc.connect(gain);
        gain.connect(ctx.destination);
        osc.start();
        cleanups.push(function() {
          try { osc.stop(); ctx.close(); } catch (e2) {}
        });
      }
    } catch (e) { /* AudioContext non disponible */ }

    return function() {
      cleanups.forEach(function(fn) { fn(); });
    };
  }, []);
}
