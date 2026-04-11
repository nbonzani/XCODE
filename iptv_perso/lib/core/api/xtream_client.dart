// ============================================================
// xtream_client.dart — Client Dio pour l'API Xtream Codes
// ============================================================
import 'package:dio/dio.dart';
import 'models.dart';

class XtreamClient {
  final Dio _dio;
  final XtreamCredentials credentials;

  XtreamClient({required this.credentials})
      : _dio = Dio(BaseOptions(
          // Timeout de connexion : 10 secondes
          connectTimeout: const Duration(seconds: 10),
          // Timeout de réception : 30 secondes (les listes peuvent être longues)
          receiveTimeout: const Duration(seconds: 30),
        ));

  // --- URL de base pour toutes les requêtes API ---
  String get _baseUrl =>
      '${credentials.host}/player_api.php'
      '?username=${credentials.username}'
      '&password=${credentials.password}';

  // --------------------------------------------------------
  // Méthode générique : effectue une requête GET et retourne
  // la réponse sous forme de Map ou List selon l'action.
  // --------------------------------------------------------
  Future<dynamic> _get(String action, [Map<String, String>? extra]) async {
    // Construction de l'URL avec l'action
    final url = '$_baseUrl&action=$action';
    try {
      final response = await _dio.get<dynamic>(url, queryParameters: extra);
      if (response.statusCode == 200) {
        return response.data;
      } else {
        throw XtreamException(
            'Erreur HTTP ${response.statusCode} pour l\'action $action');
      }
    } on DioException catch (e) {
      // On transforme l'exception Dio en une exception métier lisible
      throw XtreamException(_parseDioError(e));
    }
  }

  // --------------------------------------------------------
  // Test de connexion : vérifie les credentials
  // Retourne true si le serveur répond correctement.
  // --------------------------------------------------------
  Future<bool> testConnection() async {
    try {
      final data = await _get('get_live_categories');
      // Si on reçoit une liste (même vide), les credentials sont valides
      return data is List;
    } on XtreamException {
      return false;
    }
  }

  // --------------------------------------------------------
  // Récupère toutes les catégories VOD (films)
  // --------------------------------------------------------
  Future<List<XtreamCategory>> getVodCategories() async {
    final data = await _get('get_vod_categories') as List<dynamic>;
    return data
        .map((e) => XtreamCategory.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  // --------------------------------------------------------
  // Récupère les catégories VOD filtrées sur le français
  // --------------------------------------------------------
  Future<List<XtreamCategory>> getFrenchVodCategories() async {
    final all = await getVodCategories();
    return all.where((cat) => cat.isFrench).toList();
  }

  // --------------------------------------------------------
  // Récupère tous les films d'une catégorie donnée
  // --------------------------------------------------------
  Future<List<VodStream>> getVodStreams(String categoryId) async {
    final data = await _get('get_vod_streams') as List<dynamic>;
    return data
        .map((e) => VodStream.fromJson(e as Map<String, dynamic>))
        // Filtre uniquement les films de la catégorie demandée
        .where((v) => v.categoryId == categoryId)
        .toList();
  }

  // --------------------------------------------------------
  // Récupère TOUS les films français (toutes catégories FR)
  // C'est la méthode principale pour alimenter le catalogue.
  // Attention : peut être long (plusieurs secondes) selon le
  // nombre de films sur le serveur.
  // --------------------------------------------------------
  Future<List<VodStream>> getAllFrenchVodStreams() async {
    // 1. Récupère toutes les catégories françaises
    final frenchCategories = await getFrenchVodCategories();
    final frenchCategoryIds = frenchCategories.map((c) => c.categoryId).toSet();

    // 2. Récupère la liste complète des films (un seul appel API)
    final data = await _get('get_vod_streams') as List<dynamic>;

    // 3. Filtre sur les catégories françaises
    return data
        .map((e) => VodStream.fromJson(e as Map<String, dynamic>))
        .where((v) => frenchCategoryIds.contains(v.categoryId))
        .toList();
  }

  // --------------------------------------------------------
  // Mêmes méthodes pour les séries
  // --------------------------------------------------------
  Future<List<XtreamCategory>> getSeriesCategories() async {
    final data = await _get('get_series_categories') as List<dynamic>;
    return data
        .map((e) => XtreamCategory.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  Future<List<XtreamSeries>> getAllFrenchSeries() async {
    final frenchCategories = await getSeriesCategories()
        .then((list) => list.where((c) => c.isFrench).toSet());
    final frenchCategoryIds = frenchCategories.map((c) => c.categoryId).toSet();

    final data = await _get('get_series') as List<dynamic>;
    return data
        .map((e) => XtreamSeries.fromJson(e as Map<String, dynamic>))
        .where((s) => frenchCategoryIds.contains(s.categoryId))
        .toList();
  }

  // --------------------------------------------------------
  // Récupère les épisodes d'une série (par son ID)
  // --------------------------------------------------------
  Future<List<SeriesEpisode>> getSeriesEpisodes(int seriesId) async {
    final data = await _get(
      'get_series_info',
      {'series_id': seriesId.toString()},
    ) as Map<String, dynamic>;

    // L'API retourne les épisodes groupés par saison :
    // { "episodes": { "1": [...], "2": [...] } }
    final episodesMap = data['episodes'] as Map<String, dynamic>? ?? {};
    final allEpisodes = <SeriesEpisode>[];

    for (final seasonEntry in episodesMap.entries) {
      final episodeList = seasonEntry.value as List<dynamic>;
      for (final ep in episodeList) {
        allEpisodes.add(SeriesEpisode.fromJson(ep as Map<String, dynamic>));
      }
    }

    // Tri par saison puis par numéro d'épisode
    allEpisodes.sort((a, b) {
      final seasonCmp = a.season.compareTo(b.season);
      if (seasonCmp != 0) return seasonCmp;
      return a.episodeNum.compareTo(b.episodeNum);
    });

    return allEpisodes;
  }

  // --------------------------------------------------------
  // Traduction des erreurs Dio en messages lisibles
  // --------------------------------------------------------
  String _parseDioError(DioException e) {
    switch (e.type) {
      case DioExceptionType.connectionTimeout:
        return 'Délai de connexion dépassé. Vérifiez l\'adresse du serveur.';
      case DioExceptionType.receiveTimeout:
        return 'Le serveur met trop de temps à répondre.';
      case DioExceptionType.connectionError:
        return 'Impossible de joindre le serveur. Vérifiez votre réseau.';
      default:
        return 'Erreur réseau : ${e.message}';
    }
  }
}

// --------------------------------------------------------
// Exception métier personnalisée
// --------------------------------------------------------
class XtreamException implements Exception {
  final String message;
  const XtreamException(this.message);

  @override
  String toString() => 'XtreamException: $message';
}
