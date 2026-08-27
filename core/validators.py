import re

def check_copy_paste_error(code, description):
    """Checks if there's a subarea copy-paste error between code prefix and description.
    STP -> SIST-P, STE -> SIST-E, STF -> SIST-F, STD -> SIST-D
    """
    if not code or not description:
        return None
        
    code_upper = code.upper()
    desc_upper = description.upper()
    
    systems = {
        'STP': 'SIST-P',
        'STE': 'SIST-E',
        'STF': 'SIST-F',
        'STD': 'SIST-D'
    }
    
    # Identify which system is in the code
    detected_code_sys = None
    for sys_key in systems:
        if sys_key in code_upper:
            detected_code_sys = sys_key
            break
            
    if not detected_code_sys:
        return None
        
    # Check if description mentions a different system
    for sys_key, sys_name in systems.items():
        if sys_key != detected_code_sys:
            # Check for alternative mentions in description
            # e.g., if code is STF (SIST-F) but description contains "SIST-P" or "SIST - P" or "MANUT SIST-P"
            patterns = [
                r'SIST[- ]*' + sys_key[-1],  # SIST-P, SIST P, SIST-F, etc.
                r'SISTEMA[- ]*' + sys_key[-1]
            ]
            for pat in patterns:
                if re.search(pat, desc_upper):
                    return f"Divergência: Código indica {systems[detected_code_sys]} ({detected_code_sys}) mas descrição menciona {sys_name}."
                    
    return None

def validate_plan_row(row_num, plano_code, desc, ciclo, unid, texto_ciclo, horiz_abert, contador_ref):
    """Validates a plan row data and returns a list of error/warning dicts.
    Each dict contains: field, severity (ERROR, WARNING), message, value.
    """
    issues = []
    
    # 1. Plano Code
    if not plano_code:
        issues.append({
            'field': 'Plano',
            'severity': 'ERROR',
            'message': 'Código do plano está vazio.',
            'value': plano_code
        })
    else:
        plano_code_str = str(plano_code).strip()
        if len(plano_code_str) < 3:
            issues.append({
                'field': 'Plano',
                'severity': 'ERROR',
                'message': 'Código do plano muito curto.',
                'value': plano_code
            })

    # 2. Descrição
    if not desc:
        issues.append({
            'field': 'Descrição do Plano',
            'severity': 'ERROR',
            'message': 'Descrição do plano está vazia.',
            'value': desc
        })
    else:
        desc_str = str(desc).strip()
        actual_len = len(desc_str)
        # Check description length limits
        if actual_len > 40:
            issues.append({
                'field': 'Descrição do Plano',
                'severity': 'WARNING',
                'message': f'Descrição possui {actual_len} caracteres (limite é 40).',
                'value': desc
            })

    # 3. Ciclo
    if ciclo is None or ciclo == '':
        issues.append({
            'field': 'Ciclo',
            'severity': 'ERROR',
            'message': 'Ciclo está vazio.',
            'value': ciclo
        })
    else:
        try:
            c = int(float(str(ciclo)))
            if c <= 0:
                issues.append({
                    'field': 'Ciclo',
                    'severity': 'ERROR',
                    'message': 'Ciclo deve ser um inteiro positivo maior que zero.',
                    'value': ciclo
                })
        except ValueError:
            issues.append({
                'field': 'Ciclo',
                'severity': 'ERROR',
                'message': 'Ciclo deve ser numérico.',
                'value': ciclo
            })

    # 4. Unidade
    if not unid:
        issues.append({
            'field': 'Unid.',
            'severity': 'ERROR',
            'message': 'Unidade do ciclo está vazia.',
            'value': unid
        })

    # 5. Contador
    if contador_ref is not None and contador_ref != '':
        try:
            int(float(str(contador_ref)))
        except ValueError:
            issues.append({
                'field': 'Contador - Planos de Paradas',
                'severity': 'ERROR',
                'message': 'Contador de referência deve ser um número inteiro.',
                'value': contador_ref
            })
    
    # 6. Copy paste check
    if plano_code and desc:
        cp_err = check_copy_paste_error(str(plano_code), str(desc))
        if cp_err:
            issues.append({
                'field': 'Plano',
                'severity': 'WARNING',
                'message': cp_err,
                'value': plano_code
            })

    return issues

def validate_item_row(row_num, local_instal, gpm, centro, condicao, prioridade, plano_reparo, identificador, contador, desc_item, duracao, efetivo):
    """Validates an item row data and returns a list of error/warning dicts."""
    issues = []
    
    # 1. Identificador
    if identificador is None or identificador == '':
        issues.append({
            'field': 'Identificador',
            'severity': 'WARNING',
            'message': f'Identificador ausente. Foi gerado automaticamente o ID {row_num - 1}.',
            'value': identificador
        })
    # O identificador é uma chave textual legada. Letras, números e
    # caracteres especiais são válidos; a consistência é garantida pelo
    # vínculo exato dessa mesma chave em itens, operações e textos longos.

    # 2. Local de Instalação / Equipamento
    if not local_instal:
        issues.append({
            'field': 'Local de Instalação',
            'severity': 'WARNING',
            'message': 'Local de instalação/equipamento ausente. Preenchido com SEM_EQUIPAMENTO.',
            'value': local_instal
        })

    # 3. GPM
    if gpm is None or gpm == '':
        issues.append({
            'field': 'GPM',
            'severity': 'WARNING',
            'message': 'GPM não informado. Atribuído 000 por padrão.',
            'value': gpm
        })

    # 4. Centro de Trabalho
    if not centro:
        issues.append({
            'field': 'CENTRO DE TRABALHO',
            'severity': 'WARNING',
            'message': 'Centro de trabalho não informado. Atribuído GERAL por padrão.',
            'value': centro
        })

    # 5. Condição
    if not condicao:
        issues.append({
            'field': 'CONDIÇÃO',
            'severity': 'WARNING',
            'message': 'Condição não informada. Assumido Q (Qualquer).',
            'value': condicao
        })

    # 6. Prioridade
    if prioridade is None or prioridade == '':
        issues.append({
            'field': 'PRIORIDADE',
            'severity': 'WARNING',
            'message': 'Prioridade não informada. Assumida prioridade 3 (Baixa).',
            'value': prioridade
        })

    # 7. Plano Reparo
    if not plano_reparo:
        issues.append({
            'field': 'PLANO REPARO',
            'severity': 'WARNING',
            'message': 'Plano associado está vazio (item ficará desvinculado).',
            'value': plano_reparo
        })

    # 8. Descrição do Item
    if not desc_item:
        issues.append({
            'field': 'DESCRIÇÃO ITEM',
            'severity': 'ERROR',
            'message': 'Descrição do item está vazia.',
            'value': desc_item
        })

    # 9. Duração t(H)
    if duracao is None or duracao == '':
        issues.append({
            'field': 't(H)',
            'severity': 'ERROR',
            'message': 'Duração da atividade está vazia.',
            'value': duracao
        })
    else:
        try:
            d = float(str(duracao).replace(',', '.'))
            if d < 0:
                issues.append({
                    'field': 't(H)',
                    'severity': 'ERROR',
                    'message': 'Duração não pode ser negativa.',
                    'value': duracao
                })
            elif d == 0:
                issues.append({
                    'field': 't(H)',
                    'severity': 'WARNING',
                    'message': 'Duração é zero.',
                    'value': duracao
                })
        except ValueError:
            issues.append({
                'field': 't(H)',
                'severity': 'ERROR',
                'message': 'Duração deve ser um valor numérico decimal.',
                'value': duracao
            })

    # 10. Efetivo
    if efetivo is not None and efetivo != '':
        try:
            ef = int(float(str(efetivo)))
            if ef < 0:
                issues.append({
                    'field': 'Efetivo',
                    'severity': 'ERROR',
                    'message': 'Efetivo não pode ser negativo.',
                    'value': efetivo
                })
        except ValueError:
            issues.append({
                'field': 'Efetivo',
                'severity': 'ERROR',
                'message': 'Efetivo deve ser um número inteiro.',
                'value': efetivo
            })
    else:
        issues.append({
            'field': 'Efetivo',
            'severity': 'WARNING',
            'message': 'Efetivo pendente (ficará com valor pendente no banco).',
            'value': efetivo
        })

    return issues


STANDARD_0010_SUBOPERATIONS = {
    '0010': 'MECÂNICO SOLDADOR OU SOLDADOR',
    '0011': 'SUPERVISOR OU LIDER DE GRUPO',
    '0012': 'RECOMENDAÇÕES SEGURANÇA E MEIO AMBIENTE',
    '0013': 'ATIVIDADES DE PREPARAÇÃO',
    '0014': 'DOCUMENTOS TÉCNICOS',
}


def validate_operation_structure(operation_code, suboperation_code, short_text,
                                 long_text_count=0, item_suboperations=None):
    """Validate the corporate operation/long-text structure used by SAP."""
    code = str(operation_code or '').strip().zfill(4)
    sub = str(suboperation_code or '').strip()
    sub = sub.zfill(4) if sub.isdigit() else sub
    issues = []

    def error(code_name, message):
        issues.append({'code': code_name, 'severity': 'ERROR', 'message': message})

    if code == '0010' and not sub:
        if long_text_count:
            error('header_has_long_text', 'O 0010 principal é apenas o título e não deve possuir texto longo.')
        present = set(item_suboperations or [])
        missing = [value for value in STANDARD_0010_SUBOPERATIONS if value not in present]
        if missing:
            error('missing_standard_suboperations',
                  f"Faltam as suboperações padrão do 0010: {', '.join(missing)}.")
        return issues

    def norm_txt(s):
        import unicodedata
        if not s: return ""
        s = str(s).upper().strip()
        s = ''.join(c for c in unicodedata.normalize('NFD', s) if unicodedata.category(c) != 'Mn')
        return ' '.join(s.split())

    if code == '0010':
        expected = STANDARD_0010_SUBOPERATIONS.get(sub)
        if not expected:
            error('invalid_0010_suboperation',
                  'O 0010 aceita somente as suboperações 0010, 0011, 0012, 0013 e 0014.')
        elif norm_txt(short_text) != norm_txt(expected):
            error('invalid_standard_title', f'A suboperação {sub} deve ter o título: {expected}.')
    else:
        try:
            number = int(code)
            if number < 20 or number % 10 != 0:
                error('invalid_operation_sequence',
                      'Após o 0010, as operações devem ser numeradas de 10 em 10: 0020, 0030, 0040...')
        except ValueError:
            error('invalid_operation_sequence', 'O código da operação deve ser numérico com quatro dígitos.')
        if sub:
            error('unexpected_suboperation', 'Operações 0020, 0030, 0040... não devem possuir suboperação.')

    if not long_text_count:
        error('missing_long_text', 'Esta operação deve possuir pelo menos um texto longo atrelado.')
    return issues
