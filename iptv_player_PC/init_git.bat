@echo off
:: ============================================================
::  init_git.bat  —  Initialisation du depot Git IPTV Player
::  A executer UNE SEULE FOIS depuis le dossier du projet
:: ============================================================

echo.
echo =========================================
echo  Initialisation du depot Git IPTV Player
echo =========================================
echo.

:: Se placer dans le dossier du script
cd /d "%~dp0"

:: Verifier que Git est installe
git --version >nul 2>&1
if errorlevel 1 (
    echo [ERREUR] Git n'est pas installe ou pas dans le PATH.
    echo Telechargez-le sur https://git-scm.com/download/win
    pause
    exit /b 1
)

:: Supprimer le depot .git partiel s'il existe deja (evite l'erreur index.lock)
if exist ".git" (
    echo Suppression du depot Git precedent incomplet...
    rmdir /s /q ".git"
    echo Fait.
)

:: Initialiser le depot
git init
if errorlevel 1 goto erreur

:: Configurer l'identite (modifiez si necessaire)
git config user.name "Nico"
git config user.email "nbonzani@gmail.com"

:: Ajouter tous les fichiers sources (sauf ce que .gitignore exclut)
git add .gitignore
git add main.py main_window.py player_window.py
git add cache_db.py download_manager.py series_dialog.py
git add config.py xtream_api.py play_options_dialog.py settings_dialog.py
git add requirements.txt launch.bat install.bat

:: Creer le premier commit
git commit -m "Version stable — corrections VLC, cache SQLite, sous-repertoires, episodes visionnes"
if errorlevel 1 goto erreur

echo.
echo =========================================
echo  Depot Git initialise avec succes !
echo  Premier commit cree.
echo =========================================
echo.
echo Les 3 commandes essentielles a retenir :
echo.
echo   git add -u                    (preparer vos modifications)
echo   git commit -m "description"   (sauvegarder un jalon)
echo   git log --oneline             (voir l'historique)
echo.
pause
exit /b 0

:erreur
echo.
echo [ERREUR] Une erreur s'est produite. Verifiez les messages ci-dessus.
pause
exit /b 1
