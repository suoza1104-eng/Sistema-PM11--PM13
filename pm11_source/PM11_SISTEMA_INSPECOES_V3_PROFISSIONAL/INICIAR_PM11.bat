@echo off
setlocal
cd /d "%~dp0"
title PM11 - Planos de Inspecao
cls
echo ============================================================
echo PM11 - PLANOS E ORDENS DE INSPECAO
echo ============================================================
echo.
echo Servidor local: http://127.0.0.1:8766
echo Banco: data\pm11.db
echo.
echo Mantenha esta janela aberta para acompanhar logs e diagnosticos.
echo Para encerrar, pressione CTRL+C.
echo.
python app.py
if errorlevel 1 (
  echo.
  echo O servidor foi encerrado com erro.
  pause
)
endlocal
