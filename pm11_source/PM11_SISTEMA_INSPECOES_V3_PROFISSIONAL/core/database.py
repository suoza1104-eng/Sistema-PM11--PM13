import os, sqlite3, unicodedata

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, 'data')
DB_PATH = os.path.join(DATA_DIR, 'pm11.db')


def normalize_search(value):
    if value is None:
        return ''
    s = unicodedata.normalize('NFD', str(value))
    return ''.join(c for c in s if unicodedata.category(c) != 'Mn').casefold()


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
    return conn
