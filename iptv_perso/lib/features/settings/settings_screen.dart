// ============================================================
// settings_screen.dart — Écran de configuration du serveur Xtream
// ============================================================
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:go_router/go_router.dart';

import '../../core/api/xtream_client.dart';
import '../../core/api/models.dart';
import '../../core/cache/catalogue_cache.dart';
import '../../core/providers/xtream_providers.dart';

class SettingsScreen extends ConsumerStatefulWidget {
  const SettingsScreen({super.key});

  @override
  ConsumerState<SettingsScreen> createState() => _SettingsScreenState();
}

class _SettingsScreenState extends ConsumerState<SettingsScreen> {
  final _formKey          = GlobalKey<FormState>();
  final _hostController   = TextEditingController();
  final _userController   = TextEditingController();
  final _passController   = TextEditingController();

  bool   _isTesting       = false;
  bool   _showPassword    = false;
  String? _statusMessage;
  bool   _statusIsError   = false;
  bool   _isFirstLoad     = true;

  static const _storage = FlutterSecureStorage();

  // --------------------------------------------------------
  // Cycle de vie
  // --------------------------------------------------------
  @override
  void initState() {
    super.initState();
    _loadExistingCredentials();
  }

  @override
  void dispose() {
    _hostController.dispose();
    _userController.dispose();
    _passController.dispose();
    super.dispose();
  }

  // --------------------------------------------------------
  // Chargement des credentials existants au démarrage
  // --------------------------------------------------------
  Future<void> _loadExistingCredentials() async {
    final host     = await _storage.read(key: 'xtream_host');
    final username = await _storage.read(key: 'xtream_username');
    final password = await _storage.read(key: 'xtream_password');

    if (!mounted) return;

    if (host != null && username != null && password != null) {
      // Des credentials valides existent → aller directement au catalogue
      context.go('/catalogue');
      return;
    }

    // Aucun credential → afficher le formulaire
    setState(() => _isFirstLoad = false);
  }

  // --------------------------------------------------------
  // Test de connexion + sauvegarde
  // --------------------------------------------------------
  Future<void> _testAndSave() async {
    if (!_formKey.currentState!.validate()) return;

    setState(() {
      _isTesting      = true;
      _statusMessage  = 'Test de connexion en cours…';
      _statusIsError  = false;
    });

    final creds = XtreamCredentials(
      host:     _hostController.text.trim(),
      username: _userController.text.trim(),
      password: _passController.text.trim(),
    );

    final client = XtreamClient(credentials: creds);
    final ok = await client.testConnection();

    if (!mounted) return;

    if (ok) {
      // Sauvegarde chiffrée des credentials
      await _storage.write(key: 'xtream_host',     value: creds.host);
      await _storage.write(key: 'xtream_username', value: creds.username);
      await _storage.write(key: 'xtream_password', value: creds.password);

      // On vide le cache si le serveur a changé
      await CatalogueCache.clearAll();

      // On invalide les providers Riverpod pour forcer le rechargement
      ref.invalidate(credentialsProvider);
      ref.invalidate(xtreamClientProvider);

      if (mounted) context.go('/catalogue');
    } else {
      setState(() {
        _isTesting     = false;
        _statusMessage = 'Connexion échouée. Vérifiez l\'URL, le nom d\'utilisateur et le mot de passe.';
        _statusIsError = true;
      });
    }
  }

  // --------------------------------------------------------
  // Construction de l'interface
  // --------------------------------------------------------
  @override
  Widget build(BuildContext context) {
    // Pendant la vérification initiale, on affiche un écran de chargement
    if (_isFirstLoad) {
      return const Scaffold(
        body: Center(child: CircularProgressIndicator()),
      );
    }

    return Scaffold(
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(28.0),
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 480),
              child: Form(
                key: _formKey,
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    // En-tête
                    const Icon(Icons.live_tv, size: 72, color: Color(0xFF1565C0)),
                    const SizedBox(height: 12),
                    Text(
                      'IPTV Perso',
                      style: Theme.of(context).textTheme.headlineMedium
                          ?.copyWith(fontWeight: FontWeight.bold),
                      textAlign: TextAlign.center,
                    ),
                    const SizedBox(height: 6),
                    Text(
                      'Configurez votre serveur Xtream',
                      style: Theme.of(context).textTheme.bodyMedium
                          ?.copyWith(color: Colors.white54),
                      textAlign: TextAlign.center,
                    ),
                    const SizedBox(height: 36),

                    // Champ URL serveur
                    TextFormField(
                      controller: _hostController,
                      decoration: const InputDecoration(
                        labelText: 'URL du serveur',
                        hintText: 'http://monserveur.com:8080',
                        prefixIcon: Icon(Icons.dns_outlined),
                        border: OutlineInputBorder(),
                      ),
                      keyboardType: TextInputType.url,
                      autocorrect: false,
                      validator: (v) {
                        if (v == null || v.trim().isEmpty) return 'Champ requis';
                        if (!v.trim().startsWith('http')) {
                          return 'L\'URL doit commencer par http:// ou https://';
                        }
                        return null;
                      },
                    ),
                    const SizedBox(height: 16),

                    // Champ nom d'utilisateur
                    TextFormField(
                      controller: _userController,
                      decoration: const InputDecoration(
                        labelText: 'Nom d\'utilisateur',
                        prefixIcon: Icon(Icons.person_outline),
                        border: OutlineInputBorder(),
                      ),
                      autocorrect: false,
                      validator: (v) =>
                          (v == null || v.trim().isEmpty) ? 'Champ requis' : null,
                    ),
                    const SizedBox(height: 16),

                    // Champ mot de passe
                    TextFormField(
                      controller: _passController,
                      obscureText: !_showPassword,
                      decoration: InputDecoration(
                        labelText: 'Mot de passe',
                        prefixIcon: const Icon(Icons.lock_outline),
                        border: const OutlineInputBorder(),
                        suffixIcon: IconButton(
                          icon: Icon(_showPassword
                              ? Icons.visibility_off
                              : Icons.visibility),
                          onPressed: () =>
                              setState(() => _showPassword = !_showPassword),
                        ),
                      ),
                      validator: (v) =>
                          (v == null || v.trim().isEmpty) ? 'Champ requis' : null,
                    ),
                    const SizedBox(height: 28),

                    // Message de statut (erreur ou info)
                    if (_statusMessage != null) ...[
                      Container(
                        padding: const EdgeInsets.symmetric(
                            horizontal: 16, vertical: 12),
                        decoration: BoxDecoration(
                          color: _statusIsError
                              ? Colors.red.withOpacity(0.15)
                              : Colors.blue.withOpacity(0.15),
                          borderRadius: BorderRadius.circular(8),
                          border: Border.all(
                            color: _statusIsError ? Colors.red : Colors.blue,
                            width: 0.5,
                          ),
                        ),
                        child: Row(
                          children: [
                            Icon(
                              _statusIsError ? Icons.error_outline : Icons.info_outline,
                              color: _statusIsError ? Colors.red : Colors.blue,
                              size: 20,
                            ),
                            const SizedBox(width: 10),
                            Expanded(
                              child: Text(
                                _statusMessage!,
                                style: TextStyle(
                                  color: _statusIsError ? Colors.red[300] : Colors.blue[300],
                                  fontSize: 13,
                                ),
                              ),
                            ),
                          ],
                        ),
                      ),
                      const SizedBox(height: 20),
                    ],

                    // Bouton de connexion
                    FilledButton.icon(
                      onPressed: _isTesting ? null : _testAndSave,
                      icon: _isTesting
                          ? const SizedBox(
                              width: 18,
                              height: 18,
                              child: CircularProgressIndicator(
                                  strokeWidth: 2, color: Colors.white),
                            )
                          : const Icon(Icons.login),
                      label: Text(_isTesting ? 'Connexion…' : 'Se connecter'),
                      style: FilledButton.styleFrom(
                        padding: const EdgeInsets.symmetric(vertical: 16),
                        textStyle: const TextStyle(fontSize: 16),
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}
