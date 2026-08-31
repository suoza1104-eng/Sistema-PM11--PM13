@echo off
chcp 65001 > nul
title Gerador de Pacote de Atualizacao - PM13 / PM11

cd /d "%~dp0"

echo ========================================================
echo   GERADOR DE PACOTE DE ATUALIZACAO PM13 / PM11
echo ========================================================
echo.
echo Iniciando empacotamento para envio a equipe...
echo.

python build_package.py

if errorlevel 1 (
    echo.
    echo [ERRO] Ocorreu uma falha ao gerar o pacote. Verifique se o Python 3 esta instalado.
    echo.
)

pause
