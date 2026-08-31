@echo off
chcp 65001 > nul
title Gerador de Pacote de Atualização - PM13 / PM11

echo ========================================================
echo   GERADOR DE PACOTE DE ATUALIZAÇÃO PM13 / PM11
echo ========================================================
echo.
echo Criando pacote de distribuição limpo para envio a equipe...
echo.

python -c "
import os, zipfile, time

ts = time.strftime('%Y%m%d_%H%M%S')
zip_name = 'PACOTE_ATUALIZACAO_PM13_PM11_' + ts + '.zip'

include_items = [
    'updater_gui.py',
    'ATUALIZAR_SISTEMA.bat',
    'INICIAR_PM13.bat',
    'TESTAR_PM13.bat',
    'app.py',
    'core',
    'core_pm11',
    'catalogs',
    'static',
    'tests',
    'read_xlsb.ps1',
    'README.md',
    'MANUAL_USUARIO.html',
    '.gitignore'
]

print('Criando arquivo ZIP:', zip_name)
with zipfile.ZipFile(zip_name, 'w', zipfile.ZIP_DEFLATED) as zf:
    for item in include_items:
        if os.path.exists(item):
            if os.path.isfile(item):
                zf.write(item, item)
                print(' + Arquivo:', item)
            elif os.path.isdir(item):
                for root, dirs, files in os.walk(item):
                    dirs[:] = [d for d in dirs if d not in ('__pycache__', '.venv', '.vscode', '.claude')]
                    for file in files:
                        if not file.endswith(('.pyc', '.pyo', '.db', '.sqlite')):
                            full_path = os.path.join(root, file)
                            rel_path = os.path.relpath(full_path, '.')
                            zf.write(full_path, rel_path)
                print(' + Pasta:', item)

size_mb = os.path.getsize(zip_name) / (1024 * 1024)
print('\n[SUCESSO] PACOTE DE ATUALIZACAO GERADO COM SUCESSO!')
print('Arquivo:', zip_name, f'({size_mb:.2f} MB)')
"

echo.
echo ========================================================
echo  Processo concluido! O pacote ZIP pode ser enviado para a equipe.
echo ========================================================
pause

