// ============================================================
// catalogue_cache.dart — Cache local Hive pour le catalogue
// ============================================================
// Hive stocke des données clé-valeur de façon très rapide.
// On stocke les films et séries sous forme de listes de Maps JSON,
// ce qui évite d'avoir à générer des adaptateurs Hive typés.
// ============================================================
import 'package:hive_flutter/hive_flutter.dart';
import '../api/models.dart';

class CatalogueCache {
  // Noms des "boîtes" Hive (= tables dans une BDD)
  static const String _vodBoxName   = 'vod_cache';
  static const String _seriesBoxName = 'series_cache';

  // Clés de stockage à l'intérieur des boîtes
  static const String _vodKey    = 'vod_streams';
  static const String _seriesKey = 'series_list';

  // --------------------------------------------------------
  // Accès aux boîtes Hive (ouverture paresseuse)
  // --------------------------------------------------------
  static Future<Box<dynamic>> _openBox(String name) async {
    if (Hive.isBoxOpen(name)) return Hive.box(name);
    return Hive.openBox(name);
  }

  // --------------------------------------------------------
  // Films (VOD)
  // --------------------------------------------------------

  /// Sauvegarde la liste des films en cache.
  static Future<void> saveVodStreams(List<VodStream> streams) async {
    final box = await _openBox(_vodBoxName);
    // On convertit chaque VodStream en Map<String, dynamic> via toJson()
    final jsonList = streams.map((s) => s.toJson()).toList();
    await box.put(_vodKey, jsonList);
  }

  /// Charge la liste des films depuis le cache.
  /// Retourne une liste vide si le cache est vide.
  static Future<List<VodStream>> loadVodStreams() async {
    final box = await _openBox(_vodBoxName);
    final raw = box.get(_vodKey);
    if (raw == null) return [];

    // Hive stocke les Maps avec des clés dynamiques — on les convertit en String
    final list = (raw as List<dynamic>);
    return list
        .map((e) => VodStream.fromJson(Map<String, dynamic>.from(e as Map)))
        .toList();
  }

  /// Indique si le cache films est vide.
  static Future<bool> isVodCacheEmpty() async {
    final box = await _openBox(_vodBoxName);
    return box.get(_vodKey) == null;
  }

  // --------------------------------------------------------
  // Séries
  // --------------------------------------------------------

  /// Sauvegarde la liste des séries en cache.
  static Future<void> saveSeriesList(List<XtreamSeries> series) async {
    final box = await _openBox(_seriesBoxName);
    final jsonList = series.map((s) => s.toJson()).toList();
    await box.put(_seriesKey, jsonList);
  }

  /// Charge la liste des séries depuis le cache.
  static Future<List<XtreamSeries>> loadSeriesList() async {
    final box = await _openBox(_seriesBoxName);
    final raw = box.get(_seriesKey);
    if (raw == null) return [];

    final list = (raw as List<dynamic>);
    return list
        .map((e) => XtreamSeries.fromJson(Map<String, dynamic>.from(e as Map)))
        .toList();
  }

  /// Indique si le cache séries est vide.
  static Future<bool> isSeriesCacheEmpty() async {
    final box = await _openBox(_seriesBoxName);
    return box.get(_seriesKey) == null;
  }

  // --------------------------------------------------------
  // Gestion globale
  // --------------------------------------------------------

  /// Vide entièrement le cache (à appeler lors d'un changement de serveur).
  static Future<void> clearAll() async {
    final vod    = await _openBox(_vodBoxName);
    final series = await _openBox(_seriesBoxName);
    await vod.clear();
    await series.clear();
  }
}
