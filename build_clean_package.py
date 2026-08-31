"""
Gerador de Pacote de Sistema Limpo / Virgem (PM13/PM11)
Cria um pacote ZIP de instalação limpo contendo bancos de dados virgens (tabelas e catálogos inicializados, 0 cadastros de usuário) e atalho de área de trabalho.
"""

import os
import sys
import time
import shutil
import sqlite3
import zipfile

def create_virgin_database(target_dir):
    """Cria os arquivos de banco de dados SQLite virgens inicializados."""
    os.makedirs(target_dir, exist_ok=True)
    pm13_path = os.path.join(target_dir, "pm13.db")
    pm11_path = os.path.join(target_dir, "pm11.db")

    # Se já existirem bancos locais na pasta de origem, inicializamos a estrutura chamando get_db_connection
    try:
        from core.database import get_db_connection as get_pm13_conn
        conn13 = sqlite3.connect(pm13_path)
        cur13 = conn13.cursor()
        
        # Executar schema PM13
        from core.migrations import run_migrations as run_pm13_migrations
        run_pm13_migrations(conn13)
        
        # Limpar tabelas de projetos e cadastros de usuário no PM13
        user_tables_13 = ['projects', 'plans', 'maintenance_items', 'item_operations', 'operation_long_texts', 'audit_logs']
        for tbl in user_tables_13:
            try:
                cur13.execute(f"DELETE FROM {tbl};")
            except Exception:
                pass
        conn13.commit()
        conn13.close()
    except Exception as e:
        print("Aviso na inicialização do PM13:", e)

    try:
        from core_pm11.migrations import run_migrations as run_pm11_migrations
        run_pm11_migrations()
        conn11 = sqlite3.connect(pm11_path)
        cur11 = conn11.cursor()

        user_tables_11 = ['inspection_projects', 'inspection_plans', 'inspection_items', 'control_characteristics', 'inspection_templates', 'pm11_history']
        for tbl in user_tables_11:
            try:
                cur11.execute(f"DELETE FROM {tbl};")
            except Exception:
                pass
        conn11.commit()
        conn11.close()
    except Exception as e:
        print("Aviso na inicialização do PM11:", e)

def build_clean_package():
    sys.stdout.reconfigure(encoding='utf-8')
    root_dir = os.path.dirname(os.path.abspath(__file__))
    ts = time.strftime('%Y%m%d_%H%M%S')
    zip_filename = f'SISTEMA_PM13_PM11_VIRGEM_{ts}.zip'
    zip_path = os.path.join(root_dir, zip_filename)

    temp_clean_dir = os.path.join(root_dir, "_temp_virgin_pkg")
    if os.path.exists(temp_clean_dir):
        shutil.rmtree(temp_clean_dir, ignore_errors=True)

    os.makedirs(temp_clean_dir, exist_ok=True)
    temp_data_dir = os.path.join(temp_clean_dir, "data")
    temp_backups_dir = os.path.join(temp_clean_dir, "backups")

    print("========================================================")
    print("   GERADOR DE SISTEMA VIRGEM / LIMPO PM13 / PM11")
    print("========================================================")
    print("\nInicializando bancos de dados virgens sem cadastros de usuário...")

    create_virgin_database(temp_data_dir)
    os.makedirs(temp_backups_dir, exist_ok=True)

    include_items = [
        'launcher.py',
        'INICIAR_SISTEMA.bat',
        'INICIAR_PM13.bat',
        'ATUALIZAR_SISTEMA.bat',
        'updater_gui.py',
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

    print(f"\nCriando pacote ZIP virgem: {zip_filename}...\n")

    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        # Copiar bancos virgens inicializados
        for r, dirs, files in os.walk(temp_data_dir):
            for file in files:
                full_path = os.path.join(r, file)
                rel_path = os.path.relpath(full_path, temp_clean_dir)
                zf.write(full_path, rel_path)
        print(" + Banco de dados virgem: data/ (pm13.db, pm11.db)")

        # Pasta backups limpa (inclui placeholder .gitkeep)
        gitkeep_path = os.path.join(temp_backups_dir, ".gitkeep")
        with open(gitkeep_path, 'w') as f:
            f.write('')
        zf.write(gitkeep_path, "backups/.gitkeep")
        print(" + Pasta de backups limpa: backups/")

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

    # Limpar pasta temporária
    shutil.rmtree(temp_clean_dir, ignore_errors=True)

    size_mb = os.path.getsize(zip_path) / (1024 * 1024)
    print("\n========================================================")
    print("🎉 SISTEMA VIRGEM EMPACOTADO COM SUCESSO!")
    print(f"Arquivo: {zip_filename} ({size_mb:.2f} MB)")
    print(f"Local: {zip_path}")
    print("========================================================\n")

if __name__ == "__main__":
    build_clean_package()
