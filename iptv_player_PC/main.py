"""
main.py - Point d'entrée de l'application IPTV Player.

Lancement :
    python main.py
    ou double-clic sur launch.bat

Prérequis :
    pip install -r requirements.txt
    (ou exécuter install.bat sous Windows)
"""

import sys
from PyQt6.QtWidgets import QApplication

from main_window import MainWindow


def main():
    """Initialise et lance l'application."""

    # Créer l'application Qt
    app = QApplication(sys.argv)
    app.setApplicationName("IPTV Player")
    app.setOrganizationName("MonIPTV")

    # Note : PyQt6 gère nativement le HiDPI, aucun attribut supplémentaire nécessaire

    # Créer et afficher la fenêtre principale
    window = MainWindow()
    window.show()

    # Démarrer la boucle d'événements Qt
    # sys.exit() assure que le code de retour est propagé au système
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
