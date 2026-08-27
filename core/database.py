import sqlite3
import os
import unicodedata

# Base directory is the parent of core/ (i.e. PM13_LOCAL root)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_DIR = os.path.join(BASE_DIR, 'data')
DB_PATH = os.path.join(DB_DIR, 'pm13.db')

_migrations_run = False


def normalize_search_text(value):
    """Return a case/accent-insensitive representation for user searches."""
    if value is None:
        return ''
    normalized = unicodedata.normalize('NFD', str(value))
    return ''.join(
        char for char in normalized
        if unicodedata.category(char) != 'Mn'
    ).casefold()

def run_migrations(conn):
    global _migrations_run
    if _migrations_run:
        return
    try:
        cur = conn.cursor()
        for table in ['plans', 'maintenance_items', 'item_operations', 'operation_long_texts']:
            try:
                cols = [c[1] for c in cur.execute(f"PRAGMA table_info({table})").fetchall()]
                if cols:
                    if 'validation_status' not in cols:
                        cur.execute(f"ALTER TABLE {table} ADD COLUMN validation_status TEXT DEFAULT 'OK';")
                    if 'validation_issues_json' not in cols:
                        cur.execute(f"ALTER TABLE {table} ADD COLUMN validation_issues_json TEXT;")
            except Exception:
                pass
        conn.commit()
        _migrations_run = True
    except Exception:
        pass

def get_db_connection():
    """Returns a sqlite3 connection with foreign keys enabled and row factory set to sqlite3.Row."""
    # Ensure data directory exists
    os.makedirs(DB_DIR, exist_ok=True)
    
    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    # SQLite NOCASE only covers ASCII. This function lets text filters behave
    # consistently for Portuguese terms such as "manutencao" / "MANUTENÇÃO".
    try:
        conn.create_function('SEARCH_NORMALIZE', 1, normalize_search_text, deterministic=True)
    except TypeError:  # Compatibility with older Python/SQLite combinations.
        conn.create_function('SEARCH_NORMALIZE', 1, normalize_search_text)
    # Enable foreign keys
    conn.execute("PRAGMA foreign_keys = ON;")
    # Set row factory
    conn.row_factory = sqlite3.Row
    run_migrations(conn)
    return conn
