import sys, os, subprocess

def check(label, cmd):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        out = (r.stdout + r.stderr).strip()
        if r.returncode == 0 and out:
            print(f'  {label}: OK  ->  {out.splitlines()[0]}')
        elif r.returncode == 0:
            print(f'  {label}: OK')
        else:
            print(f'  {label}: ABSENT ou erreur')
    except FileNotFoundError:
        print(f'  {label}: ABSENT (commande introuvable)')
    except Exception as e:
        print(f'  {label}: ERREUR  ->  {e}')

def check_pip_pkg(pkg):
    try:
        r = subprocess.run([sys.executable, '-m', 'pip', 'show', pkg],
                           capture_output=True, text=True, timeout=15)
        for line in r.stdout.splitlines():
            if line.lower().startswith('version'):
                print(f'  {pkg}: OK  ->  {line}')
                return
        print(f'  {pkg}: Non installe')
    except Exception as e:
        print(f'  {pkg}: ERREUR  ->  {e}')

print()
print('=============================================')
print('  DIAGNOSTIC IPTV Player')
print('=============================================')
print()

print('--- Python ---')
print(f'  Version : {sys.version}')
print(f'  Chemin  : {sys.executable}')
print()

print('--- Bibliotheques Python ---')
check_pip_pkg('pip')
check_pip_pkg('pyinstaller')
check_pip_pkg('PyQt6')
check_pip_pkg('python-vlc')
check_pip_pkg('requests')
print()

print('--- VLC (DLL) ---')
vlc_paths = [
    r'C:\Program Files\VideoLAN\VLC\libvlc.dll',
    r'C:\Program Files (x86)\VideoLAN\VLC\libvlc.dll',
]
vlc_found = False
for p in vlc_paths:
    if os.path.exists(p):
        print(f'  VLC : OK  ->  {os.path.dirname(p)}')
        vlc_found = True
        break
if not vlc_found:
    print('  VLC : ABSENT  ->  installez VLC depuis https://www.videolan.org/')
print()

print('--- Fichiers de l application ---')
base = os.path.dirname(os.path.abspath(__file__))
for f in ['main.py', 'main_window.py', 'IPTV_Player.spec', 'build_exe.bat']:
    p = os.path.join(base, f)
    status = 'OK' if os.path.exists(p) else 'MANQUANT'
    print(f'  {f}: {status}')
print()

print(f'Dossier : {base}')
print()
print('=============================================')
input('  Appuyez sur Entree pour fermer...')
