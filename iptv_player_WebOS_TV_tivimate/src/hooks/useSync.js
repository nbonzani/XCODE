/**
 * src/hooks/useSync.js
 * Hook de synchronisation du catalogue depuis le serveur Xtream.
 *
 * Filtre FR actif dès le téléchargement :
 *   Quand config.frenchOnly === true, seules les catégories françaises
 *   sont téléchargées depuis le serveur → moins de requêtes API, moins
 *   de données en mémoire sur la TV.
 */

import { useCallback } from 'react';
import { useAppStore }     from '../store/appStore.js';
import { useCatalogStore } from '../store/catalogStore.js';
import { createClientFromConfig } from '../services/xtreamApi.js';
import {
  isFrench,
  saveVodCategories,
  saveMovies,
  saveSeriesCategories,
  saveSeriesList,
  setLastSyncDate,
  loadCatalog,
} from '../services/cacheService.js';

function setStatus(msg) {
  useAppStore.setState({ syncStatus: msg });
}

function setProgress(done, total) {
  useAppStore.setState({ syncProgress: { done, total } });
}

export function useSync() {
  const { config, isSyncing, startSync, finishSync, failSync } = useAppStore();
  const { loadCatalog: loadCatalogStore } = useCatalogStore();

  const sync = useCallback(async () => {
    if (isSyncing) return;
    startSync();

    try {
      const client      = createClientFromConfig(config);
      const frenchOnly  = config.frenchOnly !== false; // true par défaut

      setStatus('Connexion au serveur…');
      await client.authenticate();

      // ── Films ─────────────────────────────────────────────────────────────

      setStatus('Téléchargement des catégories de films…');
      const vodCats = await client.getVodCategories();
      await saveVodCategories(vodCats);

      // Filtre FR : ne télécharger que les catégories françaises si activé
      const vodCatsToFetch = frenchOnly
        ? vodCats.filter(function(c) { return isFrench(c.category_name); })
        : vodCats;

      const vodCatsMap = Object.fromEntries(
        vodCats.map(function(c) { return [String(c.category_id), c.category_name]; })
      );

      var allMovies = [];
      setProgress(0, vodCatsToFetch.length);

      for (var ci = 0; ci < vodCatsToFetch.length; ci++) {
        var cat = vodCatsToFetch[ci];
        setStatus('Films : catégorie ' + (ci + 1) + ' / ' + vodCatsToFetch.length + ' — ' + (cat.category_name || ''));
        setProgress(ci, vodCatsToFetch.length);
        try {
          var catMovies = await client.getVodStreams(cat.category_id);
          if (Array.isArray(catMovies)) allMovies = allMovies.concat(catMovies);
        } catch (e) {
          console.warn('[Sync] Erreur catégorie films', cat.category_id, e.message);
        }
      }

      setStatus('Enregistrement de ' + allMovies.length + ' films…');
      setProgress(vodCatsToFetch.length, vodCatsToFetch.length);
      await saveMovies(allMovies, vodCatsMap);

      // ── Séries ────────────────────────────────────────────────────────────

      setStatus('Téléchargement des catégories de séries…');
      const seriesCats = await client.getSeriesCategories();
      await saveSeriesCategories(seriesCats);

      const seriesCatsToFetch = frenchOnly
        ? seriesCats.filter(function(c) { return isFrench(c.category_name); })
        : seriesCats;

      const seriesCatsMap = Object.fromEntries(
        seriesCats.map(function(c) { return [String(c.category_id), c.category_name]; })
      );

      var allSeries = [];
      setProgress(0, seriesCatsToFetch.length);

      for (var si = 0; si < seriesCatsToFetch.length; si++) {
        var scat = seriesCatsToFetch[si];
        setStatus('Séries : catégorie ' + (si + 1) + ' / ' + seriesCatsToFetch.length + ' — ' + (scat.category_name || ''));
        setProgress(si, seriesCatsToFetch.length);
        try {
          var catSeries = await client.getSeries(scat.category_id);
          if (Array.isArray(catSeries)) allSeries = allSeries.concat(catSeries);
        } catch (e) {
          console.warn('[Sync] Erreur catégorie séries', scat.category_id, e.message);
        }
      }

      setStatus('Enregistrement de ' + allSeries.length + ' séries…');
      setProgress(seriesCatsToFetch.length, seriesCatsToFetch.length);
      await saveSeriesList(allSeries, seriesCatsMap);

      // ── Finalisation ──────────────────────────────────────────────────────

      setStatus('Finalisation…');
      await setLastSyncDate();

      setStatus('Chargement du catalogue…');
      await loadCatalogStore(loadCatalog, config.frenchOnly);

      finishSync(allMovies.length + allSeries.length);

    } catch (error) {
      failSync(error.message);
    }
  }, [config, isSyncing, startSync, finishSync, failSync, loadCatalogStore]);

  const syncFresh = useCallback(async () => {
    const { clearCache } = await import('../services/cacheService.js');
    if (isSyncing) return;
    setStatus('Vidage du cache…');
    await clearCache();
    await sync();
  }, [isSyncing, sync]);

  return { sync, syncFresh, isSyncing };
}
