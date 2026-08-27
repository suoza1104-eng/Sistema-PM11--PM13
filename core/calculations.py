import math
from core.database import get_db_connection

def is_all_filter(val):
    if not val:
        return True
    s = str(val).strip().lower()
    if s in ['', 'undefined', 'null', 'none', 'all', 'todas', 'todos', 'sem agrupamento']:
        return True
    if s.startswith('todos') or s.startswith('todas'):
        return True
    return False

def calculate_next_occurrence(reference_counter, cycle, current_counter):
    """Calculates the next occurrence stop number >= current_counter.
    For R (ref), C (cycle), and S (current), returns the smallest S_next >= S
    such that S_next >= R and (S_next - R) % C == 0.
    """
    if reference_counter is None or cycle is None or cycle <= 0:
        return None
    if reference_counter >= current_counter:
        return reference_counter
        
    rem = (current_counter - reference_counter) % cycle
    if rem == 0:
        return current_counter
    else:
        return current_counter + (cycle - rem)

def get_plan_occurrences(reference_counter, cycle, current_counter, horizon_count):
    """Returns the future stop counters where a plan occurs.

    Scheduling is controlled exclusively by the plan: reference_counter defines
    the phase/anchor and cycle defines the recurrence. Item legacy_start (PRD
    INÍCIO) is intentionally not part of this calculation.
    """
    if reference_counter is None or cycle is None or cycle <= 0:
        return []

    start_stop = current_counter + 1
    end_stop = current_counter + horizon_count

    occurrences = []
    for S in range(start_stop, end_stop + 1):
        if (S - reference_counter) % cycle == 0:
            occurrences.append(S)

    return occurrences

def plan_occurs_on_stop(reference_counter, cycle, stop_counter):
    """Return True when the plan is due on ``stop_counter``.

    This is the single rule used by stop detail/export endpoints so they stay
    identical to ``get_plan_occurrences``. The item-level legacy_start field is
    legacy/import metadata only and must never shift an order away from its
    plan's phase.
    """
    try:
        if reference_counter is None or cycle is None or stop_counter is None:
            return False
        reference_counter = int(reference_counter)
        cycle = int(cycle)
        stop_counter = int(stop_counter)
    except (TypeError, ValueError):
        return False

    if cycle <= 0:
        return False
    return (stop_counter - reference_counter) % cycle == 0

def get_project_shifts_and_hours(cursor, project_id):
    """Backward-compatible name for the unified project capacity rule.

    Team schedules and the old shift list do not affect balance capacity.
    One person contributes hours_per_person * tool_time_percent / 100 HH.
    """
    cursor.execute(
        "SELECT hours_per_person, tool_time_percent FROM projects WHERE id = ?;",
        (project_id,)
    )
    proj = cursor.fetchone()
    hours = float(proj['hours_per_person'] if proj and proj['hours_per_person'] is not None else 9.1)
    tool_percent = float(proj['tool_time_percent'] if proj and proj['tool_time_percent'] is not None else 100.0)
    if hours <= 0:
        hours = 9.1
    if tool_percent <= 0 or tool_percent > 100:
        tool_percent = 100.0
    util_factor = tool_percent / 100.0
    productive_hours = hours * util_factor
    return hours, util_factor, productive_hours

def project_balance(project_id, filters=None, grouping=None):
    """Projects stops workload, HH, orders quantity and headcount.
    Supports filters (dict) and grouping (string: 'work_center', 'gpm', 'condition_code', 'priority', 'cycle', 'plans', 'none').
    """
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        
        # 1. Get project info (current counter, horizon)
        cursor.execute("SELECT current_counter, default_horizon FROM projects WHERE id = ?;", (project_id,))
        proj = cursor.fetchone()
        if not proj:
            raise ValueError(f"Projeto {project_id} não encontrado.")
            
        current_counter = proj['current_counter']
        horizon = proj['default_horizon']
        if filters and filters.get('horizon'):
            try:
                horizon = int(filters['horizon'])
            except (ValueError, TypeError):
                pass
        
        # Get shift hours
        base_hours, util_factor, prod_hours = get_project_shifts_and_hours(cursor, project_id)
        if prod_hours <= 0:
            prod_hours = 9.1  # defensive fallback; valid settings are always > 0
            
        # 2. Build items query with associated plan info
        # Only active items (deleted_at is null and status = 'ACTIVE')
        # Only active plans (deleted_at is null and status = 'ACTIVE')
        manual_session_id = None
        if filters and filters.get('manual_session_id'):
            try:
                manual_session_id = int(filters.get('manual_session_id'))
            except (TypeError, ValueError):
                pass
        if manual_session_id:
            plan_select = """ep.id as plan_id, ep.legacy_code as plan_code,
                ep.description as plan_description, ep.cycle, ep.unit,
                ep.reference_counter, ep.phase as plan_phase,
                mba.balance_state as manual_balance_state"""
            plan_joins = """LEFT JOIN manual_balance_assignments mba
                    ON mba.item_id=i.id AND mba.session_id=?
                LEFT JOIN plans ep ON ep.id=mba.target_plan_id"""
            plan_predicate = """AND mba.id IS NOT NULL AND mba.balance_state<>'PENDING'
                AND ep.deleted_at IS NULL AND ep.status='ACTIVE'"""
            plan_id_expr = 'ep.id'
            cycle_expr = 'ep.cycle'
            params = [manual_session_id, project_id]
        else:
            plan_select = """p.id as plan_id, p.legacy_code as plan_code,
                p.description as plan_description, p.cycle, p.unit,
                p.reference_counter, p.phase as plan_phase,
                NULL as manual_balance_state"""
            plan_joins = 'LEFT JOIN plans p ON i.plan_id = p.id'
            plan_predicate = "AND p.deleted_at IS NULL AND p.status='ACTIVE'"
            plan_id_expr = 'p.id'
            cycle_expr = 'p.cycle'
            params = [project_id]
        query = f"""
        SELECT 
            i.id as item_id, i.legacy_identifier, i.object_code, i.gpm, i.work_center, 
            i.condition_code, i.priority, i.description as item_description, 
            i.duration_hours, i.headcount, i.hh, i.order_type,
            i.mec_headcount, i.mec_hours, i.ele_headcount, i.ele_hours, i.sol_headcount, i.sol_hours,
            {plan_select}
        FROM maintenance_items i
        {plan_joins}
        WHERE i.project_id = ? 
          AND i.deleted_at IS NULL 
          AND i.status = 'ACTIVE'
          {plan_predicate}
        """
        
        # Apply filters in Python to keep it simple or append to SQL.
        # Since we are fetching all items to project across stops, we filter in SQLite first.
        if filters:
            item_ids = [int(x) for x in str(filters.get('item_ids') or '').split(',') if x.strip().isdigit()]
            if item_ids:
                query += " AND i.id IN (" + ",".join("?" for _ in item_ids) + ")"
                params.extend(item_ids)
            plan_ids = [int(x) for x in str(filters.get('plan_ids') or '').split(',') if x.strip().isdigit()]
            if plan_ids:
                query += f" AND {plan_id_expr} IN (" + ",".join("?" for _ in plan_ids) + ")"
                params.extend(plan_ids)
            identifiers = [x.strip() for x in str(filters.get('item_identifiers') or '').split(',') if x.strip()]
            if identifiers:
                query += " AND i.legacy_identifier IN (" + ",".join("?" for _ in identifiers) + ")"
                params.extend(identifiers)
            wc = filters.get('work_center')
            if not is_all_filter(wc):
                query += " AND i.work_center = ?"
                params.append(str(wc).strip())
                
            gpm = filters.get('gpm')
            if not is_all_filter(gpm):
                query += " AND i.gpm = ?"
                params.append(str(gpm).strip())
                
            cond = filters.get('condition_code')
            if not is_all_filter(cond):
                query += " AND i.condition_code = ?"
                params.append(str(cond).strip())
                
            prio = filters.get('priority')
            if not is_all_filter(prio):
                try:
                    query += " AND i.priority = ?"
                    params.append(int(prio))
                except (ValueError, TypeError):
                    pass
                    
            cyc = filters.get('cycle')
            if not is_all_filter(cyc):
                try:
                    query += f" AND {cycle_expr} = ?"
                    params.append(int(cyc))
                except (ValueError, TypeError):
                    pass
                    
            pid = filters.get('plan_id')
            if not is_all_filter(pid):
                try:
                    query += f" AND {plan_id_expr} = ?"
                    params.append(int(pid))
                except (ValueError, TypeError):
                    pass
                    
            if filters.get('status'):
                query += " AND i.status = ?"
                params.append(filters['status'])
            if filters.get('search'):
                search_term = f"%{filters['search']}%"
                query += " AND (i.description LIKE ? OR i.legacy_identifier LIKE ? OR i.object_code LIKE ?)"
                params.extend([search_term, search_term, search_term])
                
        cursor.execute(query, params)
        items = cursor.fetchall()
        
        # Initialize stops structures
        start_stop = current_counter + 1
        end_stop = current_counter + horizon
        
        stops_range = list(range(start_stop, end_stop + 1))
        
        stops_data = {}
        for stop_num, S in enumerate(stops_range, start=1):
            stops_data[S] = {
                'stop_num': stop_num,
                'counter': S,
                'total_hh': 0.0,
                'total_duration': 0.0,
                'total_orders': 0,
                'headcount_float': 0.0,
                'headcount_needed': 0,
                'mec_hh': 0.0,
                'mec_headcount_float': 0.0,
                'mec_headcount_needed': 0,
                'ele_hh': 0.0,
                'ele_headcount_float': 0.0,
                'ele_headcount_needed': 0,
                'sol_hh': 0.0,
                'sol_headcount_float': 0.0,
                'sol_headcount_needed': 0,
                'grouped_hh': {},
                'grouped_orders': {},
                'grouped_headcount_float': {},
                'grouped_headcount': {}
            }
            
        items_skipped_count = 0
        items_without_headcount = 0

        # Single source of truth: effective HH per person for the whole stop.
        # The capacities typed in Balanceamento are TOTAL people (day 1 + day 2).
        hours_per_person = prod_hours
        
        for item in items:
            # PLAN = CLOCK. Every item inherits the recurrence of the plan it is
            # linked to. PRD INÍCIO / legacy_start is legacy/import metadata and
            # must not override the plan phase.
            ref_cnt = item['reference_counter']
            cycle = item['cycle']

            # Skip items whose plan has no valid scheduling anchor.
            if ref_cnt is None:
                items_skipped_count += 1
                continue
                
            # Headcount & Trade values
            headcount = item['headcount']
            if headcount is None:
                items_without_headcount += 1
                headcount = 1
            # Project-level productive hours are used for every discipline/item.
            item_team_daily_prod_hours = hours_per_person
            if item_team_daily_prod_hours <= 0:
                item_team_daily_prod_hours = 9.1
            stop_days = 1

            # Compute trade-specific hours & headcounts
            mec_hc = item['mec_headcount'] or 0
            mec_hrs = item['mec_hours'] or 0.0
            ele_hc = item['ele_headcount'] or 0
            ele_hrs = item['ele_hours'] or 0.0
            sol_hc = item['sol_headcount'] or 0
            sol_hrs = item['sol_hours'] or 0.0

            mec_hh = mec_hc * mec_hrs
            ele_hh = ele_hc * ele_hrs
            sol_hh = sol_hc * sol_hrs
            trade_hh_sum = mec_hh + ele_hh + sol_hh
            trade_hc_sum = mec_hc + ele_hc + sol_hc

            if trade_hc_sum > 0 or trade_hh_sum > 0:
                item_hh = trade_hh_sum
                eff_mec_hh = mec_hh
                eff_ele_hh = ele_hh
                eff_sol_hh = sol_hh
            else:
                item_hh = item['duration_hours'] * headcount
                wc_u = (item['work_center'] or '').upper()
                if 'E' in wc_u or 'ELE' in wc_u:
                    eff_ele_hh = item_hh
                    eff_mec_hh = 0.0
                    eff_sol_hh = 0.0
                elif 'S' in wc_u or 'SOL' in wc_u or 'CAL' in wc_u:
                    eff_sol_hh = item_hh
                    eff_mec_hh = 0.0
                    eff_ele_hh = 0.0
                else:
                    eff_mec_hh = item_hh
                    eff_ele_hh = 0.0
                    eff_sol_hh = 0.0

            # Workforce shown in the chart is the total number of person-day
            # allocations required by the stop. Daily staffing is this total
            # divided across the configured stop days.
            item_hc_needed = item_hh / item_team_daily_prod_hours
            mec_hc_needed = eff_mec_hh / item_team_daily_prod_hours
            ele_hc_needed = eff_ele_hh / item_team_daily_prod_hours
            sol_hc_needed = eff_sol_hh / item_team_daily_prod_hours

            # Project occurrences
            occurrences = get_plan_occurrences(ref_cnt, cycle, current_counter, horizon)


            for S in occurrences:
                if S in stops_data:
                    stops_data[S]['total_hh'] += item_hh
                    stops_data[S]['total_duration'] += item['duration_hours']
                    stops_data[S]['total_orders'] += 1
                    stops_data[S]['headcount_float'] += item_hc_needed
                    stops_data[S]['headcount_per_day_float'] = stops_data[S].get('headcount_per_day_float', 0.0) + item_hc_needed / max(1, stop_days)
                    stops_data[S]['mec_hh'] += eff_mec_hh
                    stops_data[S]['mec_headcount_float'] += mec_hc_needed
                    stops_data[S]['mec_headcount_per_day_float'] = stops_data[S].get('mec_headcount_per_day_float', 0.0) + mec_hc_needed / max(1, stop_days)
                    stops_data[S]['ele_hh'] += eff_ele_hh
                    stops_data[S]['ele_headcount_float'] += ele_hc_needed
                    stops_data[S]['ele_headcount_per_day_float'] = stops_data[S].get('ele_headcount_per_day_float', 0.0) + ele_hc_needed / max(1, stop_days)
                    stops_data[S]['sol_hh'] += eff_sol_hh
                    stops_data[S]['sol_headcount_float'] += sol_hc_needed
                    stops_data[S]['sol_headcount_per_day_float'] = stops_data[S].get('sol_headcount_per_day_float', 0.0) + sol_hc_needed / max(1, stop_days)
                    
                    # Grouping key
                    if grouping in ('specialty', 'trade', 'especialidade'):
                        if eff_mec_hh > 0:
                            stops_data[S]['grouped_hh']['Mecânica'] = stops_data[S]['grouped_hh'].get('Mecânica', 0.0) + eff_mec_hh
                            stops_data[S]['grouped_orders']['Mecânica'] = stops_data[S]['grouped_orders'].get('Mecânica', 0) + 1
                            stops_data[S]['grouped_headcount_float']['Mecânica'] = stops_data[S]['grouped_headcount_float'].get('Mecânica', 0.0) + mec_hc_needed
                        if eff_ele_hh > 0:
                            stops_data[S]['grouped_hh']['Elétrica'] = stops_data[S]['grouped_hh'].get('Elétrica', 0.0) + eff_ele_hh
                            stops_data[S]['grouped_orders']['Elétrica'] = stops_data[S]['grouped_orders'].get('Elétrica', 0) + 1
                            stops_data[S]['grouped_headcount_float']['Elétrica'] = stops_data[S]['grouped_headcount_float'].get('Elétrica', 0.0) + ele_hc_needed
                        if eff_sol_hh > 0:
                            stops_data[S]['grouped_hh']['Solda'] = stops_data[S]['grouped_hh'].get('Solda', 0.0) + eff_sol_hh
                            stops_data[S]['grouped_orders']['Solda'] = stops_data[S]['grouped_orders'].get('Solda', 0) + 1
                            stops_data[S]['grouped_headcount_float']['Solda'] = stops_data[S]['grouped_headcount_float'].get('Solda', 0.0) + sol_hc_needed
                    else:
                        g_key = 'Sem Agrupamento'
                        if grouping == 'work_center':
                            g_key = item['work_center'] or 'Sem Centro'
                        elif grouping == 'gpm':
                            g_key = item['gpm'] or 'Sem GPM'
                        elif grouping == 'condition_code':
                            g_key = item['condition_code'] or 'Sem Condição'
                        elif grouping == 'priority':
                            priorities_names = {0: '0 - Urgente', 1: '1 - Alta', 2: '2 - Média', 3: '3 - Baixa'}
                            g_key = priorities_names.get(item['priority'], str(item['priority']))
                        elif grouping == 'cycle':
                            g_key = f"Ciclo {item['cycle']} {item['unit']}"
                        elif grouping == 'plans':
                            g_key = item['plan_code'] or 'Sem Plano'
                            
                        # Grouped HH
                        stops_data[S]['grouped_hh'][g_key] = stops_data[S]['grouped_hh'].get(g_key, 0.0) + item_hh
                        # Grouped orders
                        stops_data[S]['grouped_orders'][g_key] = stops_data[S]['grouped_orders'].get(g_key, 0) + 1
                        # Grouped headcount float
                        stops_data[S]['grouped_headcount_float'][g_key] = stops_data[S]['grouped_headcount_float'].get(g_key, 0.0) + item_hc_needed
                    
        # Post-process stops to calculate headcount needed
        stops_list = []
        all_hh_vals = []
        all_orders_vals = []
        all_hc_vals = []
        
        peak_hh = 0.0
        peak_orders = 0
        peak_hc = 0
        busy_stop_cnt = None
        
        for S in stops_range:
            data = stops_data[S]
            hc = math.ceil(data['headcount_float'])
            data['headcount_needed'] = hc
            data['mec_headcount_needed'] = math.ceil(data['mec_headcount_float'])
            data['ele_headcount_needed'] = math.ceil(data['ele_headcount_float'])
            data['sol_headcount_needed'] = math.ceil(data['sol_headcount_float'])
            data['headcount_per_day'] = math.ceil(data.get('headcount_per_day_float', 0.0))
            data['mec_headcount_per_day'] = math.ceil(data.get('mec_headcount_per_day_float', 0.0))
            data['ele_headcount_per_day'] = math.ceil(data.get('ele_headcount_per_day_float', 0.0))
            data['sol_headcount_per_day'] = math.ceil(data.get('sol_headcount_per_day_float', 0.0))
            
            # Grouped headcount
            for gk, ghc_float in data['grouped_headcount_float'].items():
                data['grouped_headcount'][gk] = math.ceil(ghc_float)
                
            stops_list.append(data)
            all_hh_vals.append(data['total_hh'])
            all_orders_vals.append(data['total_orders'])
            all_hc_vals.append(hc)
            
            if data['total_hh'] > peak_hh:
                peak_hh = data['total_hh']
                busy_stop_cnt = S
                
            if data['total_orders'] > peak_orders:
                peak_orders = data['total_orders']
                
            if hc > peak_hc:
                peak_hc = hc
                
        # Calculate KPIs
        total_hh_horizon = sum(all_hh_vals)
        avg_hh_stop = total_hh_horizon / horizon if horizon > 0 else 0.0
        min_hh = min(all_hh_vals) if all_hh_vals else 0.0
        min_hc = min(all_hc_vals) if all_hc_vals else 0
        
        avg_headcount = sum(all_hc_vals) / horizon if horizon > 0 else 0.0
        
        # Standard deviation of HH
        variance = sum((x - avg_hh_stop) ** 2 for x in all_hh_vals) / horizon if horizon > 0 else 0.0
        std_dev_hh = math.sqrt(variance)
        
        kpis = {
            'total_hh': round(total_hh_horizon, 1),
            'avg_hh': round(avg_hh_stop, 1),
            'max_hh': round(peak_hh, 1),
            'min_hh': round(min_hh, 1),
            'diff_hh': round(peak_hh - min_hh, 1),
            'std_dev_hh': round(std_dev_hh, 1),
            'max_orders': peak_orders,
            'max_headcount': peak_hc,
            'avg_headcount': round(avg_headcount, 1),
            'busy_stop': busy_stop_cnt,
            'items_skipped_count': items_skipped_count,
            'items_without_headcount': items_without_headcount
        }
        
        capacity_hours_per_person = {
            'ele': hours_per_person, 'mec': hours_per_person, 'sol': hours_per_person
        }
        capacity_hours_options = {
            'ele': [hours_per_person], 'mec': [hours_per_person], 'sol': [hours_per_person]
        }
        capacity_hours_ambiguous = {'ele': False, 'mec': False, 'sol': False}
        capacity_stop_days = {'ele': 1, 'mec': 1, 'sol': 1}

        return {
            'stops': stops_list,
            'kpis': kpis,
            'productive_hours': hours_per_person,
            'hours_per_person': base_hours,
            'tool_time_percent': round(util_factor * 100.0, 4),
            'capacity_hours_per_person': capacity_hours_per_person,
            'capacity_hours_options': capacity_hours_options,
            'capacity_hours_ambiguous': capacity_hours_ambiguous,
            'capacity_stop_days': capacity_stop_days,
            'capacity_team_names': {'ele': [], 'mec': [], 'sol': []}
        }
    finally:
        conn.close()
