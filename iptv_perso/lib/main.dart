// ============================================================
// main.dart — Point d'entrée de l'application IPTV Perso
// ============================================================
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:hive_flutter/hive_flutter.dart';
import 'package:media_kit/media_kit.dart';

import 'features/settings/settings_screen.dart';
import 'features/catalogue/catalogue_screen.dart';
import 'features/catalogue/search_screen.dart';
import 'features/player/player_screen.dart';
import 'features/series/series_detail_screen.dart';
import 'core/api/models.dart';
import 'core/providers/player_provider.dart';

void main() async {
  // Requis avant tout code Flutter asynchrone au démarrage
  WidgetsFlutterBinding.ensureInitialized();

  // Initialisation de media_kit (doit être appelé avant toute lecture vidéo)
  MediaKit.ensureInitialized();

  // Initialisation de Hive dans le répertoire de documents de l'application
  await Hive.initFlutter();

  runApp(
    // ProviderScope est le conteneur global de tous les providers Riverpod
    const ProviderScope(child: IPTVApp()),
  );
}

// ============================================================
// Configuration du routeur (go_router)
// ============================================================
final _router = GoRouter(
  // L'écran de démarrage est toujours le paramétrage.
  // settings_screen.dart redirigera automatiquement vers /catalogue
  // si des credentials valides sont déjà enregistrés.
  initialLocation: '/settings',
  routes: [
    GoRoute(
      path: '/settings',
      builder: (context, state) => const SettingsScreen(),
    ),
    GoRoute(
      path: '/catalogue',
      builder: (context, state) => const CatalogueScreen(),
    ),
    GoRoute(
      path: '/search',
      builder: (context, state) {
        // Le type ('vod' ou 'series') est passé en query parameter
        final type = state.uri.queryParameters['type'] ?? 'vod';
        return SearchScreen(initialType: type);
      },
    ),
    GoRoute(
      path: '/player',
      // L'URL et le titre sont passés via le provider PlayerStateNotifier
      // (voir core/providers/player_provider.dart)
      builder: (context, state) => const PlayerScreen(),
    ),
    GoRoute(
      path: '/series',
      // L'objet XtreamSeries est passé via state.extra
      // Navigation : context.push('/series', extra: maSerie)
      builder: (context, state) {
        final series = state.extra as XtreamSeries;
        return SeriesDetailScreen(series: series);
      },
    ),
  ],
);

// ============================================================
// Widget racine de l'application
// ============================================================
class IPTVApp extends StatelessWidget {
  const IPTVApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp.router(
      title: 'IPTV Perso',
      debugShowCheckedModeBanner: false,
      // Thème sombre avec accent bleu
      theme: ThemeData.dark(useMaterial3: true).copyWith(
        colorScheme: ColorScheme.fromSeed(
          seedColor: const Color(0xFF1565C0),
          brightness: Brightness.dark,
        ),
        appBarTheme: const AppBarTheme(
          backgroundColor: Color(0xFF0D1B2A),
          elevation: 0,
        ),
        scaffoldBackgroundColor: const Color(0xFF0D1B2A),
      ),
      routerConfig: _router,
    );
  }
}
