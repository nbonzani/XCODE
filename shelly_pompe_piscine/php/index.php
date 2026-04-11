<?php header('Content-Type: text/html; charset=utf-8'); ?><!doctype html>
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
    grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
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

async function refresh() {
  try {
    const r = await fetch('api.php?_=' + Date.now());
    if (!r.ok) throw new Error('HTTP ' + r.status);
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
        <div class="value">${stateLabel}</div>
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
        <div class="label">Aujourd'hui</div>
        <div class="value">${fmtDur(d.today_sec)}</div>
        <div class="sub">cible été : 2–8 h</div>
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
        <thead><tr><th>Jour</th><th class="num">Durée</th><th style="width:50%">Répartition</th></tr></thead>
        <tbody>${dailyRows || '<tr><td colspan="3" style="opacity:0.5">Aucune donnée</td></tr>'}</tbody>
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
  `;
  document.getElementById('app').innerHTML = html;
  document.getElementById('serverTime').textContent =
    'serveur : ' + fmtTs(d.server_time);
}

refresh();
setInterval(refresh, 30000);
</script>
</body>
</html>
