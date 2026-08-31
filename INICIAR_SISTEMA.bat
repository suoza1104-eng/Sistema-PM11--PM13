@echo off
chcp 65001 > nul
title Sistema PM13 / PM11 - Inicializador

cd /d "%~dp0"

python launcher.py

if errorlevel 1 (
    echo.
    echo [AVISO] Iniciar via launcher.py direto...
    python app.py
)
