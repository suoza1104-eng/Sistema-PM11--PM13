@echo off
title PM13 Siderurgia - Iniciar Sistema
chcp 65001 > nul

echo ========================================================
echo   INICIANDO SISTEMA DE CONTROLE PM13 (SIDERURGIA)
echo ========================================================

:: Detect python
set PYTHON_CMD=python
py -3 --version >nul 2>&1
if %errorlevel% equ 0 (
    set PYTHON_CMD=py -3
)

echo Usando interpretador: %PYTHON_CMD%
echo.
echo Inicializando o servidor local e abrindo o navegador...
echo Pressione Ctrl+C ou clique em "Encerrar Sistema" na barra lateral para desligar.
echo ========================================================
echo.

%PYTHON_CMD% app.py

pause
