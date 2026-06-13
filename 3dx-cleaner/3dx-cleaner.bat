@echo off
REM ============================================================================
REM  Lanceur 3dx-cleaner (GUI PyQt6 de purge controlee de donnees 3DEXPERIENCE).
REM  A lancer depuis le repertoire du projet ou par double-clic : %~dp0 ancre
REM  le script sur son propre dossier, quel que soit le repertoire courant.
REM
REM  Astuce : pour lancer SANS fenetre console, remplacer python.exe par
REM  pythonw.exe ci-dessous (mais les traces d'erreur ne seront plus visibles).
REM ============================================================================
setlocal
cd /d "%~dp0"

set "VENV_PY=%~dp0.venv\Scripts\python.exe"

if not exist "%VENV_PY%" (
    echo [3dx-cleaner] Environnement virtuel introuvable :
    echo     %VENV_PY%
    echo.
    echo Creez-le puis installez le projet + le moteur en editable :
    echo     python -m venv .venv
    echo     .venv\Scripts\python.exe -m pip install -e .
    echo     .venv\Scripts\python.exe -m pip install -e D:\CLAUDE\XCODE\3dx-mcp
    echo.
    pause
    exit /b 1
)

echo [3dx-cleaner] Demarrage...
"%VENV_PY%" -m threedx_cleaner %*
set "RC=%ERRORLEVEL%"

if not "%RC%"=="0" (
    echo.
    echo [3dx-cleaner] Arret avec le code %RC%.
    echo Consultez la trace ci-dessus.
    pause
)

endlocal
exit /b %RC%
