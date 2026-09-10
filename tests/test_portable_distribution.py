import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from build_clean_package import create_virgin_database
from package_desktop import application_files

ROOT = Path(__file__).resolve().parents[1]


class PortableDistributionTests(unittest.TestCase):
    def test_clean_databases_and_first_electrical_plan(self):
        with tempfile.TemporaryDirectory() as temp:
            data = Path(temp) / 'data'
            create_virgin_database(data)
            env = dict(os.environ, MCM_USER_DATA_DIR=str(data), MCM_BACKUP_DIR=str(Path(temp) / 'backups'))
            code = '''
from core import models
from core.database import get_db_connection
from core.migrations import run_migrations
p = models.create_project('Teste limpo', '', '')
cycles = models.list_cycle_catalog(p)
assert len(cycles) == 20, cycles
plan = models.create_plan(p, 'URRST3E01', 'PREVENTIVA ELETRICA', 1, 'PRD', 'PARADA', 100, 0)
assert models.get_plan(plan)['legacy_code'] == 'URRST3E01'
c = get_db_connection()
row = c.execute("SELECT actor_name,actor_account,actor_sid,actor_computer FROM audit_log WHERE entity_type='PLAN'").fetchone()
assert row and row[0]
# Existing customized catalog is preserved by migrations.
c.execute('DELETE FROM cycle_catalog WHERE project_id=? AND cycle<>1', (p,))
c.execute('UPDATE cycle_catalog SET opening_horizon=35 WHERE project_id=?', (p,))
c.commit()
run_migrations(c)
assert c.execute('SELECT count(*) FROM cycle_catalog WHERE project_id=?', (p,)).fetchone()[0] == 1
assert c.execute('SELECT opening_horizon FROM cycle_catalog WHERE project_id=?', (p,)).fetchone()[0] == 35
c.close()
'''
            subprocess.run([sys.executable, '-c', code], cwd=ROOT, env=env, check=True, capture_output=True)
            with self.assertRaises(ValueError):
                create_virgin_database(data)

    def test_pre_migration_backup_only_once(self):
        with tempfile.TemporaryDirectory() as temp:
            data = Path(temp) / 'data'
            data.mkdir()
            with sqlite3.connect(data / 'pm13.db') as c:
                c.execute('CREATE TABLE sentinel(value TEXT)')
                c.execute("INSERT INTO sentinel VALUES('original')")
            c.close()
            env = dict(os.environ, MCM_USER_DATA_DIR=str(data), MCM_BACKUP_DIR=str(Path(temp) / 'backup'))
            code = '''
from runtime_paths import *
prepare_migrations()
with sqlite3.connect(DATA_DIR / 'pm13.db') as c:
    c.execute("UPDATE sentinel SET value='changed'")
prepare_migrations()
with sqlite3.connect(BACKUP_DIR / (BUILD + '-pm13.db')) as c:
    assert c.execute('SELECT value FROM sentinel').fetchone()[0] == 'original'
assert len(list(BACKUP_DIR.glob('*.db'))) == 1
'''
            subprocess.run([sys.executable, '-c', code], cwd=ROOT, env=env, check=True, capture_output=True)

    def test_update_excludes_user_data(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for name in ['dados_usuario/pm13.db', 'backups_usuario/backup.zip', 'data/private.txt',
                         'backups/private.zip', 'pm11.db', '_internal/static/index.html', 'Sistema_PM11_PM13.exe']:
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text('test')
            self.assertEqual({name for _, name in application_files(root)},
                             {'_internal/static/index.html', 'Sistema_PM11_PM13.exe'})


if __name__ == '__main__':
    unittest.main()
