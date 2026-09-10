@echo off
chcp 65001 > nul
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0build_portable.ps1" %*
if errorlevel 1 (
 echo Falha no build. Para preparar dependencias: CRIAR_EXECUTAVEL.bat -PrepareOnline
 pause
 exit /b 1
)
pause
