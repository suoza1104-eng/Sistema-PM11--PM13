"""
Script de Criação de Pacote de Atualização de Distribuição (PM13/PM11)
Empacota os arquivos fonte do sistema sem incluir bancos de dados nem caches locais.
"""

import os
import sys
import time
import zipfile

def build_update_package():
    sys.stdout.reconfigure(encoding='utf-8')
    root_dir = os.path.dirname(os.path.abspath(__file__))
    ts = time.strftime('%Y%m%d_%H%M%S')
    zip_filename = f'PACOTE_ATUALIZACAO_PM13_PM11_{ts}.zip'
    zip_path = os.path.join(root_dir, zip_filename)

    include_items = [
        'app_icon.ico',
        'launcher.py',
        'INICIAR_SISTEMA.bat',
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

    print("========================================================")
    print("   GERADOR DE PACOTE DE ATUALIZAÇÃO PM13 / PM11")
    print("========================================================")
    print(f"\nCriando pacote: {zip_filename}...\n")

    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        for item in include_items:
            item_path = os.path.join(root_dir, item)
            if os.path.exists(item_path):
                if os.path.isfile(item_path):
                    zf.write(item_path, item)
                    print(f" + Arquivo: {item}")
                elif os.path.isdir(item_path):
                    for r, dirs, files in os.walk(item_path):
                        dirs[:] = [d for d in dirs if d not in ('__pycache__', '.venv', '.vscode', '.claude')]
                        for file in files:
                            if not file.endswith(('.pyc', '.pyo', '.db', '.sqlite')):
                                full_path = os.path.join(r, file)
                                rel_path = os.path.relpath(full_path, root_dir)
                                zf.write(full_path, rel_path)
                    print(f" + Pasta: {item}")

    size_mb = os.path.getsize(zip_path) / (1024 * 1024)
    print("\n========================================================")
    print("🎉 PACOTE GERADO COM SUCESSO!")
    print(f"Arquivo: {zip_filename} ({size_mb:.2f} MB)")
    print(f"Local: {zip_path}")
    print("========================================================\n")

if __name__ == "__main__":
    build_update_package()

