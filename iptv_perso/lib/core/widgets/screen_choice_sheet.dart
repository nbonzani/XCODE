// ============================================================
// screen_choice_sheet.dart — Dialogue "Sur quel écran ?"
// ============================================================
// Appelé juste avant de lancer la lecture.
// Retourne true si l'utilisateur choisit la TV, false pour le téléphone,
// null si l'utilisateur annule.
// ============================================================
import 'package:flutter/material.dart';

Future<bool?> showScreenChoiceSheet(
  BuildContext context, {
  required String title,
  String? posterUrl,
}) {
  return showModalBottomSheet<bool>(
    context: context,
    backgroundColor: const Color(0xFF1A2744),
    shape: const RoundedRectangleBorder(
      borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
    ),
    builder: (_) => _ScreenChoiceSheet(title: title, posterUrl: posterUrl),
  );
}

class _ScreenChoiceSheet extends StatelessWidget {
  final String  title;
  final String? posterUrl;

  const _ScreenChoiceSheet({required this.title, this.posterUrl});

  @override
  Widget build(BuildContext context) {
    return SafeArea(
      child: Padding(
        padding: const EdgeInsets.fromLTRB(20, 16, 20, 24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // Poignée visuelle
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
                if (posterUrl != null && posterUrl!.isNotEmpty)
                  ClipRRect(
                    borderRadius: BorderRadius.circular(4),
                    child: Image.network(
                      posterUrl!,
                      width: 36, height: 48,
                      fit: BoxFit.cover,
                      errorBuilder: (_, __, ___) => const SizedBox(),
                    ),
                  ),
                if (posterUrl != null && posterUrl!.isNotEmpty)
                  const SizedBox(width: 12),
                Expanded(
                  child: Text(
                    title,
                    style: const TextStyle(
                      color: Colors.white,
                      fontSize: 15,
                      fontWeight: FontWeight.w600,
                    ),
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                  ),
                ),
              ],
            ),
            const SizedBox(height: 20),

            const Text(
              'Où voulez-vous regarder ?',
              style: TextStyle(color: Colors.white54, fontSize: 13),
            ),
            const SizedBox(height: 14),

            // Option : Téléphone
            _ChoiceTile(
              icon: Icons.smartphone,
              label: 'Sur ce téléphone',
              subtitle: 'Lecture plein écran sur le S25 Ultra',
              onTap: () => Navigator.pop(context, false),
            ),
            const SizedBox(height: 10),

            // Option : TV via HDMI
            _ChoiceTile(
              icon: Icons.tv,
              label: 'Sur la TV (câble HDMI)',
              subtitle: 'L\'écran du téléphone s\'éteint pour économiser la batterie',
              highlighted: true,
              onTap: () => Navigator.pop(context, true),
            ),
          ],
        ),
      ),
    );
  }
}

class _ChoiceTile extends StatelessWidget {
  final IconData icon;
  final String   label;
  final String   subtitle;
  final bool     highlighted;
  final VoidCallback onTap;

  const _ChoiceTile({
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
        onTap: onTap,
        borderRadius: BorderRadius.circular(12),
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
          child: Row(
            children: [
              Icon(icon,
                color: highlighted ? Colors.blue[300] : Colors.white70,
                size: 28,
              ),
              const SizedBox(width: 16),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(label,
                      style: TextStyle(
                        color: highlighted ? Colors.blue[200] : Colors.white,
                        fontWeight: FontWeight.w600,
                        fontSize: 15,
                      ),
                    ),
                    const SizedBox(height: 2),
                    Text(subtitle,
                      style: const TextStyle(
                          color: Colors.white38, fontSize: 12),
                    ),
                  ],
                ),
              ),
              Icon(Icons.chevron_right,
                color: highlighted ? Colors.blue[300] : Colors.white24),
            ],
          ),
        ),
      ),
    );
  }
}
