// ============================================================
// download_service.dart — Téléchargement de films et d'épisodes
// ============================================================
// Utilise Dio (déjà présent dans le projet) pour télécharger
// les fichiers vidéo en streaming (bloc par bloc).
//
// Répertoire de destination :
//   Android : [stockage externe]/IPTVPerso/Films/
//             [stockage externe]/IPTVPerso/[Nom de la série]/
//
// Note : sur Android 10+ (API 29+), l'accès au répertoire propre
// de l'application ne nécessite aucune permission.
// ============================================================
import 'dart:async';
import 'dart:io';

import 'package:dio/dio.dart';
import 'package:path_provider/path_provider.dart';

// ============================================================
// Types
// ============================================================

/// Progression du téléchargement émise périodiquement.
class DownloadProgress {
  final double received;   // Octets reçus
  final double total;      // Octets totaux (0 si inconnu)
  final double speedKBps;  // Vitesse en Ko/s

  const DownloadProgress({
    required this.received,
    required this.total,
    required this.speedKBps,
  });

  /// Pourcentage (0.0 à 1.0) — null si taille totale inconnue
  double? get fraction =>
      total > 0 ? (received / total).clamp(0.0, 1.0) : null;

  /// Texte "XMo / YMo" ou "XMo (taille inconnue)"
  String get sizeLabel {
    if (total > 0) {
      return '${_fmtSize(received)} / ${_fmtSize(total)}';
    }
    return '${_fmtSize(received)} (taille inconnue)';
  }

  /// Texte "↓ X Ko/s" ou "↓ X Mo/s"
  String get speedLabel {
    if (speedKBps >= 1024) {
      return '↓ ${(speedKBps / 1024).toStringAsFixed(1)} Mo/s';
    }
    return '↓ ${speedKBps.toStringAsFixed(0)} Ko/s';
  }

  /// Texte ETA "Reste Xmin Ys" — null si vitesse ou taille inconnues
  String? get etaLabel {
    if (total <= 0 || speedKBps <= 0) return null;
    final remainingKB = (total - received) / 1024;
    final etaSecs     = (remainingKB / speedKBps).round();
    final h = etaSecs ~/ 3600;
    final m = (etaSecs % 3600) ~/ 60;
    final s = etaSecs % 60;
    if (h > 0) return 'Reste ${h}h ${m.toString().padLeft(2, '0')}min';
    if (m > 0) return 'Reste ${m}min ${s.toString().padLeft(2, '0')}s';
    return 'Reste ${s}s';
  }

  static String _fmtSize(double bytes) {
    final gb = bytes / (1024 * 1024 * 1024);
    if (gb >= 1) return '${gb.toStringAsFixed(2)} Go';
    return '${(bytes / (1024 * 1024)).toStringAsFixed(1)} Mo';
  }
}

// ============================================================
// Service principal
// ============================================================

class DownloadService {
  static final Dio _dio = Dio(
    BaseOptions(
      connectTimeout: const Duration(seconds: 15),
      receiveTimeout: const Duration(minutes: 120), // fichiers volumineux
    ),
  );

  // --------------------------------------------------------
  // Obtenir le répertoire de base (sans permission requise)
  // --------------------------------------------------------
  static Future<Directory> _baseDir() async {
    // getExternalStorageDirectory → ex: /storage/emulated/0/Android/data/<pkg>/files
    final ext = await getExternalStorageDirectory();
    final base = Directory(
      '${ext?.path ?? (await getApplicationDocumentsDirectory()).path}'
      '/IPTVPerso',
    );
    if (!await base.exists()) await base.create(recursive: true);
    return base;
  }

  /// Répertoire pour les films
  static Future<Directory> moviesDir() async {
    final d = Directory('${(await _baseDir()).path}/Films');
    if (!await d.exists()) await d.create(recursive: true);
    return d;
  }

  /// Répertoire pour les épisodes d'une série
  static Future<Directory> seriesDir(String seriesName) async {
    final safe = _safeName(seriesName);
    final d    = Directory('${(await _baseDir()).path}/$safe');
    if (!await d.exists()) await d.create(recursive: true);
    return d;
  }

  // --------------------------------------------------------
  // Nettoyer un nom pour en faire un nom de dossier/fichier
  // --------------------------------------------------------
  static String _safeName(String name) =>
      name.replaceAll(RegExp(r'[<>:"/\\|?*\x00-\x1f]'), '_').trim();

  // --------------------------------------------------------
  // Télécharger un fichier
  //
  // Paramètres :
  //   url        : URL directe du flux Xtream
  //   filename   : Nom du fichier (avec extension)
  //   destDir    : Répertoire de destination (moviesDir ou seriesDir)
  //   onProgress : Callback émis ~toutes les 500 ms
  //   cancelToken: Pour annuler le téléchargement en cours
  //
  // Retourne le chemin complet du fichier téléchargé.
  // Lance une exception en cas d'erreur ou d'annulation.
  // --------------------------------------------------------
  static Future<String> downloadFile({
    required String    url,
    required String    filename,
    required Directory destDir,
    required void Function(DownloadProgress) onProgress,
    CancelToken? cancelToken,
  }) async {
    final dest = '${destDir.path}/${_safeName(filename)}';

    double received   = 0;
    double total      = 0;
    double speedKBps  = 0;
    int    lastEmitMs = 0;
    final  watch      = Stopwatch()..start();

    await _dio.download(
      url,
      dest,
      cancelToken: cancelToken,
      deleteOnError: true,
      onReceiveProgress: (int rcv, int tot) {
        received = rcv.toDouble();
        total    = tot > 0 ? tot.toDouble() : 0;

        final nowMs = watch.elapsedMilliseconds;
        // Émettre au maximum 1 signal toutes les 500 ms
        if (nowMs - lastEmitMs >= 500) {
          final elapsedS = nowMs / 1000;
          speedKBps = elapsedS > 0
              ? (received / elapsedS / 1024)
              : 0;
          onProgress(DownloadProgress(
            received:  received,
            total:     total,
            speedKBps: speedKBps,
          ));
          lastEmitMs = nowMs;
        }
      },
    );

    return dest;
  }

  // --------------------------------------------------------
  // Vérifier si un fichier existe déjà (évite re-téléchargement)
  // --------------------------------------------------------
  static Future<bool> fileExists(
      String filename, Directory destDir) async {
    return File('${destDir.path}/${_safeName(filename)}').exists();
  }
}
