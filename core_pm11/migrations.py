import os, json, datetime
from .database import get_conn
from .plans_util import parse_offset_from_text

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CATALOG_DIR = os.path.join(BASE_DIR, 'catalogs')

SCHEMA = r'''
CREATE TABLE IF NOT EXISTS projects (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  area TEXT DEFAULT '',
  system_name TEXT DEFAULT '',
  description TEXT DEFAULT '',
  status TEXT NOT NULL DEFAULT 'ACTIVE',
  default_center_code TEXT DEFAULT 'U',
  default_process_code TEXT DEFAULT 'R',
  default_type_code TEXT DEFAULT 'I',
  balance_anchor_date TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS cycle_catalog (
  code TEXT PRIMARY KEY,
  cycle_value INTEGER NOT NULL,
  unit TEXT NOT NULL,
  text_cycle TEXT NOT NULL,
  horizon REAL NOT NULL DEFAULT 100,
  sort_order INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS production_centers (code TEXT PRIMARY KEY, description TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS process_catalog (code TEXT PRIMARY KEY, description TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS plan_type_catalog (code TEXT PRIMARY KEY, description TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS production_lines (code TEXT PRIMARY KEY, description TEXT NOT NULL DEFAULT '');
CREATE TABLE IF NOT EXISTS subareas (code TEXT PRIMARY KEY, description TEXT NOT NULL DEFAULT '');

CREATE TABLE IF NOT EXISTS inspection_methods (
  code TEXT PRIMARY KEY,
  description TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS measurement_units (
  code TEXT PRIMARY KEY,
  description TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS inspection_plans (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  code TEXT NOT NULL,
  description TEXT NOT NULL,
  char_count INTEGER NOT NULL DEFAULT 0,
  center_code TEXT DEFAULT 'U',
  process_code TEXT DEFAULT 'R',
  type_code TEXT DEFAULT 'I',
  line_code TEXT DEFAULT '',
  subarea_code TEXT DEFAULT '',
  suffix TEXT DEFAULT '',
  cycle_code TEXT,
  cycle_value INTEGER,
  unit TEXT,
  text_cycle TEXT,
  horizon REAL,
  offset_days INTEGER DEFAULT NULL,
  status TEXT NOT NULL DEFAULT 'ACTIVE',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(project_id, code)
);

CREATE TABLE IF NOT EXISTS inspection_items (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  plan_id INTEGER REFERENCES inspection_plans(id) ON DELETE SET NULL,
  legacy_identifier INTEGER NOT NULL,
  equipment_code TEXT NOT NULL DEFAULT '',
  gpm TEXT NOT NULL DEFAULT '',
  work_center TEXT NOT NULL DEFAULT '',
  condition_code TEXT NOT NULL DEFAULT 'Q',
  priority INTEGER NOT NULL DEFAULT 0,
  route TEXT NOT NULL DEFAULT '',
  description TEXT NOT NULL DEFAULT '',
  char_count INTEGER NOT NULL DEFAULT 0,
  inspection_minutes REAL NOT NULL DEFAULT 0,
  criticality TEXT DEFAULT '',
  status TEXT NOT NULL DEFAULT 'ACTIVE',
  balance_offset_days INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(project_id, legacy_identifier)
);
CREATE INDEX IF NOT EXISTS idx_items_project_plan ON inspection_items(project_id, plan_id);
CREATE INDEX IF NOT EXISTS idx_items_project_route ON inspection_items(project_id, route);
CREATE INDEX IF NOT EXISTS idx_items_project_equipment ON inspection_items(project_id, equipment_code);

CREATE TABLE IF NOT EXISTS control_characteristics (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  item_id INTEGER NOT NULL REFERENCES inspection_items(id) ON DELETE CASCADE,
  sort_order INTEGER NOT NULL DEFAULT 0,
  characteristic_type TEXT NOT NULL DEFAULT 'QUALITAT',
  description TEXT NOT NULL DEFAULT '',
  method_code TEXT DEFAULT '',
  decimals INTEGER,
  unit_code TEXT DEFAULT '',
  reference_value REAL,
  lower_limit REAL,
  upper_limit REAL,
  status TEXT NOT NULL DEFAULT 'ACTIVE',
  source_template_id INTEGER,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_chars_item ON control_characteristics(item_id, sort_order);

CREATE TABLE IF NOT EXISTS characteristic_templates (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id INTEGER REFERENCES projects(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  category TEXT DEFAULT '',
  description TEXT DEFAULT '',
  scope TEXT NOT NULL DEFAULT 'PROJECT',
  status TEXT NOT NULL DEFAULT 'ACTIVE',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS characteristic_template_rows (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  template_id INTEGER NOT NULL REFERENCES characteristic_templates(id) ON DELETE CASCADE,
  sort_order INTEGER NOT NULL DEFAULT 0,
  characteristic_type TEXT NOT NULL DEFAULT 'QUALITAT',
  description TEXT NOT NULL DEFAULT '',
  method_code TEXT DEFAULT '',
  decimals INTEGER,
  unit_code TEXT DEFAULT '',
  reference_value REAL,
  lower_limit REAL,
  upper_limit REAL,
  status TEXT NOT NULL DEFAULT 'ACTIVE'
);

CREATE TABLE IF NOT EXISTS equipment_templates (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id INTEGER REFERENCES projects(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  category TEXT DEFAULT '',
  description TEXT DEFAULT '',
  scope TEXT NOT NULL DEFAULT 'PROJECT',
  status TEXT NOT NULL DEFAULT 'ACTIVE',
  total_minutes REAL NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS equipment_template_items (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  template_id INTEGER NOT NULL REFERENCES equipment_templates(id) ON DELETE CASCADE,
  sort_order INTEGER NOT NULL DEFAULT 0,
  plan_code TEXT DEFAULT '',
  gpm TEXT DEFAULT '',
  work_center TEXT DEFAULT '',
  condition_code TEXT DEFAULT 'Q',
  priority INTEGER DEFAULT 0,
  route_relative INTEGER DEFAULT 0,
  original_route TEXT DEFAULT '',
  description TEXT DEFAULT '',
  inspection_minutes REAL DEFAULT 0,
  criticality TEXT DEFAULT '',
  status TEXT DEFAULT 'ACTIVE'
);
CREATE TABLE IF NOT EXISTS equipment_template_characteristics (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  template_item_id INTEGER NOT NULL REFERENCES equipment_template_items(id) ON DELETE CASCADE,
  sort_order INTEGER NOT NULL DEFAULT 0,
  characteristic_type TEXT NOT NULL DEFAULT 'QUALITAT',
  description TEXT NOT NULL DEFAULT '',
  method_code TEXT DEFAULT '',
  decimals INTEGER,
  unit_code TEXT DEFAULT '',
  reference_value REAL,
  lower_limit REAL,
  upper_limit REAL,
  status TEXT NOT NULL DEFAULT 'ACTIVE'
);

CREATE TABLE IF NOT EXISTS project_history (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  action_label TEXT NOT NULL,
  before_json TEXT NOT NULL,
  after_json TEXT NOT NULL,
  undone INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS app_settings (
  key TEXT PRIMARY KEY,
  value TEXT
);
'''


def _load_json(name):
    with open(os.path.join(CATALOG_DIR, name), 'r', encoding='utf-8') as f:
        return json.load(f)




V3_SCHEMA = r"""
CREATE TABLE IF NOT EXISTS item_templates (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id INTEGER REFERENCES projects(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  category TEXT DEFAULT '',
  description TEXT DEFAULT '',
  scope TEXT NOT NULL DEFAULT 'PROJECT',
  status TEXT NOT NULL DEFAULT 'ACTIVE',
  row_color TEXT DEFAULT '',
  condition_code TEXT DEFAULT 'Q',
  priority INTEGER DEFAULT 0,
  route TEXT DEFAULT '',
  item_description TEXT DEFAULT '',
  inspection_minutes REAL DEFAULT 0,
  criticality TEXT DEFAULT '',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS item_template_characteristics (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  template_id INTEGER NOT NULL REFERENCES item_templates(id) ON DELETE CASCADE,
  sort_order INTEGER NOT NULL DEFAULT 0,
  characteristic_type TEXT NOT NULL DEFAULT 'QUALITAT',
  description TEXT NOT NULL DEFAULT '',
  method_code TEXT DEFAULT '',
  decimals INTEGER,
  unit_code TEXT DEFAULT '',
  reference_value REAL,
  lower_limit REAL,
  upper_limit REAL,
  status TEXT NOT NULL DEFAULT 'ACTIVE'
);
"""

def _ensure_column(conn, table, column, ddl):
    cols={r[1] for r in conn.execute(f'PRAGMA table_info({table})').fetchall()}
    if column not in cols:
        conn.execute(f'ALTER TABLE {table} ADD COLUMN {column} {ddl}')


def run_migrations():
    conn = get_conn()
    try:
        conn.executescript(SCHEMA)
        conn.executescript(V3_SCHEMA)
        _ensure_column(conn,'projects','locked','INTEGER NOT NULL DEFAULT 0')
        _ensure_column(conn,'projects','daily_inspection_target_minutes','REAL NOT NULL DEFAULT 240')
        _ensure_column(conn,'inspection_plans','row_color',"TEXT DEFAULT ''")
        _ensure_column(conn,'inspection_plans','offset_days','INTEGER DEFAULT NULL')
        _ensure_column(conn,'projects','balance_anchor_date','TEXT')
        # Backfill legacy plans only when the offset is still empty. Explicitly
        # entered values are preserved. Codes such as 1S2 may be in either the
        # plan description or its SAP code.
        offset_v2_done = conn.execute(
            "SELECT value FROM app_settings WHERE key='pm11_sap_weekday_offset_v2'"
        ).fetchone()
        legacy_plans = conn.execute(
            'SELECT id, description, code, offset_days FROM inspection_plans' +
            ('' if not offset_v2_done else ' WHERE offset_days IS NULL')
        ).fetchall()
        for plan in legacy_plans:
            detected_offset = parse_offset_from_text(plan['description'], plan['code'])
            if detected_offset is not None and detected_offset != plan['offset_days']:
                conn.execute(
                    'UPDATE inspection_plans SET offset_days=?, updated_at=CURRENT_TIMESTAMP WHERE id=?',
                    (detected_offset, plan['id'])
                )
        if not offset_v2_done:
            conn.execute(
                "INSERT OR REPLACE INTO app_settings(key,value) VALUES('pm11_sap_weekday_offset_v2','1')"
            )
        _ensure_column(conn,'inspection_items','row_color',"TEXT DEFAULT ''")
        _ensure_column(conn,'inspection_items','locked','INTEGER NOT NULL DEFAULT 0')
        _ensure_column(conn,'control_characteristics','row_color',"TEXT DEFAULT ''")
        _ensure_column(conn,'characteristic_templates','row_color',"TEXT DEFAULT ''")
        _ensure_column(conn,'equipment_templates','row_color',"TEXT DEFAULT ''")
        if conn.execute('SELECT COUNT(*) FROM cycle_catalog').fetchone()[0] == 0:
            for i, c in enumerate(_load_json('cycles.json')):
                conn.execute('INSERT OR REPLACE INTO cycle_catalog(code,cycle_value,unit,text_cycle,horizon,sort_order) VALUES(?,?,?,?,?,?)',
                             (c['code'], c['cycle'], c['unit'], c['text'], c['horizon'], i))
        code_cat = _load_json('code_catalog.json')
        for row in code_cat['centers']:
            conn.execute('INSERT OR IGNORE INTO production_centers(code,description) VALUES(?,?)',(row['code'],row['description']))
        for row in code_cat['processes']:
            conn.execute('INSERT OR IGNORE INTO process_catalog(code,description) VALUES(?,?)',(row['code'],row['description']))
        for row in code_cat['types']:
            conn.execute('INSERT OR IGNORE INTO plan_type_catalog(code,description) VALUES(?,?)',(row['code'],row['description']))
        for row in code_cat['lines']:
            conn.execute('INSERT OR IGNORE INTO production_lines(code,description) VALUES(?,?)',(row['code'],row['description']))
        for row in code_cat['subareas']:
            conn.execute('INSERT OR IGNORE INTO subareas(code,description) VALUES(?,?)',(row['code'],row['description']))
        if conn.execute('SELECT COUNT(*) FROM inspection_methods').fetchone()[0] == 0:
            conn.executemany('INSERT OR IGNORE INTO inspection_methods(code,description) VALUES(?,?)',
                             [(r['code'],r['description']) for r in _load_json('methods.json')])
        if conn.execute('SELECT COUNT(*) FROM measurement_units').fetchone()[0] == 0:
            conn.executemany('INSERT OR IGNORE INTO measurement_units(code,description) VALUES(?,?)',
                             [(r['code'],r['description']) for r in _load_json('units.json')])
        if conn.execute('SELECT COUNT(*) FROM projects').fetchone()[0] == 0:
            conn.execute("INSERT INTO projects(name,area,system_name,description) VALUES('PROJETO PM11 - EXEMPLO','','','Projeto inicial PM11')")
        conn.commit()
    finally:
        conn.close()
