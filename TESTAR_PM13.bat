@echo off
title PM13 Siderurgia - Suíte de Testes
chcp 65001 > nul

echo ========================================================
echo   EXECUTANDO SUÍTE DE TESTES UNITÁRIOS E INTEGRAÇÃO
echo ========================================================

:: Detect python
set PYTHON_CMD=python
py -3 --version >nul 2>&1
if %errorlevel% equ 0 (
    set PYTHON_CMD=py -3
)

echo Usando interpretador: %PYTHON_CMD%
echo.

%PYTHON_CMD% -m unittest tests/test_system.py

if %errorlevel% equ 0 (
    echo.
    echo ========================================================
    echo   [SUCESSO] Todos os testes passaram!
    echo ========================================================
) else (
    echo.
    echo ========================================================
    echo   [ERRO] Falha em um ou mais testes!
    echo ========================================================
)
echo.
pause
