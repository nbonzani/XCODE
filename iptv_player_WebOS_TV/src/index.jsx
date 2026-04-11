import React from 'react';
import ReactDOM from 'react-dom/client';
import './styles/global.css';
import './styles/focusRing.css';
import App from './App.jsx';

function mount() {
  const rootElement = document.getElementById('root');
  if (!rootElement) {
    console.error('[IPTV Player] div#root introuvable — nouveau essai dans 100ms');
    setTimeout(mount, 100);
    return;
  }
  const root = ReactDOM.createRoot(rootElement);
  root.render(
    <React.StrictMode>
      <App />
    </React.StrictMode>
  );
}

// Attend que le DOM soit prêt — obligatoire avec le format IIFE sur webOS
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', mount);
} else {
  mount();
}
