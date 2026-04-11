/**
 * src/services/usbService.js
 * Accès USB et parsing M3U pour webOS TV.
 *
 * Stratégie :
 * 1. Détection USB via luna service com.webos.service.mediaindexer
 * 2. Lecture du fichier via XMLHttpRequest file://
 * 3. Parsing M3U standard (#EXTM3U / #EXTINF)
 *
 * Fallback : saisie manuelle du chemin si luna n'est pas disponible.
 */

// ── Détection des périphériques USB ──────────────────────────────────────────

/**
 * Détecte les périphériques USB connectés à la TV via luna service.
 * @returns {Promise<Array<{ uri: string, name: string }>>}
 */
export function detectUsbDevices() {
  return new Promise((resolve) => {
    // Vérifier si on est sur webOS (luna disponible)
    if (typeof window.webOS === 'undefined' || !window.webOS.service) {
      console.warn('[USB] webOS.service non disponible — mode simulateur');
      resolve([]);
      return;
    }

    try {
      window.webOS.service.request('luna://com.webos.service.mediaindexer', {
        method: 'getDeviceList',
        onSuccess: function (res) {
          const devices = (res.deviceList || [])
            .filter(function (d) { return d.uri && d.available; })
            .map(function (d) {
              return { uri: d.uri, name: d.name || d.uri };
            });
          console.log('[USB] Devices trouvés:', devices.length);
          resolve(devices);
        },
        onFailure: function (err) {
          console.warn('[USB] Erreur getDeviceList:', err);
          resolve([]);
        },
      });
    } catch (e) {
      console.warn('[USB] Exception luna:', e);
      resolve([]);
    }
  });
}

// ── Lecture de fichier ───────────────────────────────────────────────────────

/**
 * Lit le contenu d'un fichier local via XMLHttpRequest.
 * Fonctionne avec file:// sur webOS pour les apps en mode dev.
 * @param {string} filePath — chemin absolu (ex: /tmp/usb/sda1/playlist.m3u)
 * @returns {Promise<string>}
 */
export function readFileContent(filePath) {
  return new Promise(function (resolve, reject) {
    var url = filePath.startsWith('file://') ? filePath : 'file://' + filePath;
    var xhr = new XMLHttpRequest();
    xhr.open('GET', url, true);
    xhr.responseType = 'text';
    xhr.timeout = 30000;

    xhr.onload = function () {
      if (xhr.status === 0 || xhr.status === 200) {
        resolve(xhr.responseText || '');
      } else {
        reject(new Error('Impossible de lire le fichier (HTTP ' + xhr.status + ')'));
      }
    };
    xhr.onerror = function () {
      reject(new Error('Erreur de lecture du fichier : ' + filePath));
    };
    xhr.ontimeout = function () {
      reject(new Error('Timeout de lecture du fichier'));
    };

    xhr.send();
  });
}

// ── Parsing M3U ──────────────────────────────────────────────────────────────

/**
 * Parse le contenu d'un fichier M3U en liste de streams.
 *
 * Format attendu :
 *   #EXTM3U
 *   #EXTINF:-1 tvg-name="Nom" tvg-logo="url" group-title="Catégorie",Titre
 *   http://url-du-flux
 *
 * @param {string} content — contenu brut du fichier M3U
 * @returns {{ movies: Array, series: Array, categories: Array }}
 */
export function parseM3u(content) {
  var lines = content.split(/\r?\n/);
  var entries = [];
  var categories = new Set();
  var currentInfo = null;

  for (var i = 0; i < lines.length; i++) {
    var line = lines[i].trim();

    if (line.startsWith('#EXTINF:')) {
      currentInfo = parseExtInf(line);
    } else if (line && !line.startsWith('#') && currentInfo) {
      currentInfo.url = line;
      if (currentInfo.group) categories.add(currentInfo.group);
      entries.push(currentInfo);
      currentInfo = null;
    }
  }

  // Séparer films et séries par détection dans l'URL
  var movies = [];
  var series = [];

  for (var j = 0; j < entries.length; j++) {
    var entry = entries[j];
    var url = (entry.url || '').toLowerCase();
    var type = 'movie';

    if (url.indexOf('/series/') !== -1) {
      type = 'series';
    }

    if (type === 'series') {
      series.push({
        series_id: 'm3u_s_' + j,
        name: entry.name,
        cover: entry.logo,
        category_id: entry.group,
        category_name: entry.group,
        rating: 0,
        _m3u_url: entry.url,
        _m3u_source: true,
      });
    } else {
      // Extraire l'extension du fichier depuis l'URL
      var ext = 'mkv';
      var extMatch = entry.url.match(/\.(\w{2,4})(?:\?|$)/);
      if (extMatch) ext = extMatch[1];

      movies.push({
        stream_id: 'm3u_m_' + j,
        name: entry.name,
        stream_icon: entry.logo,
        category_id: entry.group,
        category_name: entry.group,
        container_extension: ext,
        rating: 0,
        _m3u_url: entry.url,
        _m3u_source: true,
      });
    }
  }

  return {
    movies: movies,
    series: series,
    categories: Array.from(categories).sort().map(function (name, idx) {
      return { category_id: 'm3u_cat_' + idx, category_name: name };
    }),
    totalEntries: entries.length,
  };
}

/**
 * Parse une ligne #EXTINF.
 * @param {string} line
 * @returns {{ name, group, logo }}
 */
function parseExtInf(line) {
  var name = '';
  var group = '';
  var logo = '';

  // Extraire tvg-name="..."
  var nameMatch = line.match(/tvg-name="([^"]*)"/);
  if (nameMatch) name = nameMatch[1];

  // Extraire group-title="..."
  var groupMatch = line.match(/group-title="([^"]*)"/);
  if (groupMatch) group = groupMatch[1];

  // Extraire tvg-logo="..."
  var logoMatch = line.match(/tvg-logo="([^"]*)"/);
  if (logoMatch) logo = logoMatch[1];

  // Fallback : nom après la dernière virgule
  if (!name) {
    var commaIdx = line.lastIndexOf(',');
    if (commaIdx !== -1) name = line.substring(commaIdx + 1).trim();
  }

  return { name: name, group: group, logo: logo, url: '' };
}

// ── Chemins USB courants ─────────────────────────────────────────────────────

/**
 * Chemins de montage USB courants sur webOS TV.
 * Utilisés en fallback si luna n'est pas disponible.
 */
export var USB_PATHS = [
  '/tmp/usb/sda/sda1',
  '/tmp/usb/sda/sda2',
  '/tmp/usb/sdb/sdb1',
  '/tmp/usb/sdb/sdb2',
  '/media/USB_Storage',
];
