// ============================================================
// series_providers.dart — Providers pour les données de séries
// ============================================================
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../api/models.dart';
import 'xtream_providers.dart';

/// Provider des épisodes d'une série, identifiée par son seriesId.
///
/// Utilise FutureProvider.family : un provider distinct est créé
/// pour chaque seriesId différent, avec cache automatique.
///
/// Usage :
///   final epAsync = ref.watch(seriesEpisodesProvider(serie.seriesId));
final seriesEpisodesProvider =
    FutureProvider.family<List<SeriesEpisode>, int>((ref, seriesId) async {
  final client = ref.watch(xtreamClientProvider);
  if (client == null) return [];
  return client.getSeriesEpisodes(seriesId);
});

/// Provider des catégories VOD françaises.
/// Utilisé dans les filtres du catalogue Films.
final vodCategoriesProvider =
    FutureProvider<List<XtreamCategory>>((ref) async {
  final client = ref.watch(xtreamClientProvider);
  if (client == null) return [];
  return client.getFrenchVodCategories();
});

/// Provider des catégories Séries françaises.
/// Utilisé dans les filtres du catalogue Séries.
final seriesCategoriesProvider =
    FutureProvider<List<XtreamCategory>>((ref) async {
  final client = ref.watch(xtreamClientProvider);
  if (client == null) return [];
  // Filtre les catégories sur le même critère que pour les films
  final all = await client.getSeriesCategories();
  return all.where((c) => c.isFrench).toList();
});
