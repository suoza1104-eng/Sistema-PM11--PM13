"""
Motor de Validação e Diagnóstico Técnico de Consistência para o PM13.
Aprimora o sistema de alertas e armações do PM13 com as regras técnicas completas.
"""

import json
from core.database import get_db_connection
from core.technical_classes import check_technical_class_compatibility

def clean_op_code(val):
    s = str(val or '').strip()
    if s.isdigit():
        return f"{int(s):04d}"
    return s

def is_sub_empty(val):
    if val is None:
        return True
    s = str(val).strip()
    return s in ('', '0000', '-', 'None', '0', '00', '000', ' - ', ' -')

def validate_pm13_project(project_id):
    """
    Executa a varredura completa de validação técnica do PM13.
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

    lt_rows = c.execute("""
        SELECT lt.*, o.item_id, o.operation_code, o.suboperation_code
        FROM operation_long_texts lt
        JOIN item_operations o ON o.id = lt.operation_id
        WHERE lt.project_id=?
    """, (project_id,)).fetchall()

    plans = [dict(r) for r in plans_rows]
    items = [dict(r) for r in items_rows]
    ops = [dict(r) for r in ops_rows]
    lts = [dict(r) for r in lt_rows]

    plan_issues = {p['id']: [] for p in plans}
    item_issues = {i['id']: [] for i in items}
    op_issues = {op['id']: [] for op in ops}
    lt_issues = {lt['id']: [] for lt in lts}

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

        # REGRA PM13 - Pacote Obrigatório de Operações (0010, 0010 0011, 0010 0012, 0010 0013, 0010 0014, 0020)
        it_ops = [op for op in ops if op.get('item_id') == it['id']]
        
        has_0010_no_sub = any(clean_op_code(op.get('operation_code')) == '0010' and is_sub_empty(op.get('suboperation_code')) for op in it_ops)
        has_0010_0011  = any(clean_op_code(op.get('operation_code')) == '0010' and str(op.get('suboperation_code')).strip() == '0011' for op in it_ops)
        has_0010_0012  = any(clean_op_code(op.get('operation_code')) == '0010' and str(op.get('suboperation_code')).strip() == '0012' for op in it_ops)
        has_0010_0013  = any(clean_op_code(op.get('operation_code')) == '0010' and str(op.get('suboperation_code')).strip() == '0013' for op in it_ops)
        has_0010_0014  = any(clean_op_code(op.get('operation_code')) == '0010' and str(op.get('suboperation_code')).strip() == '0014' for op in it_ops)
        has_0020_no_sub = any(clean_op_code(op.get('operation_code')) == '0020' and is_sub_empty(op.get('suboperation_code')) for op in it_ops)

        missing_pkg = []
        if not has_0010_no_sub: missing_pkg.append('0010')
        if not has_0010_0011: missing_pkg.append('0010 0011')
        if not has_0010_0012: missing_pkg.append('0010 0012')
        if not has_0010_0013: missing_pkg.append('0010 0013')
        if not has_0010_0014: missing_pkg.append('0010 0014')
        if not has_0020_no_sub: missing_pkg.append('0020')

        if missing_pkg:
            item_issues[it['id']].append({
                'severity': 'ERROR',
                'field': 'operations_package',
                'message': f'Regra Pacote PM13: Item sem pacote completo de operações obrigatórias (0010, 0010 0011, 0010 0012, 0010 0013, 0010 0014, 0020). Faltante(s): {", ".join(missing_pkg)}'
            })

    # Regras das Operações e Texto Longo no PM13
    for op in ops:
        opid = op['id']
        item_id = op.get('item_id')
        method = op.get('short_text') or ''
        unit = op.get('unit') or ''
        op_code = clean_op_code(op.get('operation_code'))
        subop_code = str(op.get('suboperation_code') or '').strip()

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

        # REGRA PM13 - Exigência de Texto Longo por Operação
        op_lts = [lt for lt in lts if lt.get('operation_id') == opid]
        is_first_0010 = (op_code == '0010' and is_sub_empty(subop_code))

        if is_first_0010:
            # 0010 sem suboperação: DEVE SER VAZIA. Se estiver sem texto ou com texto vazio, está 100% OK!
            non_empty = [lt for lt in op_lts if str(lt.get('text') or '').strip() != '']
            if non_empty:
                msg = 'Regra Texto Longo PM13: A operação 0010 (sem suboperação) deve possuir Texto Longo VAZIO (encontrado conteúdo preenchido).'
                op_issues[opid].append({'code': 'header_has_long_text', 'severity': 'ERROR', 'field': 'long_text', 'message': msg})
                if item_id and item_id in item_issues:
                    item_issues[item_id].append({'code': 'header_has_long_text', 'severity': 'ERROR', 'field': 'long_text', 'message': msg})
        else:
            # Demais operações: DEVEM ter texto longo preenchido.
            non_empty = [lt for lt in op_lts if str(lt.get('text') or '').strip() != '']
            if not non_empty:
                op_label = f"{op_code} {subop_code}".strip()
                msg = f'Regra Texto Longo PM13: A operação {op_label} exige Texto Longo preenchido e não pode ficar em branco.'
                op_issues[opid].append({'code': 'missing_long_text', 'severity': 'ERROR', 'field': 'long_text', 'message': msg})
                if item_id and item_id in item_issues:
                    item_issues[item_id].append({'code': 'missing_long_text', 'severity': 'ERROR', 'field': 'long_text', 'message': msg})

    # Regras das Linhas de Texto Longo
    for lt in lts:
        ltid = lt['id']
        op_id = lt.get('operation_id')
        op_match = next((op for op in ops if op['id'] == op_id), None)
        if op_match:
            op_code = clean_op_code(op_match.get('operation_code'))
            sub_code = str(op_match.get('suboperation_code') or '').strip()
            is_first_0010 = (op_code == '0010' and is_sub_empty(sub_code))
            txt = str(lt.get('text') or '').strip()
            if is_first_0010 and txt != '':
                lt_issues[ltid].append({'severity': 'ERROR', 'field': 'text', 'message': 'Texto Longo da operação 0010 (sem suboperação) deve ser VAZIO.'})
            elif not is_first_0010 and txt == '':
                lt_issues[ltid].append({'severity': 'ERROR', 'field': 'text', 'message': 'Texto Longo desta operação é OBRIGATÓRIO e não pode ficar em branco.'})

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

    for lt in lts:
        issues = lt_issues[lt['id']]
        status = 'ERROR' if any(i['severity'] == 'ERROR' for i in issues) else ('WARNING' if issues else 'OK')
        c.execute("UPDATE operation_long_texts SET validation_status=?, validation_issues_json=? WHERE id=?",
                  (status, json.dumps(issues, ensure_ascii=False), lt['id']))

    conn.commit()
    conn.close()
    return {
        'plans_validated': len(plans),
        'items_validated': len(items),
        'ops_validated': len(ops),
        'lts_validated': len(lts)
    }
