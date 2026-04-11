# =============================================================================
# STL Slicer — Application de découpe laser par empilement de plaques
# Description : Importe un STL, sectionne en tranches, répartit sur plaque,
#               exporte en DXF pour découpe laser.
# Auteur      : Polytech Nancy
# Lancement   : python main.py
# =============================================================================

import sys
import os

# Forcer l'utilisation de PyQt6 par qtpy (abstraction Qt utilisée par pyvistaqt)
os.environ['QT_API'] = 'pyqt6'

from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QFont

from ui.main_window import MainWindow


def main():
    """Point d'entrée principal de l'application."""
    app = QApplication(sys.argv)
    app.setApplicationName("STL Slicer")
    app.setApplicationDisplayName("STL Slicer — Découpe Laser")
    app.setOrganizationName("Polytech Nancy")

    # Style sombre pour une meilleure lisibilité
    app.setStyle("Fusion")

    # Police globale agrandie pour une meilleure lisibilité
    police = QFont("Segoe UI", 11)
    app.setFont(police)

    # Création et affichage de la fenêtre principale
    fenetre = MainWindow()
    fenetre.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
