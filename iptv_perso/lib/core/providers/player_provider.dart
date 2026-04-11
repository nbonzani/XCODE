// ============================================================
// player_provider.dart — État global du lecteur vidéo
// ============================================================
import 'package:flutter_riverpod/flutter_riverpod.dart';

/// Données du média en cours de lecture.
class PlayerState {
  final String url;
  final String title;
  final String? posterUrl;
  /// true = lecture sur TV via câble HDMI (écran téléphone éteint)
  /// false = lecture normale sur l'écran du téléphone
  final bool playOnTv;

  const PlayerState({
    required this.url,
    required this.title,
    this.posterUrl,
    this.playOnTv = false,
  });
}

/// Notifier qui gère l'état du lecteur.
class PlayerStateNotifier extends StateNotifier<PlayerState?> {
  PlayerStateNotifier() : super(null);

  /// Prépare la lecture d'un média.
  void play({
    required String url,
    required String title,
    String? posterUrl,
    bool playOnTv = false,
  }) {
    state = PlayerState(
      url: url,
      title: title,
      posterUrl: posterUrl,
      playOnTv: playOnTv,
    );
  }

  /// Réinitialise l'état (ex: fermeture du lecteur).
  void clear() => state = null;
}

/// Provider global — accessible depuis n'importe quel widget.
final playerStateProvider =
    StateNotifierProvider<PlayerStateNotifier, PlayerState?>(
  (ref) => PlayerStateNotifier(),
);
