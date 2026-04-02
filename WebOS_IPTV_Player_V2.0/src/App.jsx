import { HashRouter, Routes, Route } from 'react-router-dom'

// Pages (à créer dans les étapes suivantes)
// import HomePage from './pages/HomePage'
// import PlayerPage from './pages/PlayerPage'

// Placeholder temporaire pour valider le build
function HomePage() {
  return (
    <div style={{
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      width: '1920px',
      height: '1080px',
      background: '#111',
      color: '#fff',
      fontSize: '48px'
    }}>
      IPTV Player webOS v2.0 — Build OK ✓
    </div>
  )
}

export default function App() {
  return (
    <HashRouter>
      <Routes>
        <Route path="/" element={<HomePage />} />
      </Routes>
    </HashRouter>
  )
}
