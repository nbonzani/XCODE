/**
 * src/App.jsx
 * Routeur principal de l'application.
 *
 * Structure de navigation :
 *
 *   /                → HomeScreen      (catalogue films + séries)
 *   /settings        → SettingsScreen  (configuration connexion Xtream)
 *   /series/:id      → SeriesDetailScreen (détail + épisodes d'une série)
 *   /player          → PlayerScreen    (lecteur vidéo plein écran)
 *
 * Note sur MovieDetailModal :
 *   Il s'agit d'une modale superposée à HomeScreen, PAS d'une route séparée.
 *   Elle est gérée par l'état local de HomeScreen via un store Zustand.
 *   Elle n'apparaît donc pas ici en tant que <Route>.
 *
 * Note sur le routeur webOS :
 *   On utilise HashRouter (routes avec #) plutôt que BrowserRouter (routes sans #).
 *   Raison : webOS sert l'application depuis le système de fichiers local (file://).
 *   BrowserRouter requiert un serveur HTTP pour gérer les routes — ce qui n'existe
 *   pas dans l'environnement webOS. HashRouter fonctionne sans serveur.
 *
 *   Exemple d'URL webOS :
 *     file:///media/developer/apps/usr/palm/applications/com.iptv.player/index.html#/settings
 */

import React, { useEffect } from 'react';
import { HashRouter, Routes, Route, Navigate } from 'react-router-dom';

// Imports statiques — obligatoires sur webOS (file:// bloque les imports dynamiques)
import HomeScreen           from './screens/HomeScreen.jsx';
import SettingsScreen       from './screens/SettingsScreen.jsx';
import SeriesDetailScreen   from './screens/SeriesDetailScreen.jsx';
import PlayerScreen         from './screens/PlayerScreen.jsx';
import CatalogFilterScreen  from './screens/CatalogFilterScreen.jsx';
import TestXvidScreen       from './screens/TestXvidScreen.jsx';

// Import du store Zustand pour vérifier si l'application est configurée
// et rediriger vers SettingsScreen au premier lancement.
import { useAppStore } from './store/appStore.js';
import { usePlayerStore } from './store/playerStore.js';

/**
 * Composant de fallback pendant le chargement différé des écrans.
 * Affiché pendant les quelques millisecondes de chargement du bundle.
 * Fond noir opaque pour éviter tout flash de contenu non stylisé.
 */
function LoadingFallback() {
  return (
    <div
      style={{
        width: '1920px',
        height: '1080px',
        backgroundColor: 'var(--color-bg-primary)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
      }}
    >
      <div
        style={{
          color: 'var(--color-text-secondary)',
          fontSize: 'var(--font-size-lg)',
          fontFamily: 'var(--font-family-base)',
        }}
      >
        Chargement…
      </div>
    </div>
  );
}

/**
 * Composant de garde de route : redirige vers /settings si l'application
 * n'est pas encore configurée (premier lancement).
 *
 * Logique :
 * - Si la configuration Xtream (URL, login, mot de passe) est absente du localStorage,
 *   on redirige automatiquement vers SettingsScreen.
 * - Une fois configuré, toute navigation vers / affiche HomeScreen normalement.
 */
function RequireConfig({ children }) {
  const isConfigured      = useAppStore((state) => state.isConfigured);
  const catalogSetupDone  = useAppStore((state) => state.config.catalogSetupDone);

  if (!isConfigured || !catalogSetupDone) {
    return <Navigate to="/settings" replace />;
  }

  return children;
}

/**
 * Composant racine de l'application.
 * Contient le routeur et la logique de redirection initiale.
 */
// Wrapper qui force le démontage/remontage de PlayerScreen à chaque nouvelle URL
// Résout le problème de dimensions résiduelles sur la 2ème lecture
function PlayerScreenWrapper() {
  const playKey = usePlayerStore((s) => s.playKey);
  // playKey = timestamp unique à chaque playSingle()
  // Garantit le démontage/remontage complet même pour deux films de même catégorie
  return <PlayerScreen key={playKey || 'player'} />;
}

export default function App() {
  // Tentative de chargement de la configuration depuis localStorage au démarrage
  const initConfig = useAppStore((state) => state.initConfig);

  useEffect(() => {
    // Appelé une seule fois au montage de l'application.
    // Lit le localStorage et met à jour le store Zustand.
    initConfig();
  }, [initConfig]);

  return (
    <HashRouter>
      {/*
        Suspense enveloppe toutes les routes pour gérer le chargement
        différé des composants (React.lazy).
        fallback = ce qui s'affiche pendant le chargement du chunk JS.
      */}
      <Routes>
          {/*
            Route racine : catalogue principal.
            Protégée par RequireConfig → redirige vers /settings si non configuré.
          */}
          <Route
            path="/"
            element={
              <RequireConfig>
                <HomeScreen />
              </RequireConfig>
            }
          />

          {/*
            Route paramètres : accessible sans configuration préalable
            (premier lancement, reconfiguration).
          */}
          <Route path="/settings" element={<SettingsScreen />} />
          <Route path="/catalog-filter" element={<CatalogFilterScreen />} />

          {/*
            Route détail série : :id est l'identifiant numérique de la série
            dans la base Xtream (series_id).
            Exemple : /series/42
          */}
          <Route
            path="/series/:id"
            element={
              <RequireConfig>
                <SeriesDetailScreen />
              </RequireConfig>
            }
          />

          {/*
            Route lecteur vidéo : plein écran, pas de barre de navigation.
            Les paramètres de lecture (URL du flux, playlist, titre)
            sont transmis via le playerStore Zustand — pas via l'URL —
            pour éviter d'exposer les credentials Xtream dans l'historique.
          */}
          <Route
            path="/player"
            element={
              <RequireConfig>
                <PlayerScreenWrapper />
              </RequireConfig>
            }
          />

          {/*
            Route de rattrapage : toute URL inconnue redirige vers /.
            RequireConfig s'occupera du cas "non configuré".
          */}
          {/* Route de test libav.js — dev uniquement */}
          <Route path="/test-xvid" element={<TestXvidScreen />} />

          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
    </HashRouter>
  );
}
