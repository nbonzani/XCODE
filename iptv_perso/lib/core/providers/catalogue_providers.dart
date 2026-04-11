// ============================================================
// catalogue_providers.dart — Providers avec cache Hive intégré
// ============================================================
// Ces providers améliorent frenchVodProvider / frenchSeriesProvider
// en ajoutant une couche de cache local (Hive) :
//   1. Si le cache est non vide → retour immédiat (aucun appel réseau)
//   2. Si le cache est vide → appel API + sauvegarde en cache
// ============================================================
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../api/models.dart';
import '../cache/catalogue_cache.dart';
import 'xtream_providers.dart';

/// Provider des films français avec cache.
final cachedVodProvider = FutureProvider<List<VodStream>>((ref) async {
  // Étape 1 : vérifier le cache local
  if (!await CatalogueCache.isVodCacheEmpty()) {
    return CatalogueCache.loadVodStreams();
  }

  // Étape 2 : cache vide → appel API Xtream
  final client = ref.watch(xtreamClientProvider);
  if (client == null) return [];

  final streams = await client.getAllFrenchVodStreams();

  // Étape 3 : sauvegarder pour les prochains lancements
  if (streams.isNotEmpty) {
    await CatalogueCache.saveVodStreams(streams);
  }

  return streams;
});

/// Provider des séries françaises avec cache.
final cachedSeriesProvider = FutureProvider<List<XtreamSeries>>((ref) async {
  if (!await CatalogueCache.isSeriesCacheEmpty()) {
    return CatalogueCache.loadSeriesList();
  }

  final client = ref.watch(xtreamClientProvider);
  if (client == null) return [];

  final series = await client.getAllFrenchSeries();

  if (series.isNotEmpty) {
    await CatalogueCache.saveSeriesList(series);
  }

  return series;
});
