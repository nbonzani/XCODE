@echo off
cd /d "%~dp0"
title IPTV Player - Construction

echo.
echo  ================================================
echo   IPTV Player - Construction de l'executable
echo  ================================================
echo.

:: Verification Python
echo [1/5] Verification de Python...
python --version
if errorlevel 1 (
    echo.
    echo  ERREUR : Python introuvable.
    echo  Installez Python depuis https://www.python.org/downloads/
    echo  et cochez "Add Python to PATH" lors de l'installation.
    echo.
    pause
    exit /b 1
)
echo  Python : OK
echo.

:: Verification VLC
echo [2/5] Verification de VLC...
set VLC_PATH=
if exist "C:\Program Files\VideoLAN\VLC\libvlc.dll" set VLC_PATH=C:\Program Files\VideoLAN\VLC
if exist "C:\Program Files (x86)\VideoLAN\VLC\libvlc.dll" set VLC_PATH=C:\Program Files (x86)\VideoLAN\VLC
if "%VLC_PATH%"=="" (
    echo.
    echo  ERREUR : VLC introuvable.
    echo  Installez VLC depuis https://www.videolan.org/
    echo.
    pause
    exit /b 1
)
echo  VLC : OK
echo.

:: Installation des bibliotheques
echo [3/5] Installation des bibliotheques Python...
pip install --quiet --upgrade pip
pip install --quiet PyQt6 python-vlc requests pyinstaller
if errorlevel 1 (
    echo.
    echo  ERREUR lors de l'installation pip.
    echo  Verifiez votre connexion internet.
    echo.
    pause
    exit /b 1
)
echo  Bibliotheques : OK
echo.

:: Nettoyage
echo [4/5] Nettoyage...
if exist "dist\IPTV_Player" rmdir /s /q "dist\IPTV_Player"
if exist "build" rmdir /s /q "build"
echo  Nettoyage : OK
echo.

:: Build
echo [5/5] Construction (2 a 5 minutes, merci de patienter)...
echo.
pyinstaller IPTV_Player.spec --noconfirm
if errorlevel 1 (
    echo.
    echo  ERREUR lors du build PyInstaller.
    echo  Consultez les messages ci-dessus.
    echo.
    pause
    exit /b 1
)

echo.
echo  ================================================
echo   BUILD REUSSI !
echo  ================================================
echo.
echo  Dossier de l'application :
echo    %~dp0dist\IPTV_Player\
echo.
echo  Copiez ce dossier entier sur le PC cible,
echo  puis double-cliquez sur IPTV_Player.exe
echo.
start explorer "%~dp0dist\IPTV_Player"
pause
