@echo off
chcp 65001 > nul
cd /d "%~dp0"
where py >nul 2>nul
if not errorlevel 1 (
    py -3 build_clean_package.py
) else (
    python build_clean_package.py
)
if errorlevel 1 (
    echo Falha ao executar. Verifique se Python 3 esta instalado.
    pause
    exit /b 1
)
pause
