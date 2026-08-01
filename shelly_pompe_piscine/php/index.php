<?php
header('Content-Type: text/html; charset=utf-8');
require_once __DIR__ . '/env.php';
$deployToken = env('DEPLOY_TOKEN', '');
?><!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<title>Pompe Piscine — Dashboard</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
  * { box-sizing: border-box; }
  body {
    font-family: -apple-system, "Segoe UI", Roboto, Arial, sans-serif;
    background: #0f1720; color: #e7ebf0;
    margin: 0; padding: 20px; max-width: 1200px; margin: 0 auto;
  }
  h1 { color: #4fc3f7; margin: 0 0 8px; font-size: 22px; }
  .subtitle { opacity: 0.5; font-size: 12px; margin-bottom: 20px; }
  .cards {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(130px, 1fr));
    gap: 12px; margin-bottom: 25px;
  }
  .card {
    background: #1b2533; border-radius: 8px; padding: 14px;
    border-left: 4px solid #4fc3f7;
  }
  .card .label {
    font-size: 10px; text-transform: uppercase;
    opacity: 0.55; letter-spacing: 1px;
  }
  .card .value {
    font-size: 26px; font-weight: 700; margin-top: 4px; line-height: 1.1;
  }
  .card .sub { font-size: 11px; opacity: 0.65; margin-top: 2px; }
  .card.on  { border-left-color: #4caf50; } .card.on  .value { color: #4caf50; }
  .card.off { border-left-color: #f44336; } .card.off .value { color: #f44336; }
  .card.neutral { border-left-color: #78909c; }
  .section { margin-top: 28px; }
  h2 {
    font-size: 12px; text-transform: uppercase;
    opacity: 0.55; letter-spacing: 1.5px; margin: 0 0 10px;
  }
  table {
    width: 100%; border-collapse: collapse;
    background: #1b2533; border-radius: 8px; overflow: hidden;
  }
  th, td {
    padding: 7px 12px; text-align: left;
    border-bottom: 1px solid #283244; font-size: 12px;
  }
  th { background: #0f1720; font-weight: 600; opacity: 0.75; }
  tr:last-child td { border-bottom: none; }
  .type-on  { color: #4caf50; font-weight: 600; }
  .type-off { color: #f44336; font-weight: 600; }
  .type-heartbeat { opacity: 0.45; }
  .type-manual { color: #ffb74d; }
  .type-conflict_start, .type-conflict_end { color: #ba68c8; }
  .type-boot { color: #4fc3f7; }
  .num { text-align: right; font-variant-numeric: tabular-nums; }
  .bar { display: inline-block; height: 10px; background: #4fc3f7; border-radius: 2px; vertical-align: middle; }
  .err { color: #f44336; padding: 15px; background: #2a1515; border-radius: 8px; }
  .purge-box {
    margin-top: 32px; padding: 16px 20px;
    background: #1b2533; border-radius: 8px;
    border-left: 4px solid #f44336;
    display: flex; align-items: center; gap: 12px; flex-wrap: wrap;
  }
  .purge-box label { font-size: 12px; opacity: 0.7; }
  .purge-box input[type=date] {
    background: #0f1720; color: #e7ebf0; border: 1px solid #4fc3f7;
    border-radius: 4px; padding: 5px 8px; font-size: 13px;
  }
  .purge-box button {
    background: #f44336; color: #fff; border: none;
    border-radius: 4px; padding: 6px 14px; font-size: 13px;
    cursor: pointer; font-weight: 600;
  }
  .purge-box button:hover { background: #d32f2f; }
  .purge-msg { font-size: 12px; margin-left: 4px; }
  .settings-box {
    margin-top: 24px; padding: 16px 20px;
    background: #1b2533; border-radius: 8px;
    border-left: 4px solid #4fc3f7;
  }
  .settings-box h2 { margin: 0 0 14px; }
  .seuil-table { width: auto; background: transparent; border-radius: 0; }
  .seuil-table th, .seuil-table td { padding: 5px 10px; font-size: 13px; border-bottom: 1px solid #283244; }
  .seuil-table th { background: transparent; opacity: 0.7; }
  .seuil-table input[type=number] {
    width: 90px; background: #0f1720; color: #e7ebf0;
    border: 1px solid #4fc3f7; border-radius: 4px; padding: 4px 7px; font-size: 13px;
  }
  .seuil-table .unit { opacity: 0.5; font-size: 11px; padding-left: 3px; }
  .btn-save {
    margin-top: 14px; background: #4fc3f7; color: #0f1720;
    border: none; border-radius: 4px; padding: 7px 18px;
    font-size: 13px; font-weight: 700; cursor: pointer;
  }
  .btn-save:hover { background: #29b6f6; }
  .settings-msg { font-size: 12px; margin-left: 10px; }
</style>
</head>
<body>
<h1>🏊 Pompe Piscine — Dashboard</h1>
<div class="subtitle">Rafraîchissement automatique toutes les 30 s · <span id="serverTime">—</span></div>
<div id="app">Chargement…</div>

<script>
function fmtDur(sec) {
  if (!sec || sec < 0) return '0 min';
  const h = Math.floor(sec / 3600);
  const m = Math.floor((sec % 3600) / 60);
  if (h > 0) return h + 'h' + String(m).padStart(2, '0');
  return m + ' min';
}
function fmtTs(ts) {
  if (!ts) return '—';
  const d = new Date(ts * 1000);
  return d.toLocaleString('fr-FR', {
    day: '2-digit', month: '2-digit',
    hour: '2-digit', minute: '2-digit', second: '2-digit'
  });
}
function fmtDay(iso) {
  if (!iso) return '';
  const [y, m, d] = iso.split('-');
  return d + '/' + m;
}
function num(v, suffix) {
  if (v === null || v === undefined) return '—';
  return Math.round(v) + (suffix || '');
}
function fmtWh(wh) {
  if (wh === null || wh === undefined || wh === '') return '—';
  const v = parseFloat(wh);
  if (isNaN(v)) return '—';
  if (v >= 1000) return (v / 1000).toFixed(2) + ' kWh';
  return Math.round(v) + ' Wh';
}

// ---- Paramètres (seuils) ----
let _cfg = {};

function renderSettings(cfg) {
  _cfg = cfg || {};
  const seasons = [
    { key: 'haute', label: 'HAUTE (juin–août)' },
    { key: 'mi',    label: 'MI (mars–mai, sept–oct)' },
    { key: 'basse', label: 'BASSE (nov–fév)' },
  ];
  const rows = seasons.map(s => `
    <tr>
      <td>${s.label}</td>
      <td>
        <input type="number" id="mini_${s.key}"
               value="${cfg['seuil_mini_' + s.key] !== undefined ? cfg['seuil_mini_' + s.key] : ''}">
        <span class="unit">W</span>
      </td>
      <td>
        <input type="number" id="maxi_${s.key}"
               value="${cfg['seuil_maxi_' + s.key] !== undefined ? cfg['seuil_maxi_' + s.key] : ''}">
        <span class="unit">W</span>
      </td>
      <td>
        <input type="number" id="quota_mini_${s.key}" min="0" max="24" step="0.5"
               value="${cfg['quota_mini_' + s.key] !== undefined ? cfg['quota_mini_' + s.key] : ''}">
        <span class="unit">h</span>
      </td>
      <td>
        <input type="number" id="quota_max_${s.key}" min="0" max="24" step="0.5"
               value="${cfg['quota_max_' + s.key] !== undefined ? cfg['quota_max_' + s.key] : ''}">
        <span class="unit">h</span>
      </td>
    </tr>
  `).join('');

  document.getElementById('settingsBody').innerHTML = rows;
}

async function saveSettings() {
  const msg = document.getElementById('settingsMsg');
  const seasons = ['haute', 'mi', 'basse'];
  const data = {};
  for (const s of seasons) {
    const mini = document.getElementById('mini_' + s);
    const maxi = document.getElementById('maxi_' + s);
    const qm   = document.getElementById('quota_mini_' + s);
    const qx   = document.getElementById('quota_max_'  + s);
    if (!mini || !maxi || !qm || !qx) continue;
    data['seuil_mini_' + s]  = parseInt(mini.value, 10);
    data['seuil_maxi_' + s]  = parseInt(maxi.value, 10);
    data['quota_mini_' + s]  = parseFloat(qm.value);
    data['quota_max_'  + s]  = parseFloat(qx.value);
  }

  // Validation
  for (const s of seasons) {
    if (data['seuil_mini_' + s] >= data['seuil_maxi_' + s]) {
      msg.textContent = '⚠️ Seuil mini doit être < seuil maxi pour ' + s.toUpperCase();
      msg.style.color = '#ffb74d';
      return;
    }
    if (data['quota_mini_' + s] < 0 || data['quota_mini_' + s] > 24) {
      msg.textContent = '⚠️ Quota mini invalide pour ' + s.toUpperCase() + ' (0–24 h)';
      msg.style.color = '#ffb74d';
      return;
    }
    if (data['quota_max_' + s] <= 0 || data['quota_max_' + s] > 24 ||
        data['quota_max_' + s] < data['quota_mini_' + s]) {
      msg.textContent = '⚠️ Quota max invalide pour ' + s.toUpperCase() + ' (doit être > quota mini)';
      msg.style.color = '#ffb74d';
      return;
    }
  }
  msg.textContent = '…'; msg.style.color = '#e7ebf0';
  try {
    const r = await fetch('config.php', {
      method: 'POST',
      headers: { 'X-Deploy-Token': '<?= htmlspecialchars($deployToken, ENT_QUOTES) ?>', 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });
    const d = await r.json();
    if (d.ok) {
      msg.textContent = '✅ ' + d.saved + ' valeurs sauvegardées (prise en compte au prochain cycle Shelly)';
      msg.style.color = '#4caf50';
    } else {
      msg.textContent = '❌ ' + (d.error || 'erreur');
      msg.style.color = '#f44336';
    }
  } catch(e) {
    msg.textContent = '❌ ' + e.message;
    msg.style.color = '#f44336';
  }
}

async function refresh() {
  try {
    const r = await fetch('api.php?_=' + Date.now());
    if (!r.ok) {
      let detail = 'HTTP ' + r.status;
      try {
        const body = await r.json();
        if (body && body.error) detail += ' — ' + body.error;
      } catch (_) {}
      throw new Error(detail);
    }
    const d = await r.json();
    render(d);
  } catch (e) {
    document.getElementById('app').innerHTML =
      '<div class="err">Erreur API: ' + e.message + '</div>';
  }
}

function render(d) {
  const last = d.last_event || {};
  const on = last.pump_on == 1;
  const stateClass = last.pump_on === null ? 'neutral' : (on ? 'on' : 'off');
  const stateLabel = last.pump_on === null ? '?' : (on ? 'ON' : 'OFF');

  // Ventilation 14 jours
  const maxDay = Math.max(1, ...d.daily.map(x => parseInt(x.s || 0)));
  const dailyRows = d.daily.map(row => {
    const s = parseInt(row.s || 0);
    const w = Math.round((s / maxDay) * 100);
    return `<tr>
      <td>${fmtDay(row.day)}</td>
      <td class="num">${fmtDur(s)}</td>
      <td><span class="bar" style="width:${w}%"></span></td>
      <td class="num">☀️ ${fmtWh(row.pv_wh)}</td>
      <td class="num">💶 ${fmtWh(row.pump_grid_wh)}</td>
    </tr>`;
  }).join('');

  // Évènements non-heartbeat
  const evtRows = (d.events || []).map(e => `
    <tr class="type-${e.type}">
      <td>${fmtTs(e.ts)}</td>
      <td>${e.type}</td>
      <td>${e.pump_on == 1 ? 'ON' : (e.pump_on == 0 ? 'OFF' : '—')}</td>
      <td class="num">${num(e.grid_w, ' W')}</td>
      <td class="num">${fmtDur(e.daily_sec)}</td>
      <td>${e.reason || ''}</td>
    </tr>
  `).join('');

  // Derniers points (tous types, inclut heartbeat)
  const recRows = d.recent.slice(0, 20).map(e => `
    <tr class="type-${e.type}">
      <td>${fmtTs(e.ts)}</td>
      <td>${e.type}</td>
      <td>${e.pump_on == 1 ? 'ON' : (e.pump_on == 0 ? 'OFF' : '—')}</td>
      <td class="num">${num(e.grid_w, ' W')}</td>
      <td class="num">${num(e.grid_avg_w, ' W')}</td>
      <td class="num">${num(e.pv_w, ' W')}</td>
      <td>${e.mode || ''}</td>
      <td class="num">${fmtDur(e.daily_sec)}</td>
    </tr>
  `).join('');

  const html = `
    <div class="cards">
      <div class="card ${stateClass}">
        <div class="label">État pompe</div>
        <div class="value">${stateLabel}
          <button id="pumpBtn"
            onclick="setPump(${on ? 'false' : 'true'})"
            style="margin-left:10px;padding:3px 10px;font-size:13px;font-weight:700;
                   border:none;border-radius:4px;cursor:pointer;vertical-align:middle;
                   background:${on ? '#f44336' : '#4caf50'};color:#fff;">
            ${on ? '⏹ OFF' : '▶ ON'}
          </button>
        </div>
        <div class="sub">dernier point : ${fmtTs(last.ts)}</div>
      </div>
      <div class="card">
        <div class="label">Mode saison</div>
        <div class="value">${last.mode || '—'}</div>
      </div>
      <div class="card">
        <div class="label">Réseau (dernière mesure)</div>
        <div class="value">${num(last.grid_w, ' W')}</div>
        <div class="sub">moy. ${num(last.grid_avg_w, ' W')}</div>
      </div>
      <div class="card">
        <div class="label">Solaire (production)</div>
        <div class="value">${num(last.pv_w, ' W')}</div>
      </div>
      <div class="card">
        <div class="label">Aujourd'hui</div>
        <div class="value">${fmtDur(d.today_sec)}</div>
        <div class="sub">${{'HAUTE':'cible : 4–8 h','MI':'cible : 1–4 h','BASSE':'cible : 0–2 h'}[last.mode] || 'cible : —'}</div>
      </div>
      <div class="card">
        <div class="label">Cette semaine</div>
        <div class="value">${fmtDur(d.week_sec)}</div>
      </div>
      <div class="card">
        <div class="label">Ce mois</div>
        <div class="value">${fmtDur(d.month_sec)}</div>
      </div>
    </div>

    <div class="section">
      <h2>Filtration sur 14 jours</h2>
      <table>
        <thead><tr><th>Jour</th><th class="num">Durée</th><th style="width:40%">Répartition</th><th class="num">☀️ PV produit</th><th class="num">💶 Pompe réseau</th></tr></thead>
        <tbody>${dailyRows || '<tr><td colspan="5" style="opacity:0.5">Aucune donnée</td></tr>'}</tbody>
      </table>
    </div>

    <div class="section">
      <h2>Évènements (hors heartbeats)</h2>
      <table>
        <thead><tr>
          <th>Heure</th><th>Type</th><th>Pompe</th>
          <th class="num">Grid</th><th class="num">Cumul jour</th><th>Motif</th>
        </tr></thead>
        <tbody>${evtRows || '<tr><td colspan="6" style="opacity:0.5">Aucun évènement</td></tr>'}</tbody>
      </table>
    </div>

    <div class="section">
      <h2>20 derniers points bruts (inclut heartbeats)</h2>
      <table>
        <thead><tr>
          <th>Heure</th><th>Type</th><th>Pompe</th>
          <th class="num">Grid</th><th class="num">Moy</th><th class="num">PV</th>
          <th>Mode</th><th class="num">Cumul</th>
        </tr></thead>
        <tbody>${recRows || '<tr><td colspan="8" style="opacity:0.5">Aucun point</td></tr>'}</tbody>
      </table>
    </div>

    <div class="subtitle" style="margin-top:20px">
      ${d.total_events} évènements en base
    </div>

    <div class="purge-box">
      <label>🗑️ Supprimer les données avant le</label>
      <input type="date" id="purgeDate">
      <button onclick="doPurge()">Initialiser</button>
      <span class="purge-msg" id="purgeMsg"></span>
    </div>

    <div class="settings-box">
      <h2>⚙️ Paramètres — Seuils de pilotage</h2>
      <p style="font-size:11px;opacity:0.6;margin:0 0 10px">
        Seuil mini : grid moyen ≤ valeur → pompe démarre (surplus suffisant).<br>
        Seuil maxi : grid moyen &gt; valeur → pompe s'arrête (surplus insuffisant).<br>
        Quota mini : durée minimale de filtration journalière forcée entre 12 h et 17 h.<br>
        Délai minimum entre deux bascules : 30 min (toujours actif).
      </p>
      <table class="seuil-table">
        <thead>
          <tr>
            <th>Saison</th>
            <th>Seuil mini (W)</th>
            <th>Seuil maxi (W)</th>
            <th>Quota mini (h)</th>
            <th>Quota max (h)</th>
          </tr>
        </thead>
        <tbody id="settingsBody">
          <tr><td colspan="5" style="opacity:0.5">Chargement…</td></tr>
        </tbody>
      </table>
      <button class="btn-save" onclick="saveSettings()">💾 Sauvegarder</button>
      <span class="settings-msg" id="settingsMsg"></span>
    </div>
  `;
  document.getElementById('app').innerHTML = html;
  document.getElementById('serverTime').textContent =
    'serveur : ' + fmtTs(d.server_time);
  // Mise à jour des paramètres (seulement au 1er chargement ou si pas d'édition en cours)
  if (d.config && !document.getElementById('settingsBody').dataset.edited) {
    renderSettings(d.config);
  }
}

async function doPurge() {
  const dateInput = document.getElementById('purgeDate');
  const msg = document.getElementById('purgeMsg');
  const date = dateInput ? dateInput.value : '';
  if (!date) { msg.textContent = '⚠️ Choisissez une date.'; msg.style.color='#ffb74d'; return; }
  if (!confirm('Supprimer définitivement tous les évènements avant le ' + date + ' ?')) return;
  msg.textContent = '…'; msg.style.color = '#e7ebf0';
  try {
    const r = await fetch('purge.php?before=' + date, {
      method: 'GET',
      headers: { 'X-Deploy-Token': '<?= htmlspecialchars($deployToken, ENT_QUOTES) ?>' }
    });
    const d = await r.json();
    if (d.ok) {
      msg.textContent = '✅ ' + d.deleted + ' évènements supprimés (' + d.remaining + ' restants)';
      msg.style.color = '#4caf50';
      refresh();
    } else {
      msg.textContent = '❌ ' + (d.error || 'erreur');
      msg.style.color = '#f44336';
    }
  } catch(e) {
    msg.textContent = '❌ ' + e.message;
    msg.style.color = '#f44336';
  }
}

async function setPump(on) {
  const btn = document.getElementById('pumpBtn');
  if (btn) { btn.disabled = true; btn.textContent = '…'; }
  try {
    const resp = await fetch('pump_control.php', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ on: on }),
    });
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({}));
      console.warn('Pump toggle error:', err);
    }
  } catch(e) { console.warn('Pump toggle error:', e.message); }
  setTimeout(refresh, 2500);
}

refresh();
setInterval(refresh, 30000);
</script>
</body>
</html>
