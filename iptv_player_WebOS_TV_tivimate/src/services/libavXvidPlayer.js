/**
 * src/services/libavXvidPlayer.js
 *
 * Lecteur MPEG-4 Part 2 (XVID/DivX) pour webOS 6.
 * Utilise libav.js decoder-mpeg4 (WASM) + yuv-canvas (WebGL).
 *
 * Conteneurs supportés : AVI, MKV
 *
 * Pipeline :
 *   fetch(url) → parseur AVI/MKV → packets bruts
 *     → libav.js decoder-mpeg4 → frames YUV420P
 *       → yuv-canvas WebGL → canvas visible
 *
 * Pas de SharedArrayBuffer, pas de Worker (noworker: true).
 * Compatible Chromium 79 (webOS 6).
 */

import YUVCanvas from 'yuv-canvas';
import YUVBuffer from 'yuv-buffer';

// ── Constantes ────────────────────────────────────────────────────────────────

var LIBAV_BASE    = './libav';
var LIBAV_VERSION = '6.7.7.1.1';
var LIBAV_VARIANT = 'decoder-mpeg4';

var EBML_SEGMENT  = 0x18538067;
var EBML_TRACKS   = 0x1654AE6B;
var EBML_TRACK_ENTRY   = 0xAE;
var EBML_TRACK_TYPE    = 0x83;
var EBML_CODEC_ID      = 0x86;
var EBML_CODEC_PRIVATE = 0x63A2;
var EBML_PIXEL_WIDTH   = 0xB0;
var EBML_PIXEL_HEIGHT  = 0xBA;
var EBML_CLUSTER       = 0x1F43B675;
var EBML_TIMECODE      = 0xE7;
var EBML_SIMPLE_BLOCK  = 0xA3;
var EBML_BLOCK_GROUP   = 0xA0;
var EBML_BLOCK         = 0xA1;
var EBML_DEFAULT_DUR   = 0x23E383;

// ── Helpers binaires ──────────────────────────────────────────────────────────

function readFourCC(buf, off) {
  return String.fromCharCode(buf[off], buf[off+1], buf[off+2], buf[off+3]);
}
function readU32LE(buf, off) {
  return (buf[off] | (buf[off+1]<<8) | (buf[off+2]<<16) | (buf[off+3]<<24)) >>> 0;
}
function readU16LE(buf, off) {
  return (buf[off] | (buf[off+1]<<8)) >>> 0;
}

// EBML
function readVint(buf, offset) {
  var b = buf[offset];
  if (b === 0) return { value: 0, length: 8 };
  var extra = 0, mask = 0x80;
  while ((b & mask) === 0) { extra++; mask >>= 1; }
  var value = b & (mask - 1);
  for (var i = 1; i <= extra; i++) value = value * 256 + buf[offset + i];
  return { value: value, length: extra + 1 };
}
function readUintBE(buf, off, len) {
  var v = 0;
  for (var i = 0; i < len; i++) v = v * 256 + buf[off + i];
  return v;
}
function readElement(buf, offset) {
  if (offset >= buf.length) return null;
  var b = buf[offset];
  if (b === 0) return null;
  var idBytes = 1, mask = 0x80;
  while ((b & mask) === 0) { idBytes++; mask >>= 1; }
  if (offset + idBytes > buf.length) return null;
  var id = 0;
  for (var i = 0; i < idBytes; i++) id = (id << 8) | buf[offset + i];
  var szVint = readVint(buf, offset + idBytes);
  var headerSize = idBytes + szVint.length;
  var unknownSize = (szVint.value === Math.pow(2, 7 * szVint.length) - 1);
  return {
    id: id,
    dataOffset: offset + headerSize,
    dataSize: unknownSize ? -1 : szVint.value,
    totalSize: unknownSize ? headerSize : headerSize + szVint.value,
    headerSize: headerSize,
  };
}

// ── Chargement libav.js ───────────────────────────────────────────────────────

var _libavLoadPromise = null;
var _libavInstance    = null;

function loadLibAV() {
  if (_libavInstance) return Promise.resolve(_libavInstance);
  if (_libavLoadPromise) return _libavLoadPromise;

  _libavLoadPromise = new Promise(function(resolve, reject) {
    // S'il est déjà chargé (tag script existant)
    if (window.LibAV && typeof window.LibAV.LibAV === 'function') {
      _makeInstance(resolve, reject);
      return;
    }

    window.LibAV = window.LibAV || {};
    window.LibAV.base = LIBAV_BASE;

    // vite-plugin-node-polyfills expose `process` globalement, ce qui fait
    // croire à libav.js qu'il est en Node.js → module.exports crash.
    // On masque process le temps du chargement du script.
    var _savedProcess = window.process;
    try { Object.defineProperty(window, 'process', { value: undefined, configurable: true }); } catch(e) { window.process = undefined; }

    var s = document.createElement('script');
    s.src = LIBAV_BASE + '/libav-' + LIBAV_VERSION + '-' + LIBAV_VARIANT + '.js';
    s.onload = function() {
      try { Object.defineProperty(window, 'process', { value: _savedProcess, configurable: true }); } catch(e) { window.process = _savedProcess; }
      _makeInstance(resolve, reject);
    };
    s.onerror = function() {
      try { Object.defineProperty(window, 'process', { value: _savedProcess, configurable: true }); } catch(e) { window.process = _savedProcess; }
      reject(new Error('Impossible de charger libav.js'));
    };
    document.head.appendChild(s);
  });

  return _libavLoadPromise;
}

function _makeInstance(resolve, reject) {
  window.LibAV.LibAV({ noworker: true, base: LIBAV_BASE })
    .then(function(libav) {
      _libavInstance = libav;
      resolve(libav);
    })
    .catch(reject);
}

// ── Classe principale ─────────────────────────────────────────────────────────

export default function LibavXvidPlayer(canvas) {
  this._canvas      = canvas;
  this._yuvCanvas   = null;
  this._libav       = null;
  this._codecCtx    = null;  // c
  this._pktPtr      = null;  // pkt
  this._framePtr    = null;  // frame
  this._abortCtrl   = null;
  this._destroyed   = false;
  this._cbs         = {};
  this._frameQueue  = [];    // {data, layout, width, height, ptsMs} en attente d'affichage
  this._rafId       = null;
  this._playStartMs = null;  // performance.now() quand la lecture a démarré
  this._firstPtsMs  = null;  // PTS du premier frame en ms
  this._fps         = 25;
  this._paused      = false;
  this._seekTo      = 0;
}

LibavXvidPlayer.prototype.load = function(url, seekTo, cbs) {
  this._cbs    = cbs || {};
  this._seekTo = seekTo || 0;
  this.destroy();
  this._destroyed = false;
  this._frameQueue = [];
  this._playStartMs = null;
  this._firstPtsMs  = null;

  console.warn('[XVID] load url=', url, 'seekTo=', seekTo);

  // Attacher yuv-canvas sur le canvas fourni
  try {
    this._yuvCanvas = YUVCanvas.attach(this._canvas);
    console.warn('[XVID] yuv-canvas attaché');
  } catch (e) {
    console.warn('[XVID] yuv-canvas erreur:', e.message);
    if (this._cbs.onError) this._cbs.onError('yuv-canvas: ' + e.message);
    return;
  }

  var self = this;
  loadLibAV()
    .then(function(libav) {
      if (self._destroyed) return;
      self._libav = libav;
      console.warn('[XVID] libav.js chargé');
      self._fetchAndParse(url);
    })
    .catch(function(err) {
      if (self._destroyed) return;
      console.warn('[XVID] libav.js échec chargement:', err.message);
      if (self._cbs.onError) self._cbs.onError(err.message);
    });
};

LibavXvidPlayer.prototype.destroy = function() {
  this._destroyed = true;
  if (this._rafId) { cancelAnimationFrame(this._rafId); this._rafId = null; }
  if (this._abortCtrl) { this._abortCtrl.abort(); this._abortCtrl = null; }
  var self = this;
  if (this._libav && this._codecCtx) {
    this._libav.ff_free_decoder(this._codecCtx, this._pktPtr, this._framePtr)
      .catch(function() {});
    self._codecCtx = null;
    self._pktPtr   = null;
    self._framePtr = null;
  }
};

// ── Fetch + détection format ──────────────────────────────────────────────────

LibavXvidPlayer.prototype._fetchAndParse = function(url) {
  var self = this;
  this._abortCtrl = new AbortController();

  fetch(url, { signal: this._abortCtrl.signal })
    .then(function(resp) {
      if (self._destroyed) return;
      if (!resp.ok && resp.status !== 206) {
        if (self._cbs.onError) self._cbs.onError('HTTP ' + resp.status);
        return;
      }
      self._readStream(resp.body);
    })
    .catch(function(err) {
      if (self._destroyed) return;
      if (self._cbs.onError) self._cbs.onError(err.message);
    });
};

LibavXvidPlayer.prototype._readStream = function(body) {
  var self = this;
  var reader = body.getReader();
  var buf = new Uint8Array(0);
  var headerDone = false;
  var formatInfo = null; // { format, videoStreamIdx, width, height, fps, extradata, moviOffset }

  function appendChunk(chunk) {
    var tmp = new Uint8Array(buf.length + chunk.length);
    tmp.set(buf);
    tmp.set(chunk, buf.length);
    buf = tmp;
  }

  function readMore() {
    return reader.read().then(function(r) {
      if (self._destroyed) return;
      if (r.value) appendChunk(r.value);
      return r.done;
    });
  }

  // Accumuler suffisamment pour parser le header (256 KB)
  function fillToAtLeast(n) {
    if (buf.length >= n) return Promise.resolve();
    return readMore().then(function(done) {
      if (done || buf.length >= n) return;
      return fillToAtLeast(n);
    });
  }

  fillToAtLeast(256 * 1024)
    .then(function() {
      if (self._destroyed) return;
      if (buf.length < 12) { _err('Fichier trop court'); return; }

      // Détection format
      var isAVI = buf[0]===0x52 && buf[1]===0x49 && buf[2]===0x46 && buf[3]===0x46 &&
                  buf[8]===0x41 && buf[9]===0x56 && buf[10]===0x49 && buf[11]===0x20;
      var isMKV = buf[0]===0x1A && buf[1]===0x45 && buf[2]===0xDF && buf[3]===0xA3;

      if (isAVI) {
        console.warn('[XVID] format: AVI');
        formatInfo = self._parseAviHeader(buf);
      } else if (isMKV) {
        console.warn('[XVID] format: MKV');
        formatInfo = self._parseMkvHeader(buf);
      } else {
        _err('Format non reconnu');
        return;
      }

      if (!formatInfo) { _err('Header non parsable'); return; }
      if (!formatInfo.isMpeg4) {
        console.warn('[XVID] codec non supporté par ce décodeur:', formatInfo.codec);
        if (self._cbs.onUnsupported) self._cbs.onUnsupported(formatInfo.codec || 'codec inconnu');
        return;
      }

      console.warn('[XVID] codec: MPEG-4 Part 2, width=', formatInfo.width,
        'height=', formatInfo.height, 'fps=', formatInfo.fps,
        'extradata len=', formatInfo.extradata ? formatInfo.extradata.length : 0);

      self._fps = formatInfo.fps || 25;
      self._startDecoder(formatInfo, buf, reader);
    })
    .catch(function(err) {
      if (self._destroyed) return;
      _err(err.message);
    });

  function _err(msg) {
    console.warn('[XVID] erreur header:', msg);
    if (self._cbs.onError) self._cbs.onError(msg);
  }
};

// ── Parseur AVI ───────────────────────────────────────────────────────────────

LibavXvidPlayer.prototype._parseAviHeader = function(buf) {
  // Chercher LIST 'hdrl' dans les 256 premiers KB
  var offset = 12; // après RIFF header
  var videoStreamIdx = -1;
  var width = 0, height = 0, fps = 25;
  var codec = null;
  var extradata = null;
  var moviOffset = -1;

  while (offset + 8 <= buf.length) {
    var fourcc = readFourCC(buf, offset);
    var size   = readU32LE(buf, offset + 4);
    var dataOff = offset + 8;

    if (fourcc === 'LIST') {
      var listType = readFourCC(buf, dataOff);
      if (listType === 'hdrl') {
        // Parser hdrl
        var r = this._parseAviHdrl(buf, dataOff + 4, dataOff + size);
        if (r) {
          width  = r.width;
          height = r.height;
          fps    = r.fps;
          codec  = r.codec;
          extradata = r.extradata;
          videoStreamIdx = 0;
        }
      } else if (listType === 'movi') {
        moviOffset = dataOff + 4; // début des chunks movi
      }
    }

    offset += 8 + size + (size & 1);
    if (offset > 512 * 1024) break; // ne pas dépasser 512 KB pour la recherche
  }

  if (moviOffset === -1 && buf.length >= 256 * 1024) {
    // Chercher 'movi' manuellement
    for (var i = 0; i < buf.length - 8; i++) {
      if (buf[i]===0x6D && buf[i+1]===0x6F && buf[i+2]===0x76 && buf[i+3]===0x69) {
        moviOffset = i + 4;
        break;
      }
    }
  }

  if (!codec) return null;

  var mpeg4Codecs = ['XVID', 'xvid', 'DIVX', 'divx', 'DX50', 'dx50',
                     'DIV3', 'div3', 'DIV4', 'div4', 'DIV5', 'div5',
                     'MP4V', 'mp4v', 'FMP4', 'fmp4', 'RMP4', 'rmp4'];
  var isMpeg4 = mpeg4Codecs.indexOf(codec.trim()) !== -1;

  return {
    format: 'avi',
    videoStreamIdx: videoStreamIdx,
    width: width,
    height: height,
    fps: fps,
    codec: codec,
    extradata: extradata,
    isMpeg4: isMpeg4,
    moviOffset: moviOffset,
  };
};

LibavXvidPlayer.prototype._parseAviHdrl = function(buf, start, end) {
  var offset = start;
  var width = 0, height = 0, fps = 25, codec = null, extradata = null;
  var inVideoStream = false, streamIdx = -1;

  while (offset + 8 <= end && offset + 8 <= buf.length) {
    var fourcc = readFourCC(buf, offset);
    var size   = readU32LE(buf, offset + 4);
    var dataOff = offset + 8;

    if (fourcc === 'LIST') {
      var listType = readFourCC(buf, dataOff);
      if (listType === 'strl') {
        // Nouveau stream
        streamIdx++;
        var strlResult = this._parseAviStrl(buf, dataOff + 4, dataOff + size);
        if (strlResult && strlResult.type === 'vids') {
          width  = strlResult.width;
          height = strlResult.height;
          fps    = strlResult.fps;
          codec  = strlResult.codec;
          extradata = strlResult.extradata;
          inVideoStream = true;
        }
      }
    }

    var chunkSize = 8 + size + (size & 1);
    offset += chunkSize;
  }

  if (!codec) return null;
  return { width: width, height: height, fps: fps, codec: codec, extradata: extradata };
};

LibavXvidPlayer.prototype._parseAviStrl = function(buf, start, end) {
  var offset = start;
  var type = null, codec = null, fps = 25, width = 0, height = 0, extradata = null;

  while (offset + 8 <= end && offset + 8 <= buf.length) {
    var fourcc = readFourCC(buf, offset);
    var size   = readU32LE(buf, offset + 4);
    var dataOff = offset + 8;

    if (fourcc === 'strh' && size >= 48) {
      type  = readFourCC(buf, dataOff);      // 'vids' ou 'auds'
      codec = readFourCC(buf, dataOff + 4);  // handler (codec)
      var scale = readU32LE(buf, dataOff + 20);
      var rate  = readU32LE(buf, dataOff + 24);
      if (scale > 0 && rate > 0) fps = rate / scale;
    }
    if (fourcc === 'strf' && type === 'vids' && size >= 40) {
      // BITMAPINFOHEADER
      // biSize(4) biWidth(4) biHeight(4) biPlanes(2) biBitCount(2)
      // biCompression(4) biSizeImage(4) ...
      width  = readU32LE(buf, dataOff + 4);
      height = readU32LE(buf, dataOff + 8);
      // codec fourcc depuis biCompression
      var compFCC = readFourCC(buf, dataOff + 16);
      if (!codec || codec === '\0\0\0\0') codec = compFCC;
      // Extradata : octets après BITMAPINFOHEADER (40 octets)
      var biSize = readU32LE(buf, dataOff);
      if (size > biSize && biSize >= 40) {
        extradata = buf.slice(dataOff + biSize, dataOff + size);
        console.warn('[XVID] extradata:', extradata.length, 'octets');
      }
    }

    offset += 8 + size + (size & 1);
  }

  if (!type) return null;
  return { type: type, codec: codec, fps: fps, width: width, height: height, extradata: extradata };
};

// ── Parseur MKV (minimal pour V_MPEG4/ISO/ASP) ────────────────────────────────

LibavXvidPlayer.prototype._parseMkvHeader = function(buf) {
  var end = Math.min(buf.length, 512 * 1024);

  // 1. Lire et sauter l'entête EBML (premier élément, id=0x1A45DFA3)
  var offset = 0;
  var ebmlEl = readElement(buf, offset);
  if (!ebmlEl) return null;
  offset = (ebmlEl.dataSize >= 0) ? ebmlEl.totalSize : (ebmlEl.headerSize + 64);

  // 2. Trouver le Segment
  var segEl = readElement(buf, offset);
  if (!segEl || segEl.id !== EBML_SEGMENT) return null;
  var segBodyStart = segEl.dataOffset;
  offset = segBodyStart;

  // 3. Scanner le corps du Segment pour SeekHead et Tracks
  var tracksOff = -1;

  while (offset + 4 <= end) {
    var el = readElement(buf, offset);
    if (!el) break;

    if (el.id === EBML_TRACKS) {
      tracksOff = el.dataOffset;
      break;
    }

    // SeekHead : utiliser les positions pour trouver Tracks directement
    if (el.id === 0x114D9B74 /* SeekHead */ && el.dataSize > 0) {
      var seekTracksPos = this._seekHeadTracksPos(buf, el.dataOffset, el.dataOffset + el.dataSize, segBodyStart);
      if (seekTracksPos >= 0 && seekTracksPos + 4 <= buf.length) {
        var tEl = readElement(buf, seekTracksPos);
        if (tEl && tEl.id === EBML_TRACKS) {
          tracksOff = tEl.dataOffset;
          break;
        }
      }
    }

    if (el.id === EBML_CLUSTER) break;

    // Éléments de taille connue : sauter entièrement
    // Éléments de taille inconnue (SeekHead vide, Segment void…) : avancer d'un header
    if (el.dataSize < 0) {
      offset += el.headerSize;
    } else {
      offset += el.totalSize;
    }
  }

  if (tracksOff === -1) return null;

  var track = this._parseMkvTracks(buf, tracksOff, end);
  if (!track) return null;

  return {
    format:    'mkv',
    videoStreamIdx: track.trackNumber,
    width:     track.width,
    height:    track.height,
    fps:       track.fps,
    codec:     track.codecId,
    extradata: track.extradata,
    isMpeg4:   track.codecId === 'V_MPEG4/ISO/ASP' || track.codecId === 'V_MPEG4/ISO/SP',
  };
};

// Parcourt un SeekHead et retourne l'offset absolu de l'élément Tracks, ou -1
LibavXvidPlayer.prototype._seekHeadTracksPos = function(buf, start, end, segBodyStart) {
  var offset = start;
  while (offset + 4 <= end && offset + 4 <= buf.length) {
    var el = readElement(buf, offset);
    if (!el) break;
    if (el.id === 0x4DBB /* Seek */ && el.dataSize > 0) {
      var seekId = -1, seekPos = -1;
      var soff = el.dataOffset, send = el.dataOffset + el.dataSize;
      while (soff + 2 <= send && soff + 2 <= buf.length) {
        var se = readElement(buf, soff);
        if (!se) break;
        if (se.id === 0x53AB /* SeekID */ && se.dataSize >= 1 && se.dataSize <= 4)
          seekId = readUintBE(buf, se.dataOffset, se.dataSize);
        if (se.id === 0x53AC /* SeekPosition */ && se.dataSize > 0)
          seekPos = readUintBE(buf, se.dataOffset, se.dataSize);
        soff += (se.dataSize < 0) ? se.headerSize : se.totalSize;
      }
      if (seekId === EBML_TRACKS && seekPos >= 0) {
        return segBodyStart + seekPos;
      }
    }
    offset += (el.dataSize < 0) ? el.headerSize : el.totalSize;
  }
  return -1;
};

LibavXvidPlayer.prototype._parseMkvTracks = function(buf, start, end) {
  var offset = start;
  while (offset + 4 <= end && offset + 4 <= buf.length) {
    var el = readElement(buf, offset);
    if (!el) break;
    if (el.id === EBML_TRACK_ENTRY) {
      var te = this._parseMkvTrackEntry(buf, el.dataOffset, el.dataOffset + el.dataSize);
      if (te && te.type === 1 /* video */) {
        return te;
      }
    }
    if (el.dataSize < 0) { offset += el.headerSize; }
    else { offset += el.totalSize; }
  }
  return null;
};

LibavXvidPlayer.prototype._parseMkvTrackEntry = function(buf, start, end) {
  var offset = start;
  var type = -1, trackNumber = 1, codecId = '', extradata = null;
  var width = 0, height = 0, defaultDur = 0, fps = 25;

  while (offset + 2 <= end && offset + 2 <= buf.length) {
    var el = readElement(buf, offset);
    if (!el) break;
    var d = el.dataOffset, sz = el.dataSize;

    if (el.id === EBML_TRACK_TYPE && sz > 0)    type = readUintBE(buf, d, sz);
    if (el.id === 0xD7 && sz > 0)               trackNumber = readUintBE(buf, d, sz);
    if (el.id === EBML_CODEC_ID)                codecId = readFourCC(buf, d) + String.fromCharCode(...buf.slice(d+4, d+sz));
    if (el.id === EBML_CODEC_PRIVATE && sz > 0) extradata = buf.slice(d, d + sz);
    if (el.id === EBML_DEFAULT_DUR && sz > 0) {
      defaultDur = readUintBE(buf, d, sz); // ns
      if (defaultDur > 0) fps = 1e9 / defaultDur;
    }
    if (el.id === 0xE0 /* Video */) {
      // Sous-éléments
      var voff = d;
      while (voff + 2 <= d + sz && voff + 2 <= buf.length) {
        var ve = readElement(buf, voff);
        if (!ve) break;
        if (ve.id === EBML_PIXEL_WIDTH  && ve.dataSize > 0) width  = readUintBE(buf, ve.dataOffset, ve.dataSize);
        if (ve.id === EBML_PIXEL_HEIGHT && ve.dataSize > 0) height = readUintBE(buf, ve.dataOffset, ve.dataSize);
        if (ve.dataSize < 0) voff += ve.headerSize;
        else voff += ve.totalSize;
      }
    }

    if (sz < 0) offset += el.headerSize;
    else offset += el.totalSize;
  }

  if (type !== 1) return null;
  // Normaliser codec ID (peut avoir des octets nuls)
  codecId = codecId.replace(/\0/g, '');

  return { type: type, trackNumber: trackNumber, codecId: codecId,
           extradata: extradata, width: width, height: height, fps: fps };
};

// ── Décodeur libav.js ─────────────────────────────────────────────────────────

LibavXvidPlayer.prototype._startDecoder = function(info, initialBuf, reader) {
  var self = this;
  var libav = this._libav;

  // CodecParameters JavaScript → ff_init_decoder
  var codecpar = {
    codec_type: 0,   // AVMEDIA_TYPE_VIDEO
    codec_id:   12,  // AV_CODEC_ID_MPEG4
    width:      info.width,
    height:     info.height,
  };
  if (info.extradata && info.extradata.length > 0) {
    codecpar.extradata = info.extradata;
    console.warn('[XVID] extradata transmis au décodeur:', info.extradata.length, 'B');
  }

  libav.ff_init_decoder('mpeg4', { codecpar: codecpar })
    .then(function(result) {
      if (self._destroyed) return;
      // result = [codec, c, pkt, frame]
      self._codecCtx  = result[1];
      self._pktPtr    = result[2];
      self._framePtr  = result[3];

      console.warn('[XVID] décodeur initialisé');

      if (self._cbs.onLoaded) self._cbs.onLoaded();
      self._startRenderLoop();

      // Démarrer le streaming des packets
      if (info.format === 'avi') {
        self._streamAviPackets(info, initialBuf, reader);
      } else {
        self._streamMkvPackets(info, initialBuf, reader);
      }
    })
    .catch(function(err) {
      if (self._destroyed) return;
      console.warn('[XVID] ff_init_decoder erreur:', err);
      if (self._cbs.onError) self._cbs.onError('Décodeur MPEG-4 : ' + (err.message || err));
    });
};

// ── Streaming AVI ─────────────────────────────────────────────────────────────

LibavXvidPlayer.prototype._streamAviPackets = function(info, initialBuf, reader) {
  var self = this;
  var buf = initialBuf;
  var moviStart = info.moviOffset; // offset dans buf où commence le LIST movi
  var offset = moviStart || 12;
  var frameNum = 0;
  var frameDurMs = 1000 / (info.fps || 25);
  var done = false;

  // Attendu : '00dc' ou '00db' pour le flux vidéo index 0
  function readMore() {
    return reader.read().then(function(r) {
      if (r.value) {
        var tmp = new Uint8Array(buf.length + r.value.length);
        tmp.set(buf);
        tmp.set(r.value, buf.length);
        buf = tmp;
      }
      return r.done;
    });
  }

  function processNext() {
    if (self._destroyed) return;

    // Assurer 512 octets disponibles
    if (buf.length - offset < 512) {
      readMore().then(function(eof) {
        done = eof;
        if (!eof) processNext();
        else flushDecoder();
      });
      return;
    }

    if (offset + 8 > buf.length) {
      if (done) { flushDecoder(); return; }
      readMore().then(function(eof) { done = eof; processNext(); });
      return;
    }

    var fourcc = readFourCC(buf, offset);
    var size   = readU32LE(buf, offset + 4);
    var dataOff = offset + 8;
    var totalSize = 8 + size + (size & 1);

    // Sanity check taille
    if (size > 100 * 1024 * 1024) {
      // Chunk corrompu, avancer de 4 octets
      offset += 4;
      processNext();
      return;
    }

    // Chunk LIST : entrer dedans
    if (fourcc === 'LIST') {
      offset = dataOff + 4; // sauter le fourcc de type
      processNext();
      return;
    }

    // Ignorer idx1
    if (fourcc === 'idx1' || fourcc === 'JUNK' || fourcc === 'RIFF') {
      offset += totalSize;
      processNext();
      return;
    }

    // Chunk vidéo : '00dc', '00db', '01dc', '01db'
    var isVideo = /^[0-9a-f]{2}d[bc]$/i.test(fourcc);
    var isAudio = /^[0-9a-f]{2}w[bc]$/i.test(fourcc);

    if (!isVideo && !isAudio && size === 0) {
      offset += 8;
      processNext();
      return;
    }

    // Lire les données si pas encore disponibles
    if (buf.length < dataOff + size) {
      readMore().then(function(eof) { done = eof; processNext(); });
      return;
    }

    if (isVideo && size > 0) {
      var ptsMs = frameNum * frameDurMs;
      frameNum++;
      var pktData = buf.slice(dataOff, dataOff + size);
      // Libérer la mémoire en compactant buf
      var packet = { data: pktData, pts: ptsMs, dts: ptsMs, time_base_num: 1, time_base_den: 1000 };
      offset += totalSize;

      self._decodePacket(packet).then(function() {
        // Yield
        setTimeout(processNext, 0);
      });
      return;
    }

    // Ignorer audio + chunks non-vidéo
    offset += totalSize;
    processNext();
  }

  function flushDecoder() {
    console.warn('[XVID] AVI: streaming terminé, flush décodeur');
    self._libav.ff_decode_multi(self._codecCtx, self._pktPtr, self._framePtr, [],
      { fin: true, copyoutFrame: 'video_packed' })
      .then(function(frames) {
        for (var i = 0; i < frames.length; i++) self._enqueueFrame(frames[i]);
      })
      .catch(function() {});
  }

  processNext();
};

// ── Streaming MKV ─────────────────────────────────────────────────────────────

LibavXvidPlayer.prototype._streamMkvPackets = function(info, initialBuf, reader) {
  var self = this;
  var buf = initialBuf;
  var done = false;
  var clusterTimecode = 0;
  var frameNum = 0;
  var trackNum = info.videoStreamIdx || 1;
  var timescale = 1000000; // ns par tick (défaut MKV : 1ms)
  var tickMs = 1;

  function readMore() {
    return reader.read().then(function(r) {
      if (r.value) {
        var tmp = new Uint8Array(buf.length + r.value.length);
        tmp.set(buf);
        tmp.set(r.value, buf.length);
        buf = tmp;
      }
      return r.done;
    });
  }

  function processFromOffset(offset) {
    if (self._destroyed) return;

    if (buf.length - offset < 16) {
      if (done) return;
      readMore().then(function(eof) { done = eof; processFromOffset(offset); });
      return;
    }

    var el = readElement(buf, offset);
    if (!el) {
      readMore().then(function(eof) { done = eof; processFromOffset(offset); });
      return;
    }

    if (el.id === EBML_CLUSTER) {
      processCluster(el.dataOffset, el.dataOffset + (el.dataSize > 0 ? el.dataSize : 16 * 1024 * 1024));
      return;
    }

    // Entrer dans les containers (Segment, etc.) quelle que soit leur taille
    var EBML_SEGMENT_ID = 0x18538067;
    if (el.id === EBML_SEGMENT_ID) {
      offset += el.headerSize; // entrer dans le segment
    } else if (el.dataSize < 0) {
      offset += el.headerSize;
    } else {
      offset += el.totalSize;
    }
    processFromOffset(offset);
  }

  function processCluster(start, end) {
    var offset = start;

    function next() {
      if (self._destroyed) return;
      if (buf.length - offset < 8) {
        if (done) return;
        readMore().then(function(eof) { done = eof; next(); });
        return;
      }

      var el = readElement(buf, offset);
      if (!el) {
        readMore().then(function(eof) { done = eof; next(); });
        return;
      }

      // Fin du cluster
      if (el.id === EBML_CLUSTER) {
        processCluster(el.dataOffset, el.dataOffset + (el.dataSize > 0 ? el.dataSize : 16 * 1024 * 1024));
        return;
      }
      // Fin de segment
      if (el.id === 0x1F43B676 || el.id === EBML_TRACKS) return;

      if (el.id === EBML_TIMECODE && el.dataSize > 0) {
        clusterTimecode = readUintBE(buf, el.dataOffset, el.dataSize);
        offset += el.totalSize;
        next();
        return;
      }

      if (el.id === EBML_SIMPLE_BLOCK || el.id === EBML_BLOCK) {
        var needSize = el.dataOffset + el.dataSize;
        if (el.dataSize > 0 && buf.length < needSize) {
          readMore().then(function(eof) { done = eof; next(); });
          return;
        }
        if (el.dataSize > 0) {
          parseSimpleBlock(el.dataOffset, el.dataSize);
        }
        if (el.dataSize < 0) offset += el.headerSize;
        else offset += el.totalSize;
        next();
        return;
      }

      if (el.dataSize < 0) offset += el.headerSize;
      else offset += el.totalSize;
      next();
    }

    next();
  }

  function parseSimpleBlock(offset, size) {
    var trackVint = readVint(buf, offset);
    if (trackVint.value !== trackNum) return; // ignorer autres tracks
    var relTs = (buf[offset + trackVint.length] << 8) | buf[offset + trackVint.length + 1];
    // timecode relatif signé 16 bits
    if (relTs >= 0x8000) relTs -= 0x10000;
    var ptsMs = (clusterTimecode + relTs) * tickMs;
    var dataStart = offset + trackVint.length + 3; // +1 flags
    var dataSize  = size - trackVint.length - 3;

    if (dataSize <= 0 || dataStart + dataSize > buf.length) return;

    var pktData = buf.slice(dataStart, dataStart + dataSize);
    var packet = { data: pktData, pts: ptsMs, dts: ptsMs,
                   time_base_num: 1, time_base_den: 1000 };

    self._decodePacket(packet).catch(function() {});
    frameNum++;
  }

  processFromOffset(0);
};

// ── Décodage d'un packet ──────────────────────────────────────────────────────

LibavXvidPlayer.prototype._decodePacket = function(packet) {
  if (this._destroyed) return Promise.resolve();
  var self = this;

  return this._libav.ff_decode_multi(
    this._codecCtx, this._pktPtr, this._framePtr,
    [packet],
    { copyoutFrame: 'video_packed' }
  ).then(function(frames) {
    for (var i = 0; i < frames.length; i++) {
      self._enqueueFrame(frames[i]);
    }
  }).catch(function(err) {
    console.warn('[XVID] decode erreur:', err && err.message ? err.message : err);
  });
};

LibavXvidPlayer.prototype._enqueueFrame = function(frame) {
  if (this._destroyed) return;
  // ptsMs = pts * time_base_num / time_base_den * 1000
  var ptsMs = 0;
  if (frame.pts !== undefined && frame.time_base_num && frame.time_base_den) {
    ptsMs = frame.pts * frame.time_base_num / frame.time_base_den * 1000;
  } else if (frame.pts !== undefined) {
    ptsMs = frame.pts; // supposé déjà en ms (time_base = 1/1000)
  }
  this._frameQueue.push({
    data:   frame.data,
    layout: frame.layout,
    width:  frame.width,
    height: frame.height,
    ptsMs:  ptsMs,
  });
  // Limiter la queue à 60 frames max
  if (this._frameQueue.length > 60) this._frameQueue.shift();
};

// ── Boucle de rendu ───────────────────────────────────────────────────────────

LibavXvidPlayer.prototype._startRenderLoop = function() {
  var self = this;
  var frameDurMs = 1000 / this._fps;

  function loop(now) {
    if (self._destroyed) return;
    self._rafId = requestAnimationFrame(loop);

    if (self._frameQueue.length === 0) return;
    if (self._paused) return;

    var frame = self._frameQueue[0];

    // Initialiser l'horloge au premier frame
    if (self._playStartMs === null) {
      self._playStartMs = now;
      self._firstPtsMs  = frame.ptsMs;
    }

    // Temps écoulé depuis le début de lecture
    var elapsed = now - self._playStartMs;
    // Temps relatif de ce frame
    var frameRelTime = frame.ptsMs - self._firstPtsMs;

    // Afficher si son heure est venue
    if (elapsed >= frameRelTime) {
      self._frameQueue.shift();
      self._renderYUV(frame);
      if (self._cbs.onTimeUpdate) {
        self._cbs.onTimeUpdate(frame.ptsMs / 1000, 0);
      }
    }
  }

  this._rafId = requestAnimationFrame(loop);
};

LibavXvidPlayer.prototype._renderYUV = function(frame) {
  if (!this._yuvCanvas || !frame.data || !frame.width || !frame.height) return;

  try {
    var w = frame.width;
    var h = frame.height;
    var cw = w >> 1;
    var ch = h >> 1;

    var format = YUVBuffer.format({ width: w, height: h, chromaWidth: cw, chromaHeight: ch });
    var data = frame.data;

    // video_packed : Y puis U puis V consécutifs, sans layout explicite
    var yStr, uStr, vStr, yOff, uOff, vOff;
    if (frame.layout && frame.layout.length >= 3) {
      yOff = frame.layout[0].offset; yStr = frame.layout[0].stride;
      uOff = frame.layout[1].offset; uStr = frame.layout[1].stride;
      vOff = frame.layout[2].offset; vStr = frame.layout[2].stride;
    } else {
      yStr = w; uStr = cw; vStr = cw;
      yOff = 0; uOff = yStr * h; vOff = uOff + uStr * ch;
    }

    var buf = data.buffer ? data : new Uint8Array(data);
    var yPlane = YUVBuffer.lumaPlane(format,
      new Uint8Array(buf.buffer || buf, (buf.byteOffset || 0) + yOff, yStr * h), yStr);
    var uPlane = YUVBuffer.chromaPlane(format,
      new Uint8Array(buf.buffer || buf, (buf.byteOffset || 0) + uOff, uStr * ch), uStr);
    var vPlane = YUVBuffer.chromaPlane(format,
      new Uint8Array(buf.buffer || buf, (buf.byteOffset || 0) + vOff, vStr * ch), vStr);

    var yuvFrame = YUVBuffer.frame(format, yPlane, uPlane, vPlane);
    this._yuvCanvas.drawFrame(yuvFrame);
  } catch (e) {
    console.warn('[XVID] renderYUV erreur:', e.message);
  }
};

LibavXvidPlayer.prototype.pause = function() { this._paused = true; };
LibavXvidPlayer.prototype.resume = function() { this._paused = false; };
