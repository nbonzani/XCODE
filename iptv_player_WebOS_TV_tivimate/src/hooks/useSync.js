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
      const frenchOnly  = config.frenchOnly === true; // false si non défini (nouveaux configs)

      setStatus('Connexion au serveur…');
      await client.authenticate();

      // Catégories sélectionnées par le filtre utilisateur ([] = tout)
      const selMovCatIds  = config.selectedMovieCategories  || [];
      const selSerCatIds  = config.selectedSeriesCategories || [];

      // ── Films ─────────────────────────────────────────────────────────────

      setStatus('Téléchargement des catégories de films…');
      const vodCats = await client.getVodCategories();
      await saveVodCategories(vodCats);

      // Priorité : filtre utilisateur > frenchOnly > tout
      var vodCatsToFetch;
      if (selMovCatIds.length > 0) {
        var selMovSet = new Set(selMovCatIds.map(String));
        vodCatsToFetch = vodCats.filter(function(c) { return selMovSet.has(String(c.category_id)); });
        setStatus('Films : filtre utilisateur (' + vodCatsToFetch.length + ' catégories)…');
      } else if (frenchOnly) {
        vodCatsToFetch = vodCats.filter(function(c) { return isFrench(c.category_name); });
      } else {
        vodCatsToFetch = vodCats;
      }

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

      var seriesCatsToFetch;
      if (selSerCatIds.length > 0) {
        var selSerSet = new Set(selSerCatIds.map(String));
        seriesCatsToFetch = seriesCats.filter(function(c) { return selSerSet.has(String(c.category_id)); });
        setStatus('Séries : filtre utilisateur (' + seriesCatsToFetch.length + ' catégories)…');
      } else if (frenchOnly) {
        seriesCatsToFetch = seriesCats.filter(function(c) { return isFrench(c.category_name); });
      } else {
        seriesCatsToFetch = seriesCats;
      }

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
      await loadCatalogStore(loadCatalog, config.frenchOnly, selMovCatIds, selSerCatIds);

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
