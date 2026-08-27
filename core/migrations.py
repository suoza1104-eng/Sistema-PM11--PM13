import json
import re
import sqlite3
import hashlib


def _remove_obsolete_numeric_identifier_warnings(conn):
    """Remove the retired numeric-only rule from already imported items."""
    table = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='maintenance_items'"
    ).fetchone()
    if not table:
        return
    columns = {row[1] for row in conn.execute('PRAGMA table_info("maintenance_items")').fetchall()}
    if not {'validation_status', 'validation_issues_json'}.issubset(columns):
        return

    rows = conn.execute("""SELECT id,validation_issues_json FROM maintenance_items
                           WHERE validation_issues_json IS NOT NULL
                             AND validation_issues_json LIKE '%estritamente num%'""").fetchall()
    for row in rows:
        try:
            issues = json.loads(row[1] or '[]')
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
        if not isinstance(issues, list):
            continue
        remaining = [
            issue for issue in issues
            if not (
                isinstance(issue, dict)
                and str(issue.get('field') or issue.get('code') or '').strip().casefold() == 'identificador'
                and 'estritamente num' in str(issue.get('message') or '').casefold()
            )
        ]
        if len(remaining) == len(issues):
            continue
        severities = {str(issue.get('severity') or '').upper()
                      for issue in remaining if isinstance(issue, dict)}
        status = 'ERROR' if 'ERROR' in severities else ('WARNING' if 'WARNING' in severities else 'OK')
        conn.execute("""UPDATE maintenance_items
                        SET validation_status=?,validation_issues_json=?,updated_at=CURRENT_TIMESTAMP
                        WHERE id=?""",
                     (status, json.dumps(remaining, ensure_ascii=False) if remaining else None, row[0]))


def _index_columns(conn, index_name):
    escaped = str(index_name).replace('"', '""')
    return [row[2] for row in conn.execute(f'PRAGMA index_info("{escaped}")').fetchall()]


def _migrate_plans_to_active_code_uniqueness(conn):
    """Replace the legacy table-wide plan-code UNIQUE with an active-only one.

    SQLite cannot drop a table UNIQUE constraint in place.  Rebuilding is done
    with foreign keys disabled *before* the transaction; otherwise dropping
    ``plans`` would apply ``ON DELETE SET NULL`` to every linked item.
    """

    table_row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='plans'"
    ).fetchone()
    if not table_row:
        return

    index_rows = conn.execute('PRAGMA index_list("plans")').fetchall()
    legacy_unique_names = set()
    for row in index_rows:
        # PRAGMA index_list: seq, name, unique, origin, partial.
        if bool(row[2]) and _index_columns(conn, row[1]) == ['project_id', 'legacy_code']:
            if len(row) < 5 or not bool(row[4]):
                legacy_unique_names.add(row[1])
    if not legacy_unique_names:
        return

    if conn.in_transaction:
        conn.commit()
    foreign_keys_were_enabled = bool(conn.execute('PRAGMA foreign_keys').fetchone()[0])
    conn.execute('PRAGMA foreign_keys = OFF')
    if conn.execute('PRAGMA foreign_keys').fetchone()[0]:
        raise RuntimeError('NÃ£o foi possÃ­vel desativar chaves estrangeiras para migrar planos.')

    temp_table = 'plans__active_code_migration'
    try:
        if conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (temp_table,)
        ).fetchone():
            raise RuntimeError('MigraÃ§Ã£o anterior de planos ficou incompleta; intervenÃ§Ã£o necessÃ¡ria.')

        original_sql = table_row[0]
        create_sql = re.sub(
            r'^\s*CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?(?:"plans"|plans)',
            f'CREATE TABLE "{temp_table}"',
            original_sql,
            count=1,
            flags=re.IGNORECASE,
        )
        create_sql = re.sub(
            r',\s*(?:CONSTRAINT\s+\w+\s+)?UNIQUE\s*\(\s*project_id\s*,\s*legacy_code\s*\)\s*(?=\))',
            '',
            create_sql,
            count=1,
            flags=re.IGNORECASE,
        )
        if create_sql == original_sql or re.search(
            r'UNIQUE\s*\(\s*project_id\s*,\s*legacy_code\s*\)', create_sql, re.IGNORECASE
        ):
            raise RuntimeError('NÃ£o foi possÃ­vel preparar a migraÃ§Ã£o de unicidade dos planos.')

        columns = [row[1] for row in conn.execute('PRAGMA table_info("plans")').fetchall()]
        quoted_columns = ', '.join('"' + col.replace('"', '""') + '"' for col in columns)
        plan_rows_before = [
            tuple(row) for row in conn.execute(
                f'SELECT {quoted_columns} FROM "plans" ORDER BY id'
            ).fetchall()
        ]
        item_refs_before = []
        if conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='maintenance_items'"
        ).fetchone():
            item_refs_before = [
                tuple(row) for row in conn.execute(
                    'SELECT id, plan_id FROM maintenance_items ORDER BY id'
                ).fetchall()
            ]
        fk_before = sorted(tuple(row) for row in conn.execute('PRAGMA foreign_key_check').fetchall())
        sequence_row = conn.execute(
            "SELECT seq FROM sqlite_sequence WHERE name='plans'"
        ).fetchone()
        old_sequence = int(sequence_row[0]) if sequence_row else 0

        preserved_indexes = []
        for row in conn.execute(
            "SELECT name, sql FROM sqlite_master "
            "WHERE type='index' AND tbl_name='plans' AND sql IS NOT NULL"
        ).fetchall():
            if row[0] not in legacy_unique_names and row[0] != 'idx_plans_active_code_unique':
                preserved_indexes.append(row[1])

        conn.execute('BEGIN IMMEDIATE')
        conn.execute(create_sql)
        conn.execute(
            f'INSERT INTO "{temp_table}" ({quoted_columns}) '
            f'SELECT {quoted_columns} FROM "plans"'
        )
        conn.execute('DROP TABLE "plans"')
        conn.execute(f'ALTER TABLE "{temp_table}" RENAME TO "plans"')
        for index_sql in preserved_indexes:
            conn.execute(index_sql)
        conn.execute(
            'CREATE UNIQUE INDEX idx_plans_active_code_unique '
            'ON plans(project_id, legacy_code) WHERE deleted_at IS NULL'
        )

        max_id = int(conn.execute('SELECT COALESCE(MAX(id), 0) FROM plans').fetchone()[0])
        target_sequence = max(old_sequence, max_id)
        conn.execute(
            "DELETE FROM sqlite_sequence WHERE name IN ('plans', ?)", (temp_table,)
        )
        conn.execute(
            "INSERT INTO sqlite_sequence(name, seq) VALUES ('plans', ?)", (target_sequence,)
        )

        plan_rows_after = [
            tuple(row) for row in conn.execute(
                f'SELECT {quoted_columns} FROM "plans" ORDER BY id'
            ).fetchall()
        ]
        item_refs_after = [
            tuple(row) for row in conn.execute(
                'SELECT id, plan_id FROM maintenance_items ORDER BY id'
            ).fetchall()
        ] if item_refs_before else []
        fk_after = sorted(tuple(row) for row in conn.execute('PRAGMA foreign_key_check').fetchall())
        if plan_rows_after != plan_rows_before or item_refs_after != item_refs_before or fk_after != fk_before:
            raise RuntimeError('A migraÃ§Ã£o de planos nÃ£o preservou integralmente os dados e vÃ­nculos.')
        conn.commit()
    except Exception:
        if conn.in_transaction:
            conn.rollback()
        raise
    finally:
        if foreign_keys_were_enabled:
            conn.execute('PRAGMA foreign_keys = ON')


def _migrate_auto_balance_rules(conn):
    """Upgrade legacy rule constraints while preserving existing rule ids."""
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='auto_balance_rules'"
    ).fetchone()
    if not row:
        return
    columns = {r[1] for r in conn.execute('PRAGMA table_info(auto_balance_rules)').fetchall()}
    sql = row[0] or ''
    needs_rebuild = "'separate'" not in sql.lower()
    if needs_rebuild:
        if conn.in_transaction:
            conn.commit()
        conn.execute('PRAGMA foreign_keys = OFF')
        conn.execute('BEGIN IMMEDIATE')
        try:
            conn.execute("""
                CREATE TABLE auto_balance_rules__v2 (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                    name TEXT NOT NULL,
                    rule_type TEXT NOT NULL CHECK(rule_type IN ('together','sequence','separate')),
                    item_ids_json TEXT NOT NULL,
                    enforcement TEXT NOT NULL DEFAULT 'mandatory'
                        CHECK(enforcement IN ('mandatory','preferred')),
                    config_json TEXT,
                    active INTEGER NOT NULL DEFAULT 1,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            enforcement_expr = "enforcement" if 'enforcement' in columns else "'mandatory'"
            config_expr = "config_json" if 'config_json' in columns else 'NULL'
            conn.execute(f"""INSERT INTO auto_balance_rules__v2
                (id,project_id,name,rule_type,item_ids_json,enforcement,config_json,active,created_at,updated_at)
                SELECT id,project_id,name,rule_type,item_ids_json,{enforcement_expr},{config_expr},active,
                       created_at,updated_at FROM auto_balance_rules""")
            conn.execute('DROP TABLE auto_balance_rules')
            conn.execute('ALTER TABLE auto_balance_rules__v2 RENAME TO auto_balance_rules')
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.execute('PRAGMA foreign_keys = ON')
    else:
        for ddl in (
            "ALTER TABLE auto_balance_rules ADD COLUMN enforcement TEXT NOT NULL DEFAULT 'mandatory'",
            "ALTER TABLE auto_balance_rules ADD COLUMN config_json TEXT",
        ):
            try:
                conn.execute(ddl)
            except sqlite3.OperationalError:
                pass



def _migrate_standard_item_operations_nullable_workload(conn):
    """Allow standard operation workload fields to stay blank just like source operations.

    Older databases created ``standard_item_operations.headcount`` and ``hours``
    as NOT NULL. Imported SAP/header operations legitimately keep those fields
    blank, so saving a complete item as a standard used to fail. Rebuild both
    standard operation tables preserving IDs and long-text relationships.
    """
    table = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='standard_item_operations'"
    ).fetchone()
    if not table:
        return

    info = {row[1]: row for row in conn.execute('PRAGMA table_info("standard_item_operations")').fetchall()}
    headcount_notnull = bool(info.get('headcount') and info['headcount'][3])
    hours_notnull = bool(info.get('hours') and info['hours'][3])
    if not (headcount_notnull or hours_notnull):
        return

    if conn.in_transaction:
        conn.commit()
    fk_enabled = bool(conn.execute('PRAGMA foreign_keys').fetchone()[0])
    conn.execute('PRAGMA foreign_keys = OFF')
    if conn.execute('PRAGMA foreign_keys').fetchone()[0]:
        raise RuntimeError('Não foi possível desativar chaves estrangeiras para migrar operações padrão.')

    try:
        op_rows = [tuple(row) for row in conn.execute(
            'SELECT * FROM standard_item_operations ORDER BY id'
        ).fetchall()]
        lt_exists = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='standard_operation_long_texts'"
        ).fetchone()
        lt_rows = ([tuple(row) for row in conn.execute(
            'SELECT * FROM standard_operation_long_texts ORDER BY id'
        ).fetchall()] if lt_exists else [])
        fk_before = sorted(tuple(row) for row in conn.execute('PRAGMA foreign_key_check').fetchall())
        op_seq_row = conn.execute(
            "SELECT seq FROM sqlite_sequence WHERE name='standard_item_operations'"
        ).fetchone()
        lt_seq_row = conn.execute(
            "SELECT seq FROM sqlite_sequence WHERE name='standard_operation_long_texts'"
        ).fetchone()
        old_op_seq = int(op_seq_row[0]) if op_seq_row else 0
        old_lt_seq = int(lt_seq_row[0]) if lt_seq_row else 0

        conn.execute('BEGIN IMMEDIATE')
        if lt_exists:
            conn.execute('DROP TABLE standard_operation_long_texts')
        conn.execute('DROP TABLE standard_item_operations')

        conn.execute("""
            CREATE TABLE standard_item_operations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                standard_item_id INTEGER NOT NULL REFERENCES standard_items(id) ON DELETE CASCADE,
                operation_code TEXT NOT NULL,
                suboperation_code TEXT NOT NULL DEFAULT '',
                work_center TEXT,
                short_text TEXT NOT NULL,
                unit TEXT NOT NULL DEFAULT 'H',
                headcount INTEGER,
                hours REAL
            );
        """)
        conn.execute("""
            CREATE TABLE standard_operation_long_texts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                standard_operation_id INTEGER NOT NULL REFERENCES standard_item_operations(id) ON DELETE CASCADE,
                group_code TEXT,
                group_counter TEXT,
                text TEXT NOT NULL
            );
        """)

        if op_rows:
            conn.executemany("""
                INSERT INTO standard_item_operations
                    (id,standard_item_id,operation_code,suboperation_code,work_center,short_text,unit,headcount,hours)
                VALUES (?,?,?,?,?,?,?,?,?)
            """, op_rows)
        if lt_rows:
            conn.executemany("""
                INSERT INTO standard_operation_long_texts
                    (id,standard_operation_id,group_code,group_counter,text)
                VALUES (?,?,?,?,?)
            """, lt_rows)

        max_op_id = max([row[0] for row in op_rows], default=0)
        max_lt_id = max([row[0] for row in lt_rows], default=0)
        conn.execute("DELETE FROM sqlite_sequence WHERE name IN ('standard_item_operations','standard_operation_long_texts')")
        conn.execute(
            "INSERT INTO sqlite_sequence(name,seq) VALUES ('standard_item_operations',?)",
            (max(old_op_seq, max_op_id),)
        )
        conn.execute(
            "INSERT INTO sqlite_sequence(name,seq) VALUES ('standard_operation_long_texts',?)",
            (max(old_lt_seq, max_lt_id),)
        )

        op_after = [tuple(row) for row in conn.execute(
            'SELECT * FROM standard_item_operations ORDER BY id'
        ).fetchall()]
        lt_after = [tuple(row) for row in conn.execute(
            'SELECT * FROM standard_operation_long_texts ORDER BY id'
        ).fetchall()]
        fk_after = sorted(tuple(row) for row in conn.execute('PRAGMA foreign_key_check').fetchall())
        if op_after != op_rows or lt_after != lt_rows or fk_after != fk_before:
            raise RuntimeError('A migração de operações padrão não preservou integralmente dados e vínculos.')

        conn.commit()
    except Exception:
        if conn.in_transaction:
            conn.rollback()
        raise
    finally:
        if fk_enabled:
            conn.execute('PRAGMA foreign_keys = ON')


def run_migrations(conn):
    """Creates the SQLite schema tables and indices if they do not exist."""
    cursor = conn.cursor()
    
    # 1. Projects
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS projects (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE,
        description TEXT,
        area TEXT,
        current_counter INTEGER NOT NULL DEFAULT 0,
        default_horizon INTEGER NOT NULL DEFAULT 12,
        utilization_factor REAL NOT NULL DEFAULT 1.0,
        status TEXT NOT NULL DEFAULT 'ACTIVE',
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        deleted_at DATETIME
    );
    """)

    # 2. Shifts
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS shifts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
        name TEXT NOT NULL,
        sequence INTEGER NOT NULL,
        duration_hours REAL NOT NULL,
        active INTEGER NOT NULL DEFAULT 1
    );
    """)

    # 3. Cycle Catalog
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS cycle_catalog (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
        cycle INTEGER NOT NULL,
        unit TEXT NOT NULL,
        cycle_text TEXT NOT NULL,
        opening_horizon REAL NOT NULL,
        active INTEGER NOT NULL DEFAULT 1,
        UNIQUE(project_id, cycle, unit)
    );
    """)

    # 4. Plans
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS plans (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
        legacy_code TEXT NOT NULL,
        description TEXT NOT NULL,
        character_count INTEGER NOT NULL,
        cycle INTEGER NOT NULL,
        unit TEXT NOT NULL,
        cycle_text TEXT NOT NULL,
        opening_horizon REAL NOT NULL,
        reference_counter INTEGER,
        phase INTEGER NOT NULL DEFAULT 0,
        status TEXT NOT NULL DEFAULT 'ACTIVE',
        notes TEXT,
        validation_status TEXT NOT NULL DEFAULT 'OK',
        validation_issues_json TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        deleted_at DATETIME
    );
    """)

    _migrate_plans_to_active_code_uniqueness(conn)

    # 5. Maintenance Items
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS maintenance_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
        plan_id INTEGER REFERENCES plans(id) ON DELETE SET NULL,
        team_id INTEGER REFERENCES work_teams(id) ON DELETE SET NULL,
        legacy_identifier TEXT NOT NULL,
        object_type TEXT NOT NULL DEFAULT 'EQUIPAMENTO',
        object_code TEXT NOT NULL,
        gpm TEXT NOT NULL,
        work_center TEXT NOT NULL,
        condition_code TEXT NOT NULL,
        priority INTEGER NOT NULL,
        legacy_start INTEGER,
        description TEXT NOT NULL,
        character_count INTEGER NOT NULL,
        duration_hours REAL NOT NULL,
        headcount INTEGER,
        hh REAL NOT NULL,
        order_type TEXT NOT NULL DEFAULT 'PM13',
        status TEXT NOT NULL DEFAULT 'ACTIVE',
        notes TEXT,
        validation_status TEXT NOT NULL DEFAULT 'OK',
        validation_issues_json TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        deleted_at DATETIME,
        UNIQUE(project_id, legacy_identifier)
    );
    """)

    # Dynamic Column Migration for existing databases
    try:
        cursor.execute("ALTER TABLE maintenance_items ADD COLUMN team_id INTEGER REFERENCES work_teams(id) ON DELETE SET NULL;")
    except sqlite3.OperationalError:
        pass
    for column_sql in (
        "ALTER TABLE maintenance_items ADD COLUMN validation_status TEXT NOT NULL DEFAULT 'OK'",
        "ALTER TABLE maintenance_items ADD COLUMN validation_issues_json TEXT",
        "ALTER TABLE maintenance_items ADD COLUMN mec_headcount INTEGER DEFAULT 0",
        "ALTER TABLE maintenance_items ADD COLUMN mec_hours REAL DEFAULT 0.0",
        "ALTER TABLE maintenance_items ADD COLUMN ele_headcount INTEGER DEFAULT 0",
        "ALTER TABLE maintenance_items ADD COLUMN ele_hours REAL DEFAULT 0.0",
        "ALTER TABLE maintenance_items ADD COLUMN sol_headcount INTEGER DEFAULT 0",
        "ALTER TABLE maintenance_items ADD COLUMN sol_hours REAL DEFAULT 0.0",
        "ALTER TABLE maintenance_items ADD COLUMN display_order INTEGER",
        "ALTER TABLE maintenance_items ADD COLUMN row_color TEXT",
    ):
        try:
            cursor.execute(column_sql)
        except sqlite3.OperationalError:
            pass

    cursor.execute("UPDATE maintenance_items SET display_order=id WHERE display_order IS NULL")

    # Backfill initial trades for items where all trade headcounts are 0 or NULL
    cursor.execute("""
        UPDATE maintenance_items
        SET 
            ele_headcount = CASE 
                WHEN UPPER(COALESCE(work_center, '')) LIKE '%E%' OR UPPER(COALESCE(work_center, '')) LIKE '%ELE%' 
                THEN COALESCE(headcount, 1) ELSE 0 END,
            ele_hours = CASE 
                WHEN UPPER(COALESCE(work_center, '')) LIKE '%E%' OR UPPER(COALESCE(work_center, '')) LIKE '%ELE%' 
                THEN COALESCE(duration_hours, 0.0) ELSE 0.0 END,
            sol_headcount = CASE 
                WHEN UPPER(COALESCE(work_center, '')) LIKE '%S%' OR UPPER(COALESCE(work_center, '')) LIKE '%SOL%' OR UPPER(COALESCE(work_center, '')) LIKE '%CAL%' 
                THEN COALESCE(headcount, 1) ELSE 0 END,
            sol_hours = CASE 
                WHEN UPPER(COALESCE(work_center, '')) LIKE '%S%' OR UPPER(COALESCE(work_center, '')) LIKE '%SOL%' OR UPPER(COALESCE(work_center, '')) LIKE '%CAL%' 
                THEN COALESCE(duration_hours, 0.0) ELSE 0.0 END,
            mec_headcount = CASE 
                WHEN NOT (UPPER(COALESCE(work_center, '')) LIKE '%E%' OR UPPER(COALESCE(work_center, '')) LIKE '%ELE%' OR UPPER(COALESCE(work_center, '')) LIKE '%S%' OR UPPER(COALESCE(work_center, '')) LIKE '%SOL%' OR UPPER(COALESCE(work_center, '')) LIKE '%CAL%')
                THEN COALESCE(headcount, 1) ELSE 0 END,
            mec_hours = CASE 
                WHEN NOT (UPPER(COALESCE(work_center, '')) LIKE '%E%' OR UPPER(COALESCE(work_center, '')) LIKE '%ELE%' OR UPPER(COALESCE(work_center, '')) LIKE '%S%' OR UPPER(COALESCE(work_center, '')) LIKE '%SOL%' OR UPPER(COALESCE(work_center, '')) LIKE '%CAL%')
                THEN COALESCE(duration_hours, 0.0) ELSE 0.0 END
        WHERE (COALESCE(mec_headcount, 0) = 0 AND COALESCE(ele_headcount, 0) = 0 AND COALESCE(sol_headcount, 0) = 0)
          AND (COALESCE(headcount, 0) > 0 OR COALESCE(duration_hours, 0.0) > 0);
    """)

    # 5B. Priorímetro SAP - uma linha de critérios por item de manutenção.
    # A linha é criada sob demanda; a listagem usa LEFT JOIN para que todo item
    # do projeto apareça mesmo antes do primeiro preenchimento.
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS item_priorimeter (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
        item_id INTEGER NOT NULL UNIQUE REFERENCES maintenance_items(id) ON DELETE CASCADE,
        failure_probability INTEGER CHECK(failure_probability IS NULL OR failure_probability IN (1,2,3,4,5)),
        maintenance_impact INTEGER CHECK(maintenance_impact IS NULL OR maintenance_impact IN (1,2,3,4,6,8)),
        events_over_one TEXT CHECK(events_over_one IS NULL OR events_over_one IN ('S','N')),
        asymmetric_lifting TEXT CHECK(asymmetric_lifting IS NULL OR asymmetric_lifting IN ('S','N')),
        multi_lifting TEXT CHECK(multi_lifting IS NULL OR multi_lifting IN ('S','N')),
        thermal_overload TEXT CHECK(thermal_overload IS NULL OR thermal_overload IN ('S','N')),
        tanks_gases TEXT CHECK(tanks_gases IS NULL OR tanks_gases IN ('S','N')),
        leak_exposure TEXT CHECK(leak_exposure IS NULL OR leak_exposure IN ('S','N')),
        pressurized_systems TEXT CHECK(pressurized_systems IS NULL OR pressurized_systems IN ('S','N')),
        energized_electrical TEXT CHECK(energized_electrical IS NULL OR energized_electrical IN ('S','N')),
        confined_spaces TEXT CHECK(confined_spaces IS NULL OR confined_spaces IN ('S','N')),
        height_over_2m TEXT CHECK(height_over_2m IS NULL OR height_over_2m IN ('S','N')),
        hot_metal TEXT CHECK(hot_metal IS NULL OR hot_metal IN ('S','N')),
        difficult_technical TEXT CHECK(difficult_technical IS NULL OR difficult_technical IN ('S','N')),
        hydraulic_jack TEXT CHECK(hydraulic_jack IS NULL OR hydraulic_jack IN ('S','N')),
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_priorimeter_project ON item_priorimeter(project_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_priorimeter_item ON item_priorimeter(item_id);")

    # 6. Imports
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS imports (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
        filename TEXT NOT NULL,
        file_hash TEXT NOT NULL,
        status TEXT NOT NULL,
        summary_json TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # 7. Import Errors
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS import_errors (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        import_id INTEGER NOT NULL REFERENCES imports(id) ON DELETE CASCADE,
        sheet_name TEXT NOT NULL,
        row_number INTEGER,
        field_name TEXT,
        severity TEXT NOT NULL,
        message TEXT NOT NULL,
        original_value TEXT
    );
    """)

    # 8. Audit Log
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS audit_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id INTEGER REFERENCES projects(id) ON DELETE CASCADE,
        entity_type TEXT NOT NULL,
        entity_id INTEGER NOT NULL,
        action TEXT NOT NULL,
        previous_data_json TEXT,
        new_data_json TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # 9. Project Settings
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS project_settings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id INTEGER UNIQUE NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
        code_pattern TEXT,
        balance_strategy TEXT NOT NULL DEFAULT 'horizontal',
        geography_mode TEXT NOT NULL DEFAULT 'preferred',
        vertical_tolerance REAL NOT NULL DEFAULT 10,
        similarity_enabled INTEGER NOT NULL DEFAULT 1,
        balance_max_passes INTEGER NOT NULL DEFAULT 50,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );
    """)
    for ddl in (
        "ALTER TABLE project_settings ADD COLUMN balance_strategy TEXT NOT NULL DEFAULT 'horizontal'",
        "ALTER TABLE project_settings ADD COLUMN geography_mode TEXT NOT NULL DEFAULT 'preferred'",
        "ALTER TABLE project_settings ADD COLUMN vertical_tolerance REAL NOT NULL DEFAULT 10",
        "ALTER TABLE project_settings ADD COLUMN similarity_enabled INTEGER NOT NULL DEFAULT 1",
        "ALTER TABLE project_settings ADD COLUMN balance_max_passes INTEGER NOT NULL DEFAULT 50",
    ):
        try:
            cursor.execute(ddl)
        except sqlite3.OperationalError:
            pass

    # 10. Work Teams (Equipes de Trabalho)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS work_teams (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
        name TEXT NOT NULL,
        work_center TEXT,
        num_shifts INTEGER NOT NULL DEFAULT 1,
        shift_hours REAL NOT NULL DEFAULT 9.0,
        headcount_per_shift INTEGER NOT NULL DEFAULT 1,
        tool_time_percent REAL NOT NULL DEFAULT 90.0,
        stop_days INTEGER NOT NULL DEFAULT 1,
        notes TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # Create Indices
    # Project IDs indices
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_shifts_project ON shifts(project_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_cycles_project ON cycle_catalog(project_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_plans_project ON plans(project_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_items_project ON maintenance_items(project_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_imports_project ON imports(project_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_audit_project ON audit_log(project_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_teams_project ON work_teams(project_id);")

    # Business indices for plans and items
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_plans_code ON plans(project_id, legacy_code);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_plans_status ON plans(status);")
    cursor.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_plans_active_code_unique
        ON plans(project_id, legacy_code)
        WHERE deleted_at IS NULL;
    """)
    # Older imports stored the spreadsheet's "Parada de início" (1..N)
    # directly in reference_counter. Normalize it once while retaining the
    # absolute counter internally for the calculation engine.
    cursor.execute("""UPDATE plans
                      SET phase = reference_counter,
                          reference_counter = (SELECT current_counter FROM projects WHERE projects.id=plans.project_id) + reference_counter
                      WHERE phase=0 AND reference_counter BETWEEN 1 AND 120
                        AND reference_counter < (SELECT current_counter FROM projects WHERE projects.id=plans.project_id)""")
    
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_items_legacy ON maintenance_items(project_id, legacy_identifier);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_items_plan ON maintenance_items(plan_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_items_team ON maintenance_items(team_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_items_work_center ON maintenance_items(work_center);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_items_gpm ON maintenance_items(gpm);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_items_condition ON maintenance_items(condition_code);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_items_priority ON maintenance_items(priority);")

    # 11. Automatic balance constraints configured by the user
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS auto_balance_rules (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
        name TEXT NOT NULL,
        rule_type TEXT NOT NULL CHECK(rule_type IN ('together', 'sequence', 'separate')),
        item_ids_json TEXT NOT NULL,
        enforcement TEXT NOT NULL DEFAULT 'mandatory'
            CHECK(enforcement IN ('mandatory', 'preferred')),
        config_json TEXT,
        active INTEGER NOT NULL DEFAULT 1,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );
    """)
    _migrate_auto_balance_rules(conn)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_auto_balance_rules_project ON auto_balance_rules(project_id);")

    # Manual balancing is persisted as a draft overlay. The official item-plan
    # relationship remains untouched until the user explicitly completes it.
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS manual_balance_sessions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
        status TEXT NOT NULL DEFAULT 'DRAFT'
            CHECK(status IN ('DRAFT','COMPLETED','DISCARDED')),
        base_mode TEXT NOT NULL DEFAULT 'zero'
            CHECK(base_mode IN ('zero','current')),
        horizon INTEGER NOT NULL DEFAULT 12,
        version INTEGER NOT NULL DEFAULT 1,
        settings_json TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        completed_at DATETIME
    );
    """)
    cursor.execute("""
    CREATE UNIQUE INDEX IF NOT EXISTS idx_manual_balance_one_draft
    ON manual_balance_sessions(project_id) WHERE status='DRAFT';
    """)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS manual_balance_assignments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id INTEGER NOT NULL REFERENCES manual_balance_sessions(id) ON DELETE CASCADE,
        project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
        item_id INTEGER NOT NULL REFERENCES maintenance_items(id) ON DELETE CASCADE,
        original_plan_id INTEGER REFERENCES plans(id) ON DELETE SET NULL,
        target_plan_id INTEGER REFERENCES plans(id) ON DELETE SET NULL,
        balance_state TEXT NOT NULL DEFAULT 'PENDING'
            CHECK(balance_state IN ('PENDING','MANUAL','AUTOMATIC','FIXED')),
        target_stop INTEGER,
        source TEXT NOT NULL DEFAULT 'manual'
            CHECK(source IN ('manual','automatic','fixed')),
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(session_id,item_id)
    );
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_manual_sessions_project ON manual_balance_sessions(project_id,status);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_manual_assignments_session ON manual_balance_assignments(session_id,balance_state);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_manual_assignments_item ON manual_balance_assignments(item_id);")

    # 12. SAP operations and their long texts.  The legacy identifier is the
    # stable link used by the corporate workbook; item_id keeps referential
    # integrity inside the application.
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS item_operations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
        item_id INTEGER NOT NULL REFERENCES maintenance_items(id) ON DELETE CASCADE,
        operation_code TEXT NOT NULL,
        suboperation_code TEXT NOT NULL DEFAULT '',
        work_center TEXT,
        short_text TEXT NOT NULL,
        unit TEXT NOT NULL DEFAULT 'H',
        headcount INTEGER,
        hours REAL,
        status TEXT NOT NULL DEFAULT 'ACTIVE',
        validation_status TEXT NOT NULL DEFAULT 'OK',
        validation_issues_json TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(item_id, operation_code, suboperation_code)
    );
    """)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS operation_long_texts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
        operation_id INTEGER NOT NULL REFERENCES item_operations(id) ON DELETE CASCADE,
        group_code TEXT,
        group_counter TEXT,
        line_sequence INTEGER NOT NULL DEFAULT 1,
        text TEXT NOT NULL,
        validation_status TEXT NOT NULL DEFAULT 'OK',
        validation_issues_json TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(operation_id, line_sequence)
    );
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_operations_project ON item_operations(project_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_operations_item ON item_operations(item_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_long_text_operation ON operation_long_texts(operation_id);")

    # Keep full-schema migrations self-sufficient.  On a brand-new database the
    # lightweight migration runs before these tables exist, so it cannot add
    # validation metadata later unless the canonical schema includes it here.
    # The ALTER fallback also repairs databases initialized by an older build.
    for table in ('plans', 'maintenance_items', 'item_operations', 'operation_long_texts'):
        columns = {row[1] for row in cursor.execute(f'PRAGMA table_info("{table}")').fetchall()}
        if 'validation_status' not in columns:
            cursor.execute(
                f'ALTER TABLE "{table}" ADD COLUMN validation_status TEXT NOT NULL DEFAULT \'OK\''
            )
        if 'validation_issues_json' not in columns:
            cursor.execute(
                f'ALTER TABLE "{table}" ADD COLUMN validation_issues_json TEXT'
            )

    _remove_obsolete_numeric_identifier_warnings(conn)

    # Check for system_name, ele_capacity, mec_capacity, sol_capacity columns in projects table
    cursor.execute("PRAGMA table_info(projects);")
    proj_cols = [c[1] for c in cursor.fetchall()]
    if 'system_name' not in proj_cols:
        cursor.execute("ALTER TABLE projects ADD COLUMN system_name TEXT;")
    if 'ele_capacity' not in proj_cols:
        cursor.execute("ALTER TABLE projects ADD COLUMN ele_capacity REAL;")
    if 'mec_capacity' not in proj_cols:
        cursor.execute("ALTER TABLE projects ADD COLUMN mec_capacity REAL;")
    if 'sol_capacity' not in proj_cols:
        cursor.execute("ALTER TABLE projects ADD COLUMN sol_capacity REAL;")
    # Unified workforce-capacity parameters. Team schedules are legacy-only.
    if 'hours_per_person' not in proj_cols:
        cursor.execute("ALTER TABLE projects ADD COLUMN hours_per_person REAL NOT NULL DEFAULT 9.1;")
    if 'tool_time_percent' not in proj_cols:
        cursor.execute("ALTER TABLE projects ADD COLUMN tool_time_percent REAL NOT NULL DEFAULT 100.0;")
    cursor.execute("""
        UPDATE projects
        SET hours_per_person = COALESCE(hours_per_person, 9.1),
            tool_time_percent = COALESCE(tool_time_percent, 100.0)
    """)

    # 13. Standard Long Texts Library (Modelos Padrão de Procedimentos)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS standard_long_texts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        category TEXT NOT NULL DEFAULT 'GERAL',
        text TEXT NOT NULL,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # 14. Standard Items Library (Modelos Padrão de Equipamentos)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS standard_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        category TEXT NOT NULL DEFAULT 'GERAL',
        object_type TEXT NOT NULL DEFAULT 'EQUIPAMENTO',
        gpm TEXT NOT NULL DEFAULT '',
        work_center TEXT NOT NULL DEFAULT '',
        condition_code TEXT NOT NULL DEFAULT '0',
        priority INTEGER NOT NULL DEFAULT 3,
        duration_hours REAL NOT NULL DEFAULT 8.0,
        headcount INTEGER NOT NULL DEFAULT 1,
        order_type TEXT NOT NULL DEFAULT 'PM13',
        description TEXT NOT NULL,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );
    """)
    standard_item_cols = {row[1] for row in cursor.execute("PRAGMA table_info(standard_items);").fetchall()}
    for column_sql in (
        "object_code TEXT NOT NULL DEFAULT ''",
        "notes TEXT",
        "mec_headcount INTEGER NOT NULL DEFAULT 0",
        "mec_hours REAL NOT NULL DEFAULT 0",
        "ele_headcount INTEGER NOT NULL DEFAULT 0",
        "ele_hours REAL NOT NULL DEFAULT 0",
        "sol_headcount INTEGER NOT NULL DEFAULT 0",
        "sol_hours REAL NOT NULL DEFAULT 0",
    ):
        column_name = column_sql.split()[0]
        if column_name not in standard_item_cols:
            cursor.execute(f"ALTER TABLE standard_items ADD COLUMN {column_sql};")

    # 15. Standard Item Operations
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS standard_item_operations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        standard_item_id INTEGER NOT NULL REFERENCES standard_items(id) ON DELETE CASCADE,
        operation_code TEXT NOT NULL,
        suboperation_code TEXT NOT NULL DEFAULT '',
        work_center TEXT,
        short_text TEXT NOT NULL,
        unit TEXT NOT NULL DEFAULT 'H',
        headcount INTEGER,
        hours REAL
    );
    """)

    # 16. Standard Operation Long Texts
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS standard_operation_long_texts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        standard_operation_id INTEGER NOT NULL REFERENCES standard_item_operations(id) ON DELETE CASCADE,
        group_code TEXT,
        group_counter TEXT,
        text TEXT NOT NULL,
        structure_mode TEXT NOT NULL DEFAULT 'FREE',
        structure_json TEXT,
        source_text_original TEXT
    );
    """)

    # First repair old NOT NULL workload schemas while the standard long-text
    # table still has its legacy five-column shape. Metadata is added afterwards.
    _migrate_standard_item_operations_nullable_workload(conn)
    cursor = conn.cursor()

    # 17. Structured Long Text metadata. The rendered `text` remains the SAP/export
    # source of truth; JSON metadata only powers hierarchy-aware editing.
    for table in ('operation_long_texts', 'standard_operation_long_texts', 'standard_long_texts'):
        existing_cols = {row[1] for row in cursor.execute(f'PRAGMA table_info("{table}")').fetchall()}
        if 'structure_mode' not in existing_cols:
            cursor.execute(f"ALTER TABLE {table} ADD COLUMN structure_mode TEXT NOT NULL DEFAULT 'FREE'")
        if 'structure_json' not in existing_cols:
            cursor.execute(f"ALTER TABLE {table} ADD COLUMN structure_json TEXT")
        if 'source_text_original' not in existing_cols:
            cursor.execute(f"ALTER TABLE {table} ADD COLUMN source_text_original TEXT")

    # Reusable blocks are intentionally separate from full long-text standards.
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS standard_long_text_blocks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        category TEXT NOT NULL DEFAULT 'GERAL',
        tags TEXT NOT NULL DEFAULT '',
        structure_json TEXT NOT NULL,
        text TEXT NOT NULL,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # Seed Initial Standard Templates if empty
    cursor.execute("SELECT COUNT(*) FROM standard_long_texts;")
    if cursor.fetchone()[0] == 0:
        cursor.execute("""
            INSERT INTO standard_long_texts (title, category, text) VALUES 
            ('Manutenção Preventiva de Motor Elétrico', 'Motores', '1. SEGURANÇA E BLOQUEIO (LOTO):
1.1. REALIZAR O BLOQUEIO DA ALIMENTAÇÃO ELÉTRICA DA UNIDADE E VERIFICAR AUSÊNCIA DE TENSÃO.
1.2. USAR OS EPIs OBRIGATÓRIOS: ÓCULOS DE SEGURANÇA, LUVAS E PROTETOR AURICULAR.

2. PROCEDIMENTO DE MANUTENÇÃO:
2.1. LIMPEZA EXTERNA DA CARCAÇA E DAS ALETAS DE REFRIGERAÇÃO.
2.2. VERIFICAÇÃO DO ESTADO DE FIXAÇÃO DOS PARAFUSOS DA BASE E ACOPLAMENTO.
2.3. INSPEÇÃO DOS ROLAMENTOS, VERIFICANDO RUÍDOS E NÍVEL DE VIBRAÇÃO.
2.4. RE-LUBRIFICAÇÃO DOS ROLAMENTOS CONFORME ESPECIFICAÇÃO DO FABRICANTE.
2.5. MEDIÇÃO DA RESISTÊNCIA DE ISOLAMENTO DAS BOBINAS (MEGGER).

3. FINALIZAÇÃO:
3.1. REMOVER BLOQUEIOS E RECONECTAR ALIMENTAÇÃO.
3.2. REALIZAR TESTE DE FUNCIONAMENTO A VAZIO E EM CARGA.'),
            ('Inspeção e Troca de Óleo em Redutor', 'Redutores', '1. MEDIDAS DE PREVENÇÃO:
1.1. ASSEGURAR QUE O EQUIPAMENTO ESTEJA PARADO E DESENERGIZADO.
1.2. VERIFICAR A TEMPERATURA DO REDUTOR ANTES DE ABRIR O DRENO (RISCO DE QUEIMADURA).

2. PROCEDIMENTO DE TROCA DE ÓLEO:
2.1. ABRIR O DRENO E COLETAR O ÓLEO USADO EM RECIPIENTE ADEQUADO PARA DESCARTE AMBIENTAL.
2.2. INSPECIONAR O PLUG MAGNÉTICO DO DRENO QUANTO À PRESENÇA DE LIMALHAS METÁLICAS.
2.3. LIMPAR O VISOR DE NÍVEL E O RESPIRO DO REDUTOR.
2.4. ABASTECER COM ÓLEO NOVO ATÉ O NÍVEL INDICADO NO VISOR.

3. INSPEÇÃO FINAL:
3.1. VERIFICAR AUSÊNCIA DE VAZAMENTOS NAS JUNTAS E RETENTORES.
3.2. REGISTRAR O VOLUME E O TIPO DE ÓLEO UTILIZADO.'),
            ('Alinhamento a Laser de Conjunto Motobomba', 'Alinhamento', '1. PREPARAÇÃO:
1.1. BLOQUEAR PAINEL ELÉTRICO E ABRIR CHAVE DE MANOBRA.
1.2. DESCONECTAR O PROTETOR DE ACOPLAMENTO.

2. ALINHAMENTO:
2.1. FIXAR OS SENSORES DO ALINHADOR A LASER NOS EIXOS DO MOTOR E DA BOMBA.
2.2. MEDIR O DESALINHAMENTO PARALELO E ANGULAR.
2.3. AJUSTAR A ALTURA DO MOTOR UTILIZANDO CALÇOS INOXIDÁVEIS.
2.4. REFAZER A LEITURA A LASER ATÉ OBTER VALORES DENTRO DA TOLERÂNCIA DE 0,05 MM.

3. REABERTO E TESTE:
3.1. REAPERTAREM OS PARAFUSOS DA BASE COM TORQUÍMETRO.
3.2. REINSTALAR PROTETOR DE ACOPLAMENTO E LIBERAR EQUIPAMENTO.');
        """)

    cursor.execute("SELECT COUNT(*) FROM standard_items;")
    if cursor.fetchone()[0] == 0:
        cursor.execute("""
            INSERT INTO standard_items (title, category, object_type, gpm, work_center, condition_code, priority, duration_hours, headcount, order_type, description) VALUES
            ('Manutenção Preventiva de Motor Elétrico', 'Motores', 'EQUIPAMENTO', 'MEC', 'ELE01', 'P', 3, 4.0, 2, 'PM13', 'MANUTENÇÃO PREVENTIVA DE MOTOR ELÉTRICO');
        """)
        std_item_id = cursor.lastrowid
        cursor.execute("""
            INSERT INTO standard_item_operations (standard_item_id, operation_code, suboperation_code, work_center, short_text, unit, headcount, hours) VALUES
            (?, '0010', '', 'ELE01', 'BLOQUEIO E ISOLAMENTO ELETRICO DO MOTOR', 'H', 1, 1.0),
            (?, '0020', '', 'ELE01', 'REVISAO ELETRICA E MEDICAO DE ISOLAMENTO', 'H', 1, 2.0),
            (?, '0030', '', 'MEC01', 'LUBRIFICACAO E INSPECAO DE ROLAMENTOS', 'H', 1, 1.0);
        """, (std_item_id, std_item_id, std_item_id))

    # 17. Transactional per-project undo/redo snapshots.  Snapshot payloads are
    # compressed JSON BLOBs; event/audit tables themselves are intentionally not
    # part of a project snapshot.
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS project_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
        action TEXT NOT NULL,
        metadata_json TEXT,
        before_snapshot BLOB NOT NULL,
        after_snapshot BLOB NOT NULL,
        before_hash TEXT NOT NULL,
        after_hash TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'APPLIED'
            CHECK(status IN ('APPLIED', 'UNDONE')),
        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        undone_at DATETIME,
        redone_at DATETIME
    );
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_project_history_cursor
        ON project_history(project_id, status, id);
    """)

    # Visual row markers and stable manual display order for management grids.
    for table in ('plans', 'item_operations', 'operation_long_texts'):
        for definition in ('row_color TEXT', 'display_order INTEGER'):
            try:
                cursor.execute(f"ALTER TABLE {table} ADD COLUMN {definition}")
            except sqlite3.OperationalError:
                pass
        cursor.execute(f"UPDATE {table} SET display_order=id WHERE display_order IS NULL")
    for table in ('item_operations', 'operation_long_texts'):
        try:
            cursor.execute(f"ALTER TABLE {table} ADD COLUMN pending_item_identifier TEXT")
        except sqlite3.OperationalError:
            pass
    try:
        cursor.execute("ALTER TABLE projects ADD COLUMN is_locked INTEGER NOT NULL DEFAULT 0")
    except sqlite3.OperationalError:
        pass

    # 18. Users and Sessions tables
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        login TEXT UNIQUE NOT NULL,
        name TEXT NOT NULL,
        password_hash TEXT NOT NULL,
        role TEXT NOT NULL DEFAULT 'USER',
        status TEXT NOT NULL DEFAULT 'ACTIVE',
        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    """)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS user_sessions (
        token TEXT PRIMARY KEY,
        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        expires_at DATETIME NOT NULL,
        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    """)

    admin_row = cursor.execute("SELECT 1 FROM users WHERE login = ?", ('admin@usiminas.com',)).fetchone()
    if not admin_row:
        salt = 'e4a2b8c9d1f3e5a7'
        hashed = hashlib.pbkdf2_hmac('sha256', b'admin123', salt.encode('utf-8'), 100000).hex()
        pwd_hash = f"{salt}${hashed}"
        cursor.execute("""
            INSERT INTO users (login, name, password_hash, role, status)
            VALUES (?, ?, ?, ?, ?)
        """, ('admin@usiminas.com', 'Administrador PM13/PM11', pwd_hash, 'ADMIN', 'ACTIVE'))

    conn.commit()
