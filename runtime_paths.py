"""Separate bundled resources from permanent, portable user data."""
import os
import sqlite3
import sys
from contextlib import closing
from pathlib import Path

BUILD = '2026.09.10-desktop-1'
RESOURCE_DIR = Path(__file__).resolve().parent
INSTALL_DIR = Path(sys.executable).resolve().parent if getattr(sys, 'frozen', False) else RESOURCE_DIR
DATA_DIR = Path(os.environ.get('MCM_USER_DATA_DIR') or INSTALL_DIR / ('dados_usuario' if getattr(sys, 'frozen', False) else 'data')).resolve()
BACKUP_DIR = Path(os.environ.get('MCM_BACKUP_DIR') or INSTALL_DIR / ('backups_usuario' if getattr(sys, 'frozen', False) else 'backups')).resolve()


def prepare_migrations():
    """Snapshot existing SQLite databases once per build before any migrations."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    marker = DATA_DIR / ('.prepared-' + BUILD)
    if marker.exists():
        return
    for name in ('pm13.db', 'pm11.db'):
        source = DATA_DIR / name
        target = BACKUP_DIR / (BUILD + '-' + name)
        if source.exists() and not target.exists():
            temp = target.with_suffix('.tmp')
            try:
                with closing(sqlite3.connect(source.as_uri() + '?mode=ro', uri=True)) as src:
                    with closing(sqlite3.connect(temp)) as dst:
                        src.backup(dst)
                temp.replace(target)
            finally:
                temp.unlink(missing_ok=True)
    marker.write_text(BUILD, encoding='utf-8')
