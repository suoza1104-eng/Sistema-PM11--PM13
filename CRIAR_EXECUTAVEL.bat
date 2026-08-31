@echo off
chcp 65001 > nul
title Compilador de Executável - Sistema PM13 / PM11

cd /d "%~dp0"

echo ========================================================
echo   COMPILADOR DE EXECUTÁVEL (.EXE) - SISTEMA PM13/PM11
echo ========================================================
echo.
echo Verificando PyInstaller...
echo.

python -c "import PyInstaller" 2>nul
if errorlevel 1 (
    echo [INFO] Instalando PyInstaller para compilação...
    pip install pyinstaller
)

echo.
echo Compilando launcher.py para Sistema_PM13_PM11.exe...
pyinstaller --noconfirm --onedir --windowed --name "Sistema_PM13_PM11" launcher.py

if errorlevel 0 (
    echo.
    echo ========================================================
    echo  🎉 EXECUTÁVEL COMPILADO COM SUCESSO!
    echo  Arquivo gerado na pasta: dist\Sistema_PM13_PM11\
    echo ========================================================
) else (
    echo.
    echo [AVISO] Nao foi possivel compilar o executavel standalone.
    echo O sistema continua funcionando 100%% via INICIAR_SISTEMA.bat e launcher.py.
)

pause
