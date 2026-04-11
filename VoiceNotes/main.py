"""
main.py
-------
Point d'entrée de l'application VoiceNotes.

Responsabilités :
  1. Initialiser la base de données SQLite (création des tables si nécessaire)
  2. Créer l'application PyQt6
  3. Afficher la fenêtre principale
"""

import sys
import os

# Ajout du répertoire racine au PYTHONPATH pour les imports relatifs
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QFont, QIcon
from PyQt6.QtCore import Qt

from core.database import init_database
from ui.main_window import MainWindow


def main():
    # --- Initialisation de la base de données ---
    init_database()

    # --- Création de l'application PyQt6 ---
    app = QApplication(sys.argv)
    app.setApplicationName("VoiceNotes")
    app.setOrganizationName("VoiceNotes")

    # Police par défaut (Segoe UI = police native Windows)
    font = QFont("Segoe UI", 10)
    app.setFont(font)

    # Thème visuel natif Windows
    app.setStyle("Fusion")

    # Feuille de style globale minimale
    app.setStyleSheet("""
        QMainWindow {
            background-color: #ffffff;
        }
        QMenuBar {
            background-color: #f8f8f8;
            border-bottom: 1px solid #e0e0e0;
            font-size: 10pt;
        }
        QMenuBar::item:selected {
            background-color: #e3f2fd;
        }
        QMenu {
            background-color: #ffffff;
            border: 1px solid #ddd;
        }
        QMenu::item:selected {
            background-color: #1565c0;
            color: white;
        }
        QStatusBar {
            background-color: #f8f8f8;
            border-top: 1px solid #e0e0e0;
            color: #555;
        }
        QScrollBar:vertical {
            width: 10px;
            background: #f5f5f5;
        }
        QScrollBar::handle:vertical {
            background: #bdbdbd;
            border-radius: 5px;
        }
    """)

    # --- Fenêtre principale ---
    fenetre = MainWindow()
    fenetre.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
