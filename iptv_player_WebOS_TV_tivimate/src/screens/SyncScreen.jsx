/**
 * src/screens/SyncScreen.jsx
 * Écran plein écran affiché pendant la synchronisation du catalogue.
 *
 * - Fond noir total couvrant toute l'interface
 * - Texte de statut (étape courante) qui se déplace en style "DVD logo"
 * - Barre de progression (done / total catégories)
 * - Anti-veille : subscribe Luna + AudioContext silencieux (fallback)
 */

import React, { useEffect, useState } from 'react';
import { useAppStore } from '../store/appStore.js';
import { useWakeLock } from '../hooks/useWakeLock.js';
import './SyncScreen.css';

var BLOB_W   = 680;   // largeur max du bloc (px)
var BLOB_H   = 140;   // hauteur approx du bloc (px)
var SCREEN_W = 1920;
var SCREEN_H = 1080;
var MARGIN   = 80;

var MAX_X = SCREEN_W - BLOB_W  - MARGIN * 2;
var MAX_Y = SCREEN_H - BLOB_H  - MARGIN * 2;

// Périodes en ms (valeurs premières → trajectoire non répétitive).
// ÷4 par rapport à la version précédente = déplacement 4× plus lent.
var PERIOD_X = 29200; // ms  (était 7300)
var PERIOD_Y = 20400; // ms  (était 5100)

// ── Hook : position rebondissante ────────────────────────────────────────────

function useBouncingPos() {
  var _pos = useState({ x: Math.floor(MAX_X / 2), y: Math.floor(MAX_Y / 3) });
  var pos    = _pos[0];
  var setPos = _pos[1];

  useEffect(function() {
    var startTime = Date.now();
    var raf;

    function tick() {
      var t  = Date.now() - startTime;
      // Onde triangulaire → rebond linéaire parfait
      var tx = t % (PERIOD_X * 2);
      var ty = t % (PERIOD_Y * 2);
      var x  = tx < PERIOD_X ? (tx / PERIOD_X) * MAX_X : (2 - tx / PERIOD_X) * MAX_X;
      var y  = ty < PERIOD_Y ? (ty / PERIOD_Y) * MAX_Y : (2 - ty / PERIOD_Y) * MAX_Y;
      setPos({ x: Math.round(x), y: Math.round(y) });
      raf = requestAnimationFrame(tick);
    }

    raf = requestAnimationFrame(tick);
    return function() { cancelAnimationFrame(raf); };
  }, []);

  return pos;
}

// useWakeLock importé depuis src/hooks/useWakeLock.js

// ── Composant ────────────────────────────────────────────────────────────────

export default function SyncScreen() {
  var syncStatus   = useAppStore(function(s) { return s.syncStatus; });
  var syncProgress = useAppStore(function(s) { return s.syncProgress; });
  var pos          = useBouncingPos();

  useWakeLock();

  var done         = syncProgress.done  || 0;
  var total        = syncProgress.total || 0;
  var pct          = total > 0 ? Math.round((done / total) * 100) : 0;
  var showProgress = total > 0;

  return (
    <div className="sync-screen">

      {/* Bloc texte animé — contient le statut courant */}
      <div
        className="sync-screen__blob"
        style={{ transform: 'translate(' + pos.x + 'px, ' + pos.y + 'px)' }}
      >
        <div className="sync-screen__title">
          {syncStatus || 'Chargement de la liste de lecture…'}
        </div>

        <div className="sync-screen__dots">
          <span className="sync-dot sync-dot--1" />
          <span className="sync-dot sync-dot--2" />
          <span className="sync-dot sync-dot--3" />
        </div>

        {showProgress && (
          <div className="sync-screen__progress">
            <div className="sync-screen__progress-bar">
              <div
                className="sync-screen__progress-fill"
                style={{ width: pct + '%' }}
              />
            </div>
            <span className="sync-screen__progress-pct">{pct}&nbsp;%</span>
          </div>
        )}
      </div>

    </div>
  );
}
