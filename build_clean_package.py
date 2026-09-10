"""Build a clean browser distribution without opening the source databases."""
import os
from contextlib import closing
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import time
import zipfile

ROOT = Path(__file__).resolve().parent
SOURCE_FILES = ['app.py', 'runtime_paths.py', 'windows_identity.py', 'core', 'core_pm11',
                'catalogs', 'static', 'app_icon.ico', 'read_xlsb.ps1', 'README.md',
                'MANUAL_USUARIO.html', 'INICIAR_SISTEMA.bat', 'INICIAR_PM13.bat']


def create_virgin_database(target_dir):
    target = Path(target_dir).resolve()
    target.mkdir(parents=True, exist_ok=True)
    if any(target.glob('*.db')):
        raise ValueError('A pasta de destino precisa estar vazia; bancos existentes não serão substituídos.')
    env = dict(os.environ, MCM_USER_DATA_DIR=str(target), MCM_BACKUP_DIR=str(target.parent / 'backups'))
    subprocess.run([sys.executable, '-c',
        'from core.database import get_db_connection; from core.migrations import run_migrations; '
        'c=get_db_connection(); run_migrations(c); c.close(); '
        'from core_pm11.migrations import run_migrations; run_migrations(); '
        'from core_pm11.database import get_conn; c=get_conn(); '
        'c.execute("DELETE FROM projects"); c.commit(); c.close()'], cwd=ROOT, env=env, check=True)
    for name in ('pm13.db', 'pm11.db'):
        with closing(sqlite3.connect(target / name)) as conn:
            if conn.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise RuntimeError('Banco inválido: ' + name)
            if conn.execute('SELECT COUNT(*) FROM projects').fetchone()[0]:
                raise RuntimeError('Pacote contém projetos: ' + name)


def add_sources(zf):
    for name in SOURCE_FILES:
        path = ROOT / name
        paths = path.rglob('*') if path.is_dir() else [path]
        for source in paths:
            if source.is_file() and '__pycache__' not in source.parts and source.suffix not in ('.db', '.pyc', '.pyo'):
                zf.write(source, source.relative_to(ROOT).as_posix())


def build_clean_package():
    output = ROOT / ('SISTEMA_PM13_PM11_NAVEGADOR_LIMPO_' + time.strftime('%Y%m%d_%H%M%S') + '.zip')
    with tempfile.TemporaryDirectory(prefix='pm-clean-') as temp:
        data = Path(temp) / 'data'
        create_virgin_database(data)
        with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as zf:
            add_sources(zf)
            for name in ('pm13.db', 'pm11.db'):
                zf.write(data / name, 'data/' + name)
            zf.writestr('backups/.gitkeep', '')
    print('Pacote navegador limpo: ' + str(output))
    return output


if __name__ == '__main__':
    build_clean_package()
