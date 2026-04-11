@echo off
cd /d "%~dp0"
python main.py
if %errorlevel% neq 0 (
    echo.
    echo Une erreur s'est produite. Avez-vous bien execute install.bat ?
    pause
)
