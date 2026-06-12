"""Point d'entree : ``python -m threedx_cleaner`` ou binaire ``3dx-cleaner``."""

from __future__ import annotations

import sys


def main() -> int:
    """Lance l'application PyQt6."""
    try:
        import threedx_mcp  # noqa: F401 — verifie la presence du moteur
    except ImportError as exc:  # pragma: no cover
        print(
            "Moteur 'threedx_mcp' introuvable. Installer le moteur en editable :\n"
            "    pip install -e D:\\CLAUDE\\XCODE\\3dx-mcp",
            file=sys.stderr,
        )
        raise SystemExit(2) from exc

    from PyQt6.QtWidgets import QApplication

    from threedx_cleaner.ui.main_window import MainWindow

    app = QApplication(sys.argv)
    app.setApplicationName("3dx-cleaner")
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
