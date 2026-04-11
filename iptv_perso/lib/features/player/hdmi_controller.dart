// ============================================================
// hdmi_controller.dart — Gestion HDMI, WakeLock et luminosité
// ============================================================
// Objectif : lire un film sur TV (câble USB-C/HDMI branché)
// tout en préservant la batterie du téléphone.
//
// Stratégie :
//   1. WakeLock actif → le CPU reste éveillé pour décoder la vidéo
//   2. Luminosité réduite à 0 → l'écran du téléphone s'éteint visuellement
//      sans couper le processus vidéo (la TV continue d'afficher)
//   3. À la fermeture du lecteur → tout est restauré
// ============================================================
import 'package:wakelock_plus/wakelock_plus.dart';
import 'package:screen_brightness/screen_brightness.dart';

class HdmiController {
  double? _originalBrightness;

  // --------------------------------------------------------
  // Activer le mode HDMI (début de lecture)
  // --------------------------------------------------------
  Future<void> enableHdmiMode() async {
    // 1. Activer le WakeLock : empêche le CPU de s'endormir
    //    L'écran peut toujours s'éteindre (géré séparément ci-dessous)
    await WakelockPlus.enable();

    // 2. Sauvegarder la luminosité actuelle pour la restaurer plus tard
    try {
      _originalBrightness = await ScreenBrightness().current;
    } catch (_) {
      _originalBrightness = null;
    }
  }

  // --------------------------------------------------------
  // Éteindre l'écran du téléphone (pendant lecture sur TV)
  // --------------------------------------------------------
  Future<void> dimScreen() async {
    try {
      // Luminosité à 0 = écran noir (backlight réduit au minimum)
      // La vidéo continue de s'afficher sur la TV via HDMI
      await ScreenBrightness().setScreenBrightness(0.0);
    } catch (_) {
      // Si le plugin n'est pas disponible, on ignore silencieusement
    }
  }

  // --------------------------------------------------------
  // Rallumer l'écran du téléphone (interaction utilisateur)
  // --------------------------------------------------------
  Future<void> restoreScreen() async {
    try {
      if (_originalBrightness != null) {
        await ScreenBrightness().setScreenBrightness(_originalBrightness!);
      } else {
        await ScreenBrightness().resetScreenBrightness();
      }
    } catch (_) {}
  }

  // --------------------------------------------------------
  // Désactiver le mode HDMI (fin de lecture)
  // --------------------------------------------------------
  Future<void> disableHdmiMode() async {
    // Restaurer la luminosité
    await restoreScreen();

    // Désactiver le WakeLock (le système peut à nouveau gérer la veille)
    await WakelockPlus.disable();
  }
}
