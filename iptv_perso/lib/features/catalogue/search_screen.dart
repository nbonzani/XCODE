// ============================================================
// search_screen.dart — Écran de recherche avec filtres locaux
// ============================================================
// La recherche s'effectue entièrement dans le cache local (Hive)
// sans aucun appel réseau — les résultats sont instantanés.
// ============================================================
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/api/models.dart';
import '../../core/providers/catalogue_providers.dart';
import '../../core/providers/xtream_providers.dart';
import '../../core/providers/player_provider.dart';
import '../../core/widgets/screen_choice_sheet.dart';

class SearchScreen extends ConsumerStatefulWidget {
  /// 'vod' ou 'series' — détermine l'onglet actif au démarrage
  final String initialType;

  const SearchScreen({super.key, this.initialType = 'vod'});

  @override
  ConsumerState<SearchScreen> createState() => _SearchScreenState();
}

class _SearchScreenState extends ConsumerState<SearchScreen>
    with SingleTickerProviderStateMixin {

  late TabController _tabController;
  final _searchController = TextEditingController();
  String _query = '';

  // Filtres optionnels
  double _minRating = 0.0; // Note minimale (0 = pas de filtre)

  @override
  void initState() {
    super.initState();
    _tabController = TabController(
      length:     2,
      vsync:      this,
      initialIndex: widget.initialType == 'series' ? 1 : 0,
    );
    _searchController.addListener(() {
      setState(() => _query = _searchController.text.trim().toLowerCase());
    });
  }

  @override
  void dispose() {
    _tabController.dispose();
    _searchController.dispose();
    super.dispose();
  }

  // --------------------------------------------------------
  // Filtrage des films
  // --------------------------------------------------------
  List<VodStream> _filterVod(List<VodStream> all) {
    return all.where((v) {
      final matchesQuery  = _query.isEmpty ||
          v.name.toLowerCase().contains(_query);
      final matchesRating = _minRating == 0.0 ||
          (v.rating != null && v.rating! >= _minRating);
      return matchesQuery && matchesRating;
    }).toList();
  }

  // --------------------------------------------------------
  // Filtrage des séries
  // --------------------------------------------------------
  List<XtreamSeries> _filterSeries(List<XtreamSeries> all) {
    return all.where((s) {
      final matchesQuery  = _query.isEmpty ||
          s.name.toLowerCase().contains(_query);
      final matchesRating = _minRating == 0.0 ||
          (s.rating != null && s.rating! >= _minRating);
      return matchesQuery && matchesRating;
    }).toList();
  }

  // --------------------------------------------------------
  // Interface
  // --------------------------------------------------------
  @override
  Widget build(BuildContext context) {
    final asyncVod    = ref.watch(cachedVodProvider);
    final asyncSeries = ref.watch(cachedSeriesProvider);

    return Scaffold(
      appBar: AppBar(
        title: TextField(
          controller:  _searchController,
          autofocus:   true,
          decoration:  const InputDecoration(
            hintText:    'Rechercher un film ou une série…',
            border:      InputBorder.none,
            hintStyle:   TextStyle(color: Colors.white38),
          ),
          style: const TextStyle(color: Colors.white, fontSize: 16),
        ),
        actions: [
          // Filtre par note
          IconButton(
            icon: Icon(
              Icons.filter_list,
              color: _minRating > 0 ? Colors.amber : Colors.white,
            ),
            tooltip: 'Filtrer par note',
            onPressed: () => _showRatingFilter(context),
          ),
          // Effacer la recherche
          if (_query.isNotEmpty)
            IconButton(
              icon: const Icon(Icons.clear),
              onPressed: () {
                _searchController.clear();
                setState(() => _query = '');
              },
            ),
        ],
        bottom: TabBar(
          controller: _tabController,
          tabs: const [
            Tab(icon: Icon(Icons.movie_outlined), text: 'Films'),
            Tab(icon: Icon(Icons.live_tv_outlined), text: 'Séries'),
          ],
        ),
      ),
      body: TabBarView(
        controller: _tabController,
        children: [
          // Onglet Films
          asyncVod.when(
            loading: () => const Center(child: CircularProgressIndicator()),
            error:   (e, _) => Center(child: Text('Erreur : $e')),
            data: (streams) {
              final results = _filterVod(streams);
              return _buildResultsList(
                results.length,
                (i) => _VodResultTile(
                  vod: results[i],
                  onTap: () => _playVod(results[i]),
                ),
              );
            },
          ),
          // Onglet Séries
          asyncSeries.when(
            loading: () => const Center(child: CircularProgressIndicator()),
            error:   (e, _) => Center(child: Text('Erreur : $e')),
            data: (series) {
              final results = _filterSeries(series);
              return _buildResultsList(
                results.length,
                (i) => _SeriesResultTile(series: results[i]),
              );
            },
          ),
        ],
      ),
    );
  }

  // --------------------------------------------------------
  // Liste de résultats
  // --------------------------------------------------------
  Widget _buildResultsList(int count, Widget Function(int) builder) {
    if (_query.isEmpty && _minRating == 0.0) {
      return const Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(Icons.search, size: 64, color: Colors.white12),
            SizedBox(height: 12),
            Text('Tapez un titre pour rechercher.',
                style: TextStyle(color: Colors.white38)),
          ],
        ),
      );
    }

    if (count == 0) {
      return const Center(
        child: Text('Aucun résultat trouvé.',
            style: TextStyle(color: Colors.white54)),
      );
    }

    return Column(
      children: [
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
          child: Row(
            children: [
              Text(
                '$count résultat${count > 1 ? 's' : ''}',
                style: const TextStyle(color: Colors.white54, fontSize: 13),
              ),
            ],
          ),
        ),
        Expanded(
          child: ListView.builder(
            itemCount:   count,
            itemBuilder: (_, i) => builder(i),
          ),
        ),
      ],
    );
  }

  // --------------------------------------------------------
  // Dialogue de filtre par note
  // --------------------------------------------------------
  Future<void> _showRatingFilter(BuildContext context) async {
    double temp = _minRating;
    await showDialog(
      context: context,
      builder: (_) => StatefulBuilder(
        builder: (ctx, setS) => AlertDialog(
          title: const Text('Note minimale'),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(
                temp == 0.0
                    ? 'Pas de filtre'
                    : 'Note ≥ ${temp.toStringAsFixed(1)} / 10',
                style: const TextStyle(fontSize: 16),
              ),
              Slider(
                value: temp,
                min:   0,
                max:   10,
                divisions: 20,
                label: temp == 0.0 ? 'Aucun' : temp.toStringAsFixed(1),
                onChanged: (v) => setS(() => temp = v),
              ),
            ],
          ),
          actions: [
            TextButton(
              onPressed: () {
                setS(() => temp = 0.0);
              },
              child: const Text('Réinitialiser'),
            ),
            FilledButton(
              onPressed: () {
                setState(() => _minRating = temp);
                Navigator.pop(ctx);
              },
              child: const Text('Appliquer'),
            ),
          ],
        ),
      ),
    );
  }

  // --------------------------------------------------------
  // Lancer la lecture d'un film
  // --------------------------------------------------------
  Future<void> _playVod(VodStream vod) async {
    final creds = ref.read(credentialsProvider).valueOrNull;
    if (creds == null) return;

    // Demander à l'utilisateur sur quel écran il veut regarder
    final playOnTv = await showScreenChoiceSheet(
      context,
      title:     vod.name,
      posterUrl: vod.streamIcon,
    );
    if (playOnTv == null || !context.mounted) return; // annulé

    ref.read(playerStateProvider.notifier).play(
      url:       vod.streamUrl(creds),
      title:     vod.name,
      posterUrl: vod.streamIcon,
      playOnTv:  playOnTv,
    );
    context.push('/player');
  }
}

// ============================================================
// Tuile de résultat — Film
// ============================================================
class _VodResultTile extends StatelessWidget {
  final VodStream    vod;
  final VoidCallback onTap;

  const _VodResultTile({required this.vod, required this.onTap});

  @override
  Widget build(BuildContext context) {
    return ListTile(
      contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 4),
      leading: ClipRRect(
        borderRadius: BorderRadius.circular(4),
        child: SizedBox(
          width: 44, height: 60,
          child: vod.streamIcon != null && vod.streamIcon!.isNotEmpty
              ? Image.network(vod.streamIcon!, fit: BoxFit.cover,
                  errorBuilder: (_, __, ___) =>
                      const Icon(Icons.movie, color: Colors.white24))
              : const Icon(Icons.movie, color: Colors.white24),
        ),
      ),
      title: Text(vod.name, maxLines: 2,
          overflow: TextOverflow.ellipsis,
          style: const TextStyle(fontSize: 14)),
      subtitle: vod.rating != null && vod.rating! > 0
          ? Row(children: [
              const Icon(Icons.star, size: 12, color: Colors.amber),
              const SizedBox(width: 3),
              Text(vod.rating!.toStringAsFixed(1),
                  style: const TextStyle(color: Colors.amber, fontSize: 12)),
            ])
          : null,
      trailing: const Icon(Icons.play_circle_outline),
      onTap: onTap,
    );
  }
}

// ============================================================
// Tuile de résultat — Série
// ============================================================
class _SeriesResultTile extends StatelessWidget {
  final XtreamSeries series;

  const _SeriesResultTile({required this.series});

  @override
  Widget build(BuildContext context) {
    return ListTile(
      contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 4),
      leading: ClipRRect(
        borderRadius: BorderRadius.circular(4),
        child: SizedBox(
          width: 44, height: 60,
          child: series.cover != null && series.cover!.isNotEmpty
              ? Image.network(series.cover!, fit: BoxFit.cover,
                  errorBuilder: (_, __, ___) =>
                      const Icon(Icons.live_tv, color: Colors.white24))
              : const Icon(Icons.live_tv, color: Colors.white24),
        ),
      ),
      title: Text(series.name, maxLines: 2,
          overflow: TextOverflow.ellipsis,
          style: const TextStyle(fontSize: 14)),
      subtitle: series.rating != null && series.rating! > 0
          ? Row(children: [
              const Icon(Icons.star, size: 12, color: Colors.amber),
              const SizedBox(width: 3),
              Text(series.rating!.toStringAsFixed(1),
                  style: const TextStyle(color: Colors.amber, fontSize: 12)),
            ])
          : null,
      trailing: const Icon(Icons.chevron_right),
      // TODO : naviguer vers l'écran de sélection d'épisodes
      onTap: () {},
    );
  }
}
