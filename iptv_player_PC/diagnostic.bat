@echo off
cd /d "%~dp0"
echo.
echo =============================================
echo  DIAGNOSTIC IPTV Player
echo =============================================
echo.
echo --- Python ---
python --version 2>nul
if errorlevel 1 (
    echo ABSENT
) else (
    echo OK
    where python
)
echo.
echo --- pip ---
pip --version 2>nul
if errorlevel 1 (echo ABSENT) else (echo OK)
echo.
echo --- PyInstaller ---
pip show pyinstaller 2>/dev/null | findstr /i version
if errorlevel 1 (echo Non installe) else (echo OK - voir version ci-dessus)
echo.
echo --- PyQt6 ---
pip show PyQt6 2>/dev/null | findstr /i version
if errorlevel 1 (echo Non installe) else (echo OK)
echo.
echo --- python-vlc ---
pip show python-vlc 2>/dev/null | findstr /i version
if errorlevel 1 (echo Non installe) else (echo OK)
echo.
echo --- VLC ---
if exist "C:\Program Files\VideoLAN\VLC\libvlc.dll" (
    echo OK - C:\Program Files\VideoLAN\VLC
) else if exist "C:\Program Files (x86)\VideoLAN\VLC\libvlc.dll" (
    echo OK - C:\Program Files (x86)\VideoLAN\VLC
) else (
    echo ABSENT
)
echo.
echo --- Fichiers application ---
if exist "%~dp0main.py" (echo main.py : OK) else (echo main.py : MANQUANT)
if exist "%~dp0IPTV_Player.spec" (echo IPTV_Player.spec : OK) else (echo IPTV_Player.spec : MANQUANT)
echo.
echo Dossier : %~dp0
echo.
echo =============================================
echo  Appuyez sur une touche pour fermer...
echo =============================================
pause > nul
