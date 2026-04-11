// ============================================================
// catalogue_screen.dart — Écran principal du catalogue
// ============================================================
// Nouveautés v2 :
//   - Filtres par texte + catégorie dans chaque onglet
//   - Navigation vers SeriesDetailScreen au tap sur une série
//   - CachedNetworkImage pour les affiches (cache disque)
//   - Dialogue d'options Films : Voir / Télécharger
// ============================================================
import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/api/models.dart';
import '../../core/cache/catalogue_cache.dart';
import '../../core/providers/catalogue_providers.dart';
import '../../core/providers/series_providers.dart';
import '../../core/providers/xtream_providers.dart';
import '../../core/providers/player_provider.dart';
import '../../core/widgets/screen_choice_sheet.dart';
import '../download/download_service.dart';
import '../download/download_sheet.dart';

// ============================================================
// Écran principal avec onglets Films / Séries
// ============================================================
class CatalogueScreen extends ConsumerStatefulWidget {
  const CatalogueScreen({super.key});

  @override
  ConsumerState<CatalogueScreen> createState() => _CatalogueScreenState();
}

class _CatalogueScreenState extends ConsumerState<CatalogueScreen>
    with SingleTickerProviderStateMixin {
  late final TabController _tabController;

  @override
  void initState() {
    super.initState();
    _tabController = TabController(length: 2, vsync: this);
  }

  @override
  void dispose() {
    _tabController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Catalogue FR'),
        centerTitle: false,
        actions: [
          // Bouton recherche globale
          IconButton(
            icon:    const Icon(Icons.search),
            tooltip: 'Rechercher',
            onPressed: () {
              final type = _tabController.index == 0 ? 'vod' : 'series';
              context.push('/search?type=$type');
            },
          ),
          // Menu contextuel
          PopupMenuButton<String>(
            onSelected: (value) async {
              if (value == 'refresh') {
                await CatalogueCache.clearAll();
                ref.invalidate(cachedVodProvider);
                ref.invalidate(cachedSeriesProvider);
              } else if (value == 'settings') {
                context.push('/settings');
              }
            },
            itemBuilder: (_) => [
              const PopupMenuItem(
                value: 'refresh',
                child: ListTile(
                  leading:         Icon(Icons.refresh),
                  title:           Text('Actualiser le catalogue'),
                  contentPadding:  EdgeInsets.zero,
                ),
              ),
              const PopupMenuItem(
                value: 'settings',
                child: ListTile(
                  leading:        Icon(Icons.settings),
                  title:          Text('Paramètres'),
                  contentPadding: EdgeInsets.zero,
                ),
              ),
            ],
          ),
        ],
        bottom: TabBar(
          controller: _tabController,
          tabs: const [
            Tab(icon: Icon(Icons.movie_outlined),  text: 'Films'),
            Tab(icon: Icon(Icons.live_tv_outlined), text: 'Séries'),
          ],
        ),
      ),
      body: TabBarView(
        controller: _tabController,
        children: const [
          _VodTab(),
          _SeriesTab(),
        ],
      ),
    );
  }
}

// ============================================================
// Onglet Films — avec filtres texte + catégorie
// ============================================================
class _VodTab extends ConsumerStatefulWidget {
  const _VodTab();

  @override
  ConsumerState<_VodTab> createState() => _VodTabState();
}

class _VodTabState extends ConsumerState<_VodTab> {
  String  _searchQuery       = '';
  String? _selectedCategoryId;

  @override
  Widget build(BuildContext context) {
    final asyncVod        = ref.watch(cachedVodProvider);
    final asyncCategories = ref.watch(vodCategoriesProvider);

    // Récupère la liste des catégories pour le dropdown
    final categories = asyncCategories.valueOrNull ?? [];

    return Column(
      children: [
        // --- Barre de filtres ---
        _FilterBar(
          categories:         categories,
          selectedCategoryId: _selectedCategoryId,
          onSearch:    (q) => setState(() => _searchQuery       = q),
          onCategory:  (id) => setState(() => _selectedCategoryId = id),
        ),
        // --- Grille des films ---
        Expanded(
          child: asyncVod.when(
            loading: () =>
                const _LoadingView(message: 'Chargement des films…'),
            error: (e, _) => _ErrorView(message: e.toString()),
            data: (streams) {
              // Filtrage côté client
              final filtered = _applyFilters(streams);
              if (filtered.isEmpty) {
                return const _EmptyView(
                    message: 'Aucun film correspond aux filtres.');
              }
              return _MediaGrid(
                itemCount:   filtered.length,
                itemBuilder: (i) => _VodCard(
                  vod: filtered[i],
                  onTap: () => _onVodTap(context, filtered[i]),
                ),
              );
            },
          ),
        ),
      ],
    );
  }

  // --------------------------------------------------------
  // Appliquer les filtres texte et catégorie
  // --------------------------------------------------------
  List<VodStream> _applyFilters(List<VodStream> all) {
    return all.where((v) {
      final matchesSearch = _searchQuery.isEmpty ||
          v.name.toLowerCase().contains(_searchQuery.toLowerCase());
      final matchesCategory = _selectedCategoryId == null ||
          v.categoryId == _selectedCategoryId;
      return matchesSearch && matchesCategory;
    }).toList();
  }

  // --------------------------------------------------------
  // Tap sur un film → dialogue Voir / Télécharger
  // --------------------------------------------------------
  Future<void> _onVodTap(BuildContext context, VodStream vod) async {
    final creds = ref.read(credentialsProvider).valueOrNull;
    if (creds == null) return;

    await showModalBottomSheet(
      context:         context,
      backgroundColor: const Color(0xFF1A2744),
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
      ),
      builder: (_) => _VodOptionsSheet(
        vod:   vod,
        creds: creds,
        onPlay: (playOnTv) {
          ref.read(playerStateProvider.notifier).play(
            url:      vod.streamUrl(creds),
            title:    vod.name,
            posterUrl: vod.streamIcon,
            playOnTv: playOnTv,
          );
          context.push('/player');
        },
        onDownload: () {
          showModalBottomSheet(
            context:         context,
            backgroundColor: const Color(0xFF1A2744),
            isScrollControlled: true,
            shape: const RoundedRectangleBorder(
              borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
            ),
            builder: (_) => DownloadSheet(
              url:      vod.streamUrl(creds),
              name:     vod.name,
              extension: 'mkv',
              destDir:  null, // sera résolu dans DownloadSheet → moviesDir()
              isMovie:  true,
            ),
          );
        },
      ),
    );
  }
}

// ============================================================
// Onglet Séries — avec filtres texte + catégorie
// ============================================================
class _SeriesTab extends ConsumerStatefulWidget {
  const _SeriesTab();

  @override
  ConsumerState<_SeriesTab> createState() => _SeriesTabState();
}

class _SeriesTabState extends ConsumerState<_SeriesTab> {
  String  _searchQuery       = '';
  String? _selectedCategoryId;

  @override
  Widget build(BuildContext context) {
    final asyncSeries     = ref.watch(cachedSeriesProvider);
    final asyncCategories = ref.watch(seriesCategoriesProvider);
    final categories      = asyncCategories.valueOrNull ?? [];

    return Column(
      children: [
        // --- Barre de filtres ---
        _FilterBar(
          categories:         categories,
          selectedCategoryId: _selectedCategoryId,
          onSearch:   (q)  => setState(() => _searchQuery       = q),
          onCategory: (id) => setState(() => _selectedCategoryId = id),
        ),
        // --- Grille des séries ---
        Expanded(
          child: asyncSeries.when(
            loading: () =>
                const _LoadingView(message: 'Chargement des séries…'),
            error: (e, _) => _ErrorView(message: e.toString()),
            data: (series) {
              final filtered = _applyFilters(series);
              if (filtered.isEmpty) {
                return const _EmptyView(
                    message: 'Aucune série correspond aux filtres.');
              }
              return _MediaGrid(
                itemCount:   filtered.length,
                itemBuilder: (i) => _SeriesCard(
                  serie: filtered[i],
                  onTap: () => _openSeries(context, filtered[i]),
                ),
              );
            },
          ),
        ),
      ],
    );
  }

  List<XtreamSeries> _applyFilters(List<XtreamSeries> all) {
    return all.where((s) {
      final matchesSearch = _searchQuery.isEmpty ||
          s.name.toLowerCase().contains(_searchQuery.toLowerCase());
      final matchesCategory = _selectedCategoryId == null ||
          s.categoryId == _selectedCategoryId;
      return matchesSearch && matchesCategory;
    }).toList();
  }

  // --------------------------------------------------------
  // Navigation vers l'écran détail de la série
  // --------------------------------------------------------
  void _openSeries(BuildContext context, XtreamSeries serie) {
    context.push('/series', extra: serie);
  }
}

// ============================================================
// Barre de filtres partagée (texte + catégorie)
// ============================================================
class _FilterBar extends StatefulWidget {
  final List<XtreamCategory> categories;
  final String?              selectedCategoryId;
  final void Function(String)  onSearch;
  final void Function(String?) onCategory;

  const _FilterBar({
    required this.categories,
    required this.selectedCategoryId,
    required this.onSearch,
    required this.onCategory,
  });

  @override
  State<_FilterBar> createState() => _FilterBarState();
}

class _FilterBarState extends State<_FilterBar> {
  final _controller = TextEditingController();

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      color: const Color(0xFF0D1B2A),
      padding: const EdgeInsets.fromLTRB(10, 8, 10, 8),
      child: Row(
        children: [
          // Champ de recherche textuelle
          Expanded(
            child: SizedBox(
              height: 38,
              child: TextField(
                controller:   _controller,
                onChanged:    widget.onSearch,
                style: const TextStyle(color: Colors.white, fontSize: 13),
                decoration: InputDecoration(
                  hintText:      'Rechercher…',
                  hintStyle:     const TextStyle(color: Colors.white38),
                  prefixIcon:    const Icon(Icons.search,
                      color: Colors.white38, size: 18),
                  suffixIcon: _controller.text.isNotEmpty
                      ? IconButton(
                          icon:    const Icon(Icons.clear,
                              color: Colors.white38, size: 16),
                          onPressed: () {
                            _controller.clear();
                            widget.onSearch('');
                          },
                        )
                      : null,
                  filled:      true,
                  fillColor:   const Color(0xFF1A2744),
                  contentPadding: const EdgeInsets.symmetric(
                      vertical: 0, horizontal: 12),
                  border: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(8),
                    borderSide:  BorderSide.none,
                  ),
                ),
              ),
            ),
          ),
          // Dropdown catégorie (affiché seulement si des catégories sont dispo)
          if (widget.categories.isNotEmpty) ...[
            const SizedBox(width: 8),
            _CategoryDropdown(
              categories:         widget.categories,
              selectedCategoryId: widget.selectedCategoryId,
              onChanged:          widget.onCategory,
            ),
          ],
        ],
      ),
    );
  }
}

// ============================================================
// Dropdown de sélection de catégorie
// ============================================================
class _CategoryDropdown extends StatelessWidget {
  final List<XtreamCategory> categories;
  final String?              selectedCategoryId;
  final void Function(String?) onChanged;

  const _CategoryDropdown({
    required this.categories,
    required this.selectedCategoryId,
    required this.onChanged,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      height:  38,
      padding: const EdgeInsets.symmetric(horizontal: 10),
      decoration: BoxDecoration(
        color:        const Color(0xFF1A2744),
        borderRadius: BorderRadius.circular(8),
      ),
      child: DropdownButtonHideUnderline(
        child: DropdownButton<String?>(
          value:    selectedCategoryId,
          dropdownColor: const Color(0xFF1A2744),
          style: const TextStyle(color: Colors.white, fontSize: 12),
          hint: const Text('Catégorie',
              style: TextStyle(color: Colors.white54, fontSize: 12)),
          icon: const Icon(Icons.filter_list,
              color: Colors.white54, size: 16),
          items: [
            // Option "Toutes"
            const DropdownMenuItem<String?>(
              value: null,
              child: Text('Toutes',
                  style: TextStyle(color: Colors.white54, fontSize: 12)),
            ),
            // Une entrée par catégorie
            ...categories.map((cat) => DropdownMenuItem<String?>(
              value: cat.categoryId,
              child: Text(
                // Tronquer si trop long pour le dropdown
                cat.categoryName.length > 22
                    ? '${cat.categoryName.substring(0, 20)}…'
                    : cat.categoryName,
                style: const TextStyle(fontSize: 12),
              ),
            )),
          ],
          onChanged: onChanged,
        ),
      ),
    );
  }
}

// ============================================================
// Dialogue d'options pour un film (Voir / Télécharger)
// ============================================================
class _VodOptionsSheet extends StatelessWidget {
  final VodStream         vod;
  final XtreamCredentials creds;
  final void Function(bool playOnTv) onPlay;
  final VoidCallback      onDownload;

  const _VodOptionsSheet({
    required this.vod,
    required this.creds,
    required this.onPlay,
    required this.onDownload,
  });

  @override
  Widget build(BuildContext context) {
    return SafeArea(
      child: Padding(
        padding: const EdgeInsets.fromLTRB(20, 16, 20, 24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // Poignée
            Center(
              child: Container(
                width: 40, height: 4,
                decoration: BoxDecoration(
                  color: Colors.white24,
                  borderRadius: BorderRadius.circular(2),
                ),
              ),
            ),
            const SizedBox(height: 16),
            // Titre du film
            Row(
              children: [
                if (vod.streamIcon != null && vod.streamIcon!.isNotEmpty)
                  ClipRRect(
                    borderRadius: BorderRadius.circular(4),
                    child: CachedNetworkImage(
                      imageUrl:    vod.streamIcon!,
                      width: 36,   height: 48,
                      fit: BoxFit.cover,
                      errorWidget: (_, __, ___) => const SizedBox(),
                    ),
                  ),
                if (vod.streamIcon != null && vod.streamIcon!.isNotEmpty)
                  const SizedBox(width: 12),
                Expanded(
                  child: Text(
                    vod.name,
                    style: const TextStyle(
                      color:      Colors.white,
                      fontSize:   15,
                      fontWeight: FontWeight.w600,
                    ),
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                  ),
                ),
              ],
            ),
            const SizedBox(height: 20),
            // Option : Voir sur ce téléphone
            _OptionTile(
              icon:     Icons.smartphone,
              label:    'Voir sur ce téléphone',
              subtitle: 'Lecture plein écran sur le S25 Ultra',
              onTap: () {
                Navigator.pop(context);
                onPlay(false);
              },
            ),
            const SizedBox(height: 10),
            // Option : Voir sur la TV
            _OptionTile(
              icon:        Icons.tv,
              label:       'Voir sur la TV (câble HDMI)',
              subtitle:    "L'écran du téléphone s'éteint",
              highlighted: true,
              onTap: () {
                Navigator.pop(context);
                onPlay(true);
              },
            ),
            const SizedBox(height: 10),
            // Option : Télécharger
            _OptionTile(
              icon:     Icons.download_outlined,
              label:    'Télécharger',
              subtitle: 'Sauvegarder le film pour une lecture hors ligne',
              onTap: () {
                Navigator.pop(context);
                onDownload();
              },
            ),
          ],
        ),
      ),
    );
  }
}

class _OptionTile extends StatelessWidget {
  final IconData icon;
  final String   label;
  final String   subtitle;
  final bool     highlighted;
  final VoidCallback onTap;

  const _OptionTile({
    required this.icon,
    required this.label,
    required this.subtitle,
    required this.onTap,
    this.highlighted = false,
  });

  @override
  Widget build(BuildContext context) {
    return Material(
      color: highlighted
          ? const Color(0xFF1565C0).withOpacity(0.3)
          : Colors.white.withOpacity(0.05),
      borderRadius: BorderRadius.circular(12),
      child: InkWell(
        onTap:        onTap,
        borderRadius: BorderRadius.circular(12),
        child: Padding(
          padding: const EdgeInsets.symmetric(
              horizontal: 16, vertical: 14),
          child: Row(
            children: [
              Icon(icon,
                color: highlighted
                    ? Colors.blue[300]
                    : Colors.white70,
                size: 26),
              const SizedBox(width: 16),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(label,
                      style: TextStyle(
                        color: highlighted
                            ? Colors.blue[200]
                            : Colors.white,
                        fontWeight: FontWeight.w600,
                        fontSize:   14,
                      ),
                    ),
                    const SizedBox(height: 2),
                    Text(subtitle,
                      style: const TextStyle(
                          color: Colors.white38, fontSize: 12)),
                  ],
                ),
              ),
              Icon(Icons.chevron_right,
                color: highlighted
                    ? Colors.blue[300]
                    : Colors.white24),
            ],
          ),
        ),
      ),
    );
  }
}

// ============================================================
// Carte d'un film (avec CachedNetworkImage)
// ============================================================
class _VodCard extends StatelessWidget {
  final VodStream   vod;
  final VoidCallback onTap;

  const _VodCard({required this.vod, required this.onTap});

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: ClipRRect(
        borderRadius: BorderRadius.circular(8),
        child: Stack(
          fit: StackFit.expand,
          children: [
            // Affiche (avec cache disque)
            _buildImage(vod.streamIcon),
            // Dégradé + titre + note
            Positioned(
              bottom: 0, left: 0, right: 0,
              child: Container(
                padding: const EdgeInsets.fromLTRB(6, 20, 6, 6),
                decoration: const BoxDecoration(
                  gradient: LinearGradient(
                    begin:  Alignment.bottomCenter,
                    end:    Alignment.topCenter,
                    colors: [Colors.black87, Colors.transparent],
                  ),
                ),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Text(vod.name,
                      style: const TextStyle(
                        color:      Colors.white,
                        fontSize:   10,
                        fontWeight: FontWeight.w600,
                      ),
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                    ),
                    if (vod.rating != null && vod.rating! > 0) ...[
                      const SizedBox(height: 2),
                      Row(
                        children: [
                          const Icon(Icons.star,
                              color: Colors.amber, size: 10),
                          const SizedBox(width: 2),
                          Text(vod.rating!.toStringAsFixed(1),
                            style: const TextStyle(
                                color: Colors.amber, fontSize: 9)),
                        ],
                      ),
                    ],
                  ],
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

// ============================================================
// Carte d'une série (avec CachedNetworkImage)
// ============================================================
class _SeriesCard extends StatelessWidget {
  final XtreamSeries serie;
  final VoidCallback onTap;

  const _SeriesCard({required this.serie, required this.onTap});

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: ClipRRect(
        borderRadius: BorderRadius.circular(8),
        child: Stack(
          fit: StackFit.expand,
          children: [
            _buildImage(serie.cover),
            Positioned(
              bottom: 0, left: 0, right: 0,
              child: Container(
                padding: const EdgeInsets.fromLTRB(6, 20, 6, 6),
                decoration: const BoxDecoration(
                  gradient: LinearGradient(
                    begin:  Alignment.bottomCenter,
                    end:    Alignment.topCenter,
                    colors: [Colors.black87, Colors.transparent],
                  ),
                ),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Text(serie.name,
                      style: const TextStyle(
                        color:      Colors.white,
                        fontSize:   10,
                        fontWeight: FontWeight.w600,
                      ),
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                    ),
                    if (serie.rating != null && serie.rating! > 0) ...[
                      const SizedBox(height: 2),
                      Row(
                        children: [
                          const Icon(Icons.star,
                              color: Colors.amber, size: 10),
                          const SizedBox(width: 2),
                          Text(serie.rating!.toStringAsFixed(1),
                            style: const TextStyle(
                                color: Colors.amber, fontSize: 9)),
                        ],
                      ),
                    ],
                  ],
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

// ============================================================
// Helper partagé : image avec cache disque
// ============================================================
Widget _buildImage(String? url) {
  if (url != null && url.isNotEmpty) {
    return CachedNetworkImage(
      imageUrl:    url,
      fit:         BoxFit.cover,
      placeholder: (_, __) => _placeholder(),
      errorWidget: (_, __, ___) => _placeholder(),
    );
  }
  return _placeholder();
}

Widget _placeholder() => Container(
  color: const Color(0xFF1A2744),
  child: const Center(
    child: Icon(Icons.movie, color: Colors.white24, size: 36),
  ),
);

// ============================================================
// Widgets d'état partagés
// ============================================================

class _MediaGrid extends StatelessWidget {
  final int itemCount;
  final Widget Function(int) itemBuilder;

  const _MediaGrid({
    required this.itemCount,
    required this.itemBuilder,
  });

  @override
  Widget build(BuildContext context) {
    return GridView.builder(
      padding: const EdgeInsets.all(10),
      gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
        crossAxisCount:   3,
        childAspectRatio: 0.62,
        crossAxisSpacing: 8,
        mainAxisSpacing:  8,
      ),
      itemCount:   itemCount,
      itemBuilder: (_, i) => itemBuilder(i),
    );
  }
}

class _LoadingView extends StatelessWidget {
  final String message;
  const _LoadingView({required this.message});

  @override
  Widget build(BuildContext context) => Center(
    child: Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        const CircularProgressIndicator(),
        const SizedBox(height: 16),
        Text(message,
            style: const TextStyle(color: Colors.white54)),
      ],
    ),
  );
}

class _ErrorView extends StatelessWidget {
  final String message;
  const _ErrorView({required this.message});

  @override
  Widget build(BuildContext context) => Center(
    child: Padding(
      padding: const EdgeInsets.all(24),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          const Icon(Icons.error_outline, color: Colors.red, size: 48),
          const SizedBox(height: 12),
          Text(message,
            textAlign: TextAlign.center,
            style: const TextStyle(color: Colors.white70)),
        ],
      ),
    ),
  );
}

class _EmptyView extends StatelessWidget {
  final String message;
  const _EmptyView({required this.message});

  @override
  Widget build(BuildContext context) => Center(
    child: Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        const Icon(Icons.movie_filter_outlined,
            color: Colors.white24, size: 64),
        const SizedBox(height: 12),
        Text(message,
            style: const TextStyle(color: Colors.white54),
            textAlign: TextAlign.center),
      ],
    ),
  );
}
