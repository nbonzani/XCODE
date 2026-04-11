# -*- mode: python ; coding: utf-8 -*-
#
# Fichier de configuration PyInstaller pour PC_Gestion_M3U
# Application de gestion de listes M3U / Xtream
# Dépendances : PyQt6, requests, python-vlc
#
# Usage : pyinstaller PC_Gestion_M3U.spec
#

import os
import sys
from pathlib import Path

block_cipher = None

# ──────────────────────────────────────────────
# Données à inclure dans l'exécutable
# ──────────────────────────────────────────────
datas = [
    # Dossier data/ (config.json, caches) — sera créé au premier lancement si absent
    ('data', 'data'),
]

# ──────────────────────────────────────────────
# Modules cachés que PyInstaller peut manquer
# ──────────────────────────────────────────────
hiddenimports = [
    'PyQt6.QtCore',
    'PyQt6.QtGui',
    'PyQt6.QtWidgets',
    'PyQt6.sip',
    'requests',
    'urllib3',
    'urllib3.util.retry',
    'vlc',
]

a = Analysis(
    ['main.py'],
    pathex=['.'],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter',
        'matplotlib',
        'numpy',
        'scipy',
        'PIL',
        'IPython',
        'jupyter',
        'pandas',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='PC_Gestion_M3U',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,          # Pas de fenêtre console noire
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # icon='icon.ico',      # Décommenter et fournir un fichier .ico si souhaité
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='PC_Gestion_M3U',
)
