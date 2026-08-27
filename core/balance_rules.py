"""Shared recurrence-rule helpers for automatic and manual balancing."""

import itertools
import math

from core.calculations import get_plan_occurrences


def normalize_rules(rules):
    normalized = []
    claimed = set()
    for index, raw in enumerate(rules or []):
        rule_type = str(raw.get('type') or raw.get('rule_type') or '').strip().lower()
        if rule_type not in ('together', 'sequence', 'separate'):
            raise ValueError(f'Regra {index + 1}: comportamento inválido.')
        enforcement = str(raw.get('enforcement') or 'mandatory').strip().lower()
        if enforcement not in ('mandatory', 'preferred'):
            raise ValueError(f'Regra {index + 1}: nível inválido.')
        item_ids = []
        for value in raw.get('item_ids') or []:
            value = int(value)
            if value not in item_ids:
                item_ids.append(value)
        if len(item_ids) < 2:
            raise ValueError(f'Regra {index + 1}: selecione pelo menos dois itens.')
        overlap = claimed.intersection(item_ids)
        if overlap and enforcement == 'mandatory':
            raise ValueError(
                f'Regra {index + 1}: itens de regras obrigatórias não podem se sobrepor: ' +
                ', '.join(map(str, sorted(overlap))))
        if enforcement == 'mandatory':
            claimed.update(item_ids)
        normalized.append({
            'name': str(raw.get('name') or f'Regra {index + 1}').strip(),
            'type': rule_type,
            'enforcement': enforcement,
            'item_ids': item_ids,
            'config': dict(raw.get('config') or {}),
        })
    return normalized


def occurrences_for_plan(plan, current_counter, horizon):
    if not plan:
        return set()
    return set(get_plan_occurrences(
        plan.get('reference_counter'), int(plan.get('cycle') or 0),
        int(current_counter), int(horizon)))


def _max_common_occurrences(cycles, horizon):
    period = 1
    for cycle in cycles:
        period = math.lcm(period, max(1, int(cycle)))
    return max(1, math.ceil(int(horizon) / period))


def evaluate_rule(rule, assignment_by_item, plan_by_id, current_counter, horizon, pending_ids=None):
    pending_ids = set(pending_ids or [])
    item_ids = rule['item_ids']
    assigned = [item_id for item_id in item_ids
                if item_id in assignment_by_item and item_id not in pending_ids]
    if len(assigned) < 2:
        return {'satisfied': True, 'pending': True, 'message': 'Regra aguardando itens pendentes.'}

    plans = [plan_by_id.get(int(assignment_by_item[item_id])) for item_id in assigned]
    if any(not plan for plan in plans):
        return {'satisfied': False, 'pending': False, 'message': 'Um item da regra não possui plano válido.'}
    stop_sets = [occurrences_for_plan(plan, current_counter, horizon) for plan in plans]
    rule_type = rule['type']
    if rule_type == 'separate':
        conflicts = sorted(set().union(*(
            stop_sets[a].intersection(stop_sets[b])
            for a in range(len(stop_sets)) for b in range(a + 1, len(stop_sets))
        )))
        return {
            'satisfied': not conflicts, 'pending': False, 'conflict_stops': conflicts,
            'message': ('Itens não se encontram no horizonte.' if not conflicts else
                        'Encontro proibido em: ' + ', '.join(f'P{s-current_counter}' for s in conflicts))
        }
    if rule_type == 'sequence':
        cycles = [int(plan['cycle']) for plan in plans]
        if len(set(cycles)) != 1:
            return {'satisfied': False, 'pending': False,
                    'message': 'Executar em sequência exige itens com o mesmo ciclo.'}
        cycle = cycles[0]
        phases = [((int(plan['reference_counter']) - current_counter - 1) % cycle) for plan in plans]
        ok = all(phases[i] == (phases[0] + i) % cycle for i in range(len(phases)))
        return {'satisfied': ok, 'pending': False, 'phases': phases,
                'message': 'Sequência válida.' if ok else 'As fases não estão em sequência.'}

    common = set.intersection(*stop_sets) if stop_sets else set()
    cycles = [int(plan['cycle']) for plan in plans]
    required = _max_common_occurrences(cycles, horizon)
    ok = len(common) >= required
    return {
        'satisfied': ok, 'pending': False, 'common_stops': sorted(common),
        'required_common_occurrences': required,
        'message': (f'{len(common)} encontro(s) programado(s).' if ok else
                    f'A regra exige ao menos {required} encontro(s), mas encontrou {len(common)}.')
    }


def evaluate_rules(rules, assignment_by_item, plan_by_id, current_counter, horizon, pending_ids=None):
    diagnostics = []
    mandatory_ok = True
    preferred_violations = 0
    for rule in normalize_rules(rules):
        result = evaluate_rule(rule, assignment_by_item, plan_by_id, current_counter, horizon, pending_ids)
        result.update({'name': rule['name'], 'type': rule['type'], 'enforcement': rule['enforcement']})
        diagnostics.append(result)
        if not result['satisfied'] and not result.get('pending'):
            if rule['enforcement'] == 'mandatory':
                mandatory_ok = False
            else:
                preferred_violations += 1
    return mandatory_ok, preferred_violations, diagnostics


def find_feasible_assignment(rule, candidate_plan_ids, plan_by_id, current_counter, horizon,
                             score_callback=None, max_combinations=100000,
                             deadline_callback=None):
    """Return the best feasible item->plan mapping for one mandatory rule."""
    rule = normalize_rules([rule])[0]
    item_choices_rows = []
    combinations = 1
    for item_id in rule['item_ids']:
        item_choices = list(dict.fromkeys(int(x) for x in candidate_plan_ids.get(item_id, [])))
        if not item_choices:
            return None
        item_choices_rows.append((item_id, item_choices))

    # In a "together" rule, items with the same candidate-plan set must use
    # the same phase to have common occurrences. Collapse those equivalent
    # variables before building the Cartesian product. This turns cases such
    # as 26 items in 3P plus 16 in 6P from 3^26 * 6^16 into only 3 * 6.
    if rule['type'] == 'together':
        grouped = {}
        for item_id, item_choices in item_choices_rows:
            grouped.setdefault(tuple(item_choices), []).append(item_id)
        variables = [(item_ids, list(choice_key)) for choice_key, item_ids in grouped.items()]
    else:
        variables = [([item_id], item_choices) for item_id, item_choices in item_choices_rows]

    choices = []
    for _, variable_choices in variables:
        choices.append(variable_choices)
        combinations *= len(variable_choices)
    if combinations > max_combinations:
        # Keep deterministic, geographically-near candidates first.
        width = max(2, int(max_combinations ** (1 / max(1, len(choices)))))
        choices = [row[:width] for row in choices]

    best = None
    best_score = None
    for combination_index, values in enumerate(itertools.product(*choices)):
        if combination_index >= max_combinations:
            break
        if deadline_callback:
            deadline_callback()
        assignment = {}
        for (item_ids, _), plan_id in zip(variables, values):
            assignment.update({item_id: plan_id for item_id in item_ids})
        result = evaluate_rule(rule, assignment, plan_by_id, current_counter, horizon)
        if not result['satisfied']:
            continue
        score = float(score_callback(assignment) if score_callback else 0.0)
        key = (score, tuple(values))
        if best_score is None or key < best_score:
            best, best_score = assignment, key
    return best
