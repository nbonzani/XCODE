// ============================================================
// player_screen.dart — Lecteur vidéo avec support HDMI
// ============================================================
// Utilise media_kit (basé sur libmpv) pour le décodage matériel.
// Supporte la lecture via câble USB-C/HDMI avec économie batterie.
// ============================================================
import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:media_kit/media_kit.dart';
import 'package:media_kit_video/media_kit_video.dart';
import 'package:go_router/go_router.dart';

import '../../core/providers/player_provider.dart';
import 'hdmi_controller.dart';

class PlayerScreen extends ConsumerStatefulWidget {
  const PlayerScreen({super.key});

  @override
  ConsumerState<PlayerScreen> createState() => _PlayerScreenState();
}

class _PlayerScreenState extends ConsumerState<PlayerScreen> {
  // --- Lecteur media_kit ---
  late final Player          _player;
  late final VideoController _controller;

  // --- Gestion HDMI ---
  final HdmiController _hdmi = HdmiController();

  // --- État de l'interface ---
  bool   _showControls    = true;
  bool   _hdmiModeActive  = false;
  bool   _isFullscreen    = false;
  Timer? _hideControlsTimer;

  @override
  void initState() {
    super.initState();

    // Création du lecteur avec décodage matériel activé
    _player = Player(
      configuration: const PlayerConfiguration(
        // Déléguer le décodage au GPU du processeur (Snapdragon/Exynos)
        // Réduit significativement la consommation CPU et batterie
        // Note: la configuration hwdec est gérée au niveau de la plateforme
        logLevel: MPVLogLevel.warn,
      ),
    );

    _controller = VideoController(_player);

    // Démarrer la lecture dès que l'URL est disponible
    WidgetsBinding.instance.addPostFrameCallback((_) async {
      final state = ref.read(playerStateProvider);
      if (state != null) {
        _player.open(Media(state.url));
        // Toujours activer le WakeLock (empêche la mise en veille du CPU)
        await _hdmi.enableHdmiMode();
        // Si l'utilisateur a choisi la TV : éteindre l'écran immédiatement
        if (state.playOnTv) {
          await _hdmi.dimScreen();
          if (mounted) setState(() => _hdmiModeActive = true);
        }
      }
      // Masquer les contrôles automatiquement après 3 s au démarrage
      _startHideTimer();
    });

    // Passer en plein écran et masquer les barres système
    SystemChrome.setEnabledSystemUIMode(SystemUiMode.immersiveSticky);
    SystemChrome.setPreferredOrientations([
      DeviceOrientation.landscapeLeft,
      DeviceOrientation.landscapeRight,
    ]);
  }

  @override
  void dispose() {
    // Annuler le timer d'auto-masquage pour éviter les fuites mémoire
    _hideControlsTimer?.cancel();
    // Nettoyage à la fermeture du lecteur
    _hdmi.disableHdmiMode();
    _player.dispose();

    // Restaurer l'orientation et les barres système
    SystemChrome.setEnabledSystemUIMode(SystemUiMode.edgeToEdge);
    SystemChrome.setPreferredOrientations([
      DeviceOrientation.portraitUp,
      DeviceOrientation.landscapeLeft,
      DeviceOrientation.landscapeRight,
    ]);

    // Nettoyer l'état du provider
    ref.read(playerStateProvider.notifier).clear();
    super.dispose();
  }

  // --------------------------------------------------------
  // Basculer affichage/masquage des contrôles
  // --------------------------------------------------------
  void _toggleControls() {
    setState(() => _showControls = !_showControls);
    if (_showControls) {
      _startHideTimer();
    } else {
      _hideControlsTimer?.cancel();
    }
  }

  // --------------------------------------------------------
  // Lancer (ou relancer) le minuteur d'auto-masquage
  // Les contrôles disparaissent automatiquement après 3 s
  // --------------------------------------------------------
  void _startHideTimer() {
    _hideControlsTimer?.cancel();
    _hideControlsTimer = Timer(const Duration(seconds: 3), () {
      if (mounted) {
        setState(() => _showControls = false);
      }
    });
  }

  // --------------------------------------------------------
  // Activer le mode économie batterie (écran éteint)
  // --------------------------------------------------------
  Future<void> _toggleHdmiMode() async {
    if (_hdmiModeActive) {
      await _hdmi.restoreScreen();
      setState(() => _hdmiModeActive = false);
    } else {
      await _hdmi.dimScreen();
      setState(() => _hdmiModeActive = true);
    }
  }

  // --------------------------------------------------------
  // Construction de l'interface
  // --------------------------------------------------------
  @override
  Widget build(BuildContext context) {
    final playerState = ref.watch(playerStateProvider);

    if (playerState == null) {
      // Aucun média sélectionné — retour au catalogue
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted) context.go('/catalogue');
      });
      return const Scaffold(
        body: Center(child: CircularProgressIndicator()),
      );
    }

    return Scaffold(
      backgroundColor: Colors.black,
      body: GestureDetector(
        onTap: _toggleControls,
        child: Stack(
          fit: StackFit.expand,
          children: [
            // ---- Vidéo ----
            Video(controller: _controller),

            // ---- Overlay "mode HDMI" ----
            // Quand l'écran est éteint, on affiche un écran noir
            // avec un bouton pour le rallumer
            if (_hdmiModeActive)
              _HdmiOverlay(onWake: _toggleHdmiMode),

            // ---- Contrôles ----
            if (_showControls && !_hdmiModeActive)
              _ControlsOverlay(
                player:      _player,
                title:       playerState.title,
                hdmiActive:  _hdmiModeActive,
                onHdmiToggle: _toggleHdmiMode,
                onClose: () {
                  _player.stop();
                  context.go('/catalogue');
                },
              ),
          ],
        ),
      ),
    );
  }
}

// ============================================================
// Overlay de contrôles du lecteur
// ============================================================
class _ControlsOverlay extends StatelessWidget {
  final Player    player;
  final String    title;
  final bool      hdmiActive;
  final VoidCallback onHdmiToggle;
  final VoidCallback onClose;

  const _ControlsOverlay({
    required this.player,
    required this.title,
    required this.hdmiActive,
    required this.onHdmiToggle,
    required this.onClose,
  });

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        // --- Barre supérieure ---
        _TopBar(title: title, onClose: onClose),
        const Spacer(),
        // --- Contrôles centraux ---
        _CenterControls(player: player),
        const Spacer(),
        // --- Barre inférieure ---
        _BottomBar(player: player, onHdmiToggle: onHdmiToggle),
      ],
    );
  }
}

// --- Barre du haut (titre + fermer) ---
class _TopBar extends StatelessWidget {
  final String title;
  final VoidCallback onClose;

  const _TopBar({required this.title, required this.onClose});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
      decoration: const BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topCenter,
          end:   Alignment.bottomCenter,
          colors: [Colors.black87, Colors.transparent],
        ),
      ),
      child: SafeArea(
        child: Row(
          children: [
            IconButton(
              icon: const Icon(Icons.arrow_back, color: Colors.white),
              onPressed: onClose,
            ),
            Expanded(
              child: Text(
                title,
                style: const TextStyle(
                    color: Colors.white,
                    fontSize: 16,
                    fontWeight: FontWeight.w600),
                overflow: TextOverflow.ellipsis,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

// --- Boutons play/pause/seek centraux ---
class _CenterControls extends StatelessWidget {
  final Player player;
  const _CenterControls({required this.player});

  @override
  Widget build(BuildContext context) {
    return StreamBuilder<bool>(
      stream: player.stream.playing,
      builder: (_, snap) {
        final isPlaying = snap.data ?? false;
        return Row(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            // Reculer de 10s
            IconButton(
              iconSize: 40,
              icon: const Icon(Icons.replay_10, color: Colors.white),
              onPressed: () async {
                final pos = player.state.position;
                await player.seek(pos - const Duration(seconds: 10));
              },
            ),
            const SizedBox(width: 24),
            // Play / Pause
            Container(
              decoration: const BoxDecoration(
                color: Colors.white24,
                shape: BoxShape.circle,
              ),
              child: IconButton(
                iconSize: 52,
                icon: Icon(
                  isPlaying ? Icons.pause : Icons.play_arrow,
                  color: Colors.white,
                ),
                onPressed: () => player.playOrPause(),
              ),
            ),
            const SizedBox(width: 24),
            // Avancer de 10s
            IconButton(
              iconSize: 40,
              icon: const Icon(Icons.forward_10, color: Colors.white),
              onPressed: () async {
                final pos = player.state.position;
                await player.seek(pos + const Duration(seconds: 10));
              },
            ),
          ],
        );
      },
    );
  }
}

// --- Barre du bas (progression + bouton HDMI) ---
class _BottomBar extends StatelessWidget {
  final Player       player;
  final VoidCallback onHdmiToggle;

  const _BottomBar({required this.player, required this.onHdmiToggle});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
      decoration: const BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.bottomCenter,
          end:   Alignment.topCenter,
          colors: [Colors.black87, Colors.transparent],
        ),
      ),
      child: SafeArea(
        top: false,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            // Barre de progression
            StreamBuilder<Duration>(
              stream: player.stream.position,
              builder: (_, posSnap) {
                return StreamBuilder<Duration>(
                  stream: player.stream.duration,
                  builder: (_, durSnap) {
                    final position = posSnap.data ?? Duration.zero;
                    final duration = durSnap.data ?? Duration.zero;
                    final progress = duration.inMilliseconds > 0
                        ? position.inMilliseconds / duration.inMilliseconds
                        : 0.0;

                    return Column(
                      children: [
                        SliderTheme(
                          data: SliderTheme.of(context).copyWith(
                            thumbShape: const RoundSliderThumbShape(
                                enabledThumbRadius: 6),
                            trackHeight: 3,
                          ),
                          child: Slider(
                            value: progress.clamp(0.0, 1.0),
                            onChanged: (v) => player.seek(
                              Duration(
                                  milliseconds:
                                      (v * duration.inMilliseconds).round()),
                            ),
                          ),
                        ),
                        Padding(
                          padding: const EdgeInsets.symmetric(horizontal: 8),
                          child: Row(
                            mainAxisAlignment: MainAxisAlignment.spaceBetween,
                            children: [
                              Text(_fmt(position),
                                  style: const TextStyle(
                                      color: Colors.white70, fontSize: 12)),
                              Text(_fmt(duration),
                                  style: const TextStyle(
                                      color: Colors.white70, fontSize: 12)),
                            ],
                          ),
                        ),
                      ],
                    );
                  },
                );
              },
            ),
            // Bouton mode HDMI / économie batterie
            Row(
              mainAxisAlignment: MainAxisAlignment.end,
              children: [
                TextButton.icon(
                  onPressed: onHdmiToggle,
                  icon: const Icon(Icons.tv, color: Colors.white70, size: 18),
                  label: const Text(
                    'Mode TV (écran éteint)',
                    style: TextStyle(color: Colors.white70, fontSize: 12),
                  ),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }

  /// Formate une durée en mm:ss ou hh:mm:ss
  String _fmt(Duration d) {
    final h  = d.inHours;
    final m  = d.inMinutes.remainder(60).toString().padLeft(2, '0');
    final s  = d.inSeconds.remainder(60).toString().padLeft(2, '0');
    return h > 0 ? '$h:$m:$s' : '$m:$s';
  }
}

// ============================================================
// Overlay "mode HDMI" — écran noir avec bouton de réveil
// ============================================================
class _HdmiOverlay extends StatelessWidget {
  final VoidCallback onWake;
  const _HdmiOverlay({required this.onWake});

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onWake,
      child: Container(
        color: Colors.black,
        child: Center(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Icon(Icons.tv, color: Colors.white24, size: 64),
              const SizedBox(height: 16),
              const Text(
                'Lecture en cours sur TV',
                style: TextStyle(color: Colors.white38, fontSize: 16),
              ),
              const SizedBox(height: 8),
              const Text(
                'Touchez l\'écran pour afficher les contrôles',
                style: TextStyle(color: Colors.white24, fontSize: 13),
              ),
              const SizedBox(height: 32),
              OutlinedButton.icon(
                onPressed: onWake,
                icon: const Icon(Icons.brightness_medium),
                label: const Text('Rallumer l\'écran'),
                style: OutlinedButton.styleFrom(
                  foregroundColor: Colors.white54,
                  side: const BorderSide(color: Colors.white24),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
