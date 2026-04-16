/**
 * src/services/mkvMsePlayer.js
 *
 * Lecture MKV et AVI via fetch() + démuxage JavaScript + MSE.
 *
 * MKV : parser EBML minimal → H.264 (AVC) + AAC/MP3
 * AVI : parser RIFF minimal → H.264 (x264→AVI) + MP3/AAC
 *
 * Pipeline : fetch(url) → détection format → démuxeur → JMuxer (fMP4) → MediaSource → <video>
 *
 * Usage :
 *   const player = new MkvMsePlayer(videoElement);
 *   player.load(url, seekSeconds, callbacks);
 *   player.destroy();
 */

import JMuxer from 'jmuxer';

// ── Constantes EBML (MKV) ─────────────────────────────────────────────────────

var EBML_ID = {
  EBML:              0x1A45DFA3,
  Segment:           0x18538067,
  SeekHead:          0x114D9B74,
  Info:              0x1549A966,
  Tracks:            0x1654AE6B,
  TrackEntry:        0xAE,
  TrackNumber:       0xD7,
  TrackType:         0x83,
  CodecID:           0x86,
  Video:             0xE0,
  Audio:             0xE1,
  PixelWidth:        0xB0,
  PixelHeight:       0xBA,
  SamplingFrequency: 0xB5,
  Channels:          0x9F,
  CodecPrivate:      0x63A2,
  Cluster:           0x1F43B675,
  Timecode:          0xE7,
  SimpleBlock:       0xA3,
  BlockGroup:        0xA0,
  Block:             0xA1,
  Cues:              0x1C53BB6B,
};

var TRACK_TYPE_VIDEO = 1;
var TRACK_TYPE_AUDIO = 2;

// ── Constantes AVI/RIFF ───────────────────────────────────────────────────────

// FourCC H.264 connus dans AVI
var AVI_H264_FOURCCS = ['H264', 'h264', 'X264', 'x264', 'AVC1', 'avc1', 'VSSH', 'vssh', 'DAVC', 'davc'];

// Format tags audio RIFF
var WAVE_MP3 = [0x0050, 0x0055];          // MPEG Layer 3
var WAVE_AAC = [0x00FF, 0xA106, 0x1610]; // MPEG-4 AAC

// ── Helpers EBML ──────────────────────────────────────────────────────────────

function readVint(buf, offset) {
  var b = buf[offset];
  if (b === 0) return { value: 0, length: 8 };
  var extra = 0;
  var mask   = 0x80;
  while ((b & mask) === 0) { extra++; mask >>= 1; }
  var value = b & (mask - 1);
  for (var i = 1; i <= extra; i++) value = (value * 256) + buf[offset + i];
  return { value: value, length: extra + 1 };
}

function readUint(buf, offset, len) {
  var v = 0;
  for (var i = 0; i < len; i++) v = v * 256 + buf[offset + i];
  return v;
}

function readFloat(buf, offset, len) {
  var d = new DataView(buf.buffer || buf, buf.byteOffset + offset, len);
  return len === 4 ? d.getFloat32(0) : d.getFloat64(0);
}

function readString(buf, offset, len) {
  var s = '';
  for (var i = 0; i < len; i++) s += String.fromCharCode(buf[offset + i]);
  return s;
}

/**
 * Lit un élément EBML (id + size).
 * Bug corrigé : unknownSize utilise la formule canonique uniquement
 * (évite le faux positif pour les VINTs 1 octet comme CRC-32 0xBF).
 */
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
  var headerSize  = idBytes + szVint.length;
  // Taille inconnue = tous les bits de valeur du VINT à 1 (formule canonique)
  var unknownSize = (szVint.value === Math.pow(2, 7 * szVint.length) - 1);
  return {
    id:         id,
    dataOffset: offset + headerSize,
    dataSize:   unknownSize ? -1 : szVint.value,
    totalSize:  unknownSize ? headerSize : headerSize + szVint.value,
    headerSize: headerSize,
  };
}

// ── Helpers RIFF/AVI ──────────────────────────────────────────────────────────

function readFourCC(buf, offset) {
  return String.fromCharCode(buf[offset], buf[offset+1], buf[offset+2], buf[offset+3]);
}

function readU16LE(buf, offset) {
  return (buf[offset] | (buf[offset+1] << 8)) >>> 0;
}

function readU32LE(buf, offset) {
  return (buf[offset] | (buf[offset+1]<<8) | (buf[offset+2]<<16) | (buf[offset+3]<<24)) >>> 0;
}

/**
 * Lit un chunk RIFF : fourcc(4) + size(4 LE).
 * Les chunks RIFF sont alignés sur 2 octets.
 */
function readAviChunk(buf, offset) {
  if (offset + 8 > buf.length) return null;
  var fourcc = readFourCC(buf, offset);
  var size   = readU32LE(buf, offset + 4);
  return {
    fourcc:     fourcc,
    size:       size,
    dataOffset: offset + 8,
    totalSize:  8 + size + (size & 1),  // alignement 2 octets
  };
}

/** Indice de flux depuis un ID de chunk movi (ex. '00dc' → 0, '01wb' → 1). */
function aviChunkStream(fourcc) {
  var hi = parseInt(fourcc[0], 16);
  var lo = parseInt(fourcc[1], 16);
  if (isNaN(hi) || isNaN(lo)) return -1;
  return hi * 16 + lo;
}

/** Type de chunk movi : 'dc'=video, 'wb'=audio, 'db'=video non-compressé... */
function aviChunkType(fourcc) {
  return fourcc.slice(2);
}

// ── MkvMsePlayer ─────────────────────────────────────────────────────────────

export default function MkvMsePlayer(videoElement) {
  this._video      = videoElement;
  this._jmuxer     = null;
  this._abortCtrl  = null;
  this._destroyed  = false;
  this._cbs        = {};
  this._format     = null;   // 'mkv' | 'avi'
  this._videoTrack = null;
  this._audioTrack = null;
  this._hasVideo   = false;
  this._hasAudio   = false;
  // MKV specifics
  this._clusterTimecode = 0;
  this._timeScale  = 1000000;
  this._tickMs     = 1;
  this._spsppsSent = false;
  // AVI specifics
  this._aviVideoFrameCount = 0;
  // Common
  this._jmuxerReady   = false;
  this._pendingFrames = [];
  this._clusterConsumed = 0;
  this._moviConsumed    = 0;
}

MkvMsePlayer.prototype.load = function(url, seekTo, cbs) {
  this._cbs    = cbs || {};
  this._seekTo = seekTo || 0;
  this.destroy();
  this._destroyed = false;
  this._format     = null;
  this._videoTrack = null;
  this._audioTrack = null;
  this._hasVideo   = false;
  this._hasAudio   = false;
  this._clusterTimecode = 0;
  this._timeScale  = 1000000;
  this._tickMs     = 1;
  this._spsppsSent = false;
  this._aviVideoFrameCount = 0;
  this._jmuxerReady   = false;
  this._pendingFrames = [];
  this._clusterConsumed = 0;
  this._moviConsumed    = 0;
  console.warn('[MSE] load url=', url, 'seekTo=', seekTo);
  this._fetchAndParse(url);
};

MkvMsePlayer.prototype.destroy = function() {
  this._destroyed = true;
  if (this._abortCtrl) { this._abortCtrl.abort(); this._abortCtrl = null; }
  if (this._jmuxer)    { try { this._jmuxer.destroy(); } catch(e){} this._jmuxer = null; }
};

// ── Fetch ─────────────────────────────────────────────────────────────────────

MkvMsePlayer.prototype._fetchAndParse = function(url) {
  var self = this;
  this._abortCtrl = new AbortController();
  fetch(url, { signal: this._abortCtrl.signal, headers: { 'Range': 'bytes=0-' } })
    .then(function(resp) {
      if (self._destroyed) return;
      if (!resp.ok && resp.status !== 206) {
        console.warn('[MSE] HTTP', resp.status);
        if (self._cbs.onError) self._cbs.onError('HTTP ' + resp.status);
        return;
      }
      console.warn('[MSE] fetch OK status=', resp.status);
      self._readStream(resp.body);
    })
    .catch(function(err) {
      if (self._destroyed) return;
      console.warn('[MSE] fetch erreur:', err.message);
      if (self._cbs.onError) self._cbs.onError(err.message);
    });
};

// ── Streaming principal ───────────────────────────────────────────────────────

MkvMsePlayer.prototype._readStream = function(readableStream) {
  var self       = this;
  var reader     = readableStream.getReader();
  var accumulated = new Uint8Array(0);  // buffer pour la phase init
  var parseOffset = 0;                  // curseur dans accumulated (MKV)
  var dataBuf    = new Uint8Array(0);   // buffer pour la phase data
  var phase      = 'detect';            // 'detect' | 'init' | 'data'
  var firstChunk = true;

  function appendAcc(chunk) {
    var t = new Uint8Array(accumulated.length + chunk.length);
    t.set(accumulated); t.set(chunk, accumulated.length);
    accumulated = t;
  }

  function appendData(chunk) {
    var t = new Uint8Array(dataBuf.length + chunk.length);
    t.set(dataBuf); t.set(chunk, dataBuf.length);
    dataBuf = t;
  }

  function pump() {
    reader.read().then(function(result) {
      if (self._destroyed) return;
      if (result.done) {
        console.warn('[MSE] stream terminé');
        if (self._cbs.onEnded) self._cbs.onEnded();
        return;
      }

      var chunk = result.value;

      // ── Détection format ──────────────────────────────────────────────────
      if (firstChunk) {
        firstChunk = false;
        var hex = [];
        for (var hx = 0; hx < Math.min(16, chunk.length); hx++)
          hex.push(('0' + chunk[hx].toString(16)).slice(-2));
        console.warn('[MSE] premiers octets:', hex.join(' '));

        if (chunk.length >= 4 && chunk[0] === 0x1A && chunk[1] === 0x45 && chunk[2] === 0xDF && chunk[3] === 0xA3) {
          self._format = 'mkv';
        } else if (chunk.length >= 12 && chunk[0] === 0x52 && chunk[1] === 0x49 && chunk[2] === 0x46 && chunk[3] === 0x46 &&
                   chunk[8] === 0x41 && chunk[9] === 0x56 && chunk[10] === 0x49 && chunk[11] === 0x20) {
          self._format = 'avi';
        } else {
          console.warn('[MSE] format non reconnu');
          if (self._cbs.onUnsupported) self._cbs.onUnsupported('format not recognized');
          return;
        }
        console.warn('[MSE] format détecté:', self._format);
        phase = 'init';
      }

      // ── Phase init ────────────────────────────────────────────────────────
      if (phase === 'init') {
        appendAcc(chunk);
        var parsedInit = null;
        if (self._format === 'mkv') {
          parsedInit = self._parseInitSection(accumulated, parseOffset);
          if (parsedInit) {
            appendData(accumulated.slice(parsedInit.nextOffset));
            accumulated = new Uint8Array(0);
            phase = 'data';
            self._initJMuxerMkv();
          }
        } else if (self._format === 'avi') {
          parsedInit = self._parseAviInit(accumulated);
          if (parsedInit) {
            appendData(accumulated.slice(parsedInit.nextOffset));
            accumulated = new Uint8Array(0);
            phase = 'data';
            self._initJMuxerAvi();
          }
        }
      } else if (phase === 'data') {
        appendData(chunk);
      }

      // ── Phase data ────────────────────────────────────────────────────────
      if (phase === 'data') {
        if (self._format === 'mkv') {
          self._parseClusters(dataBuf);
          if (self._clusterConsumed > 0) {
            dataBuf = dataBuf.slice(self._clusterConsumed);
            self._clusterConsumed = 0;
          }
        } else if (self._format === 'avi') {
          self._parseAviMovi(dataBuf);
          if (self._moviConsumed > 0) {
            dataBuf = dataBuf.slice(self._moviConsumed);
            self._moviConsumed = 0;
          }
        }
      }

      pump();
    }).catch(function(err) {
      if (self._destroyed) return;
      console.warn('[MSE] stream:', err.message);
    });
  }

  pump();
};

// ═════════════════════════════════════════════════════════════════════════════
// MKV — Parse section init
// ═════════════════════════════════════════════════════════════════════════════

MkvMsePlayer.prototype._parseInitSection = function(buf, startOffset) {
  var offset = startOffset;
  while (offset < buf.length - 8) {
    var el = readElement(buf, offset);
    if (!el) break;
    switch (el.id) {
      case EBML_ID.EBML:
        if (el.dataSize < 0 || offset + el.totalSize > buf.length) return null;
        offset += el.totalSize;
        break;
      case EBML_ID.Segment:
        offset += el.headerSize;
        break;
      case EBML_ID.SeekHead:
      case EBML_ID.Cues:
        if (el.dataSize < 0 || offset + el.totalSize > buf.length) return null;
        offset += el.totalSize;
        break;
      case EBML_ID.Info:
        if (el.dataSize < 0 || offset + el.totalSize > buf.length) return null;
        this._parseInfo(buf, el.dataOffset, el.dataSize);
        offset += el.totalSize;
        break;
      case EBML_ID.Tracks:
        if (el.dataSize < 0 || offset + el.totalSize > buf.length) return null;
        this._parseTracks(buf, el.dataOffset, el.dataSize);
        offset += el.totalSize;
        if (this._videoTrack || this._audioTrack) return { nextOffset: offset };
        break;
      case EBML_ID.Cluster:
        return { nextOffset: offset };
      default:
        if (el.dataSize < 0 || offset + el.totalSize > buf.length) return null;
        offset += el.totalSize;
    }
  }
  return null;
};

MkvMsePlayer.prototype._parseInfo = function(buf, offset, size) {
  var end = offset + size;
  while (offset < end - 4) {
    var el = readElement(buf, offset);
    if (!el || el.dataSize < 0) break;
    if (el.id === 0x2AD7B1) {
      this._timeScale = readUint(buf, el.dataOffset, el.dataSize);
      this._tickMs    = this._timeScale / 1000000;
      console.warn('[MSE] TimestampScale=', this._timeScale, 'tickMs=', this._tickMs);
    }
    offset += el.totalSize;
  }
};

MkvMsePlayer.prototype._parseTracks = function(buf, offset, size) {
  var end = offset + size;
  while (offset < end - 4) {
    var el = readElement(buf, offset);
    if (!el || el.dataSize < 0) break;
    if (el.id === EBML_ID.TrackEntry) this._parseTrackEntry(buf, el.dataOffset, el.dataSize);
    offset += el.totalSize;
  }
  console.warn('[MSE] MKV video track:', JSON.stringify(this._videoTrack));
  console.warn('[MSE] MKV audio track:', JSON.stringify(this._audioTrack));
};

MkvMsePlayer.prototype._parseTrackEntry = function(buf, offset, size) {
  var end = offset + size;
  var trackNum = 0, trackType = 0, codecId = '', codecPrivate = null;
  var width = 0, height = 0, sampleRate = 44100, channels = 2;
  while (offset < end - 2) {
    var el = readElement(buf, offset);
    if (!el || el.dataSize < 0) break;
    switch (el.id) {
      case EBML_ID.TrackNumber:  trackNum  = readUint(buf, el.dataOffset, el.dataSize);   break;
      case EBML_ID.TrackType:    trackType = readUint(buf, el.dataOffset, el.dataSize);   break;
      case EBML_ID.CodecID:      codecId   = readString(buf, el.dataOffset, el.dataSize).replace(/\x00/g, ''); break;
      case EBML_ID.CodecPrivate: codecPrivate = buf.slice(el.dataOffset, el.dataOffset + el.dataSize); break;
      case EBML_ID.Video: {
        var vEnd = el.dataOffset + el.dataSize, vOff = el.dataOffset;
        while (vOff < vEnd - 2) {
          var ve = readElement(buf, vOff);
          if (!ve || ve.dataSize < 0) break;
          if (ve.id === EBML_ID.PixelWidth)  width  = readUint(buf, ve.dataOffset, ve.dataSize);
          if (ve.id === EBML_ID.PixelHeight) height = readUint(buf, ve.dataOffset, ve.dataSize);
          vOff += ve.totalSize;
        }
        break;
      }
      case EBML_ID.Audio: {
        var aEnd = el.dataOffset + el.dataSize, aOff = el.dataOffset;
        while (aOff < aEnd - 2) {
          var ae = readElement(buf, aOff);
          if (!ae || ae.dataSize < 0) break;
          if (ae.id === EBML_ID.SamplingFrequency) sampleRate = Math.round(readFloat(buf, ae.dataOffset, ae.dataSize));
          if (ae.id === EBML_ID.Channels)          channels   = readUint(buf, ae.dataOffset, ae.dataSize);
          aOff += ae.totalSize;
        }
        break;
      }
    }
    offset += el.totalSize;
  }
  if (trackType === TRACK_TYPE_VIDEO && !this._videoTrack)
    this._videoTrack = { trackNum: trackNum, codecId: codecId, codecPrivate: codecPrivate, width: width, height: height };
  if (trackType === TRACK_TYPE_AUDIO && !this._audioTrack)
    this._audioTrack = { trackNum: trackNum, codecId: codecId, codecPrivate: codecPrivate, sampleRate: sampleRate, channels: channels };
};

// ── MKV : initialisation JMuxer ───────────────────────────────────────────────

MkvMsePlayer.prototype._initJMuxerMkv = function() {
  var hasVideo = this._videoTrack && (
    this._videoTrack.codecId === 'V_MPEG4/ISO/AVC' ||
    this._videoTrack.codecId === 'V_MPEG4/ISO/AVCP'
  );
  var hasAudio = this._audioTrack && (
    this._audioTrack.codecId === 'A_AAC' ||
    this._audioTrack.codecId.indexOf('A_AAC') === 0 ||
    this._audioTrack.codecId === 'A_MPEG/L3'
  );
  console.warn('[MSE] MKV codecs — video:', this._videoTrack && this._videoTrack.codecId, 'audio:', this._audioTrack && this._audioTrack.codecId);
  if (!hasVideo && !hasAudio) {
    if (this._cbs.onUnsupported) this._cbs.onUnsupported('MKV codecs not supported');
    return;
  }
  this._hasVideo = hasVideo;
  this._hasAudio = hasAudio;
  this._initJMuxerCommon(
    hasVideo && hasAudio ? 'both' : (hasVideo ? 'video' : 'audio'),
    25
  );
};

// ═════════════════════════════════════════════════════════════════════════════
// AVI — Parse header RIFF
// ═════════════════════════════════════════════════════════════════════════════

/**
 * Parse l'en-tête AVI pour trouver les streams et localiser movi.
 * Retourne { nextOffset } (offset du premier chunk dans movi) ou null si besoin de plus de données.
 */
MkvMsePlayer.prototype._parseAviInit = function(buf) {
  // RIFF chunk
  var riff = readAviChunk(buf, 0);
  if (!riff || riff.fourcc !== 'RIFF') return null;
  if (riff.dataOffset + 4 > buf.length) return null;
  if (readFourCC(buf, riff.dataOffset) !== 'AVI ') return null;

  var offset = riff.dataOffset + 4; // après 'AVI '

  while (offset + 8 <= buf.length) {
    var ch = readAviChunk(buf, offset);
    if (!ch) return null;

    if (ch.fourcc === 'LIST' && ch.size >= 4) {
      if (ch.dataOffset + 4 > buf.length) return null;
      var listType = readFourCC(buf, ch.dataOffset);

      if (listType === 'hdrl') {
        if (offset + ch.totalSize > buf.length) return null; // attendre la fin du hdrl
        this._parseAviHdrl(buf, ch.dataOffset + 4, ch.size - 4);
        offset += ch.totalSize;
        continue;
      }

      if (listType === 'movi') {
        // Premier chunk movi = ch.dataOffset + 4 (après 'movi' 4 bytes)
        console.warn('[MSE] AVI movi trouvé à offset', offset, 'données à', ch.dataOffset + 4);
        return { nextOffset: ch.dataOffset + 4 };
      }
    }

    // Chunk inconnu (JUNK, ISFT, idx1 avant movi…) → sauter
    if (offset + ch.totalSize > buf.length) return null;
    offset += ch.totalSize;
  }

  return null; // besoin de plus de données
};

/** Parse la section hdrl pour extraire les infos de streams. */
MkvMsePlayer.prototype._parseAviHdrl = function(buf, offset, size) {
  var end = offset + size;
  var streamIdx = 0;

  while (offset + 8 <= end) {
    var ch = readAviChunk(buf, offset);
    if (!ch || offset + ch.totalSize > end) break;

    if (ch.fourcc === 'LIST' && ch.size >= 4) {
      var listType = readFourCC(buf, ch.dataOffset);
      if (listType === 'strl') {
        var stream = this._parseAviStrl(buf, ch.dataOffset + 4, ch.size - 4, streamIdx);
        if (stream) {
          if (!this._videoTrack && stream.streamType === 'vids') this._videoTrack = stream;
          if (!this._audioTrack && stream.streamType === 'auds') this._audioTrack = stream;
        }
        streamIdx++;
      }
    }
    offset += ch.totalSize;
  }

  console.warn('[MSE] AVI video track:', JSON.stringify(this._videoTrack));
  console.warn('[MSE] AVI audio track:', JSON.stringify(this._audioTrack));
};

/** Parse un strl (stream list) AVI : strh + strf. */
MkvMsePlayer.prototype._parseAviStrl = function(buf, offset, size, streamIdx) {
  var end    = offset + size;
  var stream = { streamIdx: streamIdx };

  while (offset + 8 <= end) {
    var ch = readAviChunk(buf, offset);
    if (!ch || offset + ch.totalSize > end) break;

    if (ch.fourcc === 'strh' && ch.size >= 36) {
      // AVIStreamHeader
      stream.streamType  = readFourCC(buf, ch.dataOffset);      // 'vids' ou 'auds'
      stream.fccHandler  = readFourCC(buf, ch.dataOffset + 4);  // FourCC du codec
      stream.dwScale     = readU32LE(buf, ch.dataOffset + 20);
      stream.dwRate      = readU32LE(buf, ch.dataOffset + 24);
      // Pour la vidéo : fps = dwRate / dwScale
      stream.frameDurationMs = (stream.dwScale && stream.dwRate)
        ? (stream.dwScale / stream.dwRate * 1000) : 40;
    }

    if (ch.fourcc === 'strf') {
      if (stream.streamType === 'vids' && ch.size >= 20) {
        // BITMAPINFOHEADER : biCompression à l'offset 16 (4+4+4+2+2)
        stream.biCompression = readFourCC(buf, ch.dataOffset + 16);
        // Parfois biCompression est en little-endian → normaliser
      }
      if (stream.streamType === 'auds' && ch.size >= 8) {
        // WAVEFORMATEX
        stream.wFormatTag  = readU16LE(buf, ch.dataOffset);
        stream.channels    = readU16LE(buf, ch.dataOffset + 2);
        stream.sampleRate  = readU32LE(buf, ch.dataOffset + 4);
      }
    }

    offset += ch.totalSize;
  }

  return stream.streamType ? stream : null;
};

// ── AVI : initialisation JMuxer ───────────────────────────────────────────────

MkvMsePlayer.prototype._initJMuxerAvi = function() {
  // Vérifier si le codec vidéo est H.264
  var vt = this._videoTrack;
  var at = this._audioTrack;

  var hasVideo = vt && (
    AVI_H264_FOURCCS.indexOf(vt.biCompression) >= 0 ||
    AVI_H264_FOURCCS.indexOf(vt.fccHandler)    >= 0
  );
  var hasAudio = at && (
    WAVE_MP3.indexOf(at.wFormatTag) >= 0 ||
    WAVE_AAC.indexOf(at.wFormatTag) >= 0
  );

  console.warn('[MSE] AVI codec vidéo:', vt && (vt.biCompression + '/' + vt.fccHandler));
  console.warn('[MSE] AVI codec audio: formatTag=0x' + (at && at.wFormatTag ? at.wFormatTag.toString(16) : '?'));

  if (!hasVideo && !hasAudio) {
    console.warn('[MSE] AVI codecs non supportés');
    if (this._cbs.onUnsupported) this._cbs.onUnsupported('AVI codecs not supported');
    return;
  }

  this._hasVideo = hasVideo;
  this._hasAudio = hasAudio;
  this._aviVideoFrameCount = 0;

  var fps = (vt && vt.dwRate && vt.dwScale) ? (vt.dwRate / vt.dwScale) : 25;

  this._initJMuxerCommon(
    hasVideo && hasAudio ? 'both' : (hasVideo ? 'video' : 'audio'),
    Math.round(fps)
  );
};

// ── AVI : parse chunks movi ────────────────────────────────────────────────────

MkvMsePlayer.prototype._parseAviMovi = function(buf) {
  var offset = 0;

  while (offset + 8 <= buf.length) {
    var ch = readAviChunk(buf, offset);
    if (!ch) break;
    // Chunk incomplet → attendre plus de données
    if (offset + ch.totalSize > buf.length) break;
    // Fin de liste / padding
    if (ch.size === 0 || ch.fourcc[0] === '\0') { offset += Math.max(ch.totalSize, 8); break; }

    var streamIdx = aviChunkStream(ch.fourcc);
    var chType    = aviChunkType(ch.fourcc);

    if (streamIdx >= 0 && ch.size > 0) {
      var isVideo = this._videoTrack && streamIdx === this._videoTrack.streamIdx && (chType === 'dc' || chType === 'db');
      var isAudio = this._audioTrack && streamIdx === this._audioTrack.streamIdx && chType === 'wb';

      if (isVideo && this._hasVideo) {
        var videoData = buf.slice(ch.dataOffset, ch.dataOffset + ch.size);
        var fdMs = (this._videoTrack.frameDurationMs) || 40;
        var packet = { video: videoData, duration: Math.round(fdMs) };
        this._aviVideoFrameCount++;
        this._pushFrameOrQueue(packet);
      }

      if (isAudio && this._hasAudio) {
        var audioData = buf.slice(ch.dataOffset, ch.dataOffset + ch.size);
        this._pushFrameOrQueue({ audio: audioData });
      }
    }

    // Entrer dans les LIST 'rec ' (chunks interleaved)
    if (ch.fourcc === 'LIST' && ch.size >= 4 && offset + 12 <= buf.length) {
      var lt = readFourCC(buf, ch.dataOffset);
      if (lt === 'rec ') {
        // Juste sauter le header LIST+type et continuer à lire les chunks internes
        offset += 12;
        continue;
      }
    }

    offset += ch.totalSize;
  }

  this._moviConsumed = offset;
};

// ═════════════════════════════════════════════════════════════════════════════
// JMuxer — initialisation commune
// ═════════════════════════════════════════════════════════════════════════════

MkvMsePlayer.prototype._initJMuxerCommon = function(mode, fps) {
  if (this._destroyed) return;
  var self = this;

  console.warn('[MSE] JMuxer init mode=', mode, 'fps=', fps);
  try {
    this._jmuxer = new JMuxer({
      node:         this._video,
      mode:         mode,
      flushingTime: 0,
      fps:          fps || 25,
      readFPS:      false,
      debug:        false,
      onReady: function() {
        console.warn('[MSE] JMuxer ready');
        self._jmuxerReady = true;
        self._video.play().catch(function(){});
        if (self._cbs.onLoaded) self._cbs.onLoaded();
        for (var i = 0; i < self._pendingFrames.length; i++) self._pushFrame(self._pendingFrames[i]);
        self._pendingFrames = [];
      },
      onError: function(data) {
        console.warn('[MSE] JMuxer erreur:', JSON.stringify(data));
      },
    });
  } catch (e) {
    console.warn('[MSE] JMuxer init erreur:', e.message);
    if (this._cbs.onUnsupported) this._cbs.onUnsupported(e.message);
  }
};

MkvMsePlayer.prototype._pushFrameOrQueue = function(packet) {
  if (!this._jmuxerReady) { this._pendingFrames.push(packet); return; }
  this._pushFrame(packet);
};

MkvMsePlayer.prototype._pushFrame = function(packet) {
  if (!this._jmuxer || this._destroyed) return;
  try { this._jmuxer.feed(packet); } catch (e) {
    console.warn('[MSE] feed erreur:', e.message);
  }
};

// ═════════════════════════════════════════════════════════════════════════════
// MKV — Parse Clusters (frames vidéo/audio)
// ═════════════════════════════════════════════════════════════════════════════

MkvMsePlayer.prototype._parseClusters = function(buf) {
  var offset = 0;
  while (offset < buf.length - 8) {
    var el = readElement(buf, offset);
    if (!el) break;
    if (el.dataSize >= 0 && offset + el.totalSize > buf.length) break;
    if (el.id === EBML_ID.Cluster) {
      if (el.dataSize < 0) {
        var clEnd = this._findNextCluster(buf, el.dataOffset);
        if (clEnd < 0) { this._clusterConsumed += offset; return; }
        this._parseClusterContent(buf, el.dataOffset, clEnd - el.dataOffset);
        offset = clEnd;
      } else {
        this._parseClusterContent(buf, el.dataOffset, el.dataSize);
        offset += el.totalSize;
      }
    } else {
      if (el.dataSize < 0) { offset += el.headerSize; } else { offset += el.totalSize; }
    }
  }
  this._clusterConsumed += offset;
};

MkvMsePlayer.prototype._findNextCluster = function(buf, startOffset) {
  for (var i = startOffset; i < buf.length - 4; i++) {
    if (buf[i] === 0x1F && buf[i+1] === 0x43 && buf[i+2] === 0xB6 && buf[i+3] === 0x75) return i;
  }
  return -1;
};

MkvMsePlayer.prototype._parseClusterContent = function(buf, offset, size) {
  var end = offset + size;
  while (offset < end - 4) {
    var el = readElement(buf, offset);
    if (!el || el.dataSize < 0) break;
    if (offset + el.totalSize > end) break;
    if (el.id === EBML_ID.Timecode) this._clusterTimecode = readUint(buf, el.dataOffset, el.dataSize);
    else if (el.id === EBML_ID.SimpleBlock) this._parseSimpleBlock(buf, el.dataOffset, el.dataSize);
    else if (el.id === EBML_ID.BlockGroup)  this._parseBlockGroup(buf, el.dataOffset, el.dataSize);
    offset += el.totalSize;
  }
};

MkvMsePlayer.prototype._parseSimpleBlock = function(buf, offset, size) {
  if (size < 4) return;
  var tn     = readVint(buf, offset);
  var tcOff  = offset + tn.length;
  var relTc  = (buf[tcOff] << 8) | buf[tcOff + 1];
  if (relTc > 32767) relTc -= 65536;
  var flags    = buf[tcOff + 2];
  var dataOff  = tcOff + 3;
  var dataSize = size - tn.length - 3;
  if (dataSize <= 0) return;
  var tsMs = (this._clusterTimecode + relTc) * this._tickMs;
  this._dispatchFrame({
    trackNum: tn.value,
    tsMs:     tsMs,
    keyframe: (flags & 0x80) !== 0,
    data:     buf.slice(dataOff, dataOff + dataSize),
  });
};

MkvMsePlayer.prototype._parseBlockGroup = function(buf, offset, size) {
  var end = offset + size;
  while (offset < end - 4) {
    var el = readElement(buf, offset);
    if (!el || el.dataSize < 0) break;
    if (el.id === EBML_ID.Block) this._parseSimpleBlock(buf, el.dataOffset, el.dataSize);
    offset += el.totalSize;
  }
};

MkvMsePlayer.prototype._dispatchFrame = function(frame) {
  var isVideo = this._videoTrack && frame.trackNum === this._videoTrack.trackNum;
  var isAudio = this._audioTrack && frame.trackNum === this._audioTrack.trackNum;
  if (!isVideo && !isAudio) return;
  var packet = {};
  if (isVideo && this._hasVideo) {
    var vData = frame.data;
    if (this._videoTrack.codecPrivate) vData = this._avccToAnnexB(frame.data, this._videoTrack.codecPrivate);
    packet.video    = vData;
    packet.duration = Math.round(frame.tsMs);
  }
  if (isAudio && this._hasAudio) {
    packet.audio    = frame.data;
    packet.duration = Math.round(frame.tsMs);
  }
  if (!packet.video && !packet.audio) return;
  this._pushFrameOrQueue(packet);
};

// ── Conversion AVCC → Annex B ─────────────────────────────────────────────────

MkvMsePlayer.prototype._avccToAnnexB = function(data, avcC) {
  var nalLenBytes = (avcC.length > 4) ? (avcC[4] & 0x03) + 1 : 4;
  var startCode   = new Uint8Array([0, 0, 0, 1]);
  var parts       = [];

  if (!this._spsppsSent) {
    this._spsppsSent = true;
    var numSps = avcC[5] & 0x1F, avcOff = 6;
    for (var i = 0; i < numSps && avcOff + 2 <= avcC.length; i++) {
      var spsLen = (avcC[avcOff] << 8) | avcC[avcOff + 1]; avcOff += 2;
      parts.push(startCode); parts.push(avcC.slice(avcOff, avcOff + spsLen)); avcOff += spsLen;
    }
    if (avcOff < avcC.length) {
      var numPps = avcC[avcOff++];
      for (var j = 0; j < numPps && avcOff + 2 <= avcC.length; j++) {
        var ppsLen = (avcC[avcOff] << 8) | avcC[avcOff + 1]; avcOff += 2;
        parts.push(startCode); parts.push(avcC.slice(avcOff, avcOff + ppsLen)); avcOff += ppsLen;
      }
    }
  }

  var offset = 0;
  while (offset + nalLenBytes <= data.length) {
    var nalLen = 0;
    for (var k = 0; k < nalLenBytes; k++) nalLen = (nalLen << 8) | data[offset + k];
    offset += nalLenBytes;
    if (offset + nalLen > data.length) break;
    parts.push(startCode); parts.push(data.slice(offset, offset + nalLen));
    offset += nalLen;
  }

  var total = 0;
  for (var p = 0; p < parts.length; p++) total += parts[p].length;
  var out = new Uint8Array(total), pos = 0;
  for (var q = 0; q < parts.length; q++) { out.set(parts[q], pos); pos += parts[q].length; }
  return out;
};

// ── Contrôles ────────────────────────────────────────────────────────────────

MkvMsePlayer.prototype.play  = function() { if (this._video) this._video.play().catch(function(){}); };
MkvMsePlayer.prototype.pause = function() { if (this._video) this._video.pause(); };
MkvMsePlayer.prototype.seek  = function() {}; // seek non supporté (stream linéaire)
