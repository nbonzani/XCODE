import React, { useRef, useState, useEffect, useCallback } from 'react';

let LibavXvidPlayer = null;
async function loadPlayer() {
  if (!LibavXvidPlayer) {
    const m = await import('../services/libavXvidPlayer.js');
    LibavXvidPlayer = m.default;
  }
  return LibavXvidPlayer;
}

const PROXY = 'http://localhost:3001/proxy?url=';

export default function TestXvidScreen() {
  const canvasRef   = useRef(null);
  const playerRef   = useRef(null);
  const [urls, setUrls]       = useState('');
  const [results, setResults] = useState([]);   // [{url, status, detail}]
  const [current, setCurrent] = useState(null); // url en cours
  const [running, setRunning] = useState(false);
  const stopRef = useRef(false);

  function stopCurrent() {
    if (playerRef.current) { playerRef.current.destroy(); playerRef.current = null; }
  }

  const testOne = useCallback((url) => {
    return new Promise((resolve) => {
      stopCurrent();
      setCurrent(url);
      const proxied = PROXY + encodeURIComponent(url);
      const timeout = setTimeout(() => {
        stopCurrent();
        resolve({ url, status: 'nok', detail: 'Timeout 20s' });
      }, 20000);

      loadPlayer().then((Player) => {
        const player = new Player(canvasRef.current);
        playerRef.current = player;
        let done = false;
        const finish = (res) => {
          if (done) return; done = true;
          clearTimeout(timeout);
          stopCurrent();
          resolve(res);
        };
        let firstFrame = false;
        const origRender = player._renderYUV.bind(player);
        player._renderYUV = function(frame) {
          origRender(frame);
          if (!firstFrame) { firstFrame = true; finish({ url, status: 'ok', detail: '' }); }
        };
        player.load(proxied, 0, {
          onLoaded:      () => {},
          onTimeUpdate:  () => {},
          onError:       (e) => finish({ url, status: 'nok', detail: e }),
          onUnsupported: (r) => finish({ url, status: 'nok', detail: r }),
        });
      }).catch((e) => resolve({ url, status: 'nok', detail: String(e) }));
    });
  }, []);

  async function runAll() {
    const list = urls.split('\n').map(s => s.trim()).filter(Boolean);
    if (!list.length) return;
    stopRef.current = false;
    setRunning(true);
    setResults([]);
    for (const url of list) {
      if (stopRef.current) break;
      const res = await testOne(url);
      setResults(prev => [...prev, res]);
    }
    setCurrent(null);
    setRunning(false);
  }

  function stopAll() {
    stopRef.current = true;
    stopCurrent();
    setRunning(false);
    setCurrent(null);
  }

  const okCount  = results.filter(r => r.status === 'ok').length;
  const nokCount = results.filter(r => r.status === 'nok').length;

  return (
    <div style={{
      position: 'absolute', inset: 0, background: '#111', color: '#eee',
      fontFamily: 'monospace', fontSize: 13, overflow: 'auto', padding: 20,
      cursor: 'auto', zIndex: 9999,
    }}>
      <h2 style={{ color: '#4af', marginTop: 0, fontSize: 16 }}>Test libav.js — liste de liens</h2>

      <div style={{ display: 'flex', gap: 16, marginBottom: 12 }}>
        {/* Textarea URLs */}
        <div style={{ flex: 1 }}>
          <div style={{ color: '#888', marginBottom: 4, fontSize: 11 }}>
            Un lien par ligne (.avi ou .mkv) :
          </div>
          <textarea
            value={urls}
            onChange={e => setUrls(e.target.value)}
            disabled={running}
            rows={10}
            style={{ width: '100%', padding: '8px', background: '#222', border: '1px solid #555',
                     color: '#eee', borderRadius: 4, fontSize: 12, resize: 'vertical',
                     cursor: 'text', boxSizing: 'border-box' }}
            placeholder={"http://serveur/movie/user/pass/12345.avi\nhttp://serveur/series/user/pass/67890.mkv\n..."}
          />
          <div style={{ display: 'flex', gap: 8, marginTop: 8 }}>
            <Btn color="#4af" onClick={runAll} disabled={running}>▶ Tout tester</Btn>
            <Btn color="#f84" onClick={stopAll} disabled={!running}>■ Stop</Btn>
            {results.length > 0 && (
              <span style={{ alignSelf: 'center', marginLeft: 8 }}>
                <span style={{ color: '#4c4' }}>✓ {okCount} OK</span>
                {'  '}
                <span style={{ color: '#f66' }}>✗ {nokCount} NOK</span>
              </span>
            )}
          </div>
        </div>

        {/* Canvas */}
        <div style={{ flex: 1 }}>
          <div style={{ color: '#888', marginBottom: 4, fontSize: 11 }}>
            {current ? `En cours : ${current.split('/').pop()}` : 'Aperçu :'}
          </div>
          <canvas ref={canvasRef} width={480} height={270}
            style={{ display: 'block', background: '#000', border: '2px solid #333', width: '100%' }} />
        </div>
      </div>

      {/* Résultats */}
      {results.length > 0 && (
        <div style={{ background: '#1a1a1a', border: '1px solid #333', borderRadius: 4, padding: '8px 12px' }}>
          <div style={{ color: '#666', fontSize: 11, marginBottom: 6 }}>Résultats :</div>
          {results.map((r, i) => (
            <div key={i} style={{ display: 'flex', gap: 10, marginBottom: 3, fontSize: 12 }}>
              <span style={{ color: r.status === 'ok' ? '#4c4' : '#f66', minWidth: 50, fontWeight: 'bold' }}>
                {r.status === 'ok' ? '✓ OK' : '✗ NOK'}
              </span>
              <span style={{ color: '#aaa', flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {r.url.split('/').pop()}
              </span>
              {r.detail && <span style={{ color: '#888', fontSize: 11 }}>{r.detail}</span>}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function Btn({ color, onClick, disabled, children }) {
  return (
    <button onClick={onClick} disabled={disabled} style={{
      padding: '7px 16px', background: disabled ? '#444' : color, color: disabled ? '#888' : '#111',
      border: 'none', borderRadius: 4, cursor: disabled ? 'default' : 'pointer',
      fontWeight: 'bold', fontSize: 13,
    }}>{children}</button>
  );
}
