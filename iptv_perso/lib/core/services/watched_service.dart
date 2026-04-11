// ============================================================
// watched_service.dart — Suivi des épisodes visionnés
// ============================================================
// Stocke l'état "vu / non vu" de chaque épisode dans Hive.
// Identifié par l'episodeId (entier unique fourni par l'API Xtream).
//
// Usage :
//   await WatchedService.markWatched(12345);
//   final isVu = await WatchedService.isWatched(12345);
//   final vus = await WatchedService.getWatchedSet([12345, 67890, ...]);
// ============================================================
import 'package:hive_flutter/hive_flutter.dart';

class WatchedService {
  static const String _boxName = 'watched_episodes';

  // --------------------------------------------------------
  // Ouverture paresseuse de la boîte Hive
  // --------------------------------------------------------
  static Future<Box<dynamic>> _openBox() async {
    if (Hive.isBoxOpen(_boxName)) return Hive.box(_boxName);
    return Hive.openBox(_boxName);
  }

  // --------------------------------------------------------
  // Vérifier si un épisode est marqué "vu"
  // --------------------------------------------------------
  static Future<bool> isWatched(int episodeId) async {
    final box = await _openBox();
    return box.get(episodeId.toString()) == true;
  }

  // --------------------------------------------------------
  // Marquer un épisode comme "vu"
  // --------------------------------------------------------
  static Future<void> markWatched(int episodeId) async {
    final box = await _openBox();
    await box.put(episodeId.toString(), true);
  }

  // --------------------------------------------------------
  // Retirer le marquage "vu" d'un épisode
  // --------------------------------------------------------
  static Future<void> markUnwatched(int episodeId) async {
    final box = await _openBox();
    await box.delete(episodeId.toString());
  }

  // --------------------------------------------------------
  // Basculer l'état vu/non vu d'un épisode
  // Retourne le nouvel état : true = vu, false = non vu
  // --------------------------------------------------------
  static Future<bool> toggleWatched(int episodeId) async {
    final currently = await isWatched(episodeId);
    if (currently) {
      await markUnwatched(episodeId);
      return false;
    } else {
      await markWatched(episodeId);
      return true;
    }
  }

  // --------------------------------------------------------
  // Obtenir l'ensemble des IDs d'épisodes vus parmi une liste
  // Permet de charger le statut de tous les épisodes d'une
  // série en un seul appel (plus efficace que N appels séparés)
  // --------------------------------------------------------
  static Future<Set<int>> getWatchedSet(List<int> episodeIds) async {
    final box  = await _openBox();
    final seen = <int>{};
    for (final id in episodeIds) {
      if (box.get(id.toString()) == true) {
        seen.add(id);
      }
    }
    return seen;
  }

  // --------------------------------------------------------
  // Effacer tout l'historique (réinitialisation complète)
  // --------------------------------------------------------
  static Future<void> clearAll() async {
    final box = await _openBox();
    await box.clear();
  }
}
