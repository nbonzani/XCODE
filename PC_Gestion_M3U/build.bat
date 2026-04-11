@echo off
chcp 65001 >nul
echo ============================================================
echo   PC_Gestion_M3U — Creation de l executable Windows
echo ============================================================
echo.

REM Verification Python
python --version >/dev/null 2>&1
if errorlevel 1 goto ERREUR_PYTHON
echo [OK] Python detecte.

REM Installation des dependances
echo.
echo [1/3] Installation des dependances Python...
pip install PyQt6 requests python-vlc pyinstaller --quiet
if errorlevel 1 goto ERREUR_PIP
echo [OK] Dependances installees.

REM Nettoyage
echo.
echo [2/3] Nettoyage des anciens fichiers...
if exist "build" rmdir /s /q "build"
if exist "dist"  rmdir /s /q "dist"
echo [OK] Nettoyage termine.

REM Compilation
echo.
echo [3/3] Compilation (1-2 minutes, merci de patienter)...
pyinstaller PC_Gestion_M3U.spec --noconfirm
if errorlevel 1 goto ERREUR_BUILD

echo.
echo ============================================================
echo   SUCCES ! Executable cree dans :
echo   dist\PC_Gestion_M3U\PC_Gestion_M3U.exe
echo ============================================================
echo.
echo Vous pouvez copier le dossier dist\PC_Gestion_M3U\ entier
echo sur n importe quel PC Windows (VLC doit etre installe).
goto FIN

:ERREUR_PYTHON
echo.
echo [ERREUR] Python nest pas installe ou pas dans le PATH.
echo Installez Python depuis https://www.python.org/downloads/
echo Cochez bien "Add Python to PATH" lors de linstallation !
goto FIN

:ERREUR_PIP
echo.
echo [ERREUR] Installation des dependances echouee.
echo Verifiez votre connexion internet et relancez.
goto FIN

:ERREUR_BUILD
echo.
echo [ERREUR] La compilation a echoue.
echo Copiez le message derreur ci-dessus et contactez le support.
goto FIN

:FIN
echo.
pause
