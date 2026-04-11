import os, glob

# Localiser VLC
vlc_dir = None
for candidate in [
    r'C:\Program Files\VideoLAN\VLC',
    r'C:\Program Files (x86)\VideoLAN\VLC',
]:
    if os.path.exists(os.path.join(candidate, 'libvlc.dll')):
        vlc_dir = candidate
        break

if vlc_dir is None:
    raise SystemExit('ERREUR : VLC introuvable.')

print(f'VLC trouve : {vlc_dir}')

# DLL VLC a embarquer
binaries = []
for dll in glob.glob(os.path.join(vlc_dir, '*.dll')):
    binaries.append((dll, '.'))

# Dossier plugins VLC (decodeurs video - indispensable)
datas = []
vlc_plugins = os.path.join(vlc_dir, 'plugins')
if os.path.exists(vlc_plugins):
    datas.append((vlc_plugins, 'plugins'))

a = Analysis(
    ['main.py'],
    pathex=['.'],
    binaries=binaries,
    datas=datas,
    hiddenimports=[
        'PyQt6.QtWidgets',
        'PyQt6.QtCore',
        'PyQt6.QtGui',
        'PyQt6.QtNetwork',
        'PyQt6.sip',
        'sqlite3',
        'requests',
        'urllib3',
        'certifi',
        'charset_normalizer',
        'idna',
    ],
    excludes=[
        'tkinter',
        'unittest',
        'xmlrpc',
        'pydoc',
        'doctest',
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='IPTV_Player',
    debug=False,
    strip=False,
    upx=False,
    console=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name='IPTV_Player',
)
