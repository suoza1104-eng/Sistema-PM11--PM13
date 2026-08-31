import sqlite3
import json
import datetime
import hashlib
import os
import secrets
from core.database import get_db_connection, normalize_search_text
from core.audit_service import log_action
from core.long_text_structure import prepare_for_save, materialize_record, normalize_nodes, render_nodes


# ==========================================
# AUTHENTICATION & SESSION FUNCTIONS
# ==========================================

def hash_password(password, salt=None):
    if not salt:
        salt = os.urandom(16).hex()
    hashed = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt.encode('utf-8'), 100000).hex()
    return f"{salt}${hashed}"

def verify_password(password, password_hash):
    if not password_hash or '$' not in password_hash:
        return False
    salt, hashed = password_hash.split('$', 1)
    computed = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt.encode('utf-8'), 100000).hex()
    return computed == hashed

def authenticate_user(login, password):
    login = str(login or '').strip().lower()
    if not login or not password:
        return None
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE LOWER(login) = ? AND status = 'ACTIVE'", (login,))
        user = cursor.fetchone()
        if not user:
            return None
        u_dict = dict(user)
        if verify_password(password, u_dict['password_hash']):
            del u_dict['password_hash']
            return u_dict
        return None
    finally:
        conn.close()

def create_user_session(user_id, days=7):
    token = secrets.token_hex(32)
    expires = (datetime.datetime.now() + datetime.timedelta(days=days)).strftime('%Y-%m-%d %H:%M:%S')
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO user_sessions (token, user_id, expires_at) VALUES (?, ?, ?)",
                       (token, user_id, expires))
        conn.commit()
        return token
    finally:
        conn.close()

def get_user_by_session(token):
    if not token:
        return None
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT u.id, u.login, u.name, u.role, u.status, s.expires_at
            FROM user_sessions s
            JOIN users u ON u.id = s.user_id
            WHERE s.token = ? AND u.status = 'ACTIVE'
        """, (token,))
        row = cursor.fetchone()
        if not row:
            return None
        d = dict(row)
        try:
            expires = datetime.datetime.strptime(d['expires_at'], '%Y-%m-%d %H:%M:%S')
            if expires < datetime.datetime.now():
                cursor.execute("DELETE FROM user_sessions WHERE token = ?", (token,))
                conn.commit()
                return None
        except Exception:
            pass
        del d['expires_at']
        return d
    finally:
        conn.close()

def revoke_user_session(token):
    if not token:
        return
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM user_sessions WHERE token = ?", (token,))
        conn.commit()
    finally:
        conn.close()


class PlanCodeConflict(sqlite3.IntegrityError):
    """A normalized plan code is already owned by another active plan."""

    def __init__(self, conflict):
        self.conflict = dict(conflict)
        code = self.conflict.get('legacy_code', '')
        plan_id = self.conflict.get('id')
        description = self.conflict.get('description', '')
        super().__init__(
            f'J\u00e1 existe outro plano ativo com o c\u00f3digo "{code}" '
            f'(plano #{plan_id}: "{description}").'
        )


def _active_plan_code_conflict(cursor, project_id, legacy_code, exclude_plan_id=None):
    normalized_code = str(legacy_code or '').upper().strip()
    query = """SELECT id, legacy_code, description
               FROM plans
               WHERE project_id = ? AND legacy_code = ? AND deleted_at IS NULL"""
    params = [int(project_id), normalized_code]
    if exclude_plan_id is not None:
        query += " AND id <> ?"
        params.append(int(exclude_plan_id))
    query += " ORDER BY id LIMIT 1"
    return to_dict(cursor.execute(query, params).fetchone())

# Helper to convert sqlite3.Row or list of Rows to dict or list of dicts
def to_dict(row):
    if row is None:
        return None
    return dict(row)

def to_dict_list(rows):
    return [dict(r) for r in rows]

# ==========================================
# PROJECTS MODEL
# ==========================================

def _release_deleted_project_name(cursor, name):
    """Keep the audit row but release its globally-unique visible name."""
    requested = str(name or '').strip()
    rows = cursor.execute(
        "SELECT id FROM projects WHERE name=? AND deleted_at IS NOT NULL",
        (requested,),
    ).fetchall()
    for row in rows:
        cursor.execute(
            "UPDATE projects SET name=name || ' [EXCLUIDO #' || id || ']' WHERE id=?",
            (row['id'],),
        )

def list_projects():
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
        SELECT p.*,
               (SELECT COUNT(*) FROM plans WHERE project_id = p.id AND deleted_at IS NULL) AS plans_count,
               (SELECT COUNT(*) FROM maintenance_items WHERE project_id = p.id AND deleted_at IS NULL) AS items_count
        FROM projects p
        WHERE p.deleted_at IS NULL 
        ORDER BY p.status ASC, p.name ASC;
        """)
        return to_dict_list(cursor.fetchall())
    finally:
        conn.close()

def get_project(project_id):
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
        SELECT p.*,
               (SELECT COUNT(*) FROM plans WHERE project_id = p.id AND deleted_at IS NULL) AS plans_count,
               (SELECT COUNT(*) FROM maintenance_items WHERE project_id = p.id AND deleted_at IS NULL) AS items_count
        FROM projects p
        WHERE p.id = ? AND p.deleted_at IS NULL;
        """, (project_id,))
        return to_dict(cursor.fetchone())
    finally:
        conn.close()

def set_project_locked(project_id, locked):
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE projects SET is_locked=?, updated_at=CURRENT_TIMESTAMP WHERE id=? AND deleted_at IS NULL",
            (1 if locked else 0, project_id)
        )
        if cursor.rowcount == 0:
            raise ValueError("Projeto nao encontrado.")
        conn.commit()
        return get_project(project_id)
    finally:
        conn.close()

def is_project_locked(project_id):
    conn = get_db_connection()
    try:
        row = conn.execute("SELECT is_locked FROM projects WHERE id=? AND deleted_at IS NULL", (project_id,)).fetchone()
        return bool(row and row['is_locked'])
    finally:
        conn.close()

def create_project(name, description, area, system_name=None, current_counter=0, default_horizon=12, utilization_factor=1.0):
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        _release_deleted_project_name(cursor, name)
        cursor.execute("""
        INSERT INTO projects (name, description, area, system_name, current_counter, default_horizon, utilization_factor, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, 'ACTIVE');
        """, (name, description, area, system_name, current_counter, default_horizon, utilization_factor))
        project_id = cursor.lastrowid
        
        # Capacity is project-level (hours/person + Tool Time).
        # Legacy shift rows are no longer created for new projects.

        # Insert empty settings
        cursor.execute("""
        INSERT INTO project_settings (project_id, code_pattern)
        VALUES (?, 'URRST3[P,E,F,D]###');
        """, (project_id,))
        
        conn.commit()
        log_action(project_id, 'PROJECT', project_id, 'CREATE', None, {
            'name': name, 'description': description, 'area': area, 'system_name': system_name,
            'current_counter': current_counter, 'default_horizon': default_horizon
        })
        return project_id
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()

def update_project(project_id, name, description, area, system_name=None, current_counter=0, default_horizon=12, utilization_factor=1.0, status='ACTIVE'):
    old_data = get_project(project_id)
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        _release_deleted_project_name(cursor, name)
        cursor.execute("""
        UPDATE projects
        SET name = ?, description = ?, area = ?, system_name = ?, current_counter = ?, default_horizon = ?, utilization_factor = ?, status = ?, updated_at = CURRENT_TIMESTAMP
        WHERE id = ?;
        """, (name, description, area, system_name, current_counter, default_horizon, utilization_factor, status, project_id))
        conn.commit()
        log_action(project_id, 'PROJECT', project_id, 'UPDATE', old_data, {
            'name': name, 'description': description, 'area': area, 'system_name': system_name,
            'current_counter': current_counter, 'default_horizon': default_horizon,
            'utilization_factor': utilization_factor, 'status': status
        })
        return True
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()

def archive_project(project_id):
    old_data = get_project(project_id)
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("UPDATE projects SET status = 'ARCHIVED', updated_at = CURRENT_TIMESTAMP WHERE id = ?;", (project_id,))
        conn.commit()
        log_action(project_id, 'PROJECT', project_id, 'ARCHIVE', old_data, {'status': 'ARCHIVED'})
        return True
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()

def delete_project(project_id):
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        now = datetime.datetime.now().isoformat()
        cursor.execute("UPDATE projects SET deleted_at = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?;", (now, project_id))
        conn.commit()
        log_action(project_id, 'PROJECT', project_id, 'DELETE', {'id': project_id}, None)
        return True
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()

def duplicate_project(src_project_id, new_name):
    """Deep duplicates a project (plans, items, catalog, shifts, settings)."""
    src_proj = get_project(src_project_id)
    if not src_proj:
        raise ValueError("Projeto de origem não encontrado.")
        
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        
        # 1. Insert new project
        cursor.execute("""
        INSERT INTO projects (name, description, area, current_counter, default_horizon, utilization_factor, hours_per_person, tool_time_percent, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'ACTIVE');
        """, (
            new_name, f"Cópia de {src_proj['name']}. {src_proj['description'] or ''}", src_proj['area'],
            src_proj['current_counter'], src_proj['default_horizon'], src_proj['utilization_factor'],
            src_proj.get('hours_per_person') or 9.1,
            src_proj.get('tool_time_percent') if src_proj.get('tool_time_percent') is not None else 100.0
        ))
        new_project_id = cursor.lastrowid
        
        # 2. Duplicate Shifts
        cursor.execute("SELECT * FROM shifts WHERE project_id = ?;", (src_project_id,))
        shifts = cursor.fetchall()
        for s in shifts:
            cursor.execute("""
            INSERT INTO shifts (project_id, name, sequence, duration_hours, active)
            VALUES (?, ?, ?, ?, ?);
            """, (new_project_id, s['name'], s['sequence'], s['duration_hours'], s['active']))
            
        # 3. Duplicate Cycle Catalog
        cursor.execute("SELECT * FROM cycle_catalog WHERE project_id = ?;", (src_project_id,))
        cycles = cursor.fetchall()
        for c in cycles:
            cursor.execute("""
            INSERT INTO cycle_catalog (project_id, cycle, unit, cycle_text, opening_horizon, active)
            VALUES (?, ?, ?, ?, ?, ?);
            """, (new_project_id, c['cycle'], c['unit'], c['cycle_text'], c['opening_horizon'], c['active']))
            
        # 4. Duplicate Project Settings
        cursor.execute("SELECT * FROM project_settings WHERE project_id = ?;", (src_project_id,))
        setting = cursor.fetchone()
        if setting:
            cursor.execute("""
            INSERT INTO project_settings
                (project_id, code_pattern, balance_strategy, geography_mode,
                 vertical_tolerance, similarity_enabled, balance_max_passes)
            VALUES (?, ?, ?, ?, ?, ?, ?);
            """, (new_project_id, setting['code_pattern'],
                  setting['balance_strategy'], setting['geography_mode'],
                  setting['vertical_tolerance'], setting['similarity_enabled'],
                  setting['balance_max_passes']))
            
        # 5. Duplicate Plans and keep track of mapping
        cursor.execute("SELECT * FROM plans WHERE project_id = ? AND deleted_at IS NULL;", (src_project_id,))
        plans = cursor.fetchall()
        plan_map = {} # old_plan_id -> new_plan_id
        for p in plans:
            cursor.execute("""
            INSERT INTO plans (project_id, legacy_code, description, character_count, cycle, unit, cycle_text, opening_horizon, reference_counter, phase, status, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """, (new_project_id, p['legacy_code'], p['description'], p['character_count'], p['cycle'], p['unit'], p['cycle_text'], p['opening_horizon'], p['reference_counter'], p['phase'], p['status'], p['notes']))
            new_plan_id = cursor.lastrowid
            plan_map[p['id']] = new_plan_id
            
        # 6. Duplicate Items, mapping plan_id to the new plan IDs
        cursor.execute("SELECT * FROM maintenance_items WHERE project_id = ? AND deleted_at IS NULL;", (src_project_id,))
        items = cursor.fetchall()
        for item in items:
            new_plan_id = plan_map.get(item['plan_id']) # Could be None if item was unlinked
            cursor.execute("""
            INSERT INTO maintenance_items (
                project_id, legacy_identifier, plan_id, object_type, object_code,
                gpm, work_center, condition_code, priority, legacy_start,
                description, character_count, duration_hours, headcount, hh,
                order_type, status, notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """, (
                new_project_id, item['legacy_identifier'], new_plan_id, item['object_type'], item['object_code'],
                item['gpm'], item['work_center'], item['condition_code'], item['priority'], item['legacy_start'],
                item['description'], item['character_count'], item['duration_hours'], item['headcount'], item['hh'],
                item['order_type'], item['status'], item['notes']
            ))
            
        conn.commit()
        log_action(new_project_id, 'PROJECT', new_project_id, 'DUPLICATE', {'source_project_id': src_project_id}, {'new_project_id': new_project_id, 'new_name': new_name})
        return new_project_id
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()


# Complete graph clone. This definition intentionally replaces the legacy
# column-list implementation above so newly added project fields are copied too.
def duplicate_project(src_project_id, new_name):
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        source_project = cursor.execute(
            "SELECT * FROM projects WHERE id=? AND deleted_at IS NULL", (src_project_id,)
        ).fetchone()
        if not source_project:
            raise ValueError("Projeto de origem nao encontrado.")

        # Project names are globally unique, including soft-deleted records.
        # Resolve collisions here so every caller/import path gets the same
        # safe behavior instead of leaking a raw SQLite UNIQUE error.
        requested_name = str(new_name or '').strip()
        if not requested_name:
            raise ValueError("Nome da copia e obrigatorio.")
        _release_deleted_project_name(cursor, requested_name)
        resolved_name = requested_name
        copy_number = 1
        while cursor.execute(
                "SELECT 1 FROM projects WHERE name=? COLLATE NOCASE LIMIT 1",
                (resolved_name,)).fetchone():
            suffix = " (Cópia)" if copy_number == 1 else f" (Cópia {copy_number})"
            resolved_name = f"{requested_name}{suffix}"
            copy_number += 1

        def insert_row(table, source, overrides=None):
            data = dict(source)
            for key in ('id', 'created_at', 'updated_at'):
                data.pop(key, None)
            data.update(overrides or {})
            columns = list(data)
            cursor.execute(
                f"INSERT INTO {table} ({','.join(columns)}) VALUES ({','.join('?' for _ in columns)})",
                [data[column] for column in columns],
            )
            return cursor.lastrowid

        new_project_id = insert_row('projects', source_project, {
            'name': resolved_name, 'status': 'ACTIVE', 'is_locked': 0, 'deleted_at': None,
        })

        # Only active project configuration is duplicated. Legacy shifts/work_teams
        # are intentionally not copied because capacity is now project-level.
        for table in ('cycle_catalog', 'project_settings'):
            rows = cursor.execute(
                f"SELECT * FROM {table} WHERE project_id=? ORDER BY id", (src_project_id,)
            ).fetchall()
            for row in rows:
                insert_row(table, row, {'project_id': new_project_id})

        plan_map = {}
        rows = cursor.execute(
            "SELECT * FROM plans WHERE project_id=? AND deleted_at IS NULL ORDER BY id", (src_project_id,)
        ).fetchall()
        for row in rows:
            plan_map[row['id']] = insert_row('plans', row, {'project_id': new_project_id})

        item_map = {}
        rows = cursor.execute(
            "SELECT * FROM maintenance_items WHERE project_id=? AND deleted_at IS NULL ORDER BY id",
            (src_project_id,),
        ).fetchall()
        for row in rows:
            # A soft-deleted plan can leave an old item row behind. It is not
            # part of the visible project graph and cannot be cloned safely.
            if row['plan_id'] not in plan_map:
                continue
            item_map[row['id']] = insert_row('maintenance_items', row, {
                'project_id': new_project_id,
                'plan_id': plan_map[row['plan_id']],
                'team_id': None,
            })

        # Priorímetro acompanha os itens na duplicação do projeto.
        if cursor.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='item_priorimeter'").fetchone():
            rows = cursor.execute(
                "SELECT * FROM item_priorimeter WHERE project_id=? ORDER BY id", (src_project_id,)
            ).fetchall()
            for row in rows:
                if row['item_id'] not in item_map:
                    continue
                insert_row('item_priorimeter', row, {
                    'project_id': new_project_id, 'item_id': item_map[row['item_id']],
                })

        operation_map = {}
        rows = cursor.execute(
            "SELECT * FROM item_operations WHERE project_id=? ORDER BY id", (src_project_id,)
        ).fetchall()
        for row in rows:
            # Historical operations of deleted items remain in the database
            # for audit purposes, but are outside the active project graph.
            if row['item_id'] not in item_map:
                continue
            operation_map[row['id']] = insert_row('item_operations', row, {
                'project_id': new_project_id, 'item_id': item_map[row['item_id']],
            })

        rows = cursor.execute(
            "SELECT * FROM operation_long_texts WHERE project_id=? ORDER BY id", (src_project_id,)
        ).fetchall()
        for row in rows:
            if row['operation_id'] not in operation_map:
                continue
            insert_row('operation_long_texts', row, {
                'project_id': new_project_id, 'operation_id': operation_map[row['operation_id']],
            })

        rows = cursor.execute(
            "SELECT * FROM auto_balance_rules WHERE project_id=? ORDER BY id", (src_project_id,)
        ).fetchall()
        for row in rows:
            overrides = {'project_id': new_project_id}
            try:
                old_ids = json.loads(row['item_ids_json'] or '[]')
                overrides['item_ids_json'] = json.dumps([item_map[i] for i in old_ids if i in item_map])
            except (TypeError, ValueError):
                overrides['item_ids_json'] = '[]'
            insert_row('auto_balance_rules', row, overrides)

        conn.commit()
        log_action(new_project_id, 'PROJECT', new_project_id, 'DUPLICATE',
                   {'source_project_id': src_project_id},
                   {'new_project_id': new_project_id, 'new_name': resolved_name})
        return new_project_id
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ==========================================
# PLANS MODEL
def autofill_plans_start_stops(project_id):
    """Automatically populates and locks plan starting stops and cycle text based on plan description patterns (e.g. 6P1 -> P1, 6P2 -> P2, 6P3 -> P3)."""
    conn = get_db_connection()
    try:
        from core.import_service import extract_cycle_and_start_from_text
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, legacy_code, description, cycle, reference_counter, phase, cycle_text
            FROM plans
            WHERE project_id = ? AND deleted_at IS NULL
        """, (project_id,))
        plans = [dict(r) for r in cursor.fetchall()]
        updated = 0
        for p in plans:
            c, start, _ = extract_cycle_and_start_from_text(p.get('description', '') or '')
            if not start and p.get('legacy_code'):
                c, start, _ = extract_cycle_and_start_from_text(p['legacy_code'])
            if start:
                expected_phase = start
                expected_cycle_text = f"P{start}"
                if p['phase'] != expected_phase or p['reference_counter'] != expected_phase or p.get('cycle_text') != expected_cycle_text:
                    cursor.execute("""
                        UPDATE plans SET phase = ?, reference_counter = ?, cycle_text = ?
                        WHERE id = ?
                    """, (expected_phase, expected_phase, expected_cycle_text, p['id']))
                    updated += 1
        conn.commit()
        return updated
    except Exception:
        return 0
    finally:
        conn.close()


def list_plans(project_id, filters=None, limit=25, offset=0, order_by='legacy_code', order_dir='ASC'):
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        
        # Base query counts items and sums HH connected to the plan
        query = """
        SELECT 
            p.*, 
            COUNT(i.id) as items_count, 
            COALESCE(SUM(i.hh), 0) as total_hh
        FROM plans p
        LEFT JOIN maintenance_items i ON p.id = i.plan_id AND i.deleted_at IS NULL AND i.status = 'ACTIVE'
        WHERE p.project_id = ? AND p.deleted_at IS NULL
        """
        params = [project_id]
        
        if filters:
            if filters.get('search'):
                normalized = normalize_search_text(filters['search'])
                escaped = normalized.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
                term = f"%{escaped}%"
                query += """ AND (
                    SEARCH_NORMALIZE(p.legacy_code) LIKE ? ESCAPE '\\'
                    OR SEARCH_NORMALIZE(p.description) LIKE ? ESCAPE '\\'
                )"""
                params.extend([term, term])
            if filters.get('cycle'):
                query += " AND p.cycle = ?"
                params.append(int(filters['cycle']))
            if filters.get('unit'):
                query += " AND p.unit = ?"
                params.append(filters['unit'])
            if filters.get('status'):
                query += " AND p.status = ?"
                params.append(filters['status'])
            if filters.get('row_color'):
                query += " AND p.row_color = ?"
                params.append(str(filters['row_color']).strip().lower())
            if filters.get('with_items') == 'true':
                # Handled via HAVING below
                pass
            if filters.get('without_items') == 'true':
                # Handled via HAVING below
                pass
            if filters.get('no_counter') == 'true':
                query += " AND p.phase <= 0"
            if filters.get('long_desc') == 'true':
                query += " AND p.character_count > 40"
                
        query += " GROUP BY p.id"
        
        # HAVING filters for items count
        having_clauses = []
        if filters:
            if filters.get('with_items') == 'true':
                having_clauses.append("items_count > 0")
            if filters.get('without_items') == 'true':
                having_clauses.append("items_count = 0")
                
        if having_clauses:
            query += " HAVING " + " AND ".join(having_clauses)
            
        # Validation of order_by to prevent injection
        allowed_cols = ['legacy_code', 'description', 'character_count', 'cycle', 'unit', 'phase', 'items_count', 'total_hh', 'status']
        if order_by not in allowed_cols:
            order_by = 'legacy_code'
        order_dir = 'ASC' if order_dir.upper() == 'ASC' else 'DESC'
        
        query += f" ORDER BY {order_by} {order_dir}"
        
        if limit is not None:
            query += " LIMIT ? OFFSET ?"
            params.extend([limit, offset])
            
        cursor.execute(query, params)
        return to_dict_list(cursor.fetchall())
    finally:
        conn.close()

def count_plans(project_id, filters=None):
    # To count correctly with HAVING clauses, we wrap the base group query
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        
        query = """
        SELECT COUNT(*) FROM (
            SELECT p.id, COUNT(i.id) as items_count
            FROM plans p
            LEFT JOIN maintenance_items i ON p.id = i.plan_id AND i.deleted_at IS NULL AND i.status = 'ACTIVE'
            WHERE p.project_id = ? AND p.deleted_at IS NULL
        """
        params = [project_id]
        
        if filters:
            if filters.get('search'):
                normalized = normalize_search_text(filters['search'])
                escaped = normalized.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
                term = f"%{escaped}%"
                query += """ AND (
                    SEARCH_NORMALIZE(p.legacy_code) LIKE ? ESCAPE '\\'
                    OR SEARCH_NORMALIZE(p.description) LIKE ? ESCAPE '\\'
                )"""
                params.extend([term, term])
            if filters.get('cycle'):
                query += " AND p.cycle = ?"
                params.append(int(filters['cycle']))
            if filters.get('unit'):
                query += " AND p.unit = ?"
                params.append(filters['unit'])
            if filters.get('status'):
                query += " AND p.status = ?"
                params.append(filters['status'])
            if filters.get('no_counter') == 'true':
                query += " AND p.phase <= 0"
            if filters.get('long_desc') == 'true':
                query += " AND p.character_count > 40"
                
        query += " GROUP BY p.id"
        
        having_clauses = []
        if filters:
            if filters.get('with_items') == 'true':
                having_clauses.append("items_count > 0")
            if filters.get('without_items') == 'true':
                having_clauses.append("items_count = 0")
                
        if having_clauses:
            query += " HAVING " + " AND ".join(having_clauses)
            
        query += ") t;"
        
        cursor.execute(query, params)
        row = cursor.fetchone()
        return row[0] if row else 0
    finally:
        conn.close()

def get_plan(plan_id):
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM plans WHERE id = ? AND deleted_at IS NULL;", (plan_id,))
        return to_dict(cursor.fetchone())
    finally:
        conn.close()

def get_plan_by_code(project_id, legacy_code):
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM plans WHERE project_id = ? AND legacy_code = ? AND deleted_at IS NULL;", (project_id, legacy_code.upper().strip()))
        return to_dict(cursor.fetchone())
    finally:
        conn.close()

def create_plan(project_id, legacy_code, description, cycle, unit, cycle_text, opening_horizon, reference_counter, notes=None, start_stop=None):
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        normalized_code = str(legacy_code or '').upper().strip()
        conflict = _active_plan_code_conflict(cursor, project_id, normalized_code)
        if conflict:
            raise PlanCodeConflict(conflict)
        desc_clean = description.strip() if description else ""
        char_count = len(desc_clean)
        
        cursor.execute("""
        INSERT INTO plans (project_id, legacy_code, description, character_count, cycle, unit, cycle_text, opening_horizon, reference_counter, phase, status, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'ACTIVE', ?);
        """, (project_id, normalized_code, desc_clean, char_count, int(cycle), unit.strip(), cycle_text.strip(), float(opening_horizon), reference_counter, int(start_stop or 0), notes))
        plan_id = cursor.lastrowid
        
        # Add to catalog as fallback
        cursor.execute("""
        INSERT OR IGNORE INTO cycle_catalog (project_id, cycle, unit, cycle_text, opening_horizon, active)
        VALUES (?, ?, ?, ?, ?, 1);
        """, (project_id, int(cycle), unit.strip(), cycle_text.strip(), float(opening_horizon)))
        conn.commit()
        
        log_action(project_id, 'PLAN', plan_id, 'CREATE', None, {
            'legacy_code': legacy_code, 'description': desc_clean, 'cycle': cycle, 'reference_counter': reference_counter
        })
        return plan_id
    except PlanCodeConflict:
        conn.rollback()
        raise
    except sqlite3.IntegrityError as e:
        conn.rollback()
        conflict = _active_plan_code_conflict(
            conn.cursor(), project_id, str(legacy_code or '').upper().strip()
        )
        if conflict:
            raise PlanCodeConflict(conflict) from e
        raise
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def update_plan(plan_id, legacy_code, description, cycle, unit, cycle_text, opening_horizon, reference_counter, status='ACTIVE', notes=None, start_stop=None):
    old_data = get_plan(plan_id)
    if not old_data:
        raise ValueError("Plano não encontrado.")
    
    project_id = old_data['project_id']
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        normalized_code = str(legacy_code or '').upper().strip()
        conflict = _active_plan_code_conflict(
            cursor, project_id, normalized_code, exclude_plan_id=plan_id
        )
        if conflict:
            raise PlanCodeConflict(conflict)
        desc_clean = description.strip() if description else ""
        char_count = len(desc_clean)
        
        cursor.execute("""
        UPDATE plans
        SET legacy_code = ?, description = ?, character_count = ?, cycle = ?, unit = ?, cycle_text = ?, opening_horizon = ?, reference_counter = ?, phase = ?, status = ?, notes = ?, updated_at = CURRENT_TIMESTAMP
        WHERE id = ?;
        """, (normalized_code, desc_clean, char_count, int(cycle), unit.strip(), cycle_text.strip(), float(opening_horizon), reference_counter, int(start_stop or 0), status, notes, plan_id))
        conn.commit()
        log_action(project_id, 'PLAN', plan_id, 'UPDATE', old_data, {
            'legacy_code': legacy_code, 'description': desc_clean, 'cycle': cycle, 'reference_counter': reference_counter, 'status': status
        })
        return True
    except PlanCodeConflict:
        conn.rollback()
        raise
    except sqlite3.IntegrityError as e:
        conn.rollback()
        conflict = _active_plan_code_conflict(
            conn.cursor(), project_id, str(legacy_code or '').upper().strip(),
            exclude_plan_id=plan_id,
        )
        if conflict:
            raise PlanCodeConflict(conflict) from e
        raise
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def update_plan_reference_counter(plan_id, reference_counter):
    old_data = get_plan(plan_id)
    if not old_data:
        raise ValueError("Plano não encontrado.")
    project_id = old_data['project_id']
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
        UPDATE plans
        SET reference_counter = ?, updated_at = CURRENT_TIMESTAMP
        WHERE id = ?;
        """, (reference_counter, plan_id))
        conn.commit()
        log_action(project_id, 'PLAN', plan_id, 'UPDATE_REF', old_data, {
            'reference_counter': reference_counter
        })
        return True
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()

def delete_plan(plan_id, item_action='unbind', target_plan_id=None):
    """Logically deletes a plan.
    - unbind: sets plan_id = NULL on linked items.
    - transfer: moves linked items to target_plan_id.
    """
    old_data = get_plan(plan_id)
    if not old_data:
        return False
        
    project_id = old_data['project_id']
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        now = datetime.datetime.now().isoformat()
        
        # 1. Handle linked items
        cursor.execute("SELECT id FROM maintenance_items WHERE plan_id = ? AND deleted_at IS NULL;", (plan_id,))
        affected_items = [r['id'] for r in cursor.fetchall()]
        
        if affected_items:
            if item_action == 'unbind':
                cursor.execute("UPDATE maintenance_items SET plan_id = NULL, updated_at = CURRENT_TIMESTAMP WHERE plan_id = ?;", (plan_id,))
            elif item_action == 'transfer':
                if not target_plan_id:
                    raise ValueError("Plano de destino não especificado para transferência.")
                cursor.execute("UPDATE maintenance_items SET plan_id = ?, updated_at = CURRENT_TIMESTAMP WHERE plan_id = ?;", (target_plan_id, plan_id))
                
        # 2. Mark plan as deleted
        cursor.execute("UPDATE plans SET deleted_at = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?;", (now, plan_id))
        
        conn.commit()
        log_action(project_id, 'PLAN', plan_id, 'DELETE', {
            'plan': old_data, 'item_action': item_action, 'affected_items_count': len(affected_items)
        }, None)
        return True
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()

# ==========================================
# MAINTENANCE ITEMS MODEL
# ==========================================

def _with_derived_workload(item):
    """Return an item whose total workforce/HH agrees with ELE+MEC+SOL."""
    if not item:
        return item
    result = dict(item)
    try:
        issues = json.loads(result.get('validation_issues_json') or '[]')
    except (TypeError, ValueError, json.JSONDecodeError):
        issues = []
    if not result.get('plan_code') and not any(x.get('code') == 'item_without_plan' for x in issues):
        issues.append({'code': 'item_without_plan', 'severity': 'ERROR',
                       'message': 'Item sem plano existente atrelado.'})
    result['validation_issues'] = issues
    result['validation_status'] = ('ERROR' if any(x.get('severity') == 'ERROR' for x in issues)
                                   else 'WARNING' if issues else 'OK')
    specialty_hc = sum(int(result.get(f'{trade}_headcount') or 0)
                       for trade in ('ele', 'mec', 'sol'))
    specialty_hh = sum(
        int(result.get(f'{trade}_headcount') or 0) * float(result.get(f'{trade}_hours') or 0.0)
        for trade in ('ele', 'mec', 'sol')
    )
    if specialty_hc > 0 or specialty_hh > 0:
        result['headcount'] = specialty_hc
        result['hh'] = specialty_hh
    else:
        duration = float(result.get('duration_hours') or 0.0)
        headcount = result.get('headcount')
        result['hh'] = duration * (int(headcount) if headcount is not None else 1)
    return result


def synchronize_item_workload_totals(project_id):
    """Persist the same derived workload used by UI and balancing services."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""UPDATE maintenance_items
            SET headcount = CASE WHEN
                    COALESCE(ele_headcount,0)+COALESCE(mec_headcount,0)+COALESCE(sol_headcount,0) > 0
                THEN COALESCE(ele_headcount,0)+COALESCE(mec_headcount,0)+COALESCE(sol_headcount,0)
                ELSE headcount END,
                hh = CASE WHEN
                    COALESCE(ele_headcount,0)+COALESCE(mec_headcount,0)+COALESCE(sol_headcount,0) > 0
                    OR COALESCE(ele_headcount,0)*COALESCE(ele_hours,0)
                     + COALESCE(mec_headcount,0)*COALESCE(mec_hours,0)
                     + COALESCE(sol_headcount,0)*COALESCE(sol_hours,0) > 0
                THEN COALESCE(ele_headcount,0)*COALESCE(ele_hours,0)
                   + COALESCE(mec_headcount,0)*COALESCE(mec_hours,0)
                   + COALESCE(sol_headcount,0)*COALESCE(sol_hours,0)
                ELSE COALESCE(duration_hours,0)*COALESCE(headcount,1) END,
                updated_at = CURRENT_TIMESTAMP
            WHERE project_id=? AND deleted_at IS NULL""", (int(project_id),))
        count = cursor.rowcount
        conn.commit()
        return count
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def list_items(project_id, filters=None, limit=25, offset=0, order_by='display_order', order_dir='ASC'):
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        
        query = """
        SELECT 
            i.*, 
            p.legacy_code as plan_code, 
            p.description as plan_description,
            p.cycle as plan_cycle,
            p.unit as plan_unit,
            p.cycle_text as plan_cycle_text,
            p.opening_horizon as plan_opening_horizon,
            p.phase as plan_phase,
            CASE WHEN p.id IS NULL OR p.cycle IS NULL THEN NULL
                 WHEN p.phase BETWEEN 1 AND p.cycle
                 THEN CAST(p.cycle AS TEXT) || 'P' || CAST(p.phase AS TEXT)
                 ELSE CAST(p.cycle AS TEXT) || 'P?' END as plan_cycle_phase,
            p.reference_counter as plan_reference_counter,
            wt.name as team_name,
            wt.work_center as team_work_center
        FROM maintenance_items i
        LEFT JOIN plans p ON i.plan_id = p.id AND p.deleted_at IS NULL
        LEFT JOIN work_teams wt ON i.team_id = wt.id
        WHERE i.project_id = ? AND i.deleted_at IS NULL
        """
        params = [project_id]
        
        if filters:
            if filters.get('search'):
                term = f"%{filters['search']}%"
                query += " AND (i.legacy_identifier LIKE ? OR i.object_code LIKE ? OR i.description LIKE ? OR i.work_center LIKE ?)"
                params.extend([term, term, term, term])
            if filters.get('gpm'):
                query += " AND i.gpm = ?"
                params.append(filters['gpm'])
            if filters.get('work_center'):
                query += " AND i.work_center = ?"
                params.append(filters['work_center'])
            if filters.get('condition_code'):
                query += " AND i.condition_code = ?"
                params.append(filters['condition_code'])
            if filters.get('priority') is not None and filters.get('priority') != '':
                query += " AND i.priority = ?"
                params.append(int(filters['priority']))
            if filters.get('plan_id'):
                query += " AND i.plan_id = ?"
                params.append(int(filters['plan_id']))
            if filters.get('team_id'):
                query += " AND i.team_id = ?"
                params.append(int(filters['team_id']))
            if filters.get('status'):
                query += " AND i.status = ?"
                params.append(filters['status'])
            if filters.get('row_color'):
                query += " AND i.row_color = ?"
                params.append(str(filters['row_color']).strip().lower())
            if filters.get('without_plan') == 'true':
                query += " AND i.plan_id IS NULL"
            if filters.get('without_headcount') == 'true':
                query += " AND i.headcount IS NULL"
            if filters.get('duration_zero') == 'true':
                query += " AND i.duration_hours = 0"
            if filters.get('long_desc') == 'true':
                query += " AND i.character_count > 35"
                
        # Order by validation
        allowed_cols = ['display_order', 'legacy_identifier', 'object_code', 'gpm', 'work_center', 'condition_code', 'priority', 'duration_hours', 'headcount', 'hh', 'status', 'plan_code', 'plan_cycle_phase', 'team_name']
        if order_by not in allowed_cols:
            order_by = 'display_order'
        if order_dir.upper() not in ['ASC', 'DESC']:
            order_dir = 'ASC'
            
        # Cast legacy_identifier to numeric inside sort if it is numeric to avoid '10' before '2'
        if order_by == 'display_order':
            query += f" ORDER BY COALESCE(i.display_order, i.id) {order_dir}, i.id {order_dir}"
        elif order_by == 'legacy_identifier':
            query += f" ORDER BY CAST(i.legacy_identifier AS INTEGER) {order_dir}, i.legacy_identifier {order_dir}"
        elif order_by == 'plan_cycle_phase':
            query += f" ORDER BY p.cycle {order_dir}, p.phase {order_dir}, p.legacy_code {order_dir}"
        else:
            query += f" ORDER BY {order_by} {order_dir}"
            
        if limit is not None:
            query += " LIMIT ? OFFSET ?"
            params.extend([limit, offset])
            
        cursor.execute(query, params)
        return [_with_derived_workload(row) for row in cursor.fetchall()]
    finally:
        conn.close()


def reorder_item_identifiers(project_id):
    """Renumber active project items deterministically without breaking FKs.

    Uses a two-phase update because (project_id, legacy_identifier) is unique.
    Operations and long texts reference the immutable item PK, so their links
    remain valid. Returns the explicit old/new map for audit and UI feedback.
    """
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""SELECT id, legacy_identifier, validation_status, validation_issues_json
                          FROM maintenance_items WHERE project_id=? AND deleted_at IS NULL
                          ORDER BY CASE WHEN legacy_identifier GLOB '[0-9]*' THEN 0 ELSE 1 END,
                                   CAST(legacy_identifier AS INTEGER), legacy_identifier, id""", (project_id,))
        rows = cursor.fetchall()
        mapping = []
        for row in rows:
            cursor.execute("UPDATE maintenance_items SET legacy_identifier=? WHERE id=?",
                           (f'__REORDER_{project_id}_{row["id"]}__', row['id']))
        for sequence, row in enumerate(rows, 1):
            issues = []
            try: issues = json.loads(row['validation_issues_json'] or '[]')
            except (TypeError, ValueError, json.JSONDecodeError): pass
            issues = [issue for issue in issues if issue.get('code') != 'duplicate_identifier']
            status = ('ERROR' if any(x.get('severity') == 'ERROR' for x in issues)
                      else 'WARNING' if issues else 'OK')
            cursor.execute("""UPDATE maintenance_items SET legacy_identifier=?, validation_status=?,
                              validation_issues_json=?, updated_at=CURRENT_TIMESTAMP WHERE id=?""",
                           (str(sequence), status, json.dumps(issues, ensure_ascii=False), row['id']))
            mapping.append({'item_id': row['id'], 'old_identifier': row['legacy_identifier'],
                            'new_identifier': str(sequence)})
        conn.commit()
        log_action(project_id, 'ITEM_BULK', project_id, 'REORDER_IDENTIFIERS', None,
                   {'count': len(mapping), 'mapping': mapping})
        return mapping
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def count_items(project_id, filters=None):
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        
        query = """
        SELECT COUNT(*)
        FROM maintenance_items i
        LEFT JOIN plans p ON i.plan_id = p.id AND p.deleted_at IS NULL
        LEFT JOIN work_teams wt ON i.team_id = wt.id
        WHERE i.project_id = ? AND i.deleted_at IS NULL
        """
        params = [project_id]
        
        if filters:
            if filters.get('search'):
                term = f"%{filters['search']}%"
                query += " AND (i.legacy_identifier LIKE ? OR i.object_code LIKE ? OR i.description LIKE ? OR i.work_center LIKE ?)"
                params.extend([term, term, term, term])
            if filters.get('gpm'):
                query += " AND i.gpm = ?"
                params.append(filters['gpm'])
            if filters.get('work_center'):
                query += " AND i.work_center = ?"
                params.append(filters['work_center'])
            if filters.get('condition_code'):
                query += " AND i.condition_code = ?"
                params.append(filters['condition_code'])
            if filters.get('priority') is not None and filters.get('priority') != '':
                query += " AND i.priority = ?"
                params.append(int(filters['priority']))
            if filters.get('plan_id'):
                query += " AND i.plan_id = ?"
                params.append(int(filters['plan_id']))
            if filters.get('team_id'):
                query += " AND i.team_id = ?"
                params.append(int(filters['team_id']))
            if filters.get('status'):
                query += " AND i.status = ?"
                params.append(filters['status'])
            if filters.get('without_plan') == 'true':
                query += " AND i.plan_id IS NULL"
            if filters.get('without_headcount') == 'true':
                query += " AND i.headcount IS NULL"
            if filters.get('duration_zero') == 'true':
                query += " AND i.duration_hours = 0"
            if filters.get('long_desc') == 'true':
                query += " AND i.character_count > 35"
                
        cursor.execute(query, params)
        row = cursor.fetchone()
        return row[0] if row else 0
    finally:
        conn.close()

def get_item(item_id):
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
        SELECT i.*, p.legacy_code as plan_code, p.description as plan_description, wt.name as team_name
        FROM maintenance_items i
        LEFT JOIN plans p ON i.plan_id = p.id AND p.deleted_at IS NULL
        LEFT JOIN work_teams wt ON i.team_id = wt.id
        WHERE i.id = ? AND i.deleted_at IS NULL;
        """, (item_id,))
        return _with_derived_workload(cursor.fetchone())
    finally:
        conn.close()

def create_item(project_id, legacy_identifier, plan_id, object_type, object_code, gpm, work_center, condition_code, priority, legacy_start, description, duration_hours, headcount, notes=None, team_id=None, mec_headcount=0, mec_hours=0.0, ele_headcount=0, ele_hours=0.0, sol_headcount=0, sol_hours=0.0):
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        desc_clean = description.strip() if description else ""
        char_count = len(desc_clean)
        
        # Trade metrics calculation
        mec_hc = int(mec_headcount) if mec_headcount is not None and str(mec_headcount).strip() != '' else 0
        mec_h = float(mec_hours) if mec_hours is not None and str(mec_hours).strip() != '' else 0.0
        ele_hc = int(ele_headcount) if ele_headcount is not None and str(ele_headcount).strip() != '' else 0
        ele_h = float(ele_hours) if ele_hours is not None and str(ele_hours).strip() != '' else 0.0
        sol_hc = int(sol_headcount) if sol_headcount is not None and str(sol_headcount).strip() != '' else 0
        sol_h = float(sol_hours) if sol_hours is not None and str(sol_hours).strip() != '' else 0.0

        trade_hh = (mec_hc * mec_h) + (ele_hc * ele_h) + (sol_hc * sol_h)
        trade_hc = mec_hc + ele_hc + sol_hc

        if trade_hc > 0 or trade_hh > 0:
            ef_val = trade_hc
            dur_val = max(mec_h, ele_h, sol_h) if (duration_hours is None or float(duration_hours or 0) == 0.0) else float(duration_hours)
            hh_val = trade_hh
        else:
            ef_val = int(headcount) if headcount is not None and headcount != '' else None
            dur_val = float(duration_hours or 0.0)
            hh_val = dur_val * (ef_val if ef_val is not None else 1)

        t_id = int(team_id) if team_id is not None and team_id != '' else None
        p_id = int(plan_id) if plan_id is not None and plan_id != '' else None
        
        display_order = cursor.execute(
            "SELECT COALESCE(MAX(display_order),0)+1 FROM maintenance_items WHERE project_id=?",
            (project_id,)
        ).fetchone()[0]
        cursor.execute("""
        INSERT INTO maintenance_items (
            project_id, legacy_identifier, plan_id, team_id, object_type, object_code,
            gpm, work_center, condition_code, priority, legacy_start,
            description, character_count, duration_hours, headcount, hh,
            mec_headcount, mec_hours, ele_headcount, ele_hours, sol_headcount, sol_hours,
            order_type, status, notes, display_order
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'PM13', 'ACTIVE', ?, ?);
        """, (
            project_id, str(legacy_identifier).strip(), p_id, t_id, object_type.upper().strip(), str(object_code).strip(),
            str(gpm).strip(), str(work_center).strip(), str(condition_code).upper().strip(), int(priority), legacy_start,
            desc_clean, char_count, dur_val, ef_val, hh_val,
            mec_hc, mec_h, ele_hc, ele_h, sol_hc, sol_h,
            notes, display_order
        ))
        item_id = cursor.lastrowid
        conn.commit()
        log_action(project_id, 'ITEM', item_id, 'CREATE', None, {
            'legacy_identifier': legacy_identifier, 'plan_id': p_id, 'team_id': t_id, 'object_code': object_code, 'hh': hh_val
        })
        return item_id
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()

def clone_item(item_id, include_structure=False):
    """Clone an item and optionally its complete operation/long-text tree.

    The cloned operations are linked directly to the new item, so every operation
    and long text automatically exposes the new ``legacy_identifier`` through the
    normal item relationship. Nothing is left as a pending/unlinked copy.
    """
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        source = cursor.execute(
            "SELECT * FROM maintenance_items WHERE id=? AND deleted_at IS NULL", (item_id,)
        ).fetchone()
        if not source:
            raise ValueError("Item nao encontrado.")

        project_id = source['project_id']
        identifier = next_item_identifier(project_id, cursor)
        source_order = source['display_order'] if source['display_order'] is not None else source['id']
        clone_description = f"[copia] {source['description'] or ''}".strip()
        cursor.execute(
            "UPDATE maintenance_items SET display_order=display_order+1 WHERE project_id=? AND display_order>?",
            (project_id, source_order)
        )
        columns = (
            'project_id,legacy_identifier,plan_id,team_id,object_type,object_code,gpm,work_center,'
            'condition_code,priority,legacy_start,description,character_count,duration_hours,headcount,hh,'
            'mec_headcount,mec_hours,ele_headcount,ele_hours,sol_headcount,sol_hours,order_type,status,notes,display_order'
        )
        values = [
            project_id, identifier, source['plan_id'], source['team_id'], source['object_type'],
            source['object_code'], source['gpm'], source['work_center'], source['condition_code'],
            source['priority'], source['legacy_start'], clone_description, len(clone_description),
            source['duration_hours'], source['headcount'], source['hh'], source['mec_headcount'],
            source['mec_hours'], source['ele_headcount'], source['ele_hours'], source['sol_headcount'],
            source['sol_hours'], source['order_type'], source['status'], source['notes'], source_order + 1
        ]
        cursor.execute(
            f"INSERT INTO maintenance_items ({columns}) VALUES ({','.join(['?'] * len(values))})", values
        )
        new_id = cursor.lastrowid

        operations_created = 0
        long_texts_created = 0
        if include_structure:
            source_ops = cursor.execute(
                """SELECT * FROM item_operations WHERE item_id=?
                   ORDER BY COALESCE(display_order,id), id""", (item_id,)
            ).fetchall()
            next_op_order = cursor.execute(
                "SELECT COALESCE(MAX(display_order),0)+1 FROM item_operations WHERE project_id=?",
                (project_id,)
            ).fetchone()[0]
            next_text_order = cursor.execute(
                "SELECT COALESCE(MAX(display_order),0)+1 FROM operation_long_texts WHERE project_id=?",
                (project_id,)
            ).fetchone()[0]

            for src_op in source_ops:
                cursor.execute("""
                    INSERT INTO item_operations (
                        project_id,item_id,operation_code,suboperation_code,work_center,short_text,
                        unit,headcount,hours,status,validation_status,validation_issues_json,row_color,
                        display_order,pending_item_identifier
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,NULL)
                """, (
                    project_id, new_id, src_op['operation_code'], src_op['suboperation_code'],
                    src_op['work_center'], src_op['short_text'], src_op['unit'], src_op['headcount'],
                    src_op['hours'], src_op['status'], src_op['validation_status'],
                    src_op['validation_issues_json'], src_op['row_color'], next_op_order
                ))
                new_op_id = cursor.lastrowid
                next_op_order += 1
                operations_created += 1

                source_texts = cursor.execute(
                    """SELECT * FROM operation_long_texts WHERE operation_id=?
                       ORDER BY line_sequence, id""", (src_op['id'],)
                ).fetchall()
                for src_text in source_texts:
                    cursor.execute("""
                        INSERT INTO operation_long_texts (
                            project_id,operation_id,group_code,group_counter,line_sequence,text,
                            validation_status,validation_issues_json,row_color,display_order,pending_item_identifier,
                            structure_mode,structure_json,source_text_original
                        ) VALUES (?,?,?,?,?,?,?,?,?,?,NULL,?,?,?)
                    """, (
                        project_id, new_op_id, src_text['group_code'], src_text['group_counter'],
                        src_text['line_sequence'], src_text['text'], src_text['validation_status'],
                        src_text['validation_issues_json'], src_text['row_color'], next_text_order,
                        src_text['structure_mode'] if 'structure_mode' in src_text.keys() else 'FREE',
                        src_text['structure_json'] if 'structure_json' in src_text.keys() else None,
                        src_text['source_text_original'] if 'source_text_original' in src_text.keys() else None
                    ))
                    next_text_order += 1
                    long_texts_created += 1

        conn.commit()
        return {
            'id': new_id,
            'legacy_identifier': identifier,
            'include_structure': bool(include_structure),
            'operations_created': operations_created,
            'long_texts_created': long_texts_created,
        }
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def clone_item_shallow(item_id):
    """Backward-compatible helper for callers that want only the item fields."""
    return clone_item(item_id, include_structure=False)

def set_item_row_color(item_id, row_color):
    allowed = {'red', 'green', 'light_blue', 'dark_blue', 'purple', 'pink', 'orange', 'yellow', 'black', ''}
    color = str(row_color or '').strip().lower()
    if color not in allowed:
        raise ValueError("Cor de marcador invalida.")
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("UPDATE maintenance_items SET row_color=?, updated_at=CURRENT_TIMESTAMP WHERE id=? AND deleted_at IS NULL", (color or None, item_id))
        if cursor.rowcount == 0:
            raise ValueError("Item nao encontrado.")
        conn.commit()
        return {'id': item_id, 'row_color': color}
    finally:
        conn.close()

def set_entity_row_color(entity, entity_id, row_color):
    tables = {'plans': 'plans', 'operations': 'item_operations', 'long-texts': 'operation_long_texts'}
    table = tables.get(entity)
    if not table:
        raise ValueError("Tipo de registro invalido.")
    allowed = {'red', 'green', 'light_blue', 'dark_blue', 'purple', 'pink', 'orange', 'yellow', 'black', ''}
    color = str(row_color or '').strip().lower()
    if color not in allowed:
        raise ValueError("Cor de marcador invalida.")
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(f"UPDATE {table} SET row_color=?, updated_at=CURRENT_TIMESTAMP WHERE id=?", (color or None, entity_id))
        if cursor.rowcount == 0:
            raise ValueError("Registro nao encontrado.")
        conn.commit()
        return {'id': entity_id, 'row_color': color}
    finally:
        conn.close()

def clone_operation_pending(operation_id):
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        src = cur.execute("SELECT * FROM item_operations WHERE id=?", (operation_id,)).fetchone()
        if not src:
            raise ValueError("Operacao nao encontrada.")
        position = src['display_order'] if src['display_order'] is not None else src['id']
        cur.execute("UPDATE item_operations SET display_order=display_order+1 WHERE project_id=? AND display_order>?", (src['project_id'], position))
        code = f"COPIA{operation_id}"
        issues = '[{"code":"copy_requires_item_review","severity":"ERROR","message":"Copia pendente: altere [COPIA] 1111 e atrele ao item correto."}]'
        cur.execute("""INSERT INTO item_operations
            (project_id,item_id,operation_code,suboperation_code,work_center,short_text,unit,headcount,hours,status,
             validation_status,validation_issues_json,pending_item_identifier,display_order)
            VALUES (?,?,?,?,?,?,?,?,?,?,'ERROR',?,'[COPIA] 1111',?)""",
            (src['project_id'],src['item_id'],code,src['suboperation_code'],src['work_center'],
             f"[COPIA] {src['short_text']}",src['unit'],src['headcount'],src['hours'],src['status'],issues,position+1))
        new_id = cur.lastrowid
        conn.commit()
        return {'id': new_id, 'pending_item_identifier': '[COPIA] 1111'}
    except Exception:
        conn.rollback(); raise
    finally:
        conn.close()

def clone_long_text_pending(text_id):
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        src = cur.execute("SELECT * FROM operation_long_texts WHERE id=?", (text_id,)).fetchone()
        if not src:
            raise ValueError("Texto longo nao encontrado.")
        position = src['display_order'] if src['display_order'] is not None else src['id']
        cur.execute("UPDATE operation_long_texts SET display_order=display_order+1 WHERE project_id=? AND display_order>?", (src['project_id'], position))
        next_sequence = cur.execute(
            "SELECT COALESCE(MAX(line_sequence),0)+1 FROM operation_long_texts WHERE operation_id=?",
            (src['operation_id'],)
        ).fetchone()[0]
        issues = '[{"code":"copy_requires_item_review","severity":"ERROR","message":"Copia pendente: altere [COPIA] 1111 e atrele ao item/operacao correto."}]'
        cur.execute("""INSERT INTO operation_long_texts
            (project_id,operation_id,group_code,group_counter,line_sequence,text,validation_status,
             validation_issues_json,pending_item_identifier,display_order,structure_mode,structure_json,source_text_original)
            VALUES (?,?,?,?,?,?,'ERROR',?,'[COPIA] 1111',?,?,?,?)""",
            (src['project_id'],src['operation_id'],src['group_code'],src['group_counter'],next_sequence,
             f"[COPIA] {src['text']}",issues,position+1,
             src['structure_mode'] if 'structure_mode' in src.keys() else 'FREE',
             src['structure_json'] if 'structure_json' in src.keys() else None,
             src['source_text_original'] if 'source_text_original' in src.keys() else None))
        new_id = cur.lastrowid
        conn.commit()
        return {'id': new_id, 'pending_item_identifier': '[COPIA] 1111'}
    except Exception:
        conn.rollback(); raise
    finally:
        conn.close()

def update_item(item_id, legacy_identifier, plan_id, object_type, object_code, gpm, work_center, condition_code, priority, legacy_start, description, duration_hours, headcount, status='ACTIVE', notes=None, team_id=None, mec_headcount=0, mec_hours=0.0, ele_headcount=0, ele_hours=0.0, sol_headcount=0, sol_hours=0.0):
    old_data = get_item(item_id)
    if not old_data:
        raise ValueError("Item não encontrado.")
        
    project_id = old_data['project_id']
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        desc_clean = description.strip() if description else ""
        char_count = len(desc_clean)
        
        # Trade metrics calculation
        mec_hc = int(mec_headcount) if mec_headcount is not None and str(mec_headcount).strip() != '' else 0
        mec_h = float(mec_hours) if mec_hours is not None and str(mec_hours).strip() != '' else 0.0
        ele_hc = int(ele_headcount) if ele_headcount is not None and str(ele_headcount).strip() != '' else 0
        ele_h = float(ele_hours) if ele_hours is not None and str(ele_hours).strip() != '' else 0.0
        sol_hc = int(sol_headcount) if sol_headcount is not None and str(sol_headcount).strip() != '' else 0
        sol_h = float(sol_hours) if sol_hours is not None and str(sol_hours).strip() != '' else 0.0

        trade_hh = (mec_hc * mec_h) + (ele_hc * ele_h) + (sol_hc * sol_h)
        trade_hc = mec_hc + ele_hc + sol_hc

        if trade_hc > 0 or trade_hh > 0:
            ef_val = trade_hc
            dur_val = max(mec_h, ele_h, sol_h) if (duration_hours is None or float(duration_hours or 0) == 0.0) else float(duration_hours)
            hh_val = trade_hh
        else:
            ef_val = int(headcount) if headcount is not None and headcount != '' else None
            dur_val = float(duration_hours or 0.0)
            hh_val = dur_val * (ef_val if ef_val is not None else 1)

        t_id = int(team_id) if team_id is not None and team_id != '' else None
        p_id = int(plan_id) if plan_id is not None and plan_id != '' else None
        
        cursor.execute("""
        UPDATE maintenance_items
        SET legacy_identifier = ?, plan_id = ?, team_id = ?, object_type = ?, object_code = ?, gpm = ?,
            work_center = ?, condition_code = ?, priority = ?, legacy_start = ?,
            description = ?, character_count = ?, duration_hours = ?, headcount = ?, hh = ?,
            mec_headcount = ?, mec_hours = ?, ele_headcount = ?, ele_hours = ?, sol_headcount = ?, sol_hours = ?,
            status = ?, notes = ?, updated_at = CURRENT_TIMESTAMP
        WHERE id = ?;
        """, (
            str(legacy_identifier).strip(), p_id, t_id, object_type.upper().strip(), str(object_code).strip(), str(gpm).strip(),
            str(work_center).strip(), str(condition_code).upper().strip(), int(priority), legacy_start,
            desc_clean, char_count, dur_val, ef_val, hh_val,
            mec_hc, mec_h, ele_hc, ele_h, sol_hc, sol_h,
            status, notes, item_id
        ))
        # Keep the operation editor and both SAP exports consistent with the
        # discipline workload entered on the Item screen.
        principal = cursor.execute("""SELECT id FROM item_operations WHERE item_id=? AND operation_code='0010'
            AND TRIM(COALESCE(suboperation_code,''))='' ORDER BY id LIMIT 1""", (item_id,)).fetchone()
        main_hc, main_hours = (ele_hc, ele_h) if (ele_hc or ele_h) else (mec_hc, mec_h)
        if principal:
            cursor.execute("UPDATE item_operations SET headcount=?,hours=?,unit='H',updated_at=CURRENT_TIMESTAMP WHERE id=?", (main_hc, main_hours, principal['id']))
        else:
            cursor.execute("""INSERT INTO item_operations(project_id,item_id,operation_code,suboperation_code,work_center,short_text,unit,headcount,hours,status)
                VALUES(?,?,?,'',?,?, 'H',?,?,'ACTIVE')""", (project_id,item_id,'0010',str(work_center).strip(),desc_clean,main_hc,main_hours))
        welding = cursor.execute("""SELECT id FROM item_operations WHERE item_id=? AND operation_code='0010'
            AND TRIM(COALESCE(suboperation_code,''))='0010' ORDER BY id LIMIT 1""", (item_id,)).fetchone()
        if welding:
            welding_id=welding['id'];cursor.execute("UPDATE item_operations SET headcount=?,hours=?,unit='H',updated_at=CURRENT_TIMESTAMP WHERE id=?", (sol_hc, sol_h, welding_id))
        else:
            cursor.execute("""INSERT INTO item_operations(project_id,item_id,operation_code,suboperation_code,work_center,short_text,unit,headcount,hours,status)
                VALUES(?,?,?,'0010',?,?,'H',?,?,'ACTIVE')""", (project_id,item_id,'0010',str(work_center).strip(),'APOIO DE SOLDA',sol_hc,sol_h));welding_id=cursor.lastrowid
        welding_text = f'{sol_hc} MECÂNICOS {sol_h:g} HORAS' if (sol_hc or sol_h) else 'NÃO SE APLICA'
        text_row=cursor.execute("SELECT id FROM operation_long_texts WHERE operation_id=? ORDER BY line_sequence,id LIMIT 1",(welding_id,)).fetchone()
        if text_row:cursor.execute("UPDATE operation_long_texts SET text=?,structure_mode='FREE',structure_json=NULL,updated_at=CURRENT_TIMESTAMP WHERE id=?",(welding_text,text_row['id']))
        else:cursor.execute("INSERT INTO operation_long_texts(project_id,operation_id,line_sequence,text,structure_mode) VALUES(?,?,?,?,?)",(project_id,welding_id,1,welding_text,'FREE'))
        conn.commit()
        log_action(project_id, 'ITEM', item_id, 'UPDATE', old_data, {
            'legacy_identifier': legacy_identifier, 'plan_id': p_id, 'team_id': t_id, 'hh': hh_val, 'status': status
        })
        return True
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()

def delete_item(item_id, cascade_related=False):
    old_data = get_item(item_id)
    if not old_data:
        return False
        
    project_id = old_data['project_id']
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        now = datetime.datetime.now().isoformat()
        operation_ids = [row['id'] for row in cursor.execute(
            "SELECT id FROM item_operations WHERE item_id=?", (item_id,)).fetchall()]
        if cascade_related:
            if operation_ids:
                placeholders = ','.join('?' for _ in operation_ids)
                cursor.execute(f"DELETE FROM operation_long_texts WHERE operation_id IN ({placeholders})", operation_ids)
            cursor.execute("DELETE FROM item_operations WHERE item_id=?", (item_id,))
        else:
            orphan_op_issue = json.dumps([{'code': 'operation_without_item', 'severity': 'ERROR',
                'message': f'Operacao sem item existente (item excluido: {old_data["legacy_identifier"]}).'}], ensure_ascii=False)
            cursor.execute("""UPDATE item_operations SET validation_status='ERROR',validation_issues_json=?,
                updated_at=CURRENT_TIMESTAMP WHERE item_id=?""", (orphan_op_issue, item_id))
            if operation_ids:
                placeholders = ','.join('?' for _ in operation_ids)
                orphan_text_issue = json.dumps([{'code': 'long_text_without_item', 'severity': 'ERROR',
                    'message': f'Texto longo sem ID de item existente ({old_data["legacy_identifier"]}).'}], ensure_ascii=False)
                cursor.execute(f"""UPDATE operation_long_texts SET validation_status='ERROR',validation_issues_json=?,
                    updated_at=CURRENT_TIMESTAMP WHERE operation_id IN ({placeholders})""",
                    [orphan_text_issue] + operation_ids)
        cursor.execute("UPDATE maintenance_items SET deleted_at = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?;", (now, item_id))
        conn.commit()
        log_action(project_id, 'ITEM', item_id, 'DELETE', old_data, {
            'cascade_related': bool(cascade_related), 'operations_affected': len(operation_ids)})
        return True
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()


# ==========================================
# BULK ACTIONS MODEL
# ==========================================

def _bulk_update_table(project_id, record_ids, updates, table, allowed_fields):
    if not record_ids or not updates:
        return 0
    invalid = set(updates) - set(allowed_fields)
    if invalid:
        raise ValueError(f"Campos não permitidos para edição em massa: {', '.join(sorted(invalid))}.")
    ids = [int(record_id) for record_id in record_ids]
    placeholders = ','.join('?' for _ in ids)
    set_parts, values = [], []
    for field, converter in allowed_fields.items():
        if field not in updates:
            continue
        value = updates[field]
        set_parts.append(f'{field}=?')
        values.append(converter(value) if value is not None else None)
    if not set_parts:
        return 0
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            f"UPDATE {table} SET {', '.join(set_parts)}, updated_at=CURRENT_TIMESTAMP "
            f"WHERE project_id=? AND id IN ({placeholders})",
            values + [int(project_id)] + ids)
        count = cursor.rowcount
        conn.commit()
        return count
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def bulk_update_operations(project_id, operation_ids, updates):
    return _bulk_update_table(project_id, operation_ids, updates, 'item_operations', {
        'work_center': lambda value: str(value).strip(),
        'short_text': lambda value: str(value).strip()[:40],
        'unit': lambda value: str(value).strip() or 'H',
        'headcount': lambda value: int(value),
        'hours': lambda value: float(value),
    })


def bulk_update_long_texts(project_id, text_ids, updates):
    return _bulk_update_table(project_id, text_ids, updates, 'operation_long_texts', {
        'group_code': lambda value: str(value).strip(),
        'group_counter': lambda value: str(value).strip(),
        'text': lambda value: str(value),
    })

def bulk_update_items(project_id, item_ids, updates):
    """Updates fields of multiple items in bulk.
    Updates can contain the general fields and ELE/MEC/SOL headcount and hours.
    """
    if not item_ids:
        return 0
        
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        
        # Fetch previous data for audit
        placeholders = ",".join("?" for _ in item_ids)
        cursor.execute(
            f"SELECT * FROM maintenance_items WHERE project_id = ? AND id IN ({placeholders});",
            (project_id, *item_ids),
        )
        old_items = to_dict_list(cursor.fetchall())
        
        # Build SQL dynamically based on update fields
        set_clauses = []
        params = []
        
        if 'gpm' in updates:
            set_clauses.append("gpm = ?")
            params.append(str(updates['gpm']).strip())
        if 'work_center' in updates:
            set_clauses.append("work_center = ?")
            params.append(str(updates['work_center']).strip())
        if 'condition_code' in updates:
            set_clauses.append("condition_code = ?")
            params.append(str(updates['condition_code']).upper().strip())
        if 'priority' in updates:
            set_clauses.append("priority = ?")
            params.append(int(updates['priority']))
        if 'headcount' in updates:
            ef_val = int(updates['headcount']) if updates['headcount'] is not None and updates['headcount'] != '' else None
            set_clauses.append("headcount = ?")
            params.append(ef_val)
            # Also update HH (hh = duration_hours * headcount).
            set_clauses.append("hh = duration_hours * COALESCE(?, 1)")
            params.append(ef_val)
        specialty_changed = False
        for field in ('ele_headcount', 'mec_headcount', 'sol_headcount'):
            if field in updates:
                value = int(updates[field])
                if value < 0:
                    raise ValueError(f'{field} não pode ser negativo.')
                set_clauses.append(f"{field} = ?")
                params.append(value)
                specialty_changed = True
                # If only the specialty workforce was supplied, its duration is
                # the duration already registered for each individual item.
                hours_field = field.replace('_headcount', '_hours')
                if hours_field not in updates:
                    set_clauses.append(
                        f"{hours_field} = CASE WHEN ? > 0 THEN duration_hours ELSE 0 END"
                    )
                    params.append(value)
        for field in ('ele_hours', 'mec_hours', 'sol_hours'):
            if field in updates:
                value = float(updates[field])
                if value < 0:
                    raise ValueError(f'{field} não pode ser negativo.')
                set_clauses.append(f"{field} = ?")
                params.append(value)
                specialty_changed = True
        if 'team_id' in updates:
            t_val = int(updates['team_id']) if updates['team_id'] is not None and updates['team_id'] != '' else None
            set_clauses.append("team_id = ?")
            params.append(t_val)
        if 'status' in updates:
            set_clauses.append("status = ?")
            params.append(updates['status'])
            
        if not set_clauses:
            return 0
            
        set_clauses.append("updated_at = CURRENT_TIMESTAMP")
        
        sql = f"UPDATE maintenance_items SET {', '.join(set_clauses)} WHERE project_id = ? AND id IN ({placeholders});"
        params.append(project_id)
        params.extend(item_ids)
        
        cursor.execute(sql, params)
        count = cursor.rowcount

        if specialty_changed:
            # Keep legacy/general totals synchronized with the specialty fields.
            # This second statement sees the values persisted by the first one.
            cursor.execute(
                f"""UPDATE maintenance_items
                    SET headcount = COALESCE(ele_headcount, 0)
                                  + COALESCE(mec_headcount, 0)
                                  + COALESCE(sol_headcount, 0),
                        hh = COALESCE(ele_headcount, 0) * COALESCE(ele_hours, 0)
                           + COALESCE(mec_headcount, 0) * COALESCE(mec_hours, 0)
                           + COALESCE(sol_headcount, 0) * COALESCE(sol_hours, 0)
                    WHERE project_id = ? AND id IN ({placeholders});""",
                (project_id, *item_ids),
            )
        conn.commit()
        
        log_action(project_id, 'ITEM_BULK', project_id, 'BULK_UPDATE', {
            'item_ids': item_ids, 'fields': list(updates.keys()), 'previous_states': old_items
        }, updates)
        
        return count
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()

def bulk_update_plans(project_id, plan_ids, updates):
    """Updates fields of multiple plans in bulk.
    Updates can contain: cycle, unit, cycle_text, opening_horizon, reference_counter, phase, status.
    """
    if not plan_ids:
        return 0
        
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        
        # Fetch previous data for audit
        placeholders = ",".join("?" for _ in plan_ids)
        cursor.execute(
            f"SELECT * FROM plans WHERE project_id = ? AND id IN ({placeholders});",
            (project_id, *plan_ids),
        )
        old_plans = to_dict_list(cursor.fetchall())
        
        set_clauses = []
        params = []
        
        if 'cycle' in updates and updates['cycle'] is not None and str(updates['cycle']).strip() != '':
            set_clauses.append("cycle = ?")
            params.append(int(updates['cycle']))
        if 'unit' in updates and updates['unit'] is not None:
            set_clauses.append("unit = ?")
            params.append(str(updates['unit']).strip())
        if 'cycle_text' in updates and updates['cycle_text'] is not None:
            set_clauses.append("cycle_text = ?")
            params.append(str(updates['cycle_text']).strip())
        if 'opening_horizon' in updates and updates['opening_horizon'] is not None and str(updates['opening_horizon']).strip() != '':
            set_clauses.append("opening_horizon = ?")
            params.append(float(updates['opening_horizon']))
        if 'reference_counter' in updates:
            rc_val = int(updates['reference_counter']) if updates['reference_counter'] is not None and str(updates['reference_counter']).strip() != '' else None
            set_clauses.append("reference_counter = ?")
            params.append(rc_val)
        if 'phase' in updates:
            ph_val = int(updates['phase']) if updates['phase'] is not None and str(updates['phase']).strip() != '' else 0
            set_clauses.append("phase = ?")
            params.append(ph_val)
        if 'status' in updates and updates['status']:
            set_clauses.append("status = ?")
            params.append(updates['status'])
            
        if not set_clauses:
            return 0
            
        set_clauses.append("updated_at = CURRENT_TIMESTAMP")
        
        sql = f"UPDATE plans SET {', '.join(set_clauses)} WHERE project_id = ? AND id IN ({placeholders});"
        params.append(project_id)
        params.extend(plan_ids)
        
        cursor.execute(sql, params)
        conn.commit()
        
        log_action(project_id, 'PLAN_BULK', project_id, 'BULK_UPDATE', {
            'plan_ids': plan_ids, 'fields': list(updates.keys()), 'previous_states': old_plans
        }, updates)
        
        return cursor.rowcount
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()

def bulk_assign_plan(project_id, item_ids, plan_id):
    """Assigns plan_id to multiple items in bulk."""
    if not item_ids:
        return 0
        
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        
        # Verify plan exists and belongs to the same project
        if plan_id:
            cursor.execute("SELECT id FROM plans WHERE id = ? AND project_id = ? AND deleted_at IS NULL;", (plan_id, project_id))
            if not cursor.fetchone():
                raise ValueError("Plano de destino não encontrado no projeto.")
                
        placeholders = ",".join("?" for _ in item_ids)
        cursor.execute(
            f"SELECT id, plan_id FROM maintenance_items WHERE project_id = ? AND id IN ({placeholders});",
            (project_id, *item_ids),
        )
        old_states = to_dict_list(cursor.fetchall())
        
        cursor.execute(f"""
        UPDATE maintenance_items 
        SET plan_id = ?, updated_at = CURRENT_TIMESTAMP 
        WHERE project_id = ? AND id IN ({placeholders});
        """, (plan_id, project_id, *item_ids))
        
        conn.commit()
        log_action(project_id, 'ITEM_BULK', project_id, 'BULK_ASSIGN_PLAN', {
            'plan_id_assigned': plan_id, 'item_ids': item_ids, 'previous_states': old_states
        }, None)
        
        return cursor.rowcount
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()


# ==========================================
# CATALOG & SHIFTS MODELS
# ==========================================

def list_cycle_catalog(project_id):
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM cycle_catalog WHERE project_id = ? AND active = 1 ORDER BY cycle ASC;", (project_id,))
        return to_dict_list(cursor.fetchall())
    finally:
        conn.close()

def update_cycle_catalog(project_id, cycles_list):
    """Rewrites the cycle catalog for a project."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM cycle_catalog WHERE project_id = ?;", (project_id,))
        for c in cycles_list:
            cursor.execute("""
            INSERT INTO cycle_catalog (project_id, cycle, unit, cycle_text, opening_horizon, active)
            VALUES (?, ?, ?, ?, ?, 1);
            """, (project_id, int(c['cycle']), c['unit'].strip(), c['cycle_text'].strip(), float(c['opening_horizon'])))
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()

def list_shifts(project_id):
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM shifts WHERE project_id = ? AND active = 1 ORDER BY sequence ASC;", (project_id,))
        return to_dict_list(cursor.fetchall())
    finally:
        conn.close()

def update_shifts(project_id, shifts_list):
    """Rewrites shifts for a project."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM shifts WHERE project_id = ?;", (project_id,))
        for idx, s in enumerate(shifts_list, start=1):
            cursor.execute("""
            INSERT INTO shifts (project_id, name, sequence, duration_hours, active)
            VALUES (?, ?, ?, ?, 1);
            """, (project_id, s['name'].strip(), idx, float(s['duration_hours'])))
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()


# ==========================================
# HISTORY & AUDIT MODELS
# ==========================================

def get_audit_log(project_id, limit=100, offset=0):
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
        SELECT * FROM audit_log 
        WHERE project_id = ? 
        ORDER BY created_at DESC 
        LIMIT ? OFFSET ?;
        """, (project_id, limit, offset))
        return to_dict_list(cursor.fetchall())
    finally:
        conn.close()

def get_imports_history(project_id):
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM imports WHERE project_id = ? ORDER BY created_at DESC;", (project_id,))
        return to_dict_list(cursor.fetchall())
    finally:
        conn.close()

def get_import_errors(import_id):
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM import_errors WHERE import_id = ? ORDER BY id ASC;", (import_id,))
        return to_dict_list(cursor.fetchall())
    finally:
        conn.close()

# ==========================================
# WORK TEAMS (EQUIPES DE TRABALHO)
# ==========================================

def list_teams(project_id):
    """Returns all work teams registered for a project."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM work_teams 
            WHERE project_id = ? 
            ORDER BY name ASC;
        """, (project_id,))
        return to_dict_list(cursor.fetchall())
    finally:
        conn.close()

def get_team(team_id):
    """Fetches a single work team by ID."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM work_teams WHERE id = ?;", (team_id,))
        row = cursor.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()

def create_team(project_id, data):
    """Creates a new work team entry."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO work_teams (
                project_id, name, work_center, num_shifts, shift_hours, 
                headcount_per_shift, tool_time_percent, stop_days, notes, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP);
        """, (
            project_id,
            data.get('name', '').strip(),
            data.get('work_center', '').strip() or None,
            int(data.get('num_shifts', 1)),
            float(data.get('shift_hours', 9.0)),
            int(data.get('headcount_per_shift', 1)),
            float(data.get('tool_time_percent', 90.0)),
            int(data.get('stop_days', 1)),
            data.get('notes', '').strip() or None
        ))
        team_id = cursor.lastrowid
        conn.commit()
        return get_team(team_id)
    finally:
        conn.close()

def update_team(team_id, data):
    """Updates an existing work team entry."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE work_teams 
            SET name = ?,
                work_center = ?,
                num_shifts = ?,
                shift_hours = ?,
                headcount_per_shift = ?,
                tool_time_percent = ?,
                stop_days = ?,
                notes = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?;
        """, (
            data.get('name', '').strip(),
            data.get('work_center', '').strip() or None,
            int(data.get('num_shifts', 1)),
            float(data.get('shift_hours', 9.0)),
            int(data.get('headcount_per_shift', 1)),
            float(data.get('tool_time_percent', 90.0)),
            int(data.get('stop_days', 1)),
            data.get('notes', '').strip() or None,
            team_id
        ))
        conn.commit()
        return get_team(team_id)
    finally:
        conn.close()

def delete_team(team_id):
    """Deletes a work team entry."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM work_teams WHERE id = ?;", (team_id,))
        conn.commit()
        return True
    finally:
        conn.close()

# =========================================================================
# PROJECT CAPACITIES PERSISTENCE
# =========================================================================

def get_project_capacities(project_id):
    """Returns saved discipline capacities (ele_capacity, mec_capacity, sol_capacity) for a project."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT ele_capacity, mec_capacity, sol_capacity FROM projects WHERE id = ?;", (project_id,))
        row = cursor.fetchone()
        if not row:
            return {'ele': None, 'mec': None, 'sol': None}
        return {
            'ele': row['ele_capacity'],
            'mec': row['mec_capacity'],
            'sol': row['sol_capacity']
        }
    finally:
        conn.close()

def update_project_capacities(project_id, ele, mec, sol):
    """Updates saved discipline capacities for a project."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE projects
            SET ele_capacity = ?,
                mec_capacity = ?,
                sol_capacity = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?;
        """, (
            float(ele) if ele is not None and str(ele).strip() != '' else None,
            float(mec) if mec is not None and str(mec).strip() != '' else None,
            float(sol) if sol is not None and str(sol).strip() != '' else None,
            project_id
        ))
        conn.commit()
        return get_project_capacities(project_id)
    finally:
        conn.close()

# =========================================================================
# PROJECT WORK-CAPACITY SETTINGS
# =========================================================================

def get_project_work_capacity_settings(project_id):
    """Single source of truth for productive hours per person in balance."""
    conn = get_db_connection()
    try:
        row = conn.execute(
            "SELECT hours_per_person, tool_time_percent FROM projects WHERE id=? AND deleted_at IS NULL",
            (project_id,)
        ).fetchone()
        if not row:
            raise ValueError("Projeto não encontrado.")
        hours = float(row['hours_per_person'] if row['hours_per_person'] is not None else 9.1)
        tool = float(row['tool_time_percent'] if row['tool_time_percent'] is not None else 100.0)
        if hours <= 0:
            hours = 9.1
        tool = min(100.0, max(0.0, tool))
        return {
            'hours_per_person': hours,
            'tool_time_percent': tool,
            'productive_hours_per_person': hours * (tool / 100.0),
        }
    finally:
        conn.close()


def update_project_work_capacity_settings(project_id, hours_per_person, tool_time_percent):
    try:
        hours = float(hours_per_person)
        tool = float(tool_time_percent)
    except (TypeError, ValueError):
        raise ValueError("Horas por pessoa e Tool Time devem ser numéricos.")
    if hours <= 0 or hours > 24:
        raise ValueError("Horas trabalhadas por pessoa deve ser maior que 0 e no máximo 24.")
    if tool <= 0 or tool > 100:
        raise ValueError("Tool Time deve ser maior que 0% e no máximo 100%.")
    conn = get_db_connection()
    try:
        cur = conn.execute(
            """UPDATE projects SET hours_per_person=?, tool_time_percent=?, updated_at=CURRENT_TIMESTAMP
               WHERE id=? AND deleted_at IS NULL""",
            (hours, tool, project_id)
        )
        if cur.rowcount == 0:
            raise ValueError("Projeto não encontrado.")
        conn.commit()
    finally:
        conn.close()
    return get_project_work_capacity_settings(project_id)


# =========================================================================
# STANDARD LONG TEXTS LIBRARY (Modelos Padrão de Procedimentos)
# =========================================================================

def get_standard_long_texts():
    """Lists all global standard long text templates."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM standard_long_texts ORDER BY category, title;")
        return [dict(r) for r in cursor.fetchall()]
    finally:
        conn.close()

def create_standard_long_text(title, category, text, structure_mode=None, structure_json=None):
    """Creates a full long-text template, preserving hierarchy when available."""
    prepared = prepare_for_save(text, structure_mode, structure_json, text)
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO standard_long_texts
                (title, category, text, structure_mode, structure_json, source_text_original)
            VALUES (?, ?, ?, ?, ?, ?);
        """, (title.strip(), (category or 'GERAL').strip(), prepared['text'],
              prepared['structure_mode'], prepared['structure_json'], prepared['source_text_original']))
        conn.commit()
        new_id = cursor.lastrowid
        cursor.execute("SELECT * FROM standard_long_texts WHERE id = ?;", (new_id,))
        return dict(cursor.fetchone())
    finally:
        conn.close()

def update_standard_long_text(text_id, title, category, text, structure_mode=None, structure_json=None):
    """Updates an existing full long-text template."""
    prepared = prepare_for_save(text, structure_mode, structure_json, text)
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE standard_long_texts
            SET title = ?, category = ?, text = ?, structure_mode=?, structure_json=?,
                source_text_original=?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?;
        """, (title.strip(), (category or 'GERAL').strip(), prepared['text'],
              prepared['structure_mode'], prepared['structure_json'], prepared['source_text_original'], text_id))
        conn.commit()
        cursor.execute("SELECT * FROM standard_long_texts WHERE id = ?;", (text_id,))
        row = cursor.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()

def delete_standard_long_text(text_id):
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM standard_long_texts WHERE id = ?;", (text_id,))
        conn.commit()
        return True
    finally:
        conn.close()

# =========================================================================
# STANDARD LONG-TEXT BLOCKS LIBRARY
# =========================================================================

def get_standard_long_text_blocks():
    conn = get_db_connection()
    try:
        rows = conn.execute("SELECT * FROM standard_long_text_blocks ORDER BY category,title,id").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()

def create_standard_long_text_block(title, category, structure_json, tags=''):
    nodes = normalize_nodes(structure_json)
    if not nodes or not any(n['type'] == 'topic' for n in nodes):
        raise ValueError('O bloco padrão precisa possuir pelo menos um tópico estruturado.')
    # Store root-relative numbering. render_nodes materializes 1 / 1.1 / ... for preview only.
    text = render_nodes(nodes)
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute("""INSERT INTO standard_long_text_blocks
            (title,category,tags,structure_json,text) VALUES(?,?,?,?,?)""",
            (str(title or '').strip(), str(category or 'GERAL').strip(), str(tags or '').strip(),
             json.dumps(nodes, ensure_ascii=False), text))
        if not str(title or '').strip():
            raise ValueError('Informe um título para o bloco padrão.')
        new_id = cur.lastrowid
        conn.commit()
        row = cur.execute("SELECT * FROM standard_long_text_blocks WHERE id=?", (new_id,)).fetchone()
        return dict(row)
    finally:
        conn.close()

def update_standard_long_text_block(block_id, title, category, structure_json, tags=''):
    nodes = normalize_nodes(structure_json)
    if not nodes:
        raise ValueError('Bloco vazio.')
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute("""UPDATE standard_long_text_blocks SET title=?,category=?,tags=?,structure_json=?,text=?,
                       updated_at=CURRENT_TIMESTAMP WHERE id=?""",
                    (str(title or '').strip(), str(category or 'GERAL').strip(), str(tags or '').strip(),
                     json.dumps(nodes, ensure_ascii=False), render_nodes(nodes), int(block_id)))
        conn.commit()
        row = cur.execute("SELECT * FROM standard_long_text_blocks WHERE id=?", (int(block_id),)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()

def delete_standard_long_text_block(block_id):
    conn = get_db_connection()
    try:
        conn.execute("DELETE FROM standard_long_text_blocks WHERE id=?", (int(block_id),))
        conn.commit()
        return True
    finally:
        conn.close()

# =========================================================================
# STANDARD ITEMS LIBRARY (Modelos Padrão de Equipamentos)
# =========================================================================

def get_standard_items():
    """Lists all global standard item templates with operation count."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT s.*, 
                   COUNT(o.id) as operations_count
            FROM standard_items s
            LEFT JOIN standard_item_operations o ON o.standard_item_id = s.id
            GROUP BY s.id
            ORDER BY s.category, s.title;
        """)
        return [dict(r) for r in cursor.fetchall()]
    finally:
        conn.close()

def get_standard_item_detail(standard_id):
    """Returns full details of a standard item including its operations and long texts."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM standard_items WHERE id = ?;", (standard_id,))
        item_row = cursor.fetchone()
        if not item_row:
            return None
        
        item_dict = dict(item_row)
        item_dict['equipment_code'] = item_dict.get('object_code', '')
        cursor.execute("SELECT * FROM standard_item_operations WHERE standard_item_id = ? ORDER BY operation_code;", (standard_id,))
        ops = [dict(r) for r in cursor.fetchall()]
        
        for op in ops:
            cursor.execute("SELECT * FROM standard_operation_long_texts WHERE standard_operation_id = ?;", (op['id'],))
            op['long_texts'] = [dict(r) for r in cursor.fetchall()]
            if op['long_texts']:
                op['long_text'] = op['long_texts'][0].get('text', '')
                op['long_text_structure_mode'] = op['long_texts'][0].get('structure_mode', 'FREE')
                op['long_text_structure_json'] = op['long_texts'][0].get('structure_json', '')
                op['long_text_source_original'] = op['long_texts'][0].get('source_text_original', '')
            else:
                op['long_text'] = op.get('long_text', '')
            
        item_dict['operations'] = ops
        return item_dict
    finally:
        conn.close()

def create_standard_item(data):
    """Creates a standard item template with operations and long texts."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO standard_items (
                title, category, object_type, gpm, work_center, condition_code,
                priority, duration_hours, headcount, order_type, description,
                object_code, notes, mec_headcount, mec_hours, ele_headcount,
                ele_hours, sol_headcount, sol_hours
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """, (
            data.get('title', '').strip(),
            data.get('category', 'GERAL').strip(),
            data.get('object_type', 'EQUIPAMENTO').strip(),
            data.get('gpm', '').strip(),
            data.get('work_center', '').strip(),
            data.get('condition_code', '0').strip(),
            int(data.get('priority', 3)),
            float(data.get('duration_hours', 8.0)),
            int(data.get('headcount', 1)),
            data.get('order_type', 'PM13').strip(),
            data.get('description', '').strip(),
            str(data.get('equipment_code') or data.get('object_code') or '').strip(),
            str(data.get('notes') or '').strip() or None,
            int(data.get('mec_headcount') or 0), float(data.get('mec_hours') or 0),
            int(data.get('ele_headcount') or 0), float(data.get('ele_hours') or 0),
            int(data.get('sol_headcount') or 0), float(data.get('sol_hours') or 0)
        ))
        std_item_id = cursor.lastrowid

        ops = data.get('operations', [])
        for op in ops:
            cursor.execute("""
                INSERT INTO standard_item_operations (
                    standard_item_id, operation_code, suboperation_code, work_center,
                    short_text, unit, headcount, hours
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
            """, (
                std_item_id,
                op.get('operation_code', '0010'),
                op.get('suboperation_code', ''),
                op.get('work_center', data.get('work_center', '')),
                op.get('short_text', ''),
                op.get('unit', 'H'),
                (None if op.get('headcount') is None or str(op.get('headcount')).strip() == '' else int(op.get('headcount'))),
                (None if op.get('hours') is None or str(op.get('hours')).strip() == '' else float(op.get('hours')))
            ))
            std_op_id = cursor.lastrowid
            
            lts = op.get('long_texts', [])
            if not lts and op.get('long_text'):
                lts = [{
                    'text': op.get('long_text'),
                    'structure_mode': op.get('long_text_structure_mode'),
                    'structure_json': op.get('long_text_structure_json'),
                    'source_text_original': op.get('long_text_source_original')
                }]

            for lt in lts:
                lt_saved = prepare_for_save(lt.get('text', ''), lt.get('structure_mode'), lt.get('structure_json'), lt.get('source_text_original'))
                cursor.execute("""
                    INSERT INTO standard_operation_long_texts (
                        standard_operation_id, group_code, group_counter, text,
                        structure_mode, structure_json, source_text_original
                    ) VALUES (?, ?, ?, ?, ?, ?, ?);
                """, (
                    std_op_id,
                    lt.get('group_code', ''),
                    lt.get('group_counter', ''),
                    lt_saved['text'],
                    lt_saved['structure_mode'],
                    lt_saved['structure_json'],
                    lt_saved['source_text_original']
                ))

        conn.commit()
        return get_standard_item_detail(std_item_id)
    finally:
        conn.close()

def delete_standard_item(standard_id):
    """Deletes a standard item template and cascade deletes operations/long texts."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM standard_items WHERE id = ?;", (standard_id,))
        conn.commit()
        return True
    finally:
        conn.close()

def update_standard_item(standard_id, data):
    """Updates a standard item template and its operations."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        title = (data.get('title') or '').strip()
        category = (data.get('category') or 'GERAL').strip().upper()
        description = (data.get('description') or '').strip()
        object_code = (data.get('equipment_code') or data.get('object_code') or '').strip()
        gpm = (data.get('gpm') or '').strip()
        work_center = (data.get('work_center') or '').strip()

        cursor.execute("""
            UPDATE standard_items
            SET title = ?, category = ?, description = ?, object_code = ?, gpm = ?, work_center = ?
            WHERE id = ?;
        """, (title, category, description, object_code, gpm, work_center, standard_id))

        if 'operations' in data and isinstance(data['operations'], list):
            cursor.execute("DELETE FROM standard_item_operations WHERE standard_item_id = ?;", (standard_id,))
            for op in data['operations']:
                cursor.execute("""
                    INSERT INTO standard_item_operations (
                        standard_item_id, operation_code, suboperation_code, work_center,
                        short_text, unit, headcount, hours
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
                """, (
                    standard_id,
                    op.get('operation_code', '0010'),
                    op.get('suboperation_code', ''),
                    op.get('work_center', 'MEC01'),
                    op.get('short_text', ''),
                    op.get('unit', 'H'),
                    (None if op.get('headcount') is None or str(op.get('headcount')).strip() == '' else float(op.get('headcount'))),
                    (None if op.get('hours') is None or str(op.get('hours')).strip() == '' else float(op.get('hours')))
                ))
                std_op_id = cursor.lastrowid
                
                lts = op.get('long_texts', [])
                if not lts and op.get('long_text'):
                    lts = [{
                        'text': op.get('long_text'),
                        'structure_mode': op.get('long_text_structure_mode'),
                        'structure_json': op.get('long_text_structure_json'),
                        'source_text_original': op.get('long_text_source_original')
                    }]

                for lt in lts:
                    lt_saved = prepare_for_save(lt.get('text', ''), lt.get('structure_mode'), lt.get('structure_json'), lt.get('source_text_original'))
                    cursor.execute("""
                        INSERT INTO standard_operation_long_texts (
                            standard_operation_id, group_code, group_counter, text,
                            structure_mode, structure_json, source_text_original
                        ) VALUES (?, ?, ?, ?, ?, ?, ?);
                    """, (
                        std_op_id,
                        lt.get('group_code', ''),
                        lt.get('group_counter', ''),
                        lt_saved['text'],
                        lt_saved['structure_mode'],
                        lt_saved['structure_json'],
                        lt_saved['source_text_original']
                    ))

        conn.commit()
        return get_standard_item_detail(standard_id)
    finally:
        conn.close()

def duplicate_standard_item(standard_id, new_title=None):
    """Duplicates a standard item template."""
    std = get_standard_item_detail(standard_id)
    if not std:
        return None
    data = {
        'title': new_title or f"{std['title']} (Cópia)",
        'category': std.get('category', 'GERAL'),
        'description': std.get('description', ''),
        'equipment_code': std.get('equipment_code', ''),
        'gpm': std.get('gpm', ''),
        'work_center': std.get('work_center', ''),
        'operations': std.get('operations', [])
    }
    return create_standard_item(data)


def next_item_identifier(project_id, cursor=None):
    """Returns MAX(numeric identifier)+1 for a project."""
    owns_connection = cursor is None
    conn = get_db_connection() if owns_connection else None
    cur = conn.cursor() if owns_connection else cursor
    try:
        row = cur.execute("""SELECT MAX(CAST(legacy_identifier AS INTEGER))
            FROM maintenance_items
            WHERE project_id=? AND legacy_identifier <> ''
              AND legacy_identifier NOT GLOB '*[^0-9]*'""", (int(project_id),)).fetchone()
        return str((row[0] or 0) + 1)
    finally:
        if conn:
            conn.close()

def instantiate_standard_item(project_id, standard_id, override_data=None):
    """
    Creates a new maintenance_item in project_id based on standard_id template.
    Copies all standard operations and standard long texts into item_operations and operation_long_texts.
    """
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM standard_items WHERE id = ?;", (standard_id,))
        std = cursor.fetchone()
        if not std:
            raise ValueError(f"Modelo de item padrão id {standard_id} não encontrado.")
        
        override = override_data or {}
        
        requested_identifier = str(override.get('legacy_identifier') or '').strip()
        next_legacy = requested_identifier or next_item_identifier(project_id, cursor)
        
        desc = override.get('description', std['description']).strip()
        mec_hc = int(override.get('mec_headcount', std['mec_headcount']) or 0)
        mec_h = float(override.get('mec_hours', std['mec_hours']) or 0)
        ele_hc = int(override.get('ele_headcount', std['ele_headcount']) or 0)
        ele_h = float(override.get('ele_hours', std['ele_hours']) or 0)
        sol_hc = int(override.get('sol_headcount', std['sol_headcount']) or 0)
        sol_h = float(override.get('sol_hours', std['sol_hours']) or 0)
        specialty_hc = mec_hc + ele_hc + sol_hc
        specialty_hh = mec_hc * mec_h + ele_hc * ele_h + sol_hc * sol_h
        duration = float(override.get('duration_hours', std['duration_hours']) or 0)
        hc = specialty_hc if specialty_hc > 0 else int(override.get('headcount', std['headcount']) or 0)
        hh = specialty_hh if specialty_hc > 0 or specialty_hh > 0 else duration * hc
        display_order = cursor.execute(
            "SELECT COALESCE(MAX(display_order),0)+1 FROM maintenance_items WHERE project_id=?",
            (project_id,)
        ).fetchone()[0]
        
        cursor.execute("""
            INSERT INTO maintenance_items (
                project_id, plan_id, legacy_identifier, object_type, object_code,
                gpm, work_center, condition_code, priority, legacy_start,
                description, character_count, duration_hours, headcount, hh,
                mec_headcount, mec_hours, ele_headcount, ele_hours, sol_headcount, sol_hours,
                order_type, status, notes, display_order
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """, (
            project_id,
            override.get('plan_id'),
            next_legacy,
            override.get('object_type', std['object_type']),
            override.get('object_code') or std['object_code'] or std['title'][:20],
            override.get('gpm', std['gpm']),
            override.get('work_center', std['work_center']),
            override.get('condition_code', std['condition_code']),
            int(override.get('priority', std['priority'])),
            override.get('legacy_start'),
            desc,
            len(desc),
            duration,
            hc,
            hh,
            mec_hc, mec_h, ele_hc, ele_h, sol_hc, sol_h,
            override.get('order_type', std['order_type']),
            override.get('status', 'ACTIVE'),
            override.get('notes', std['notes']), display_order
        ))
        new_item_id = cursor.lastrowid
        
        # Fetch standard operations and copy
        cursor.execute("SELECT * FROM standard_item_operations WHERE standard_item_id = ? ORDER BY operation_code;", (standard_id,))
        std_ops = [dict(r) for r in cursor.fetchall()]
        
        for op in std_ops:
            cursor.execute("""
                INSERT INTO item_operations (
                    project_id, item_id, operation_code, suboperation_code,
                    work_center, short_text, unit, headcount, hours, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'ACTIVE');
            """, (
                project_id,
                new_item_id,
                op['operation_code'],
                op['suboperation_code'],
                op['work_center'] or std['work_center'],
                op['short_text'],
                op['unit'],
                op['headcount'],
                op['hours']
            ))
            new_op_id = cursor.lastrowid
            
            # Fetch standard operation long texts and copy
            cursor.execute("SELECT * FROM standard_operation_long_texts WHERE standard_operation_id = ?;", (op['id'],))
            std_lts = [dict(r) for r in cursor.fetchall()]
            for idx, lt in enumerate(std_lts, start=1):
                cursor.execute("""
                    INSERT INTO operation_long_texts (
                        project_id, operation_id, group_code, group_counter,
                        line_sequence, text, structure_mode, structure_json, source_text_original
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
                """, (
                    project_id,
                    new_op_id,
                    lt['group_code'],
                    lt['group_counter'],
                    idx,
                    lt['text'], lt.get('structure_mode', 'FREE'), lt.get('structure_json'), lt.get('source_text_original')
                ))

        conn.commit()
        return new_item_id
    finally:
        conn.close()

def apply_standard_item_to_existing(item_id, standard_id, override_data=None, replace_existing=False):
    """Replace an item's data and complete operation tree with a standard model."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        item = cursor.execute("SELECT * FROM maintenance_items WHERE id = ?;", (item_id,)).fetchone()
        std = cursor.execute("SELECT * FROM standard_items WHERE id = ?;", (standard_id,)).fetchone()
        if not item:
            raise ValueError(f"Item id {item_id} nao encontrado.")
        if not std:
            raise ValueError(f"Modelo de item padrao id {standard_id} nao encontrado.")

        existing_count = cursor.execute(
            "SELECT COUNT(*) FROM item_operations WHERE item_id = ?;", (item_id,)
        ).fetchone()[0]
        if existing_count and not replace_existing:
            raise ValueError("CONFIRM_REPLACE:Este item ja possui operacoes e textos longos.")

        override = override_data or {}
        desc = str(override.get('description', std['description']) or '').strip()
        mec_hc = int(override.get('mec_headcount', std['mec_headcount']) or 0)
        mec_h = float(override.get('mec_hours', std['mec_hours']) or 0)
        ele_hc = int(override.get('ele_headcount', std['ele_headcount']) or 0)
        ele_h = float(override.get('ele_hours', std['ele_hours']) or 0)
        sol_hc = int(override.get('sol_headcount', std['sol_headcount']) or 0)
        sol_h = float(override.get('sol_hours', std['sol_hours']) or 0)
        specialty_hc = mec_hc + ele_hc + sol_hc
        specialty_hh = mec_hc * mec_h + ele_hc * ele_h + sol_hc * sol_h
        duration = float(override.get('duration_hours', std['duration_hours']) or 0)
        headcount = specialty_hc if specialty_hc else int(override.get('headcount', std['headcount']) or 0)
        hh = specialty_hh if specialty_hc or specialty_hh else duration * headcount

        cursor.execute("""
            UPDATE maintenance_items SET
                plan_id=?, legacy_identifier=?, object_type=?, object_code=?, gpm=?,
                work_center=?, condition_code=?, priority=?, legacy_start=?, description=?,
                character_count=?, duration_hours=?, headcount=?, hh=?, mec_headcount=?,
                mec_hours=?, ele_headcount=?, ele_hours=?, sol_headcount=?, sol_hours=?,
                order_type=?, status=?, notes=?, team_id=?, updated_at=CURRENT_TIMESTAMP
            WHERE id=?;
        """, (
            override.get('plan_id', item['plan_id']),
            override.get('legacy_identifier') or item['legacy_identifier'],
            override.get('object_type', std['object_type']),
            override.get('object_code') or std['object_code'] or std['title'][:20],
            override.get('gpm', std['gpm']), override.get('work_center', std['work_center']),
            override.get('condition_code', std['condition_code']),
            int(override.get('priority', std['priority'])), override.get('legacy_start'),
            desc, len(desc), duration, headcount, hh,
            mec_hc, mec_h, ele_hc, ele_h, sol_hc, sol_h,
            override.get('order_type', std['order_type']), override.get('status', item['status']),
            override.get('notes', std['notes']), override.get('team_id', item['team_id']), item_id
        ))

        cursor.execute("DELETE FROM item_operations WHERE item_id = ?;", (item_id,))
        std_ops = cursor.execute(
            "SELECT * FROM standard_item_operations WHERE standard_item_id=? ORDER BY operation_code;",
            (standard_id,)
        ).fetchall()
        text_count = 0
        for op in std_ops:
            cursor.execute("""
                INSERT INTO item_operations (project_id,item_id,operation_code,suboperation_code,
                    work_center,short_text,unit,headcount,hours,status)
                VALUES (?,?,?,?,?,?,?,?,?,'ACTIVE');
            """, (item['project_id'], item_id, op['operation_code'], op['suboperation_code'],
                  op['work_center'] or std['work_center'], op['short_text'], op['unit'],
                  op['headcount'], op['hours']))
            new_op_id = cursor.lastrowid
            texts = cursor.execute(
                "SELECT * FROM standard_operation_long_texts WHERE standard_operation_id=? ORDER BY id;",
                (op['id'],)
            ).fetchall()
            for sequence, lt in enumerate(texts, 1):
                cursor.execute("""
                    INSERT INTO operation_long_texts
                        (project_id,operation_id,group_code,group_counter,line_sequence,text,structure_mode,structure_json,source_text_original)
                    VALUES (?,?,?,?,?,?,?,?,?);
                """, (item['project_id'], new_op_id, lt['group_code'], lt['group_counter'], sequence, lt['text'],
                      lt['structure_mode'] if 'structure_mode' in lt.keys() else 'FREE',
                      lt['structure_json'] if 'structure_json' in lt.keys() else None,
                      lt['source_text_original'] if 'source_text_original' in lt.keys() else None))
                text_count += 1
        conn.commit()
        return {'id': item_id, 'operations_created': len(std_ops), 'long_texts_created': text_count}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()



def _standard_structure_from_db(cursor, standard_id):
    """Return a normalized operation/long-text tree for one standard item."""
    std = cursor.execute("SELECT * FROM standard_items WHERE id = ?;", (standard_id,)).fetchone()
    if not std:
        raise ValueError(f"Modelo de item padrão id {standard_id} não encontrado.")

    operations = []
    std_ops = cursor.execute(
        "SELECT * FROM standard_item_operations WHERE standard_item_id=? ORDER BY operation_code, id;",
        (standard_id,),
    ).fetchall()
    for op in std_ops:
        texts = cursor.execute(
            "SELECT * FROM standard_operation_long_texts WHERE standard_operation_id=? ORDER BY id;",
            (op['id'],),
        ).fetchall()
        operations.append({
            'operation_code': str(op['operation_code'] or '').strip(),
            'suboperation_code': str(op['suboperation_code'] or '').strip(),
            'work_center': op['work_center'],
            'short_text': str(op['short_text'] or '').strip(),
            'unit': str(op['unit'] or 'H').strip() or 'H',
            'headcount': op['headcount'],
            'hours': op['hours'],
            'long_texts': [
                {
                    'group_code': lt['group_code'],
                    'group_counter': lt['group_counter'],
                    'text': str(lt['text'] or ''),
                    'structure_mode': lt['structure_mode'] if 'structure_mode' in lt.keys() else 'FREE',
                    'structure_json': lt['structure_json'] if 'structure_json' in lt.keys() else None,
                    'source_text_original': lt['source_text_original'] if 'source_text_original' in lt.keys() else None,
                }
                for lt in texts
            ],
        })
    return dict(std), operations


def _normalize_application_operations(raw_operations):
    """Validate editable preview data before it is replicated to existing items."""
    if not isinstance(raw_operations, list) or not raw_operations:
        raise ValueError("O modelo precisa possuir pelo menos uma operação para ser aplicado.")

    normalized = []
    seen_codes = set()
    for index, raw in enumerate(raw_operations, start=1):
        if not isinstance(raw, dict):
            raise ValueError(f"Operação {index} inválida.")

        code = str(raw.get('operation_code') or '').strip()
        subcode = str(raw.get('suboperation_code') or '').strip()
        short_text = str(raw.get('short_text') or '').strip()
        work_center = str(raw.get('work_center') or '').strip() or None
        unit = str(raw.get('unit') or 'H').strip().upper() or 'H'
        if not code:
            raise ValueError(f"Informe o código da operação {index}.")
        if not short_text:
            raise ValueError(f"Informe o texto breve da operação {code}.")
        key = (code, subcode)
        if key in seen_codes:
            raise ValueError(f"A operação {code}{('/' + subcode) if subcode else ''} está duplicada na prévia.")
        seen_codes.add(key)

        def nullable_int(value, field_name):
            if value is None or str(value).strip() == '':
                return None
            try:
                parsed = int(float(value))
            except (TypeError, ValueError):
                raise ValueError(f"{field_name} inválido na operação {code}.")
            if parsed < 0:
                raise ValueError(f"{field_name} não pode ser negativo na operação {code}.")
            return parsed

        def nullable_float(value, field_name):
            if value is None or str(value).strip() == '':
                return None
            try:
                parsed = float(str(value).replace(',', '.'))
            except (TypeError, ValueError):
                raise ValueError(f"{field_name} inválido na operação {code}.")
            if parsed < 0:
                raise ValueError(f"{field_name} não pode ser negativo na operação {code}.")
            return parsed

        long_texts = []
        for text_index, raw_text in enumerate(raw.get('long_texts') or [], start=1):
            if not isinstance(raw_text, dict):
                raise ValueError(f"Texto longo {text_index} da operação {code} é inválido.")
            text = str(raw_text.get('text') or '').replace('\r\n', '\n').replace('\r', '\n')
            if not text.strip():
                # Blank rows in the editor are ignored instead of creating invalid SAP text rows.
                continue
            prepared_text = prepare_for_save(text, raw_text.get('structure_mode'), raw_text.get('structure_json'), raw_text.get('source_text_original'))
            long_texts.append({
                'group_code': str(raw_text.get('group_code') or '').strip() or None,
                'group_counter': str(raw_text.get('group_counter') or '').strip() or None,
                'text': prepared_text['text'],
                'structure_mode': prepared_text['structure_mode'],
                'structure_json': prepared_text['structure_json'],
                'source_text_original': prepared_text['source_text_original'],
            })

        normalized.append({
            'operation_code': code,
            'suboperation_code': subcode,
            'work_center': work_center,
            'short_text': short_text[:40],
            'unit': unit[:10],
            'headcount': nullable_int(raw.get('headcount'), 'Efetivo'),
            'hours': nullable_float(raw.get('hours'), 'Horas'),
            'long_texts': long_texts,
        })
    return normalized


def _restore_standard_blank_lines(raw_operations, standard_operations):
    """Restore formatting lost by the mass-application HTML editor.

    Some browsers compact blank lines while round-tripping a model through the
    editable preview. If all nonblank lines still match the stored standard, the
    standard is authoritative for whitespace and structured metadata.
    """
    standard_by_key = {
        (str(op.get('operation_code') or '').strip(), str(op.get('suboperation_code') or '').strip()): op
        for op in standard_operations or []
    }
    restored = []
    for raw_op in raw_operations or []:
        operation = dict(raw_op) if isinstance(raw_op, dict) else raw_op
        if not isinstance(operation, dict):
            restored.append(operation)
            continue
        key = (str(operation.get('operation_code') or '').strip(), str(operation.get('suboperation_code') or '').strip())
        standard_op = standard_by_key.get(key) or {}
        standard_texts = standard_op.get('long_texts') or []
        incoming_texts = []
        for index, incoming in enumerate(operation.get('long_texts') or []):
            current = dict(incoming) if isinstance(incoming, dict) else incoming
            if isinstance(current, dict) and index < len(standard_texts):
                source = standard_texts[index]
                incoming_value = str(current.get('text') or '').replace('\r\n', '\n').replace('\r', '\n')
                source_value = str(source.get('text') or '').replace('\r\n', '\n').replace('\r', '\n')
                incoming_content = [line for line in incoming_value.split('\n') if line.strip()]
                source_content = [line for line in source_value.split('\n') if line.strip()]
                incoming_blanks = sum(not line.strip() for line in incoming_value.split('\n'))
                source_blanks = sum(not line.strip() for line in source_value.split('\n'))
                if incoming_content == source_content and incoming_blanks < source_blanks:
                    current['text'] = source_value
                    current['structure_mode'] = source.get('structure_mode')
                    current['structure_json'] = source.get('structure_json')
                    current['source_text_original'] = source.get('source_text_original')
            incoming_texts.append(current)
        operation['long_texts'] = incoming_texts
        restored.append(operation)
    return restored


def preview_bulk_standard_structure(project_id, item_ids, standard_id):
    """
    Build the read-only impact preview used by the mass "Aplicar Modelo" workflow.

    This deliberately does NOT modify maintenance_items.  The model contributes only
    its operation tree and long texts; item identity/header fields stay as they are.
    """
    ids = []
    for value in item_ids or []:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            continue
        if parsed not in ids:
            ids.append(parsed)
    if not ids:
        raise ValueError("Selecione pelo menos um item.")

    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        std, operations = _standard_structure_from_db(cursor, int(standard_id))
        if not operations:
            raise ValueError("O modelo selecionado não possui operações para aplicar.")

        placeholders = ','.join('?' for _ in ids)
        rows = cursor.execute(f"""
            SELECT i.id, i.project_id, i.legacy_identifier, i.object_type, i.object_code,
                   i.description, i.gpm, i.work_center, i.condition_code, i.priority,
                   i.plan_id, i.order_type, p.legacy_code AS plan_code,
                   p.description AS plan_description
              FROM maintenance_items i
              LEFT JOIN plans p ON p.id=i.plan_id
             WHERE i.project_id=? AND i.deleted_at IS NULL AND i.id IN ({placeholders})
             ORDER BY i.display_order, CAST(i.legacy_identifier AS INTEGER), i.legacy_identifier;
        """, (int(project_id), *ids)).fetchall()
        if len(rows) != len(ids):
            found = {int(row['id']) for row in rows}
            missing = [str(i) for i in ids if i not in found]
            raise ValueError("Há itens inválidos ou pertencentes a outro projeto: " + ', '.join(missing))

        conflict_rows = cursor.execute(f"""
            SELECT o.item_id,
                   COUNT(DISTINCT o.id) AS operations_count,
                   COUNT(t.id) AS long_texts_count
              FROM item_operations o
              LEFT JOIN operation_long_texts t ON t.operation_id=o.id
             WHERE o.project_id=? AND o.item_id IN ({placeholders})
             GROUP BY o.item_id;
        """, (int(project_id), *ids)).fetchall()
        conflict_map = {
            int(row['item_id']): {
                'operations_count': int(row['operations_count'] or 0),
                'long_texts_count': int(row['long_texts_count'] or 0),
            }
            for row in conflict_rows
        }

        items = []
        conflicts = []
        for row in rows:
            item = dict(row)
            counts = conflict_map.get(int(row['id']), {'operations_count': 0, 'long_texts_count': 0})
            item.update(counts)
            item['has_existing_structure'] = bool(counts['operations_count'] or counts['long_texts_count'])
            items.append(item)
            if item['has_existing_structure']:
                conflicts.append(item)

        long_texts_per_item = sum(len(op.get('long_texts') or []) for op in operations)
        return {
            'standard': {
                'id': int(std['id']),
                'title': std['title'],
                'category': std['category'],
                'description': std['description'],
                'operations': operations,
            },
            'items': items,
            'conflicts': conflicts,
            'summary': {
                'selected_items': len(items),
                'clean_items': len(items) - len(conflicts),
                'conflicting_items': len(conflicts),
                'operations_per_item': len(operations),
                'long_texts_per_item': long_texts_per_item,
                'projected_operations': len(items) * len(operations),
                'projected_long_texts': len(items) * long_texts_per_item,
            },
        }
    finally:
        conn.close()


def bulk_apply_standard_structure(project_id, item_ids, standard_id, operations=None, conflict_policy='skip'):
    """
    Replicate a standard operation tree into existing maintenance items.

    Item/header data (identifier, equipment, description, plan, GPM, HH, etc.) is
    intentionally preserved.  Only item_operations and operation_long_texts are
    created/replaced.  Each copied operation receives the destination item's item_id,
    and every copied long text receives the id of that newly-created operation.
    """
    ids = []
    for value in item_ids or []:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            continue
        if parsed not in ids:
            ids.append(parsed)
    if not ids:
        raise ValueError("Selecione pelo menos um item.")

    policy = str(conflict_policy or 'skip').strip().lower()
    if policy not in {'skip', 'replace'}:
        raise ValueError("Política de conflito inválida. Use 'skip' ou 'replace'.")

    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        std, db_operations = _standard_structure_from_db(cursor, int(standard_id))
        application_operations = operations if operations is not None else db_operations
        if operations is not None:
            application_operations = _restore_standard_blank_lines(application_operations, db_operations)
        template_operations = _normalize_application_operations(application_operations)

        placeholders = ','.join('?' for _ in ids)
        item_rows = cursor.execute(f"""
            SELECT id, project_id, legacy_identifier, object_code, description, work_center
              FROM maintenance_items
             WHERE project_id=? AND deleted_at IS NULL AND id IN ({placeholders})
             ORDER BY display_order, id;
        """, (int(project_id), *ids)).fetchall()
        if len(item_rows) != len(ids):
            found = {int(row['id']) for row in item_rows}
            missing = [str(i) for i in ids if i not in found]
            raise ValueError("Há itens inválidos ou pertencentes a outro projeto: " + ', '.join(missing))

        existing_rows = cursor.execute(f"""
            SELECT o.item_id, COUNT(DISTINCT o.id) AS operations_count,
                   COUNT(t.id) AS long_texts_count
              FROM item_operations o
              LEFT JOIN operation_long_texts t ON t.operation_id=o.id
             WHERE o.project_id=? AND o.item_id IN ({placeholders})
             GROUP BY o.item_id;
        """, (int(project_id), *ids)).fetchall()
        existing_map = {
            int(row['item_id']): (int(row['operations_count'] or 0), int(row['long_texts_count'] or 0))
            for row in existing_rows
        }

        result_items = []
        applied = skipped = replaced = operations_created = long_texts_created = 0
        for item in item_rows:
            item_id = int(item['id'])
            existing_ops, existing_texts = existing_map.get(item_id, (0, 0))
            has_structure = bool(existing_ops or existing_texts)
            if has_structure and policy == 'skip':
                skipped += 1
                result_items.append({
                    'id': item_id,
                    'legacy_identifier': item['legacy_identifier'],
                    'status': 'skipped',
                    'existing_operations': existing_ops,
                    'existing_long_texts': existing_texts,
                })
                continue

            if has_structure:
                # FK ON DELETE CASCADE removes existing long texts atomically.
                cursor.execute("DELETE FROM item_operations WHERE project_id=? AND item_id=?;", (int(project_id), item_id))
                replaced += 1

            item_op_count = 0
            item_text_count = 0
            for op_index, op in enumerate(template_operations, start=1):
                cursor.execute("""
                    INSERT INTO item_operations (
                        project_id, item_id, operation_code, suboperation_code,
                        work_center, short_text, unit, headcount, hours, status, display_order
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'ACTIVE', ?);
                """, (
                    int(project_id), item_id, op['operation_code'], op['suboperation_code'],
                    op['work_center'] or item['work_center'], op['short_text'], op['unit'],
                    op['headcount'], op['hours'], op_index,
                ))
                new_op_id = cursor.lastrowid
                item_op_count += 1
                for text_index, lt in enumerate(op.get('long_texts') or [], start=1):
                    cursor.execute("""
                        INSERT INTO operation_long_texts (
                            project_id, operation_id, group_code, group_counter,
                            line_sequence, text, display_order,structure_mode,structure_json,source_text_original
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                    """, (
                        int(project_id), new_op_id, lt.get('group_code'), lt.get('group_counter'),
                        text_index, lt['text'], text_index, lt.get('structure_mode','FREE'),
                        lt.get('structure_json'), lt.get('source_text_original'),
                    ))
                    item_text_count += 1

            applied += 1
            operations_created += item_op_count
            long_texts_created += item_text_count
            result_items.append({
                'id': item_id,
                'legacy_identifier': item['legacy_identifier'],
                'status': 'replaced' if has_structure else 'created',
                'operations_created': item_op_count,
                'long_texts_created': item_text_count,
            })

        conn.commit()
        return {
            'standard_id': int(std['id']),
            'standard_title': std['title'],
            'selected_items': len(item_rows),
            'applied_items': applied,
            'skipped_items': skipped,
            'replaced_items': replaced,
            'operations_created': operations_created,
            'long_texts_created': long_texts_created,
            'items': result_items,
        }
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def save_item_as_standard(item_id, title, category):
    """
    Converts an existing maintenance_item in a project into a new global standard item template.
    """
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM maintenance_items WHERE id = ?;", (item_id,))
        item = cursor.fetchone()
        if not item:
            raise ValueError(f"Item id {item_id} não encontrado.")
            
        cursor.execute("""
            INSERT INTO standard_items (
                title, category, object_type, gpm, work_center, condition_code,
                priority, duration_hours, headcount, order_type, description,
                object_code, notes, mec_headcount, mec_hours, ele_headcount,
                ele_hours, sol_headcount, sol_hours
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """, (
            title.strip() or item['description'],
            (category or 'GERAL').strip(),
            item['object_type'],
            item['gpm'],
            item['work_center'],
            item['condition_code'],
            item['priority'],
            item['duration_hours'],
            item['headcount'],
            item['order_type'],
            item['description'],
            item['object_code'], item['notes'],
            int(item['mec_headcount'] or 0), float(item['mec_hours'] or 0),
            int(item['ele_headcount'] or 0), float(item['ele_hours'] or 0),
            int(item['sol_headcount'] or 0), float(item['sol_hours'] or 0)
        ))
        std_item_id = cursor.lastrowid
        
        # Copy item operations
        cursor.execute("SELECT * FROM item_operations WHERE item_id = ? ORDER BY operation_code;", (item_id,))
        ops = [dict(r) for r in cursor.fetchall()]
        
        for op in ops:
            cursor.execute("""
                INSERT INTO standard_item_operations (
                    standard_item_id, operation_code, suboperation_code, work_center,
                    short_text, unit, headcount, hours
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
            """, (
                std_item_id,
                op['operation_code'],
                op['suboperation_code'],
                op['work_center'],
                op['short_text'],
                op['unit'],
                op['headcount'],
                op['hours']
            ))
            std_op_id = cursor.lastrowid
            
            cursor.execute("SELECT * FROM operation_long_texts WHERE operation_id = ? ORDER BY line_sequence;", (op['id'],))
            lts = [dict(r) for r in cursor.fetchall()]
            for lt in lts:
                cursor.execute("""
                    INSERT INTO standard_operation_long_texts (
                        standard_operation_id, group_code, group_counter, text,structure_mode,structure_json,source_text_original
                    ) VALUES (?, ?, ?, ?, ?, ?, ?);
                """, (
                    std_op_id,
                    lt['group_code'],
                    lt['group_counter'],
                    lt['text'],
                    lt.get('structure_mode','FREE'), lt.get('structure_json'), lt.get('source_text_original')
                ))

        conn.commit()
        return get_standard_item_detail(std_item_id)
    finally:
        conn.close()

# ==========================================
# PRIORÍMETRO SAP
# ==========================================

PRIORIMETER_FIELDS = {
    'failure_probability': 'Probabilidade de Falha',
    'maintenance_impact': 'Impacto da Manutenção',
    'events_over_one': 'Quantidade de Eventos em 1 ano > 1?',
    'asymmetric_lifting': 'Elevação/movimentação de carga assimétrica',
    'multi_lifting': 'Elevação/movimentação com talha/ponte rolante/guindaste',
    'thermal_overload': 'Ambiente com sobrecarga térmica',
    'tanks_gases': 'Tanques/gases asfixiantes e/ou inflamáveis',
    'leak_exposure': 'Risco de vazamento/exposição',
    'pressurized_systems': 'Risco em sistemas pressurizados',
    'energized_electrical': 'Sistemas elétricos energizados',
    'confined_spaces': 'Espaços confinados',
    'height_over_2m': 'Desnível superior a 2 metros',
    'hot_metal': 'Risco de metal quente',
    'difficult_technical': 'Conhecimento técnico específico/difícil realização',
    'hydraulic_jack': 'Macaco hidráulico: acionamento simultâneo e/ou fora do centro de gravidade',
}

PRIORIMETER_YES_NO_FIELDS = {
    'events_over_one', 'asymmetric_lifting', 'multi_lifting', 'thermal_overload',
    'tanks_gases', 'leak_exposure', 'pressurized_systems', 'energized_electrical',
    'confined_spaces', 'height_over_2m', 'hot_metal', 'difficult_technical', 'hydraulic_jack'
}


def _normalize_priorimeter_value(field, value):
    if field not in PRIORIMETER_FIELDS:
        raise ValueError(f'Campo de priorímetro inválido: {field}.')
    if value is None or str(value).strip() == '':
        return None
    if field == 'failure_probability':
        parsed = int(value)
        if parsed not in (1, 2, 3, 4, 5):
            raise ValueError('Probabilidade de falha deve ser 1, 2, 3, 4 ou 5.')
        return parsed
    if field == 'maintenance_impact':
        parsed = int(value)
        if parsed not in (1, 2, 3, 4, 6, 8):
            raise ValueError('Impacto da manutenção deve ser 1, 2, 3, 4, 6 ou 8.')
        return parsed
    text = str(value).strip().upper()
    if text in ('SIM', 'S'):
        return 'S'
    if text in ('NAO', 'NÃO', 'N'):
        return 'N'
    raise ValueError(f'{PRIORIMETER_FIELDS[field]} deve ser S ou N.')


def list_priorimeter(project_id, search=None, status='ACTIVE'):
    """Return one priorimeter row for every maintenance item in the project.

    The LEFT JOIN is intentional: new/existing items appear immediately even if
    their priorimeter criteria have never been saved.
    """
    conn = get_db_connection()
    try:
        sql = """
            SELECT i.id AS item_id, i.legacy_identifier, i.object_code,
                   i.description AS item_description, i.object_type, i.gpm,
                   i.work_center, i.status AS item_status, i.display_order,
                   p.id AS priorimeter_id,
                   p.failure_probability, p.maintenance_impact, p.events_over_one,
                   p.asymmetric_lifting, p.multi_lifting, p.thermal_overload,
                   p.tanks_gases, p.leak_exposure, p.pressurized_systems,
                   p.energized_electrical, p.confined_spaces, p.height_over_2m,
                   p.hot_metal, p.difficult_technical, p.hydraulic_jack,
                   p.updated_at AS priorimeter_updated_at
            FROM maintenance_items i
            LEFT JOIN item_priorimeter p ON p.item_id = i.id
            WHERE i.project_id=? AND i.deleted_at IS NULL
        """
        params = [int(project_id)]
        normalized_status = str(status or '').upper().strip()
        if normalized_status in ('ACTIVE', 'INACTIVE'):
            sql += ' AND i.status=?'
            params.append(normalized_status)
        if search:
            term = f"%{str(search).strip()}%"
            sql += " AND (i.legacy_identifier LIKE ? OR i.object_code LIKE ? OR i.description LIKE ?)"
            params.extend([term, term, term])
        sql += " ORDER BY COALESCE(i.display_order,i.id), i.id"
        rows = [dict(row) for row in conn.execute(sql, params).fetchall()]
        fields = list(PRIORIMETER_FIELDS)
        for row in rows:
            filled = sum(1 for field in fields if row.get(field) not in (None, ''))
            row['filled_fields'] = filled
            row['total_fields'] = len(fields)
            row['complete'] = filled == len(fields)
        return rows
    finally:
        conn.close()


def get_priorimeter_for_item(project_id, item_id):
    rows = list_priorimeter(project_id, status='')
    item_id = int(item_id)
    return next((row for row in rows if int(row['item_id']) == item_id), None)


def _assert_priorimeter_item(cursor, project_id, item_id):
    row = cursor.execute(
        "SELECT id FROM maintenance_items WHERE id=? AND project_id=? AND deleted_at IS NULL",
        (int(item_id), int(project_id)),
    ).fetchone()
    if not row:
        raise ValueError('Item não encontrado no projeto ativo.')


def update_priorimeter_item(project_id, item_id, updates):
    clean = {}
    for field, value in (updates or {}).items():
        if field in PRIORIMETER_FIELDS:
            clean[field] = _normalize_priorimeter_value(field, value)
    if not clean:
        raise ValueError('Nenhum campo válido do priorímetro foi informado.')

    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        _assert_priorimeter_item(cursor, project_id, item_id)
        cursor.execute(
            "INSERT OR IGNORE INTO item_priorimeter(project_id,item_id) VALUES (?,?)",
            (int(project_id), int(item_id)),
        )
        sets = ', '.join(f'{field}=?' for field in clean)
        cursor.execute(
            f"UPDATE item_priorimeter SET {sets}, updated_at=CURRENT_TIMESTAMP WHERE project_id=? AND item_id=?",
            (*clean.values(), int(project_id), int(item_id)),
        )
        conn.commit()
        log_action(int(project_id), 'PRIORIMETER', int(item_id), 'UPDATE', None, clean)
        return get_priorimeter_for_item(project_id, item_id)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def bulk_update_priorimeter(project_id, item_ids, updates):
    ids = []
    for value in item_ids or []:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            continue
        if parsed not in ids:
            ids.append(parsed)
    if not ids:
        raise ValueError('Selecione pelo menos um item.')

    clean = {}
    for field, value in (updates or {}).items():
        if field in PRIORIMETER_FIELDS:
            clean[field] = _normalize_priorimeter_value(field, value)
    if not clean:
        raise ValueError('Nenhum campo válido do priorímetro foi informado.')

    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        placeholders = ','.join('?' for _ in ids)
        valid_rows = cursor.execute(
            f"SELECT id FROM maintenance_items WHERE project_id=? AND deleted_at IS NULL AND id IN ({placeholders})",
            (int(project_id), *ids),
        ).fetchall()
        valid_ids = [int(row['id']) for row in valid_rows]
        if len(valid_ids) != len(ids):
            raise ValueError('Um ou mais itens selecionados não pertencem ao projeto ativo.')
        cursor.executemany(
            "INSERT OR IGNORE INTO item_priorimeter(project_id,item_id) VALUES (?,?)",
            [(int(project_id), item_id) for item_id in valid_ids],
        )
        sets = ', '.join(f'{field}=?' for field in clean)
        for item_id in valid_ids:
            cursor.execute(
                f"UPDATE item_priorimeter SET {sets}, updated_at=CURRENT_TIMESTAMP WHERE project_id=? AND item_id=?",
                (*clean.values(), int(project_id), item_id),
            )
        conn.commit()
        log_action(int(project_id), 'PRIORIMETER_BULK', int(project_id), 'BULK_UPDATE',
                   {'item_ids': valid_ids}, clean)
        return {'updated': len(valid_ids), 'item_ids': valid_ids}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def copy_priorimeter_row(project_id, source_item_id, target_item_ids):
    source = get_priorimeter_for_item(project_id, source_item_id)
    if not source:
        raise ValueError('Linha de origem não encontrada.')
    payload = {field: source.get(field) for field in PRIORIMETER_FIELDS}
    return bulk_update_priorimeter(project_id, target_item_ids, payload)
