"""
Motor de Validação e Diagnóstico Técnico de Consistência para o PM11.
Aplica as 9 regras de validação e atualiza o validation_status e validation_issues_json.
"""

import json
from .database import get_conn
from . import models
from core.technical_classes import check_technical_class_compatibility, sanitize_code

def validate_pm11_project(project_id):
    """
    Executa a varredura completa de validação técnica do PM11 de acordo com as 9 regras.
    """
    db = get_conn()
    c = db.cursor()

    plans = models.list_plans(project_id)
    items = models.list_items(project_id)
    chars = models.list_characteristics(project_id)

    plan_issues = {p['id']: [] for p in plans}
    item_issues = {i['id']: [] for i in items}
    char_issues = {ch['id']: [] for ch in chars}

    # Regra 7: Unicidade de Identificador em Itens (legacy_identifier)
    seen_item_identifiers = set()
    for it in items:
        item_code = str(it.get('legacy_identifier') or '').strip()
        if item_code and item_code in seen_item_identifiers:
            item_issues[it['id']].append({
                'severity': 'ERROR',
                'field': 'legacy_identifier',
                'message': f'Regra 7: Identificador de item repetido: {item_code}'
            })
        elif item_code:
            seen_item_identifiers.add(item_code)

        # Regra 6: Prioridade no PM11 deve ser 0
        if it.get('priority') not in (0, '0', None, ''):
            item_issues[it['id']].append({
                'severity': 'WARNING',
                'field': 'priority',
                'message': f'Regra 6: No PM11 a prioridade deve ser 0 (atual: {it.get("priority")})'
            })

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

    # Regras das Características (Regra 1, 2, 3, 9)
    for ch in chars:
        cid = ch['id']
        item_id = ch.get('item_id')
        ctype = (ch.get('characteristic_type') or '').upper()
        method = ch.get('method_code') or ''
        unit = ch.get('unit_code') or ''
        ref_val = ch.get('reference_value')
        inf_val = ch.get('lower_limit')
        sup_val = ch.get('upper_limit')
        decimals = ch.get('decimals')

        # Regra 2: Pertence a um Item Válido
        if not item_id or not any(i['id'] == item_id for i in items):
            char_issues[cid].append({
                'severity': 'ERROR',
                'field': 'item_id',
                'message': 'Regra 2: Característica aponta para um Item inexistente'
            })

        # Regra 9: Sanitização no PM11 (Tipo e Método sem Ç/acentos/espaços)
        san_type = sanitize_code(ctype)
        if ctype and ctype != san_type and ' ' in ctype:
            char_issues[cid].append({
                'severity': 'WARNING',
                'field': 'characteristic_type',
                'message': f'Regra 9: Tipo possui caracteres especiais/espaços. Sugestão: {san_type}'
            })

        san_method = sanitize_code(method)
        if method and method != san_method and (' ' in method or any(ord(x) > 127 for x in method)):
            char_issues[cid].append({
                'severity': 'WARNING',
                'field': 'method_code',
                'message': f'Regra 9: Método possui acentos/espaços no PM11. Código limpo SAP: {san_method}'
            })

        # Regra 3: Quantitativo vs Qualitativo
        if ctype == 'QUANTIT':
            if ref_val is None or inf_val is None or sup_val is None:
                char_issues[cid].append({
                    'severity': 'ERROR',
                    'field': 'reference_value',
                    'message': 'Regra 3: Item QUANTITATIVO exige Valor Teórico, Limite Inferior e Limite Superior'
                })
            else:
                try:
                    r, i, s = float(ref_val), float(inf_val), float(sup_val)
                    if not (i < r < s):
                        char_issues[cid].append({
                            'severity': 'ERROR',
                            'field': 'reference_value',
                            'message': f'Regra 3: Violação de Limites ({i} < {r} < {s} é FALSO). Limite Inf deve ser < Teórico < Limite Sup'
                        })
                except (ValueError, TypeError):
                    pass

            if not method:
                char_issues[cid].append({'severity': 'ERROR', 'field': 'method_code', 'message': 'Regra 3: Item QUANTITATIVO exige Método de Inspeção'})
            if not unit:
                char_issues[cid].append({'severity': 'ERROR', 'field': 'unit_code', 'message': 'Regra 3: Item QUANTITATIVO exige Unidade de Medida'})

            if decimals != 2:
                char_issues[cid].append({'severity': 'WARNING', 'field': 'decimals', 'message': 'Regra 3: Casas decimais deve ser sempre 2'})

        elif ctype == 'QUALITAT':
            if ref_val is not None or inf_val is not None or sup_val is not None:
                char_issues[cid].append({
                    'severity': 'WARNING',
                    'field': 'reference_value',
                    'message': 'Regra 3: Item QUALITATIVO não deve ter limites numéricos preenchidos'
                })

        # Regra 3.4: Classes de Compatibilidade Física entre Método e Unidade
        if method and unit:
            compat, m_cls, u_cls, warning_msg = check_technical_class_compatibility(method, unit)
            if not compat:
                char_issues[cid].append({
                    'severity': 'WARNING',
                    'field': 'unit_code',
                    'message': f'Regra 3: {warning_msg}'
                })

    for p in plans:
        issues = plan_issues[p['id']]
        status = 'ERROR' if any(i['severity'] == 'ERROR' for i in issues) else ('WARNING' if issues else 'OK')
        c.execute("UPDATE inspection_plans SET validation_status=?, validation_issues_json=? WHERE id=?",
                  (status, json.dumps(issues, ensure_ascii=False), p['id']))

    for it in items:
        issues = item_issues[it['id']]
        status = 'ERROR' if any(i['severity'] == 'ERROR' for i in issues) else ('WARNING' if issues else 'OK')
        c.execute("UPDATE inspection_items SET validation_status=?, validation_issues_json=? WHERE id=?",
                  (status, json.dumps(issues, ensure_ascii=False), it['id']))

    for ch in chars:
        issues = char_issues[ch['id']]
        status = 'ERROR' if any(i['severity'] == 'ERROR' for i in issues) else ('WARNING' if issues else 'OK')
        c.execute("UPDATE control_characteristics SET validation_status=?, validation_issues_json=? WHERE id=?",
                  (status, json.dumps(issues, ensure_ascii=False), ch['id']))

    db.commit()
    return {
        'plans_validated': len(plans),
        'items_validated': len(items),
        'chars_validated': len(chars)
    }
