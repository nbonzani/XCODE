// ============================================================
// series_detail_screen.dart — Écran détail d'une série
// ============================================================
// Affiche :
//   - Couverture + titre + note + synopsis
//   - Liste des saisons (expansibles)
//   - Épisodes avec statut vu/non vu
//   - Tap  → lire l'épisode
//   - Appui long → basculer vu/non vu sans lire
// ============================================================
import 'dart:async';

import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/api/models.dart';
import '../../core/providers/series_providers.dart';
import '../../core/providers/player_provider.dart';
import '../../core/providers/xtream_providers.dart';
import '../../core/services/watched_service.dart';
import '../../core/widgets/screen_choice_sheet.dart';

class SeriesDetailScreen extends ConsumerStatefulWidget {
  final XtreamSeries series;

  const SeriesDetailScreen({super.key, required this.series});

  @override
  ConsumerState<SeriesDetailScreen> createState() => _SeriesDetailScreenState();
}

class _SeriesDetailScreenState extends ConsumerState<SeriesDetailScreen> {
  // IDs des épisodes déjà vus — chargés depuis Hive au démarrage
  Set<int> _watchedIds   = {};
  bool     _watchedReady = false; // Évite de recharger inutilement

  // --------------------------------------------------------
  // Chargement du statut "vu" pour tous les épisodes
  // --------------------------------------------------------
  Future<void> _loadWatchedStatus(List<SeriesEpisode> episodes) async {
    if (_watchedReady) return; // Déjà chargé
    final ids     = episodes.map((e) => e.episodeId).toList();
    final watched = await WatchedService.getWatchedSet(ids);
    if (mounted) {
      setState(() {
        _watchedIds   = watched;
        _watchedReady = true;
      });
    }
  }

  // --------------------------------------------------------
  // Basculer vu/non vu (appui long sur un épisode)
  // --------------------------------------------------------
  Future<void> _toggleWatched(SeriesEpisode episode) async {
    final nowWatched = await WatchedService.toggleWatched(episode.episodeId);
    if (mounted) {
      setState(() {
        if (nowWatched) {
          _watchedIds.add(episode.episodeId);
        } else {
          _watchedIds.remove(episode.episodeId);
        }
      });
      // Petit retour visuel
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
            nowWatched
                ? '✓ Marqué comme vu'
                : 'Marqué comme non vu',
          ),
          duration: const Duration(seconds: 1),
          behavior: SnackBarBehavior.floating,
        ),
      );
    }
  }

  // --------------------------------------------------------
  // Lancer la lecture d'un épisode
  // --------------------------------------------------------
  Future<void> _playEpisode(
      BuildContext context, SeriesEpisode episode) async {
    final creds = ref.read(credentialsProvider).valueOrNull;
    if (creds == null) return;

    // Label de l'épisode : "S01E03 Titre"
    final label =
        'S${episode.season.toString().padLeft(2, '0')}'
        'E${episode.episodeNum.toString().padLeft(2, '0')}'
        '${episode.title.isNotEmpty ? '  ${episode.title}' : ''}';

    final playOnTv = await showScreenChoiceSheet(
      context,
      title:     '${widget.series.name}\n$label',
      posterUrl: widget.series.cover,
    );
    if (playOnTv == null || !context.mounted) return;

    // Marquer automatiquement comme vu au lancement
    await WatchedService.markWatched(episode.episodeId);
    if (mounted) setState(() => _watchedIds.add(episode.episodeId));

    ref.read(playerStateProvider.notifier).play(
      url:      episode.streamUrl(creds),
      title:    '${widget.series.name} — $label',
      posterUrl: widget.series.cover,
      playOnTv: playOnTv,
    );

    if (context.mounted) context.push('/player');
  }

  // ============================================================
  // BUILD
  // ============================================================
  @override
  Widget build(BuildContext context) {
    final episodesAsync =
        ref.watch(seriesEpisodesProvider(widget.series.seriesId));

    return Scaffold(
      backgroundColor: const Color(0xFF0D1B2A),
      body: episodesAsync.when(
        loading: () => _buildLoading(),
        error:   (e, _) => _buildError(e.toString()),
        data: (episodes) {
          // Charger le statut "vu" une seule fois quand les épisodes arrivent
          if (!_watchedReady && episodes.isNotEmpty) {
            WidgetsBinding.instance
                .addPostFrameCallback((_) => _loadWatchedStatus(episodes));
          }

          // Regrouper les épisodes par numéro de saison
          final seasonsMap = <int, List<SeriesEpisode>>{};
          for (final ep in episodes) {
            seasonsMap.putIfAbsent(ep.season, () => []).add(ep);
          }
          final sortedSeasonNumbers = seasonsMap.keys.toList()..sort();

          return CustomScrollView(
            slivers: [
              // --- Bandeau expansible avec l'image de couverture ---
              _buildSliverAppBar(context),

              // --- Synopsis + note ---
              SliverToBoxAdapter(child: _buildSynopsis()),

              // --- Liste des saisons / épisodes ---
              SliverToBoxAdapter(
                child: _buildSeasonsList(
                  context,
                  sortedSeasonNumbers,
                  seasonsMap,
                ),
              ),

              // Espace en bas pour le scroll
              const SliverToBoxAdapter(child: SizedBox(height: 40)),
            ],
          );
        },
      ),
    );
  }

  // --------------------------------------------------------
  // AppBar expansible avec couverture
  // --------------------------------------------------------
  Widget _buildSliverAppBar(BuildContext context) {
    return SliverAppBar(
      expandedHeight:  280,
      pinned:          true,
      backgroundColor: const Color(0xFF0D1B2A),
      flexibleSpace: FlexibleSpaceBar(
        titlePadding: const EdgeInsets.fromLTRB(16, 0, 64, 12),
        title: Text(
          widget.series.name,
          style: const TextStyle(
            fontSize:   13,
            fontWeight: FontWeight.bold,
            shadows: [Shadow(blurRadius: 6, color: Colors.black)],
          ),
          maxLines: 2,
          overflow: TextOverflow.ellipsis,
        ),
        background: Stack(
          fit: StackFit.expand,
          children: [
            // Image de couverture
            if (widget.series.cover != null &&
                widget.series.cover!.isNotEmpty)
              CachedNetworkImage(
                imageUrl:    widget.series.cover!,
                fit:         BoxFit.cover,
                placeholder: (_, __) => _coverPlaceholder(),
                errorWidget: (_, __, ___) => _coverPlaceholder(),
              )
            else
              _coverPlaceholder(),

            // Dégradé bas → haut pour lisibilité du titre
            const DecoratedBox(
              decoration: BoxDecoration(
                gradient: LinearGradient(
                  begin:  Alignment.topCenter,
                  end:    Alignment.bottomCenter,
                  colors: [Colors.transparent, Color(0xFF0D1B2A)],
                  stops:  [0.45, 1.0],
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _coverPlaceholder() => Container(
    color: const Color(0xFF1A2744),
    child: const Center(
      child: Icon(Icons.live_tv, color: Colors.white24, size: 64),
    ),
  );

  // --------------------------------------------------------
  // Section synopsis + note
  // --------------------------------------------------------
  Widget _buildSynopsis() {
    final plot   = widget.series.plot;
    final rating = widget.series.rating;
    if ((plot == null || plot.isEmpty) && (rating == null || rating <= 0)) {
      return const SizedBox.shrink();
    }

    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 4, 16, 16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Note
          if (rating != null && rating > 0)
            Row(
              children: [
                const Icon(Icons.star, color: Colors.amber, size: 16),
                const SizedBox(width: 4),
                Text(
                  rating.toStringAsFixed(1),
                  style: const TextStyle(
                    color:      Colors.amber,
                    fontWeight: FontWeight.bold,
                    fontSize:   14,
                  ),
                ),
                const SizedBox(width: 4),
                const Text('/10',
                    style: TextStyle(color: Colors.white38, fontSize: 12)),
              ],
            ),
          if (rating != null && rating > 0 &&
              plot != null && plot.isNotEmpty)
            const SizedBox(height: 8),
          // Synopsis
          if (plot != null && plot.isNotEmpty)
            Text(
              plot,
              style: const TextStyle(color: Colors.white60, fontSize: 13),
              maxLines: 4,
              overflow: TextOverflow.ellipsis,
            ),
        ],
      ),
    );
  }

  // --------------------------------------------------------
  // Liste des saisons avec épisodes
  // --------------------------------------------------------
  Widget _buildSeasonsList(
    BuildContext context,
    List<int> seasonNumbers,
    Map<int, List<SeriesEpisode>> seasonsMap,
  ) {
    if (seasonNumbers.isEmpty) {
      return const Padding(
        padding: EdgeInsets.all(32),
        child: Center(
          child: Text(
            'Aucun épisode disponible pour cette série.',
            style:     TextStyle(color: Colors.white54),
            textAlign: TextAlign.center,
          ),
        ),
      );
    }

    // Aide : appui long sur un épisode pour marquer vu/non vu
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        // Titre de section + aide gestuelle
        Padding(
          padding: const EdgeInsets.fromLTRB(16, 0, 16, 4),
          child: Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              const Text(
                'Épisodes',
                style: TextStyle(
                  color:      Colors.white,
                  fontSize:   18,
                  fontWeight: FontWeight.bold,
                ),
              ),
              const Text(
                'Appui long = marquer vu',
                style: TextStyle(color: Colors.white38, fontSize: 11),
              ),
            ],
          ),
        ),
        // Une ExpansionTile par saison
        ...seasonNumbers.map((seasonNum) {
          final episodes = seasonsMap[seasonNum]!;
          return _buildSeasonTile(
            context,
            seasonNum,
            episodes,
            autoExpand: seasonNumbers.length == 1,
          );
        }),
      ],
    );
  }

  // --------------------------------------------------------
  // Tuile d'une saison (repliable/dépliable)
  // --------------------------------------------------------
  Widget _buildSeasonTile(
    BuildContext context,
    int   seasonNum,
    List<SeriesEpisode> episodes, {
    bool  autoExpand = false,
  }) {
    final watchedCount =
        episodes.where((e) => _watchedIds.contains(e.episodeId)).length;

    return Theme(
      // Masquer le séparateur Divider interne d'ExpansionTile
      data: Theme.of(context).copyWith(dividerColor: Colors.transparent),
      child: ExpansionTile(
        initiallyExpanded:        autoExpand,
        backgroundColor:          const Color(0xFF111E30),
        collapsedBackgroundColor: const Color(0xFF0D1B2A),
        tilePadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 4),
        iconColor:          Colors.white54,
        collapsedIconColor: Colors.white54,
        title: Text(
          'Saison $seasonNum',
          style: const TextStyle(
            color:      Colors.white,
            fontWeight: FontWeight.w600,
            fontSize:   15,
          ),
        ),
        subtitle: Text(
          '$watchedCount / ${episodes.length} vu${watchedCount > 1 ? 's' : ''}',
          style: const TextStyle(color: Colors.white38, fontSize: 12),
        ),
        trailing: Text(
          '${episodes.length} ép.',
          style: const TextStyle(color: Colors.white54, fontSize: 12),
        ),
        children: episodes
            .map((ep) => _buildEpisodeTile(context, ep))
            .toList(),
      ),
    );
  }

  // --------------------------------------------------------
  // Tuile d'un épisode
  // --------------------------------------------------------
  Widget _buildEpisodeTile(BuildContext context, SeriesEpisode episode) {
    final isWatched = _watchedIds.contains(episode.episodeId);
    final epCode    = 'E${episode.episodeNum.toString().padLeft(2, '0')}';
    final title     = episode.title.isNotEmpty ? episode.title : epCode;

    return InkWell(
      onTap:      () => _playEpisode(context, episode),
      onLongPress: () => _toggleWatched(episode),
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 11),
        decoration: BoxDecoration(
          border: Border(
            bottom: BorderSide(color: Colors.white.withOpacity(0.06)),
          ),
        ),
        child: Row(
          children: [
            // Badge numéro d'épisode
            Container(
              width:  44,
              height: 40,
              decoration: BoxDecoration(
                color: isWatched
                    ? Colors.green.withOpacity(0.15)
                    : Colors.white.withOpacity(0.07),
                borderRadius: BorderRadius.circular(6),
              ),
              child: Center(
                child: Text(
                  epCode,
                  style: TextStyle(
                    color: isWatched
                        ? Colors.green[300]
                        : Colors.white70,
                    fontSize:   11,
                    fontWeight: FontWeight.bold,
                  ),
                ),
              ),
            ),
            const SizedBox(width: 12),

            // Titre + durée (si disponible)
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    title,
                    style: TextStyle(
                      color:     isWatched ? Colors.white38 : Colors.white,
                      fontSize:  14,
                      decoration: isWatched
                          ? TextDecoration.lineThrough
                          : TextDecoration.none,
                    ),
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                  ),
                  if (episode.durationLabel != null) ...[
                    const SizedBox(height: 2),
                    Text(
                      episode.durationLabel!,
                      style: const TextStyle(
                        color:    Colors.white38,
                        fontSize: 11,
                      ),
                    ),
                  ],
                ],
              ),
            ),

            // Icône d'état
            const SizedBox(width: 8),
            Icon(
              isWatched
                  ? Icons.check_circle
                  : Icons.play_circle_outline,
              color: isWatched ? Colors.green[400] : Colors.white38,
              size: 20,
            ),
          ],
        ),
      ),
    );
  }

  // --------------------------------------------------------
  // Vues d'état : chargement / erreur
  // --------------------------------------------------------
  Widget _buildLoading() => const Center(
    child: Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        CircularProgressIndicator(),
        SizedBox(height: 16),
        Text(
          'Chargement des épisodes…',
          style: TextStyle(color: Colors.white54),
        ),
      ],
    ),
  );

  Widget _buildError(String message) => Center(
    child: Padding(
      padding: const EdgeInsets.all(24),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          const Icon(Icons.error_outline, color: Colors.red, size: 48),
          const SizedBox(height: 12),
          Text(
            message,
            textAlign: TextAlign.center,
            style: const TextStyle(color: Colors.white70),
          ),
          const SizedBox(height: 16),
          ElevatedButton.icon(
            onPressed: () => ref.refresh(
                seriesEpisodesProvider(widget.series.seriesId)),
            icon:  const Icon(Icons.refresh),
            label: const Text('Réessayer'),
          ),
        ],
      ),
    ),
  );
}
