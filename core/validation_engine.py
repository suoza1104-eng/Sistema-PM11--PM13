"""
Motor de Validação e Diagnóstico Técnico de Consistência para o PM13.
Aprimora o sistema de alertas e armações do PM13 com as 9 regras técnicas completas.
"""

import json
from core.database import get_db_connection
from core.technical_classes import check_technical_class_compatibility

def validate_pm13_project(project_id):
    """
    Executa a varredura completa de validação técnica do PM13 de acordo com as 9 regras.
    """
    conn = get_db_connection()
    c = conn.cursor()

    plans_rows = c.execute("SELECT * FROM plans WHERE project_id=? AND (deleted_at IS NULL OR deleted_at='')", (project_id,)).fetchall()
    items_rows = c.execute("SELECT * FROM maintenance_items WHERE project_id=? AND (deleted_at IS NULL OR deleted_at='')", (project_id,)).fetchall()
    ops_rows = c.execute("""
        SELECT o.*, i.plan_id
        FROM item_operations o
        JOIN maintenance_items i ON i.id = o.item_id
        WHERE o.project_id=?
    """, (project_id,)).fetchall()

    plans = [dict(r) for r in plans_rows]
    items = [dict(r) for r in items_rows]
    ops = [dict(r) for r in ops_rows]

    plan_issues = {p['id']: [] for p in plans}
    item_issues = {i['id']: [] for i in items}
    op_issues = {op['id']: [] for op in ops}

    # Regra 7: Unicidade de Identificador em Itens
    seen_item_codes = set()
    for it in items:
        code = it.get('legacy_identifier') or it.get('object_code') or str(it['id'])
        if code in seen_item_codes:
            item_issues[it['id']].append({
                'severity': 'ERROR',
                'field': 'legacy_identifier',
                'message': f'Regra 7: Identificador de item repetido: {code}'
            })
        else:
            seen_item_codes.add(code)

        # Regra 6: Prioridade no PM13 deve ser de 1 a 4
        prio = it.get('priority')
        if prio is not None and prio != '':
            try:
                prio_int = int(prio)
                if not (1 <= prio_int <= 4):
                    item_issues[it['id']].append({
                        'severity': 'WARNING',
                        'field': 'priority',
                        'message': f'Regra 6: No PM13 a prioridade deve ser entre 1 e 4 (atual: {prio})'
                    })
            except (ValueError, TypeError):
                pass

        # Regra 8: Existência de Referência em Planos
        plan_id = it.get('plan_id')
        if not plan_id or not any(p['id'] == plan_id for p in plans):
            item_issues[it['id']].append({
                'severity': 'ERROR',
                'field': 'plan_id',
                'message': 'Regra 8: Item sem Plano pai associado'
            })

        # Regra 5: Condição Operacional vs Ciclo
        parent_plan = next((p for p in plans if p['id'] == plan_id), None) if plan_id else None
        if parent_plan:
            unit = (parent_plan.get('unit') or '').upper()
            cond = (it.get('condition_code') or '').upper()
            if unit == 'SMS' and cond not in ('P', 'F', 'Q', ''):
                item_issues[it['id']].append({
                    'severity': 'WARNING',
                    'field': 'condition_code',
                    'message': f'Regra 5: Plano ciclo SMS exige condição P, F ou Q (atual: {cond})'
                })
            elif unit == 'PRD' and cond != 'M':
                item_issues[it['id']].append({
                    'severity': 'WARNING',
                    'field': 'condition_code',
                    'message': f'Regra 5: Plano ciclo PRD exige condição M (atual: {cond})'
                })

    # Regras das Operações / Características no PM13
    for op in ops:
        opid = op['id']
        item_id = op.get('item_id')
        method = op.get('short_text') or ''
        unit = op.get('unit') or ''

        # Regra 2: Pertence a um Item Válido
        if not item_id or not any(i['id'] == item_id for i in items):
            op_issues[opid].append({
                'severity': 'ERROR',
                'field': 'item_id',
                'message': 'Regra 2: Operação aponta para um Item inexistente'
            })

        # Regra 3.4: Classes de Compatibilidade Física
        if method and unit:
            compat, m_cls, u_cls, warning_msg = check_technical_class_compatibility(method, unit)
            if not compat:
                op_issues[opid].append({
                    'severity': 'WARNING',
                    'field': 'unit',
                    'message': f'Regra 3: {warning_msg}'
                })

    for p in plans:
        issues = plan_issues[p['id']]
        status = 'ERROR' if any(i['severity'] == 'ERROR' for i in issues) else ('WARNING' if issues else 'OK')
        c.execute("UPDATE plans SET validation_status=?, validation_issues_json=? WHERE id=?",
                  (status, json.dumps(issues, ensure_ascii=False), p['id']))

    for it in items:
        issues = item_issues[it['id']]
        status = 'ERROR' if any(i['severity'] == 'ERROR' for i in issues) else ('WARNING' if issues else 'OK')
        c.execute("UPDATE maintenance_items SET validation_status=?, validation_issues_json=? WHERE id=?",
                  (status, json.dumps(issues, ensure_ascii=False), it['id']))

    for op in ops:
        issues = op_issues[op['id']]
        status = 'ERROR' if any(i['severity'] == 'ERROR' for i in issues) else ('WARNING' if issues else 'OK')
        c.execute("UPDATE item_operations SET validation_status=?, validation_issues_json=? WHERE id=?",
                  (status, json.dumps(issues, ensure_ascii=False), op['id']))

    conn.commit()
    conn.close()
    return {
        'plans_validated': len(plans),
        'items_validated': len(items),
        'ops_validated': len(ops)
    }

