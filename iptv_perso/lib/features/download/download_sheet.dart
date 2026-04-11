// ============================================================
// download_sheet.dart — Bottom sheet de progression du téléchargement
// ============================================================
// Affiche en temps réel :
//   - Nom du fichier
//   - Barre de progression
//   - Taille téléchargée / totale
//   - Vitesse (Ko/s ou Mo/s)
//   - ETA (temps restant estimé)
//   - Bouton Annuler
// ============================================================
import 'dart:async';
import 'dart:io';

import 'package:dio/dio.dart';
import 'package:flutter/material.dart';

import 'download_service.dart';

class DownloadSheet extends StatefulWidget {
  final String     url;
  final String     name;
  final String     extension;
  final Directory? destDir;   // null → sera résolu (moviesDir ou seriesDir)
  final bool       isMovie;   // true = Films/, false = dossier par nom de série
  final String?    seriesName;// Nom de la série (si isMovie == false)

  const DownloadSheet({
    super.key,
    required this.url,
    required this.name,
    required this.extension,
    this.destDir,
    this.isMovie     = true,
    this.seriesName,
  });

  @override
  State<DownloadSheet> createState() => _DownloadSheetState();
}

class _DownloadSheetState extends State<DownloadSheet> {
  // Progression
  DownloadProgress? _progress;

  // États
  bool   _done      = false;
  bool   _cancelled = false;
  String _statusMsg = 'Initialisation…';

  // Annulation Dio
  final CancelToken _cancelToken = CancelToken();

  @override
  void initState() {
    super.initState();
    _startDownload();
  }

  @override
  void dispose() {
    // Annulation propre si la fiche est fermée avant la fin
    if (!_done && !_cancelToken.isCancelled) {
      _cancelToken.cancel('Fiche fermée');
    }
    super.dispose();
  }

  Future<void> _startDownload() async {
    try {
      // Résoudre le répertoire de destination
      final Directory dir;
      if (widget.destDir != null) {
        dir = widget.destDir!;
      } else if (widget.isMovie) {
        dir = await DownloadService.moviesDir();
      } else {
        dir = await DownloadService.seriesDir(
            widget.seriesName ?? widget.name);
      }

      final filename = '${widget.name}.${widget.extension}';

      // Vérifier si le fichier existe déjà
      if (await DownloadService.fileExists(filename, dir)) {
        if (mounted) {
          setState(() {
            _done      = true;
            _statusMsg = 'Fichier déjà téléchargé.';
          });
        }
        return;
      }

      // Lancer le téléchargement
      await DownloadService.downloadFile(
        url:         widget.url,
        filename:    filename,
        destDir:     dir,
        cancelToken: _cancelToken,
        onProgress:  (p) {
          if (mounted) setState(() => _progress = p);
        },
      );

      if (mounted) {
        setState(() {
          _done      = true;
          _statusMsg = 'Téléchargement terminé ✓';
        });
      }
    } on DioException catch (e) {
      if (CancelToken.isCancel(e)) {
        if (mounted) {
          setState(() {
            _cancelled = true;
            _statusMsg = 'Téléchargement annulé.';
          });
        }
      } else {
        if (mounted) {
          setState(() {
            _done      = true;
            _statusMsg = 'Erreur : ${e.message}';
          });
        }
      }
    } catch (e) {
      if (mounted) {
        setState(() {
          _done      = true;
          _statusMsg = 'Erreur : $e';
        });
      }
    }
  }

  void _cancel() {
    if (!_cancelToken.isCancelled) {
      _cancelToken.cancel('Annulé par l\'utilisateur');
    }
  }

  @override
  Widget build(BuildContext context) {
    final p = _progress;

    return SafeArea(
      child: Padding(
        padding: const EdgeInsets.fromLTRB(20, 16, 20, 28),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // Poignée
            Center(
              child: Container(
                width: 40, height: 4,
                decoration: BoxDecoration(
                  color:        Colors.white24,
                  borderRadius: BorderRadius.circular(2),
                ),
              ),
            ),
            const SizedBox(height: 16),

            // Titre
            Row(
              children: [
                const Icon(Icons.download, color: Colors.blue, size: 20),
                const SizedBox(width: 8),
                Expanded(
                  child: Text(
                    widget.name,
                    style: const TextStyle(
                      color:      Colors.white,
                      fontSize:   14,
                      fontWeight: FontWeight.w600,
                    ),
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                  ),
                ),
              ],
            ),
            const SizedBox(height: 16),

            // Barre de progression
            if (!_done && !_cancelled && p != null) ...[
              ClipRRect(
                borderRadius: BorderRadius.circular(4),
                child: LinearProgressIndicator(
                  value:           p.fraction,     // null si taille inconnue
                  backgroundColor: const Color(0xFF1E1E38),
                  color:           Colors.blue,
                  minHeight:       8,
                ),
              ),
              const SizedBox(height: 10),
              // Statistiques
              Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  Text(p.sizeLabel,
                      style: const TextStyle(
                          color: Colors.white60, fontSize: 12)),
                  Text(p.speedLabel,
                      style: const TextStyle(
                          color: Colors.white60, fontSize: 12)),
                ],
              ),
              if (p.etaLabel != null) ...[
                const SizedBox(height: 4),
                Text(p.etaLabel!,
                    style: const TextStyle(
                        color: Colors.white38, fontSize: 11)),
              ],
            ] else ...[
              // Barre indéterminée ou message final
              if (!_done && !_cancelled)
                const LinearProgressIndicator(
                  backgroundColor: Color(0xFF1E1E38),
                  color:           Colors.blue,
                  minHeight:       8,
                ),
              const SizedBox(height: 10),
              Text(
                _statusMsg,
                style: TextStyle(
                  color: _done && !_cancelled
                      ? Colors.green[300]
                      : Colors.white54,
                  fontSize: 13,
                ),
              ),
            ],
            const SizedBox(height: 16),

            // Bouton Annuler / Fermer
            Align(
              alignment: Alignment.centerRight,
              child: _done || _cancelled
                  ? ElevatedButton(
                      onPressed: () => Navigator.pop(context),
                      child: const Text('Fermer'),
                    )
                  : OutlinedButton.icon(
                      onPressed: _cancel,
                      icon: const Icon(Icons.cancel_outlined,
                          color: Colors.red),
                      label: const Text('Annuler',
                          style: TextStyle(color: Colors.red)),
                      style: OutlinedButton.styleFrom(
                        side: const BorderSide(color: Colors.red),
                      ),
                    ),
            ),
          ],
        ),
      ),
    );
  }
}
