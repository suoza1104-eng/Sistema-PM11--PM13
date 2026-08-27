import os, sqlite3, unicodedata

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, 'data')
DB_PATH = os.path.join(DATA_DIR, 'pm11.db')


def normalize_search(value):
    if value is None:
        return ''
    s = unicodedata.normalize('NFD', str(value))
    return ''.join(c for c in s if unicodedata.category(c) != 'Mn').casefold()


def ensure_validation_columns(conn):
    for table in ('inspection_plans', 'inspection_items', 'control_characteristics'):
        try:
            cols = [dict(r)['name'] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()]
            if 'validation_status' not in cols:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN validation_status TEXT DEFAULT 'OK'")
            if 'validation_issues_json' not in cols:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN validation_issues_json TEXT")
            if table == 'inspection_items' and 'in_book' not in cols:
                conn.execute("ALTER TABLE inspection_items ADD COLUMN in_book INTEGER DEFAULT 0")
        except Exception:
            pass
    conn.commit()


def get_conn():
    os.makedirs(DATA_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys = ON')
    conn.execute('PRAGMA journal_mode = WAL')
    conn.execute('PRAGMA synchronous = NORMAL')
    try:
        conn.create_function('SEARCH_NORMALIZE', 1, normalize_search, deterministic=True)
    except TypeError:
        conn.create_function('SEARCH_NORMALIZE', 1, normalize_search)
    ensure_validation_columns(conn)
    return conn
