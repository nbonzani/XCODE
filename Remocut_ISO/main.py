"""
main.py — Point d'entrée de Remocut ISO Generator.

Lance l'application PyQt6 avec le style Fusion.
Accepte un chemin de fichier DXF en argument optionnel.

Usage :
    python main.py                      # lance l'interface
    python main.py piece.dxf            # lance et charge directement le DXF
"""

import logging
import sys
from pathlib import Path


def configurer_logging() -> None:
    """Configure le système de logging pour l'application."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s  %(levelname)-8s  %(name)s — %(message)s',
        datefmt='%H:%M:%S',
    )
    # Réduire le bruit des bibliothèques tierces
    logging.getLogger('ezdxf').setLevel(logging.WARNING)
    logging.getLogger('shapely').setLevel(logging.WARNING)


def main() -> int:
    """
    Point d'entrée principal.

    Returns:
        Code de retour (0 = succès).
    """
    configurer_logging()
    logger = logging.getLogger(__name__)

    try:
        from PyQt6.QtWidgets import QApplication
    except ImportError:
        print(
            "ERREUR : PyQt6 n'est pas installé.\n"
            "Exécutez : pip install PyQt6",
            file=sys.stderr,
        )
        return 1

    app = QApplication(sys.argv)

    # Style Fusion pour un rendu cohérent sur Windows 10/11
    app.setStyle('Fusion')
    app.setApplicationName("Remocut ISO Generator")
    app.setApplicationVersion("1.0")
    app.setOrganizationName("Polytech Nancy")

    # Créer et afficher la fenêtre principale
    try:
        from ui.main_window import MainWindow
        fenetre = MainWindow()
        fenetre.show()
    except Exception as e:
        logger.exception("Erreur lors du démarrage de l'interface")
        print(f"ERREUR CRITIQUE : {e}", file=sys.stderr)
        return 1

    # Charger un fichier DXF passé en argument de ligne de commande
    if len(sys.argv) > 1:
        chemin_dxf = sys.argv[1]
        if Path(chemin_dxf).is_file() and chemin_dxf.lower().endswith('.dxf'):
            logger.info(f"Chargement du fichier DXF en argument : '{chemin_dxf}'")
            fenetre.charger_fichier(chemin_dxf)
        else:
            logger.warning(
                f"Argument ignoré : '{chemin_dxf}' n'est pas un fichier DXF valide."
            )

    return app.exec()


if __name__ == '__main__':
    sys.exit(main())
