@echo off
echo ============================================================
echo   Installation de l'application IPTV Player
echo ============================================================
echo.

REM ---- Verification Python ----
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ERREUR : Python n'est pas installe ou pas dans le PATH.
    echo.
    echo  Telechargez Python 3.10 ou superieur sur :
    echo  https://www.python.org/downloads/
    echo.
    echo  IMPORTANT : cochez "Add Python to PATH" lors de l'installation.
    pause
    exit /b 1
)

REM ---- Verification que Python est bien 64-bit ----
python -c "import struct; assert struct.calcsize('P')*8 == 64" >nul 2>&1
if %errorlevel% neq 0 (
    echo AVERTISSEMENT : Votre Python semble etre en 32-bit.
    echo python-vlc requiert Python 64-bit et VLC 64-bit.
    echo Telechargez Python 64-bit sur https://www.python.org/downloads/
    echo.
    pause
)

REM ---- Verification VLC ----
if exist "C:\Program Files\VideoLAN\VLC\libvlc.dll" (
    echo VLC 64-bit detecte.
) else if exist "C:\Program Files (x86)\VideoLAN\VLC\libvlc.dll" (
    echo AVERTISSEMENT : VLC 32-bit detecte dans Program Files ^(x86^).
    echo python-vlc necessite VLC 64-bit.
    echo Telechargez VLC 64-bit sur : https://www.videolan.org/vlc/
    echo.
    pause
) else (
    echo AVERTISSEMENT : VLC introuvable dans les emplacements habituels.
    echo Si VLC est installe dans un autre dossier, ignorez ce message.
    echo Sinon, telechargez VLC 64-bit sur : https://www.videolan.org/vlc/
    echo.
    pause
)

REM ---- Installation des dependances Python ----
echo.
echo Installation des dependances Python...
echo.
pip install -r requirements.txt

if %errorlevel% neq 0 (
    echo.
    echo ERREUR lors de l'installation des dependances.
    echo Verifiez votre connexion internet et relancez ce script.
    pause
    exit /b 1
)

echo.
echo ============================================================
echo   Installation terminee avec succes !
echo.
echo   Pour lancer l'application :
echo     - Double-cliquez sur launch.bat
echo     - ou : python main.py dans ce dossier
echo ============================================================
echo.
pause
