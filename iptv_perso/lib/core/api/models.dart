// ============================================================
// models.dart — Modèles de données Xtream
// ============================================================

// --- Credentials du serveur ---
class XtreamCredentials {
  final String host;      // ex: "http://monserveur.com:8080"
  final String username;
  final String password;

  const XtreamCredentials({
    required this.host,
    required this.username,
    required this.password,
  });
}

// --- Catégorie (films OU séries) ---
class XtreamCategory {
  final String categoryId;
  final String categoryName;

  const XtreamCategory({
    required this.categoryId,
    required this.categoryName,
  });

  // Constructeur depuis le JSON reçu de l'API
  factory XtreamCategory.fromJson(Map<String, dynamic> json) {
    return XtreamCategory(
      categoryId: json['category_id'].toString(),
      categoryName: json['category_name'] as String,
    );
  }

  // Filtre : la catégorie est-elle en français ?
  // On cherche "FR", "FRENCH", "VF", "FRA" dans le nom (insensible à la casse)
  bool get isFrench {
    final name = categoryName.toUpperCase();
    return name.contains('FR') ||
        name.contains('FRENCH') ||
        name.contains('VF') ||
        name.contains('FRA');
  }
}

// --- Film (VOD stream) ---
class VodStream {
  final int streamId;
  final String name;
  final String? streamIcon;   // URL de l'affiche (peut être null)
  final String? categoryId;
  final String? releaseDate;  // Format variable selon les serveurs
  final double? rating;       // Note sur 10
  final String? plot;         // Synopsis

  const VodStream({
    required this.streamId,
    required this.name,
    this.streamIcon,
    this.categoryId,
    this.releaseDate,
    this.rating,
    this.plot,
  });

  factory VodStream.fromJson(Map<String, dynamic> json) {
    return VodStream(
      streamId: int.tryParse(json['stream_id'].toString()) ?? 0,
      name: json['name'] as String? ?? '',
      streamIcon: json['stream_icon'] as String?,
      categoryId: json['category_id']?.toString(),
      releaseDate: json['added'] as String?,  // Timestamp UNIX en général
      rating: double.tryParse(json['rating']?.toString() ?? ''),
      plot: json['plot'] as String?,
    );
  }

  // Construit l'URL de lecture du film
  String streamUrl(XtreamCredentials creds) {
    return '${creds.host}/movie/${creds.username}/${creds.password}/$streamId.mkv';
  }

  // Sérialisation vers JSON pour le cache Hive
  Map<String, dynamic> toJson() => {
    'stream_id': streamId,
    'name': name,
    'stream_icon': streamIcon,
    'category_id': categoryId,
    'added': releaseDate,
    'rating': rating?.toString(),
    'plot': plot,
  };
}

// --- Série ---
class XtreamSeries {
  final int seriesId;
  final String name;
  final String? cover;
  final String? categoryId;
  final String? plot;
  final double? rating;
  final String? releaseDate;

  const XtreamSeries({
    required this.seriesId,
    required this.name,
    this.cover,
    this.categoryId,
    this.plot,
    this.rating,
    this.releaseDate,
  });

  factory XtreamSeries.fromJson(Map<String, dynamic> json) {
    return XtreamSeries(
      seriesId: int.tryParse(json['series_id'].toString()) ?? 0,
      name: json['name'] as String? ?? '',
      cover: json['cover'] as String?,
      categoryId: json['category_id']?.toString(),
      plot: json['plot'] as String?,
      rating: double.tryParse(json['rating']?.toString() ?? ''),
      releaseDate: json['releaseDate'] as String?,
    );
  }

  // Sérialisation vers JSON pour le cache Hive
  Map<String, dynamic> toJson() => {
    'series_id': seriesId,
    'name': name,
    'cover': cover,
    'category_id': categoryId,
    'plot': plot,
    'rating': rating?.toString(),
    'releaseDate': releaseDate,
  };
}

// --- Épisode (dans le détail d'une série) ---
class SeriesEpisode {
  final int    episodeId;
  final String title;
  final int    episodeNum;
  final int    season;
  final String? containerExtension;  // "mkv", "mp4", etc.
  final String? plot;                // Synopsis de l'épisode (champ "info.plot")
  final int?   durationSecs;         // Durée en secondes  (champ "info.duration_secs")
  final String? thumbnail;           // Miniature de l'épisode (champ "info.movie_image")

  const SeriesEpisode({
    required this.episodeId,
    required this.title,
    required this.episodeNum,
    required this.season,
    this.containerExtension,
    this.plot,
    this.durationSecs,
    this.thumbnail,
  });

  factory SeriesEpisode.fromJson(Map<String, dynamic> json) {
    // Le sous-objet "info" contient synopsis, durée, miniature
    final info = json['info'] as Map<String, dynamic>? ?? {};
    return SeriesEpisode(
      episodeId:          int.tryParse(json['id'].toString()) ?? 0,
      title:              json['title'] as String? ?? '',
      episodeNum:         int.tryParse(json['episode_num'].toString()) ?? 0,
      season:             int.tryParse(json['season'].toString()) ?? 0,
      containerExtension: json['container_extension'] as String?,
      plot:               info['plot'] as String?,
      durationSecs:       int.tryParse(info['duration_secs']?.toString() ?? ''),
      thumbnail:          info['movie_image'] as String?,
    );
  }

  // Construit l'URL de lecture de l'épisode
  String streamUrl(XtreamCredentials creds) {
    final ext = containerExtension ?? 'mkv';
    return '${creds.host}/series/${creds.username}/${creds.password}/$episodeId.$ext';
  }

  // Formate la durée en "45 min" ou "1h 30min"
  String? get durationLabel {
    if (durationSecs == null || durationSecs! <= 0) return null;
    final h = durationSecs! ~/ 3600;
    final m = (durationSecs! % 3600) ~/ 60;
    if (h > 0) return '${h}h ${m.toString().padLeft(2, '0')}min';
    return '${m}min';
  }
}
