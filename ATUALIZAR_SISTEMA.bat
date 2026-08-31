@echo off
chcp 65001 > nul
title Atualizador de Sistema - PM13 / PM11

echo ========================================================
echo       ATUALIZADOR DE SISTEMA PM13 / PM11
echo ========================================================
echo.
echo Iniciando interface grafica do atualizador...
echo.

python updater_gui.py

if errorlevel 1 (
    echo.
    echo [ERRO] Nao foi possivel iniciar a interface do atualizador.
    echo Verifique se o Python 3 esta instalado no computador.
    pause
)

