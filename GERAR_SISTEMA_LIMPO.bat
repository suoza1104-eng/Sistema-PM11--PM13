@echo off
chcp 65001 > nul
title Gerador de Sistema Virgem / Limpo - PM13 / PM11

cd /d "%~dp0"

echo ========================================================
echo   GERADOR DE SISTEMA VIRGEM / LIMPO PM13 / PM11
echo ========================================================
echo.
echo Gerando pacote limpo com bancos inicializados e sem cadastros...
echo.

python build_clean_package.py

if errorlevel 1 (
    echo.
    echo [ERRO] Ocorreu uma falha ao gerar o pacote limpo.
    echo.
)

pause
