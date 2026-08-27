"""Automatic PM13 balancing with horizontal/vertical strategies and rules."""

import json
import math
import random
import re
import time
import unicodedata

from core.audit_service import log_action
from core.balance_rules import evaluate_rules, find_feasible_assignment, normalize_rules
from core.calculations import get_plan_occurrences
from core.database import get_db_connection


def _clean_text(text):
    return unicodedata.normalize('NFKD', str(text or '')).encode('ascii', 'ignore').decode().upper()


def _extract_machine_tag(text, object_code=None):
    cleaned = _clean_text(text).replace('_', '')
    match = re.match(r'^([A-Z0-9]+(?:[.\-][A-Z0-9]+)?(?:\s+[0-9]+)?)', cleaned)
    if match:
        tag = re.sub(r'\s+(MANUT|PREV|PREVENTIVA|MOTOR|MECANICA|ELETRICA|LUBRIFICACAO)$',
                     '', match.group(1).strip())
        if len(tag) >= 2:
            return tag
    if object_code and str(object_code).strip().upper() not in ('SEM_EQUIPAMENTO', 'GERAL', 'NONE'):
        return str(object_code).strip().upper()
    return cleaned.split()[0] if cleaned else 'UNKNOWN'


def get_plan_prefix9(legacy_code):
    code = str(legacy_code or '').strip().upper()
    return code[:9] if len(code) >= 9 else code


def _metrics(loads):
    values = [round(float(value), 4) for value in loads]
    if not values:
        return {'total_hh': 0.0, 'average_hh': 0.0, 'max_hh': 0.0, 'min_hh': 0.0,
                'range_hh': 0.0, 'std_dev': 0.0, 'coefficient_variation': 0.0}
    average = sum(values) / len(values)
    variance = sum((value - average) ** 2 for value in values) / len(values)
    deviation = math.sqrt(variance)
    return {
        'total_hh': round(sum(values), 1), 'average_hh': round(average, 1),
        'max_hh': round(max(values), 1), 'min_hh': round(min(values), 1),
        'range_hh': round(max(values) - min(values), 1), 'std_dev': round(deviation, 2),
        'coefficient_variation': round((deviation / average * 100) if average else 0.0, 2),
    }


def _fast_score(loads):
    if not loads:
        return 0.0
    average = sum(loads) / len(loads)
    variance = sum((value - average) ** 2 for value in loads) / len(loads)
    return variance + max(loads) * 0.03 + (max(loads) - min(loads)) * 0.02


def list_rules(project_id):
    conn = get_db_connection()
    try:
        rows = conn.execute("""SELECT id,name,rule_type,item_ids_json,enforcement,config_json,active
            FROM auto_balance_rules WHERE project_id=? AND active=1 ORDER BY id""", (project_id,)).fetchall()
        return [{
            'id': row['id'], 'name': row['name'], 'type': row['rule_type'],
            'item_ids': json.loads(row['item_ids_json'] or '[]'),
            'enforcement': row['enforcement'] or 'mandatory',
            'config': json.loads(row['config_json'] or '{}'),
        } for row in rows]
    finally:
        conn.close()


def get_preferences(project_id):
    conn = get_db_connection()
    try:
        row = conn.execute("""SELECT balance_strategy,geography_mode,vertical_tolerance,
            similarity_enabled,balance_max_passes FROM project_settings WHERE project_id=?""",
            (project_id,)).fetchone()
        if not row:
            return {'distribution_strategy': 'horizontal', 'geography_mode': 'preferred',
                    'vertical_tolerance': 10, 'similarity_enabled': True, 'max_passes': 50}
        return {
            'distribution_strategy': row['balance_strategy'] or 'horizontal',
            'geography_mode': row['geography_mode'] or 'preferred',
            'vertical_tolerance': float(row['vertical_tolerance'] or 0),
            'similarity_enabled': bool(row['similarity_enabled']),
            'max_passes': int(row['balance_max_passes'] or 50),
        }
    finally:
        conn.close()


def save_preferences(project_id, strategy, geography_mode, vertical_tolerance,
                     similarity_enabled, max_passes):
    conn = get_db_connection()
    try:
        conn.execute("""UPDATE project_settings SET balance_strategy=?,geography_mode=?,
            vertical_tolerance=?,similarity_enabled=?,balance_max_passes=?,updated_at=CURRENT_TIMESTAMP
            WHERE project_id=?""", (
            strategy, geography_mode, float(vertical_tolerance or 0),
            1 if similarity_enabled else 0, int(max_passes or 50), project_id))
        conn.commit()
    finally:
        conn.close()


def save_rules(project_id, rules):
    normalized = normalize_rules(rules or [])
    conn = get_db_connection()
    try:
        conn.execute('DELETE FROM auto_balance_rules WHERE project_id=?', (project_id,))
        for rule in normalized:
            conn.execute("""INSERT INTO auto_balance_rules
                (project_id,name,rule_type,item_ids_json,enforcement,config_json,active)
                VALUES (?,?,?,?,?,?,1)""", (
                project_id, rule['name'], rule['type'], json.dumps(rule['item_ids']),
                rule['enforcement'], json.dumps(rule.get('config') or {})))
        conn.commit()
    finally:
        conn.close()


def _load_data(project_id):
    conn = get_db_connection()
    try:
        project = conn.execute("""SELECT id,current_counter,default_horizon,
            hours_per_person,tool_time_percent
            FROM projects WHERE id=? AND deleted_at IS NULL""", (project_id,)).fetchone()
        if not project:
            raise ValueError('Projeto não encontrado.')
        plans = [dict(row) for row in conn.execute("""SELECT id,legacy_code,description,cycle,unit,
            reference_counter,phase FROM plans WHERE project_id=? AND deleted_at IS NULL
            AND status='ACTIVE' AND cycle>0 ORDER BY cycle DESC,legacy_code""", (project_id,)).fetchall()]
        items = [dict(row) for row in conn.execute("""SELECT i.id,i.legacy_identifier,i.description,
            i.object_code,i.plan_id,p.legacy_code plan_code,p.cycle,p.reference_counter,
            CASE WHEN (COALESCE(i.mec_headcount,0)*COALESCE(i.mec_hours,0)+
                            COALESCE(i.ele_headcount,0)*COALESCE(i.ele_hours,0)+
                            COALESCE(i.sol_headcount,0)*COALESCE(i.sol_hours,0))>0
                 THEN (COALESCE(i.mec_headcount,0)*COALESCE(i.mec_hours,0)+
                       COALESCE(i.ele_headcount,0)*COALESCE(i.ele_hours,0)+
                       COALESCE(i.sol_headcount,0)*COALESCE(i.sol_hours,0))
                 ELSE COALESCE(i.duration_hours,0)*COALESCE(i.headcount,1) END hh,
            COALESCE(i.mec_headcount,0)*COALESCE(i.mec_hours,0) mec_hh,
            COALESCE(i.ele_headcount,0)*COALESCE(i.ele_hours,0) ele_hh,
            COALESCE(i.sol_headcount,0)*COALESCE(i.sol_hours,0) sol_hh
            FROM maintenance_items i JOIN plans p ON p.id=i.plan_id
            WHERE i.project_id=? AND i.deleted_at IS NULL AND i.status='ACTIVE'
              AND p.deleted_at IS NULL AND p.status='ACTIVE' AND p.cycle>0
            ORDER BY p.cycle DESC,p.legacy_code,CAST(i.legacy_identifier AS INTEGER),i.legacy_identifier""",
            (project_id,)).fetchall()]
        return dict(project), plans, items
    finally:
        conn.close()


def _add_item(loads, trade_loads, item, stops, sign=1):
    hh = float(item['hh']) * sign
    for stop in stops:
        loads[stop] += hh
        for trade in ('mec', 'ele', 'sol'):
            trade_loads[trade][stop] += float(item.get(f'{trade}_hh') or 0.0) * sign


def _identifier_key(item):
    value = str(item.get('legacy_identifier') or '')
    return (0, int(value), value) if value.isdigit() else (1, 10**15, value)


def optimize(project_id, rules=None, horizon=None, max_passes=100, timeout_seconds=30.0,
             similarity_enabled=True, distribution_strategy='horizontal', geography_mode='off',
             vertical_tolerance=10.0, capacities=None, manual_session_id=None,
             preserve_manual=True):
    started = time.time()
    timeout_seconds = min(30.0, max(0.1, float(timeout_seconds or 30)))
    deadline = started + timeout_seconds

    def check_deadline():
        if time.time() >= deadline:
            limit_label = f'{timeout_seconds:.1f}' if timeout_seconds < 1 else f'{timeout_seconds:.0f}'
            raise TimeoutError(
                f'Balanceamento interrompido após {limit_label} segundos. '
                'Reduza a quantidade de varreduras ou simplifique as regras.')
    project, plans, items = _load_data(project_id)
    horizon = int(horizon or project['default_horizon'] or 12)
    if not 2 <= horizon <= 120:
        raise ValueError('O horizonte deve ter entre 2 e 120 paradas.')
    strategy = str(distribution_strategy or 'horizontal').lower()
    if strategy not in ('horizontal', 'vertical'):
        raise ValueError("Estratégia inválida. Use 'horizontal' ou 'vertical'.")
    geography_mode = str(geography_mode or 'off').lower()
    if geography_mode not in ('off', 'preferred', 'mandatory'):
        raise ValueError('Modo de agrupamento geográfico inválido.')
    tolerance = max(0.0, min(100.0, float(vertical_tolerance or 0))) / 100.0
    capacities = {key: (None if value in (None, '') else max(0.0, float(value)))
                  for key, value in dict(capacities or {}).items()}
    current_counter = int(project['current_counter'])
    start_counter = current_counter + 1
    plan_by_id = {int(plan['id']): plan for plan in plans}
    item_by_id = {int(item['id']): item for item in items}

    plan_stops = {}
    for plan in plans:
        pid = int(plan['id']); cycle = int(plan['cycle'])
        reference = int(plan['reference_counter']) if plan['reference_counter'] is not None else start_counter
        plan_stops[pid] = [counter - start_counter for counter in
                           get_plan_occurrences(reference, cycle, current_counter, horizon)]

    initial = {int(item['id']): int(item['plan_id']) for item in items}
    # The original plan is the immutable family reference for this run. A
    # draft may contain a manual exception, but automatic balancing must never
    # use that exception to migrate the item into another 9-character family.
    origin = dict(initial)
    locked = {int(item['id']) for item in items if int(item['cycle']) == 1}
    eligible = set(initial)
    draft_states = {}
    baseline_manual = set()
    if manual_session_id:
        conn = get_db_connection()
        try:
            session = conn.execute("""SELECT id FROM manual_balance_sessions
                WHERE id=? AND project_id=? AND status='DRAFT'""",
                (int(manual_session_id), project_id)).fetchone()
            if not session:
                raise ValueError('Rascunho manual não encontrado.')
            incompatible_locked = []
            for row in conn.execute("""SELECT item_id,original_plan_id,target_plan_id,balance_state
                FROM manual_balance_assignments WHERE session_id=?""", (manual_session_id,)):
                iid = int(row['item_id'])
                # Inactive items deliberately keep their draft assignment so a
                # future reactivation can restore the exact position/lock. They
                # are absent from _load_data and must not participate in this
                # automatic run.
                if iid not in item_by_id:
                    continue
                draft_states[iid] = row['balance_state']
                if row['original_plan_id'] and int(row['original_plan_id']) in plan_by_id:
                    origin[iid] = int(row['original_plan_id'])
                # Compatibility for drafts created before baseline positions
                # were stored as AUTOMATIC: MANUAL on the unchanged original
                # plan means "not explicitly moved" and remains balanceable.
                if (row['balance_state'] == 'MANUAL' and row['target_plan_id']
                        and row['original_plan_id']
                        and int(row['target_plan_id']) == int(row['original_plan_id'])):
                    baseline_manual.add(iid)
                if row['target_plan_id'] and (preserve_manual or row['balance_state'] == 'FIXED'):
                    initial[iid] = int(row['target_plan_id'])
                elif not preserve_manual:
                    initial[iid] = origin[iid]
                if (row['balance_state'] == 'FIXED' or
                        (preserve_manual and row['balance_state'] == 'MANUAL'
                         and iid not in baseline_manual)):
                    locked.add(iid)
                    target_id = int(row['target_plan_id'] or origin[iid])
                    source_plan = plan_by_id[origin[iid]]
                    target_plan = plan_by_id.get(target_id)
                    if (not target_plan or
                            int(target_plan['cycle']) != int(source_plan['cycle']) or
                            get_plan_prefix9(target_plan['legacy_code']) != get_plan_prefix9(source_plan['legacy_code'])):
                        incompatible_locked.append(iid)
            if incompatible_locked:
                labels = ', '.join(str(item_by_id[iid]['legacy_identifier']) for iid in incompatible_locked[:10])
                raise ValueError(
                    'O automático não pode preservar item(ns) manual(is) fora da família original '
                    f'dos 9 primeiros caracteres: {labels}. Rebalanceie tudo ou devolva-os ao Book.')
            # FIXED is an absolute lock, independent of whether the caller
            # chooses to preserve other manual placements.
            eligible.difference_update(locked)
            if preserve_manual:
                # Preserve only explicit user decisions. Items positioned by a
                # previous automatic run must remain eligible, otherwise a
                # second run has zero movable candidates and falsely reports
                # 0% improvement even when the horizon/settings changed.
                eligible = {iid for iid in eligible
                            if (draft_states.get(iid) in ('PENDING', 'AUTOMATIC')
                                or iid in baseline_manual)}
        finally:
            conn.close()

    families = {}
    for plan in plans:
        key = (get_plan_prefix9(plan['legacy_code']), int(plan['cycle']))
        families.setdefault(key, []).append(int(plan['id']))
    candidate_plans = {}
    for iid, pid in origin.items():
        plan = plan_by_id[pid]
        key = (get_plan_prefix9(plan['legacy_code']), int(plan['cycle']))
        candidate_plans[iid] = sorted(families.get(key) or [pid])

    normalized_rules = normalize_rules(rules or [])
    for index, rule in enumerate(normalized_rules, 1):
        missing = [iid for iid in rule['item_ids'] if iid not in item_by_id]
        if missing:
            raise ValueError(f'Regra {index}: contém itens inexistentes ou inativos.')
        cycles = [int(plan_by_id[origin[iid]]['cycle']) for iid in rule['item_ids']]
        if rule['type'] == 'sequence' and len(set(cycles)) != 1:
            raise ValueError(f'Regra {index}: executar em sequência exige a mesma periodicidade.')
        if rule['type'] == 'sequence' and len(rule['item_ids']) > cycles[0]:
            raise ValueError(f'Regra {index}: há mais itens que fases no ciclo {cycles[0]}P.')
        if rule['type'] == 'separate' and 1 in cycles:
            raise ValueError(f'Regra {index}: um item 1P não pode usar “Não executar juntos”.')

    # Similarity and geographic adjacency maps.
    machine_groups = {}
    geo_groups = {}
    for item in items:
        iid = int(item['id']); plan = plan_by_id[origin[iid]]
        tag = _extract_machine_tag(item['description'], item.get('object_code'))
        if tag != 'UNKNOWN':
            machine_groups.setdefault(tag, []).append(iid)
        geo_groups.setdefault(get_plan_prefix9(plan['legacy_code']), []).append(item)
    similarity_pairs = {(min(a, b), max(a, b)) for group in machine_groups.values()
                        for a in group for b in group if a < b} if similarity_enabled else set()
    geography_pairs = set()
    if geography_mode != 'off':
        for group in geo_groups.values():
            group.sort(key=_identifier_key)
            for left, right in zip(group, group[1:]):
                geography_pairs.add((int(left['id']), int(right['id'])))

    def loads_for(assignments, include_ids=None):
        loads = [0.0] * horizon
        trades = {name: [0.0] * horizon for name in ('mec', 'ele', 'sol')}
        include_ids = set(assignments) if include_ids is None else set(include_ids)
        for iid in include_ids:
            _add_item(loads, trades, item_by_id[iid], plan_stops.get(assignments[iid], []))
        return loads, trades

    def pair_separations(assignments, pairs):
        separated = 0
        for index, (a, b) in enumerate(pairs):
            if index % 128 == 0:
                check_deadline()
            if not set(plan_stops.get(assignments[a], [])).intersection(plan_stops.get(assignments[b], [])):
                separated += 1
        return separated

    def solution_score(assignments, loads):
        hard_ok, preferred, _ = evaluate_rules(
            normalized_rules, assignments, plan_by_id, current_counter, horizon)
        if not hard_ok:
            return float('inf')
        average = max(1.0, sum(loads) / horizon)
        penalty = preferred * average
        penalty += pair_separations(assignments, similarity_pairs) * average * 0.03
        if geography_mode == 'preferred':
            penalty += pair_separations(assignments, geography_pairs) * average * 0.06
        return _fast_score(loads) + penalty

    # Capacity entered in Balanceamento is TOTAL people for the whole stop
    # (e.g. day 1 + day 2). Every person contributes the project-level
    # productive hours: hours_per_person * Tool Time.
    base_hours = float(project.get('hours_per_person') or 9.1)
    tool_time_percent = float(project.get('tool_time_percent') if project.get('tool_time_percent') is not None else 100.0)
    if base_hours <= 0:
        base_hours = 9.1
    if tool_time_percent <= 0 or tool_time_percent > 100:
        tool_time_percent = 100.0
    productive_hours_per_person = base_hours * (tool_time_percent / 100.0)

    def capacities_ok(trades):
        for trade in ('mec', 'ele', 'sol'):
            cap = capacities.get(trade)
            if cap is not None and any(
                    value > cap * productive_hours_per_person + 1e-9
                    for value in trades[trade]):
                return False
        return True

    def capacity_overflow(trades):
        overflow = 0.0
        for trade in ('mec', 'ele', 'sol'):
            cap = capacities.get(trade)
            if cap is None:
                continue
            limit = cap * productive_hours_per_person
            overflow += sum(max(0.0, value - limit) for value in trades[trade])
        return overflow

    before_ids = set(initial)
    if manual_session_id:
        before_ids = {iid for iid in initial if draft_states.get(iid) != 'PENDING'}
    before_loads, _ = loads_for(initial, before_ids)
    before_metrics = _metrics(before_loads)

    # Mandatory rules receive a feasible phase combination first.
    seed = dict(initial)
    for rule in normalized_rules:
        if rule['enforcement'] != 'mandatory':
            continue
        def combo_score(changes):
            trial = dict(seed); trial.update(changes)
            candidate_loads, _ = loads_for(trial)
            return _fast_score(candidate_loads)
        solved = find_feasible_assignment(
            rule, candidate_plans, plan_by_id, current_counter, horizon, combo_score,
            deadline_callback=check_deadline)
        if not solved:
            labels = [f"{plan_by_id[seed[iid]]['cycle']}P" for iid in rule['item_ids']]
            raise ValueError(f"Regra obrigatória '{rule['name']}' é inviável para " + ', '.join(labels) + '.')
        seed.update(solved)
        locked.update(rule['item_ids'])

    # Mandatory geography treats each 9-character group as one co-occurrence
    # block when a feasible phase combination exists.
    if geography_mode == 'mandatory':
        for family, group in geo_groups.items():
            ids = [int(item['id']) for item in group if int(item['cycle']) > 1]
            if len(ids) < 2:
                continue
            geo_rule = {'name': f'Geografia {family}', 'type': 'together',
                        'enforcement': 'mandatory', 'item_ids': ids}
            solved = find_feasible_assignment(
                geo_rule, candidate_plans, plan_by_id, current_counter, horizon,
                lambda changes: _fast_score(loads_for({**seed, **changes})[0]),
                max_combinations=30000, deadline_callback=check_deadline)
            if not solved:
                raise ValueError(f'Agrupamento geográfico obrigatório inviável para a família {family}.')
            seed.update(solved); locked.update(ids)

    seed_loads, seed_trades = loads_for(seed)
    _, locked_trades = loads_for(seed, locked)
    if not capacities_ok(locked_trades):
        raise ValueError('As cargas fixas/regras já ultrapassam a capacidade rígida informada.')

    vertical_target = None
    sequence_skips = 0
    passes = 1
    snapshots = []

    if strategy == 'vertical':
        assignments = dict(seed)
        fixed = set(locked)
        loads, trades = loads_for(assignments, fixed)
        total_loads, _ = loads_for(assignments)
        vertical_target = sum(total_loads) / horizon
        limit = vertical_target * (1 + tolerance)
        movable = sorted((item for item in items
                          if int(item['id']) in eligible and int(item['id']) not in fixed), key=_identifier_key)
        remaining = {int(item['id']) for item in movable}
        for focus in range(horizon):
            check_deadline()
            for item in movable:
                check_deadline()
                iid = int(item['id'])
                if iid not in remaining:
                    continue
                candidates = [pid for pid in candidate_plans[iid] if focus in plan_stops.get(pid, [])]
                best = None
                for pid in candidates:
                    trial_loads = list(loads); trial_trades = {k: list(v) for k, v in trades.items()}
                    _add_item(trial_loads, trial_trades, item, plan_stops.get(pid, []))
                    trial_assignments = {**assignments, iid: pid}
                    overflow = max([0.0] + [trial_loads[s] - limit for s in plan_stops.get(pid, [])])
                    key = (overflow > 0 or not capacities_ok(trial_trades), overflow,
                           abs(trial_loads[focus] - vertical_target), solution_score(trial_assignments, trial_loads), pid)
                    if best is None or key < best[0]:
                        best = (key, pid, trial_loads, trial_trades)
                if best and not best[0][0]:
                    assignments[iid] = best[1]; loads, trades = best[2], best[3]; remaining.remove(iid)
                elif candidates:
                    sequence_skips += 1
        # Final pass positions every remaining item by the smallest safe/global impact.
        for item in movable:
            check_deadline()
            iid = int(item['id'])
            if iid not in remaining:
                continue
            best = None
            for pid in candidate_plans[iid]:
                trial_loads = list(loads); trial_trades = {k: list(v) for k, v in trades.items()}
                _add_item(trial_loads, trial_trades, item, plan_stops.get(pid, []))
                key = (not capacities_ok(trial_trades), solution_score({**assignments, iid: pid}, trial_loads),
                       max(trial_loads), pid)
                if best is None or key < best[0]:
                    best = (key, pid, trial_loads, trial_trades)
            if best:
                assignments[iid] = best[1]; loads, trades = best[2], best[3]; remaining.remove(iid)
        final_assignments, final_loads = assignments, loads
        snapshots.append({'pass': 1, 'gap': _metrics(loads)['range_hh'],
                          'std_dev': _metrics(loads)['std_dev'], 'is_champion': True})
    else:
        champion_assignments = dict(seed)
        champion_loads = list(seed_loads)
        champion_score = solution_score(champion_assignments, champion_loads)
        champion_overflow = capacity_overflow(seed_trades)
        max_passes = min(2000, max(1, int(max_passes or 100)))
        no_improvement = 0
        family_rows = [(key, ids) for key, ids in families.items() if len(ids) > 1 and key[1] > 1]
        item_family = {}
        for iid, pid in origin.items():
            plan = plan_by_id[pid]
            item_family.setdefault((get_plan_prefix9(plan['legacy_code']), int(plan['cycle'])), []).append(iid)
        for pass_number in range(1, max_passes + 1):
            passes = pass_number
            check_deadline()
            assignments = dict(seed); loads = list(seed_loads); trades = {k: list(v) for k, v in seed_trades.items()}
            rng = random.Random(pass_number * 1000 + 42)
            families_pass = list(family_rows)
            if pass_number > 1:
                rng.shuffle(families_pass)
            for family_key, siblings in families_pass:
                check_deadline()
                family_items = list(item_family.get(family_key, []))
                if pass_number > 1:
                    rng.shuffle(family_items)
                for iid in family_items:
                    check_deadline()
                    if iid in locked or iid not in eligible:
                        continue
                    item = item_by_id[iid]; current_pid = assignments[iid]
                    old_stops = plan_stops.get(current_pid, [])
                    current_overflow = capacity_overflow(trades)
                    best = (current_overflow, solution_score(assignments, loads), current_pid, None, None)
                    for pid in candidate_plans[iid]:
                        check_deadline()
                        if pid == current_pid:
                            continue
                        trial_loads = list(loads); trial_trades = {k: list(v) for k, v in trades.items()}
                        _add_item(trial_loads, trial_trades, item, old_stops, -1)
                        _add_item(trial_loads, trial_trades, item, plan_stops.get(pid, []), 1)
                        trial_overflow = capacity_overflow(trial_trades)
                        if trial_overflow > current_overflow + 1e-9:
                            continue
                        trial_assignments = {**assignments, iid: pid}
                        score = solution_score(trial_assignments, trial_loads)
                        if (trial_overflow, score, pid) < (best[0], best[1], best[2]):
                            best = (trial_overflow, score, pid, trial_loads, trial_trades)
                    if best[2] != current_pid:
                        assignments[iid] = best[2]; loads, trades = best[3], best[4]
            score = solution_score(assignments, loads)
            overflow = capacity_overflow(trades)
            metrics = _metrics(loads)
            champion_metrics = _metrics(champion_loads)
            is_better = ((overflow, metrics['range_hh'], metrics['std_dev'], score) <
                         (champion_overflow, champion_metrics['range_hh'],
                          champion_metrics['std_dev'], champion_score))
            if is_better:
                champion_assignments, champion_loads, champion_score = dict(assignments), list(loads), score
                champion_overflow = overflow
                no_improvement = 0
            else:
                no_improvement += 1
            if is_better or pass_number == 1 or pass_number == max_passes or pass_number % max(1, max_passes // 20) == 0:
                snapshots.append({'pass': pass_number, 'gap': metrics['range_hh'],
                                  'std_dev': metrics['std_dev'], 'is_champion': is_better})
            if pass_number >= 40 and no_improvement >= 120:
                break
        final_assignments, final_loads = champion_assignments, champion_loads

    _, final_trades = loads_for(final_assignments)
    if not capacities_ok(final_trades):
        raise ValueError('Não foi possível atender às capacidades informadas com as regras e famílias disponíveis.')

    after_metrics = _metrics(final_loads)
    geo_separated = pair_separations(final_assignments, geography_pairs) if geography_pairs else 0
    geo_preserved = max(0, len(geography_pairs) - geo_separated)
    final_ok, _, diagnostics = evaluate_rules(
        normalized_rules, final_assignments, plan_by_id, current_counter, horizon)
    if not final_ok:
        failures = [d for d in diagnostics if d['enforcement'] == 'mandatory' and not d['satisfied']]
        raise ValueError('Não foi possível cumprir: ' + '; '.join(f"{d['name']}: {d['message']}" for d in failures))
    family_violations = []
    for iid, new_pid in final_assignments.items():
        source_plan = plan_by_id[origin[iid]]
        target_plan = plan_by_id[new_pid]
        if (int(source_plan['cycle']) != int(target_plan['cycle']) or
                get_plan_prefix9(source_plan['legacy_code']) != get_plan_prefix9(target_plan['legacy_code'])):
            family_violations.append(str(item_by_id[iid]['legacy_identifier']))
    if family_violations:
        raise ValueError(
            'Proteção de família interrompeu o balanceamento automático. Item(ns): ' +
            ', '.join(family_violations[:10]))
    changes = []
    for item in items:
        iid = int(item['id']); old_pid = initial[iid]; new_pid = final_assignments.get(iid, old_pid)
        if old_pid != new_pid:
            changes.append({
                'item_id': iid, 'item_identifier': item['legacy_identifier'],
                'description': item['description'], 'hh': round(float(item['hh']), 1),
                'old_plan_id': old_pid, 'old_plan_code': plan_by_id[old_pid]['legacy_code'],
                'new_plan_id': new_pid, 'new_plan_code': plan_by_id[new_pid]['legacy_code'],
            })
    improvement = ((before_metrics['std_dev'] - after_metrics['std_dev']) /
                   before_metrics['std_dev'] * 100) if before_metrics['std_dev'] else 0.0
    before_gap = before_metrics['range_hh']
    gap_improvement = ((before_gap - after_metrics['range_hh']) / before_gap * 100) if before_gap else 0.0
    champion_pass = next((s['pass'] for s in reversed(snapshots) if s['is_champion']), 1)
    return {
        'project_id': project_id, 'horizon': horizon, 'start_counter': start_counter,
        'rules': normalized_rules, 'rule_diagnostics': diagnostics,
        'distribution_strategy': strategy, 'geography_mode': geography_mode,
        'geographic_pairs_analyzed': len(geography_pairs),
        'geographic_pairs_preserved': geo_preserved,
        'geographic_pairs_separated': geo_separated,
        'vertical_target_hh': round(vertical_target, 1) if vertical_target is not None else None,
        'sequence_skips': sequence_skips, 'total_passes_run': passes,
        'champion_pass': champion_pass, 'passes_summary': snapshots,
        'changes': [], 'item_changes': changes,
        'assignment_results': [{'item_id': iid, 'plan_id': final_assignments[iid]}
                               for iid in sorted(eligible)],
        'before': before_metrics, 'after': after_metrics, 'before_gap': before_gap,
        'after_gap': after_metrics['range_hh'], 'gap_improvement_percent': round(gap_improvement, 1),
        'improvement_percent': round(improvement, 1),
        'stops_before': [round(value, 1) for value in before_loads],
        'stops_after': [round(value, 1) for value in final_loads],
        'plans_analyzed': len(plans), 'plans_changed': 0, 'items_reassigned': len(changes),
        'elapsed_seconds': round(time.time() - started, 2),
    }


def apply(project_id, rules=None, horizon=None, max_passes=100, timeout_seconds=30.0,
          similarity_enabled=True, distribution_strategy='horizontal', geography_mode='off',
          vertical_tolerance=10.0, capacities=None, manual_session_id=None,
          preserve_manual=True):
    result = optimize(
        project_id, rules, horizon, max_passes, timeout_seconds, similarity_enabled,
        distribution_strategy, geography_mode, vertical_tolerance, capacities,
        manual_session_id, preserve_manual)
    conn = get_db_connection()
    try:
        conn.execute('BEGIN IMMEDIATE')
        if manual_session_id:
            for assignment in result['assignment_results']:
                if preserve_manual:
                    state_sql = "CASE WHEN balance_state IN ('MANUAL','FIXED') THEN balance_state ELSE 'AUTOMATIC' END"
                    source_sql = "CASE WHEN balance_state IN ('MANUAL','FIXED') THEN source ELSE 'automatic' END"
                else:
                    state_sql = "CASE WHEN balance_state='FIXED' THEN 'FIXED' ELSE 'AUTOMATIC' END"
                    source_sql = "CASE WHEN balance_state='FIXED' THEN 'fixed' ELSE 'automatic' END"
                conn.execute(f"""UPDATE manual_balance_assignments SET target_plan_id=?,
                    balance_state={state_sql},source={source_sql},updated_at=CURRENT_TIMESTAMP
                    WHERE session_id=? AND item_id=?""",
                    (assignment['plan_id'], manual_session_id, assignment['item_id']))
            conn.execute("UPDATE manual_balance_sessions SET version=version+1,updated_at=CURRENT_TIMESTAMP WHERE id=?",
                         (manual_session_id,))
        else:
            for change in result['item_changes']:
                conn.execute("""UPDATE maintenance_items SET plan_id=?,updated_at=CURRENT_TIMESTAMP
                    WHERE id=? AND project_id=? AND deleted_at IS NULL""",
                    (change['new_plan_id'], change['item_id'], project_id))
        conn.commit()
        save_rules(project_id, rules or [])
        save_preferences(project_id, distribution_strategy, geography_mode,
                         vertical_tolerance, similarity_enabled, max_passes)
        log_action(project_id, 'AUTO_BALANCE', project_id, 'APPLY', {
            'rules': rules, 'horizon': result['horizon'], 'strategy': distribution_strategy,
            'geography_mode': geography_mode, 'manual_session_id': manual_session_id,
        }, {'improvement_percent': result['improvement_percent'],
            'items_reassigned': result['items_reassigned']})
        return result
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
