import sys, os, subprocess, shutil

base = os.path.dirname(os.path.abspath(__file__))
os.chdir(base)
log_path = os.path.join(base, 'build_log.txt')

def section(title):
    print()
    print(f'[{title}]')

def run(cmd):
    print(f'  > {" ".join(str(c) for c in cmd)}')
    with open(log_path, 'a', encoding='utf-8') as log:
        r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                           text=True, encoding='utf-8', errors='replace')
        log.write(r.stdout)
        print(r.stdout[-3000:] if len(r.stdout) > 3000 else r.stdout)
    return r.returncode

# Vider le log
open(log_path, 'w').close()

print()
print('=================================================')
print('  IPTV Player - Construction du .exe')
print('=================================================')
print(f'  Dossier : {base}')
print(f'  Log     : {log_path}')
print()

section('1/4 - Installation PyInstaller')
rc = run([sys.executable, '-m', 'pip', 'install', 'pyinstaller'])
if rc != 0:
    print('  ERREUR : installation PyInstaller impossible.')
    input('Entree pour quitter...')
    sys.exit(1)
print('  OK')

section('2/4 - Nettoyage')
for d in ['dist', 'build']:
    p = os.path.join(base, d)
    if os.path.exists(p):
        shutil.rmtree(p)
        print(f'  {d} supprime')
print('  OK')

section('3/4 - Build PyInstaller (2 a 5 min)')
spec = os.path.join(base, 'IPTV_Player.spec')
rc = run([sys.executable, '-m', 'PyInstaller', spec, '--noconfirm', '--clean'])
print()
if rc != 0:
    print('  ERREUR lors du build.')
    print(f'  Le log complet est dans : {log_path}')
    print(  '  Copiez le contenu de ce fichier et partagez-le pour obtenir de l aide.')
    input('Entree pour quitter...')
    sys.exit(1)

section('4/4 - Verification')
exe_path = os.path.join(base, 'dist', 'IPTV_Player', 'IPTV_Player.exe')
if os.path.exists(exe_path):
    size_mb = os.path.getsize(exe_path) / 1024 / 1024
    print(f'  IPTV_Player.exe : OK ({size_mb:.1f} Mo)')
else:
    print('  ERREUR : IPTV_Player.exe non trouve apres le build.')
    print(f'  Consultez : {log_path}')
    input('Entree pour quitter...')
    sys.exit(1)

dist = os.path.join(base, 'dist', 'IPTV_Player')
print()
print('=================================================')
print('  BUILD REUSSI !')
print('=================================================')
print()
print(f'  Application : {dist}')
print()
print('  Pour utiliser sur un autre PC :')
print('  Copiez le dossier dist\\IPTV_Player\\ en entier')
print('  puis double-cliquez sur IPTV_Player.exe')
print()
os.startfile(dist)
input('Entree pour fermer...')
