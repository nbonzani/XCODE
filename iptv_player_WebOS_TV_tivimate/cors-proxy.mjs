/**
 * cors-proxy.mjs — proxy CORS local pour tests dev
 * Usage: node cors-proxy.mjs
 * Écoute sur http://localhost:3001/proxy?url=<URL encodée>
 */
import http from 'http';
import https from 'https';
import { URL } from 'url';

const PORT = 3001;

http.createServer((req, res) => {
  const reqUrl = new URL(req.url, `http://localhost:${PORT}`);
  const target = reqUrl.searchParams.get('url');

  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Headers', '*');
  if (req.method === 'OPTIONS') { res.writeHead(204); res.end(); return; }

  if (!target) {
    res.writeHead(400); res.end('?url= manquant'); return;
  }

  console.log('PROXY →', target.slice(0, 80));

  function doRequest(urlStr, redirects) {
    if (redirects > 5) { res.writeHead(502); res.end('Trop de redirections'); return; }
    const u = new URL(urlStr);
    const lib = u.protocol === 'https:' ? https : http;
    const options = {
      hostname: u.hostname, port: u.port || (u.protocol === 'https:' ? 443 : 80),
      path: u.pathname + u.search,
      method: req.method,
      headers: {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0',
        'Range': req.headers['range'] || '',
      },
    };
    const proxyReq = lib.request(options, (proxyRes) => {
      if ([301,302,303,307,308].includes(proxyRes.statusCode)) {
        doRequest(proxyRes.headers['location'], redirects + 1);
        proxyRes.resume(); return;
      }
      res.writeHead(proxyRes.statusCode, {
        'Content-Type': proxyRes.headers['content-type'] || 'application/octet-stream',
        'Content-Length': proxyRes.headers['content-length'] || '',
        'Accept-Ranges': 'bytes',
        'Access-Control-Allow-Origin': '*',
      });
      proxyRes.pipe(res);
    });
    proxyReq.on('error', (e) => { console.error(e.message); res.writeHead(502); res.end(e.message); });
    proxyReq.end();
  }

  doRequest(target, 0);
}).listen(PORT, () => console.log(`CORS proxy → http://localhost:${PORT}/proxy?url=<URL>`));
