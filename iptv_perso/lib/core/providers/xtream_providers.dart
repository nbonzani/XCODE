// ============================================================
// xtream_providers.dart — Providers Riverpod globaux
// ============================================================
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import '../api/xtream_client.dart';
import '../api/models.dart';

// --- Provider des credentials (chargés depuis le stockage sécurisé) ---
final credentialsProvider = FutureProvider<XtreamCredentials?>((ref) async {
  const storage = FlutterSecureStorage();
  final host     = await storage.read(key: 'xtream_host');
  final username = await storage.read(key: 'xtream_username');
  final password = await storage.read(key: 'xtream_password');

  if (host == null || username == null || password == null) return null;

  return XtreamCredentials(
    host: host,
    username: username,
    password: password,
  );
});

// --- Provider du client API (dépend des credentials) ---
final xtreamClientProvider = Provider<XtreamClient?>((ref) {
  final creds = ref.watch(credentialsProvider).valueOrNull;
  if (creds == null) return null;
  return XtreamClient(credentials: creds);
});

// --- Provider du catalogue films français ---
// Se rafraîchit automatiquement quand les credentials changent.
final frenchVodProvider = FutureProvider<List<VodStream>>((ref) async {
  final client = ref.watch(xtreamClientProvider);
  if (client == null) return [];
  return client.getAllFrenchVodStreams();
});

// --- Provider du catalogue séries françaises ---
final frenchSeriesProvider = FutureProvider<List<XtreamSeries>>((ref) async {
  final client = ref.watch(xtreamClientProvider);
  if (client == null) return [];
  return client.getAllFrenchSeries();
});
