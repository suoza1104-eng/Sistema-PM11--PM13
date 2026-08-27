"""Persistent manual-balancing drafts and Book operations."""

import json
from core.database import get_db_connection
from core.auto_balance_service import get_plan_prefix9
from core.calculations import plan_occurs_on_stop, project_balance
from core.balance_rules import evaluate_rules


def _row_dict(row):
    return dict(row) if row else None


def _session_row(conn, project_id=None, session_id=None, require_draft=True):
    where = ['id=?'] if session_id else ['project_id=?']
    params = [int(session_id if session_id else project_id)]
    if require_draft:
        where.append("status='DRAFT'")
    row = conn.execute(
        'SELECT * FROM manual_balance_sessions WHERE ' + ' AND '.join(where) + ' ORDER BY id DESC LIMIT 1',
        params).fetchone()
    return _row_dict(row)


def _session_matches_current_items(conn, session):
    """A draft remains valid across item activation-status changes.

    Assignments belonging to inactive items are deliberately retained. They are
    ignored by balance calculations while inactive and recover their exact draft
    position if reactivated. Missing/deleted items or active items without an
    assignment still indicate a structural replacement/import and invalidate the
    draft.
    """
    if not session:
        return False
    project_id = int(session['project_id'])
    session_id = int(session['id'])
    active_items = conn.execute("""SELECT COUNT(*)
        FROM maintenance_items i JOIN plans p ON p.id=i.plan_id
        WHERE i.project_id=? AND i.deleted_at IS NULL AND i.status='ACTIVE'
          AND p.deleted_at IS NULL AND p.status='ACTIVE'""", (project_id,)).fetchone()[0]
    assignment_counts = conn.execute("""SELECT
        SUM(CASE WHEN i.id IS NOT NULL AND i.status='ACTIVE' AND p.id IS NOT NULL
                 THEN 1 ELSE 0 END) AS live_active,
        SUM(CASE WHEN i.id IS NULL THEN 1 ELSE 0 END) AS missing_items
        FROM manual_balance_assignments a
        LEFT JOIN maintenance_items i ON i.id=a.item_id AND i.project_id=a.project_id
            AND i.deleted_at IS NULL
        LEFT JOIN plans p ON p.id=i.plan_id AND p.deleted_at IS NULL
            AND p.status='ACTIVE'
        WHERE a.session_id=?""", (session_id,)).fetchone()
    return (int(assignment_counts['live_active'] or 0) == int(active_items)
            and int(assignment_counts['missing_items'] or 0) == 0)


def _discard_stale_session(conn, session):
    if session and not _session_matches_current_items(conn, session):
        conn.execute("""UPDATE manual_balance_sessions
            SET status='DISCARDED',updated_at=CURRENT_TIMESTAMP WHERE id=?""", (session['id'],))
        return True
    return False


def get_active_session(project_id):
    conn = get_db_connection()
    try:
        session = _session_row(conn, project_id=project_id)
        if _discard_stale_session(conn, session):
            conn.commit()
            return None
        return _decorate_session(conn, session) if session else None
    finally:
        conn.close()


def _decorate_session(conn, session):
    if not session:
        return None
    counts = {row['balance_state']: row['qty'] for row in conn.execute(
        """SELECT a.balance_state,COUNT(*) qty FROM manual_balance_assignments a
        JOIN maintenance_items i ON i.id=a.item_id
        WHERE a.session_id=? AND i.deleted_at IS NULL AND i.status='ACTIVE'
        GROUP BY a.balance_state""",
        (session['id'],)).fetchall()}
    hh_rows = conn.execute("""
        SELECT a.balance_state,COALESCE(SUM(CASE WHEN
          (COALESCE(i.mec_headcount,0)*COALESCE(i.mec_hours,0)+
           COALESCE(i.ele_headcount,0)*COALESCE(i.ele_hours,0)+
           COALESCE(i.sol_headcount,0)*COALESCE(i.sol_hours,0))>0
          THEN (COALESCE(i.mec_headcount,0)*COALESCE(i.mec_hours,0)+
                COALESCE(i.ele_headcount,0)*COALESCE(i.ele_hours,0)+
                COALESCE(i.sol_headcount,0)*COALESCE(i.sol_hours,0))
          ELSE COALESCE(i.duration_hours,0)*COALESCE(i.headcount,1) END),0) hh
        FROM manual_balance_assignments a JOIN maintenance_items i ON i.id=a.item_id
        WHERE a.session_id=? AND i.deleted_at IS NULL AND i.status='ACTIVE'
        GROUP BY a.balance_state""", (session['id'],)).fetchall()
    hh = {row['balance_state']: round(float(row['hh']), 1) for row in hh_rows}
    total = sum(counts.values())
    pending = counts.get('PENDING', 0)
    session = dict(session)
    try:
        session['settings'] = json.loads(session.pop('settings_json') or '{}')
    except (TypeError, ValueError):
        session['settings'] = {}
    session['counts'] = counts
    session['hh_by_state'] = hh
    session['total_items'] = total
    session['pending_items'] = pending
    session['positioned_items'] = total - pending
    session['progress_percent'] = round(((total - pending) / total * 100) if total else 100, 1)
    return session


def start_session(project_id, base_mode='zero', horizon=12, restart=False):
    if base_mode not in ('zero', 'current'):
        raise ValueError("Modo inicial inválido. Use 'zero' ou 'current'.")
    horizon = max(2, min(120, int(horizon or 12)))
    conn = get_db_connection()
    try:
        conn.execute('BEGIN IMMEDIATE')
        existing = _session_row(conn, project_id=project_id)
        if _discard_stale_session(conn, existing):
            existing = None
        if existing and not restart:
            conn.commit()
            return _decorate_session(conn, existing)
        if existing:
            conn.execute("UPDATE manual_balance_sessions SET status='DISCARDED',updated_at=CURRENT_TIMESTAMP WHERE id=?",
                         (existing['id'],))
        cursor = conn.execute("""INSERT INTO manual_balance_sessions
            (project_id,status,base_mode,horizon,settings_json) VALUES (?,'DRAFT',?,?,?)""",
            (project_id, base_mode, horizon, json.dumps({'only_pending': base_mode == 'zero'})))
        session_id = cursor.lastrowid
        items = conn.execute("""SELECT i.id,i.plan_id,p.cycle,p.reference_counter
            FROM maintenance_items i JOIN plans p ON p.id=i.plan_id
            WHERE i.project_id=? AND i.deleted_at IS NULL AND i.status='ACTIVE'
              AND p.deleted_at IS NULL AND p.status='ACTIVE' ORDER BY i.id""", (project_id,)).fetchall()
        for item in items:
            fixed = int(item['cycle'] or 0) == 1
            # Positions copied from the official scenario are only a baseline,
            # not explicit manual decisions. Keep them eligible for automatic
            # balancing until the user actually moves or locks the item.
            state = 'FIXED' if fixed else ('PENDING' if base_mode == 'zero' else 'AUTOMATIC')
            target = item['plan_id'] if state != 'PENDING' else None
            source = 'fixed' if fixed else ('manual' if state == 'PENDING' else 'automatic')
            conn.execute("""INSERT INTO manual_balance_assignments
                (session_id,project_id,item_id,original_plan_id,target_plan_id,balance_state,source)
                VALUES (?,?,?,?,?,?,?)""",
                (session_id, project_id, item['id'], item['plan_id'], target, state, source))
        conn.commit()
        return get_active_session(project_id)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def list_book(project_id, session_id, search='', cycles=None, states=None, plan_query='', only_pending=False):
    conn = get_db_connection()
    try:
        session = _session_row(conn, session_id=session_id)
        if not session or int(session['project_id']) != int(project_id):
            raise ValueError('Rascunho manual não encontrado.')
        rows = conn.execute("""SELECT a.item_id AS id,a.balance_state,a.target_stop,a.source,
            i.legacy_identifier,i.description,i.object_code,i.work_center,i.gpm,
            CASE WHEN (COALESCE(i.mec_headcount,0)*COALESCE(i.mec_hours,0)+
                            COALESCE(i.ele_headcount,0)*COALESCE(i.ele_hours,0)+
                            COALESCE(i.sol_headcount,0)*COALESCE(i.sol_hours,0))>0
                 THEN (COALESCE(i.mec_headcount,0)*COALESCE(i.mec_hours,0)+
                       COALESCE(i.ele_headcount,0)*COALESCE(i.ele_hours,0)+
                       COALESCE(i.sol_headcount,0)*COALESCE(i.sol_hours,0))
                 ELSE COALESCE(i.duration_hours,0)*COALESCE(i.headcount,1) END AS hh,
            op.id original_plan_id,op.legacy_code original_plan_code,op.cycle original_cycle,
            tp.id target_plan_id,tp.legacy_code target_plan_code,tp.cycle target_cycle
            FROM manual_balance_assignments a
            JOIN maintenance_items i ON i.id=a.item_id
            LEFT JOIN plans op ON op.id=a.original_plan_id
            LEFT JOIN plans tp ON tp.id=a.target_plan_id
            WHERE a.session_id=? AND i.deleted_at IS NULL AND i.status='ACTIVE' ORDER BY
              CASE WHEN i.legacy_identifier GLOB '[0-9]*' THEN 0 ELSE 1 END,
              CAST(i.legacy_identifier AS INTEGER),i.legacy_identifier,i.id""", (session_id,)).fetchall()
        cycles = {int(x) for x in (cycles or [])}
        states = {str(x).upper() for x in (states or [])}
        search = str(search or '').strip().casefold()
        plan_query = str(plan_query or '').strip().casefold()
        result = []
        for raw in rows:
            row = dict(raw)
            row['cycle'] = int(row['target_cycle'] or row['original_cycle'] or 0)
            row['plan_code'] = row['target_plan_code'] or row['original_plan_code'] or ''
            row['family9'] = get_plan_prefix9(row['plan_code'])
            if only_pending and row['balance_state'] != 'PENDING':
                continue
            if cycles and row['cycle'] not in cycles:
                continue
            if states and row['balance_state'] not in states:
                continue
            haystack = f"{row['legacy_identifier']} {row['description']} {row['object_code']} {row['plan_code']}".casefold()
            if search and search not in haystack:
                continue
            if plan_query and plan_query not in f"{row['plan_code']} {row['family9']}".casefold():
                continue
            result.append(row)
        cycle_counts = {}
        state_counts = {}
        for raw in rows:
            cycle = int(raw['target_cycle'] or raw['original_cycle'] or 0)
            cycle_counts[cycle] = cycle_counts.get(cycle, 0) + 1
            state_counts[raw['balance_state']] = state_counts.get(raw['balance_state'], 0) + 1
        return {'items': result, 'total': len(result), 'cycle_counts': cycle_counts,
                'state_counts': state_counts, 'session': _decorate_session(conn, session)}
    finally:
        conn.close()


def _plan_context(conn, project_id):
    project = conn.execute('SELECT current_counter FROM projects WHERE id=?', (project_id,)).fetchone()
    plans = [dict(row) for row in conn.execute("""SELECT id,legacy_code,description,cycle,unit,reference_counter
        FROM plans WHERE project_id=? AND deleted_at IS NULL AND status='ACTIVE' AND cycle>0""",
        (project_id,)).fetchall()]
    return int(project['current_counter']), plans, {int(p['id']): p for p in plans}


def _candidate_plans_with_conn(conn, project_id, session_id, item_ids, target_stop,
                               include_incompatible=False):
    item_ids = [int(x) for x in item_ids]
    if not item_ids:
        return {}
    placeholders = ','.join('?' for _ in item_ids)
    items = conn.execute(f"""SELECT i.id,op.legacy_code,op.cycle
        FROM manual_balance_assignments a JOIN maintenance_items i ON i.id=a.item_id
        JOIN plans op ON op.id=a.original_plan_id
        WHERE a.session_id=? AND i.id IN ({placeholders})""", (session_id, *item_ids)).fetchall()
    _, plans, _ = _plan_context(conn, project_id)
    result = {}
    for item in items:
        family = get_plan_prefix9(item['legacy_code'])
        rows = []
        for plan in plans:
            compatible = get_plan_prefix9(plan['legacy_code']) == family
            if (int(plan['cycle']) == int(item['cycle'])
                    and (compatible or include_incompatible)
                    and plan_occurs_on_stop(plan['reference_counter'], plan['cycle'], target_stop)):
                candidate = dict(plan)
                candidate['source_family9'] = family
                candidate['family9'] = get_plan_prefix9(plan['legacy_code'])
                candidate['family_compatible'] = compatible
                rows.append(candidate)
        rows.sort(key=lambda plan: (not plan['family_compatible'], str(plan['legacy_code'])))
        result[str(item['id'])] = rows
    return result


def candidate_plans(project_id, session_id, item_ids, target_stop):
    conn = get_db_connection()
    try:
        session = _session_row(conn, session_id=session_id)
        if not session or int(session['project_id']) != int(project_id):
            raise ValueError('Rascunho manual não encontrado.')
        return _candidate_plans_with_conn(
            conn, project_id, session_id, item_ids, int(target_stop), True)
    finally:
        conn.close()


def stop_details(project_id, session_id, stop_counter, horizon=12):
    balance = project_balance(project_id, {
        'manual_session_id': session_id, 'horizon': horizon
    }, 'none')
    target = next((row for row in balance['stops'] if int(row['counter']) == int(stop_counter)), None)
    conn = get_db_connection()
    try:
        rows = conn.execute("""SELECT i.*,p.id plan_id,p.legacy_code plan_code,
            p.description plan_description,p.cycle,p.unit,p.reference_counter,
            a.balance_state,a.target_stop
            FROM manual_balance_assignments a
            JOIN maintenance_items i ON i.id=a.item_id
            JOIN plans p ON p.id=a.target_plan_id
            WHERE a.session_id=? AND a.project_id=? AND a.balance_state<>'PENDING'
              AND i.deleted_at IS NULL AND i.status='ACTIVE'
            ORDER BY CASE WHEN i.legacy_identifier GLOB '[0-9]*' THEN 0 ELSE 1 END,
                     CAST(i.legacy_identifier AS INTEGER),i.legacy_identifier""",
            (session_id, project_id)).fetchall()
        orders = [dict(row) for row in rows if plan_occurs_on_stop(
            row['reference_counter'], row['cycle'], stop_counter)]
        return {'orders': orders, 'stop_info': target or {
            'counter': int(stop_counter), 'stop_num': int(stop_counter), 'total_orders': 0,
            'total_hh': 0, 'headcount_needed': 0, 'grouped_hh': {}}}
    finally:
        conn.close()


def _saved_rules(conn, project_id):
    result = []
    for row in conn.execute("""SELECT name,rule_type,item_ids_json,enforcement,config_json
        FROM auto_balance_rules WHERE project_id=? AND active=1 ORDER BY id""", (project_id,)).fetchall():
        result.append({'name': row['name'], 'type': row['rule_type'],
                       'item_ids': json.loads(row['item_ids_json'] or '[]'),
                       'enforcement': row['enforcement'] or 'mandatory',
                       'config': json.loads(row['config_json'] or '{}')})
    return result


def move_items(project_id, session_id, item_ids, target_stop, target_plan_ids=None,
               source='manual', allow_family_mismatch=False):
    item_ids = [int(x) for x in item_ids]
    if not item_ids:
        raise ValueError('Selecione ao menos um item.')
    target_plan_ids = {int(k): int(v) for k, v in (target_plan_ids or {}).items()}
    conn = get_db_connection()
    try:
        conn.execute('BEGIN IMMEDIATE')
        session = _session_row(conn, session_id=session_id)
        if not session or int(session['project_id']) != int(project_id):
            raise ValueError('Rascunho manual não encontrado.')
        placeholders = ','.join('?' for _ in item_ids)
        fixed = conn.execute(f"""SELECT item_id FROM manual_balance_assignments
            WHERE session_id=? AND item_id IN ({placeholders}) AND balance_state='FIXED'""",
            (session_id, *item_ids)).fetchall()
        if fixed:
            raise ValueError('Itens trancados ou planos 1P são protegidos e não podem ser movimentados.')
        candidates = _candidate_plans_with_conn(
            conn, project_id, session_id, item_ids, int(target_stop), bool(target_plan_ids))
        chosen = {}
        warnings = []
        for item_id in item_ids:
            options = candidates.get(str(item_id), [])
            explicit = target_plan_ids.get(item_id)
            if explicit:
                options = [p for p in options if int(p['id']) == explicit]
            if not options:
                raise ValueError(f'Item {item_id}: não existe plano da mesma família/ciclo na parada escolhida.')
            selected = options[0]
            if not selected.get('family_compatible', True):
                warning = (f"Item {item_id}: família de origem {selected['source_family9']} e "
                           f"destino {selected['family9']}.")
                if not allow_family_mismatch:
                    raise ValueError('FAMILY_MISMATCH_CONFIRMATION_REQUIRED: ' + warning)
                warnings.append(warning)
            chosen[item_id] = int(selected['id'])

        current_counter, plans, plan_by_id = _plan_context(conn, project_id)
        rows = conn.execute("SELECT item_id,target_plan_id,balance_state FROM manual_balance_assignments WHERE session_id=?",
                            (session_id,)).fetchall()
        assignment = {int(r['item_id']): int(r['target_plan_id']) for r in rows if r['target_plan_id']}
        pending = {int(r['item_id']) for r in rows if r['balance_state'] == 'PENDING'}
        assignment.update(chosen)
        pending.difference_update(chosen)
        ok, _, diagnostics = evaluate_rules(
            _saved_rules(conn, project_id), assignment, plan_by_id, current_counter,
            int(session['horizon']), pending)
        if not ok:
            failures = [d for d in diagnostics if d['enforcement'] == 'mandatory'
                        and not d['satisfied'] and not d.get('pending')]
            raise ValueError('Movimento viola regra obrigatória: ' + '; '.join(
                f"{d['name']}: {d['message']}" for d in failures))
        state = 'AUTOMATIC' if source == 'automatic' else 'MANUAL'
        for item_id, plan_id in chosen.items():
            conn.execute("""UPDATE manual_balance_assignments SET target_plan_id=?,target_stop=?,
                balance_state=?,source=?,updated_at=CURRENT_TIMESTAMP WHERE session_id=? AND item_id=?""",
                (plan_id, int(target_stop), state, source, session_id, item_id))
        conn.execute("UPDATE manual_balance_sessions SET version=version+1,updated_at=CURRENT_TIMESTAMP WHERE id=?",
                     (session_id,))
        conn.commit()
        return {'moved': len(chosen), 'assignments': chosen, 'warnings': warnings,
                'session': get_active_session(project_id)}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def set_item_lock(project_id, session_id, item_id, locked, target_stop=None):
    """Lock/unlock one positioned item without changing its current plan."""
    conn = get_db_connection()
    try:
        conn.execute('BEGIN IMMEDIATE')
        session = _session_row(conn, session_id=session_id)
        if not session or int(session['project_id']) != int(project_id):
            raise ValueError('Rascunho manual não encontrado.')
        row = conn.execute("""SELECT a.*,p.cycle FROM manual_balance_assignments a
            LEFT JOIN plans p ON p.id=a.target_plan_id
            WHERE a.session_id=? AND a.item_id=? AND a.project_id=?""",
            (session_id, int(item_id), int(project_id))).fetchone()
        if not row:
            raise ValueError('Item não encontrado no balanceamento atual.')
        row = dict(row)

        if locked:
            if not row.get('target_plan_id'):
                raise ValueError('Posicione o item em uma parada antes de trancá-lo.')
            if row.get('balance_state') != 'FIXED':
                conn.execute("""UPDATE manual_balance_assignments
                    SET balance_state='FIXED',source=?,target_stop=COALESCE(?,target_stop),
                        updated_at=CURRENT_TIMESTAMP WHERE session_id=? AND item_id=?""",
                    ('fixed', target_stop, session_id, int(item_id)))
        else:
            if int(row.get('cycle') or 0) == 1 and row.get('source') == 'fixed':
                raise ValueError('Itens de planos 1P são fixos e não podem ser destrancados.')
            if row.get('balance_state') == 'FIXED':
                conn.execute("""UPDATE manual_balance_assignments
                    SET balance_state=?,source=?,updated_at=CURRENT_TIMESTAMP
                    WHERE session_id=? AND item_id=?""",
                    ('MANUAL', 'manual', session_id, int(item_id)))

        conn.execute("""UPDATE manual_balance_sessions
            SET version=version+1,updated_at=CURRENT_TIMESTAMP WHERE id=?""", (session_id,))
        conn.commit()
        return {'item_id': int(item_id), 'locked': bool(locked),
                'session': get_active_session(project_id)}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def return_to_book(project_id, session_id, item_ids):
    item_ids = [int(x) for x in item_ids]
    conn = get_db_connection()
    try:
        conn.execute('BEGIN IMMEDIATE')
        session = _session_row(conn, session_id=session_id)
        if not session or int(session['project_id']) != int(project_id):
            raise ValueError('Rascunho manual não encontrado.')
        placeholders = ','.join('?' for _ in item_ids)
        conn.execute(f"""UPDATE manual_balance_assignments SET target_plan_id=NULL,target_stop=NULL,
            balance_state='PENDING',source='manual',updated_at=CURRENT_TIMESTAMP
            WHERE session_id=? AND item_id IN ({placeholders}) AND balance_state<>'FIXED'""",
            (session_id, *item_ids))
        changed = conn.total_changes
        conn.execute("UPDATE manual_balance_sessions SET version=version+1,updated_at=CURRENT_TIMESTAMP WHERE id=?",
                     (session_id,))
        conn.commit()
        return {'returned': changed, 'session': get_active_session(project_id)}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def complete_session(project_id, session_id, allow_pending=False):
    conn = get_db_connection()
    try:
        conn.execute('BEGIN IMMEDIATE')
        session = _session_row(conn, session_id=session_id)
        if not session or int(session['project_id']) != int(project_id):
            raise ValueError('Rascunho manual não encontrado.')
        pending = conn.execute("SELECT COUNT(*) FROM manual_balance_assignments WHERE session_id=? AND balance_state='PENDING'",
                               (session_id,)).fetchone()[0]
        if pending and not allow_pending:
            raise ValueError(f'Existem {pending} item(ns) pendentes. Balanceie-os ou confirme a conclusão com pendências.')
        conn.execute("""UPDATE maintenance_items SET plan_id=(SELECT a.target_plan_id
            FROM manual_balance_assignments a WHERE a.session_id=? AND a.item_id=maintenance_items.id),
            updated_at=CURRENT_TIMESTAMP WHERE project_id=? AND id IN
            (SELECT item_id FROM manual_balance_assignments WHERE session_id=? AND target_plan_id IS NOT NULL)""",
            (session_id, project_id, session_id))
        conn.execute("""UPDATE manual_balance_sessions SET status='COMPLETED',completed_at=CURRENT_TIMESTAMP,
            updated_at=CURRENT_TIMESTAMP,version=version+1 WHERE id=?""", (session_id,))
        conn.commit()
        return {'completed': True, 'pending_preserved': pending}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def discard_session(project_id, session_id):
    conn = get_db_connection()
    try:
        row = _session_row(conn, session_id=session_id)
        if not row or int(row['project_id']) != int(project_id):
            raise ValueError('Rascunho manual não encontrado.')
        conn.execute("UPDATE manual_balance_sessions SET status='DISCARDED',updated_at=CURRENT_TIMESTAMP WHERE id=?",
                     (session_id,))
        conn.commit()
        return {'discarded': True}
    finally:
        conn.close()


def discard_active_sessions(project_id):
    """Invalidate drafts that no longer match a restored official scenario."""
    conn = get_db_connection()
    try:
        cursor = conn.execute("""UPDATE manual_balance_sessions
            SET status='DISCARDED',updated_at=CURRENT_TIMESTAMP
            WHERE project_id=? AND status='DRAFT'""", (project_id,))
        conn.commit()
        return cursor.rowcount
    finally:
        conn.close()
