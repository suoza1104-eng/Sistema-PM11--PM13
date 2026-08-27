import hashlib
import json
import os
import re
from core.xlsx_reader import XLSXReader
from core.database import get_db_connection
from core.validators import validate_plan_row, validate_item_row, validate_operation_structure
from core.long_text_structure import detect_structure

def extract_cycle_and_start_from_text(text):
    """
    Extracts cycle (e.g. 6 in 6P1) and start stop (e.g. 1 in 6P1) from description or code.
    Matches patterns like '6P1', '6P-1', '6P 1', '6 P 1', '6P.1', '6P_1', '6p1', '2P2', '5P1', '12P1'.
    Returns (cycle_num, start_stop_num, matched_str) or (None, None, None).
    """
    if not text:
        return None, None, None
    
    text_str = str(text).strip()
    
    # 1. Match standard patterns with boundary or separators like '6P1', '6P-1', '6P 1', '6 P 1', '6P.1', '6P_1'
    matches = re.findall(r'(?:^|[\s\-_.,/])([0-9]+)\s*[Pp]\s*[-_.]?\s*([0-9]+)(?:$|[\s\-_.,/])', text_str)
    if matches:
        c_str, s_str = matches[-1]
        try:
            return int(c_str), int(s_str), f"{c_str}P{s_str}"
        except ValueError:
            pass
            
    # 2. Match direct pattern like '6P1' or '2P2'
    direct = re.search(r'([0-9]+)\s*[Pp]\s*([0-9]+)', text_str)
    if direct:
        try:
            return int(direct.group(1)), int(direct.group(2)), f"{direct.group(1)}P{direct.group(2)}"
        except ValueError:
            pass
            
    return None, None, None

def compute_file_hash(file_path):
    """Computes MD5 hash of a file to check for duplicate imports."""
    hasher = hashlib.md5()
    with open(file_path, 'rb') as f:
        buf = f.read(65536)
        while len(buf) > 0:
            hasher.update(buf)
            buf = f.read(65536)
    return hasher.hexdigest()

def normalize_value(val):
    """Clean string values or format floats/ints."""
    if val is None or val == "" or val == '#N/A':
        return None
    if isinstance(val, str):
        val_str = val.strip()
        if val_str == "" or val_str == '#N/A':
            return None
        return val_str
    # If float with .0, return int
    if isinstance(val, float):
        if val.is_integer():
            return int(val)
    return val

def normalize_identifier(val):
    """Preserve an identifier as an opaque textual natural key.

    Numeric spreadsheet cells such as 157.0 become ``157`` through the normal
    value conversion, while textual identifiers (including dots, letters,
    slashes, hyphens and other characters) are never rewritten.
    """
    normalized = normalize_value(val)
    if normalized is None:
        return ""
    return str(normalized).strip()

def _optional_number(value, integer=False):
    """Parse an optional Excel numeric value without turning blank into zero."""
    value = normalize_value(value)
    if value in (None, ''):
        return None
    try:
        number = float(str(value).replace(',', '.'))
        return int(number) if integer else round(number, 4)
    except (TypeError, ValueError):
        return None


def _normalize_item_status(value):
    """Normalize PM13 round-trip item status without inventing inactivity.

    Corporate sheets normally do not contain this helper column, so blank/absent
    values remain ACTIVE. The PM13 export writes ATIVO/INATIVO in STATUS (apagar).
    """
    raw = normalize_value(value)
    if raw in (None, ''):
        return 'ACTIVE'
    token = str(raw).strip().upper()
    inactive = {'INACTIVE', 'INATIVO', 'INATIVA', '0', 'FALSE', 'FALSO', 'NÃO', 'NAO'}
    active = {'ACTIVE', 'ATIVO', 'ATIVA', '1', 'TRUE', 'VERDADEIRO', 'SIM'}
    if token in inactive:
        return 'INACTIVE'
    if token in active:
        return 'ACTIVE'
    # Unknown values are safer as ACTIVE; status is a PM13 helper, not a corporate field.
    return 'ACTIVE'


def format_code(val):
    """Normalize GPM or Equipment codes, keeping them as text without decimals."""
    if val is None:
        return ""
    val_norm = normalize_value(val)
    if val_norm is None:
        return ""
    if isinstance(val_norm, float):
        return str(int(val_norm))
    return str(val_norm)

HEADER_KEYWORDS = [
    'identificador', 'id', 'plano', 'código', 'codigo', 'descrição', 'descricao', 'desc',
    'equipamento', 'local', 'gpm', 'centro', 'condição', 'condicao', 'prioridade',
    'operação', 'operacao', 'oper', 'suboperação', 'suboperacao', 'suboper',
    'texto breve', 'texto longo', 'efetivo', 'homens', 'horas', 'unidade', 'ciclo',
    'parada', 'horizonte', 'objeto', 'floc', 'duração', 'duracao', 'procedimento',
    'posicao', 'posição', 'manutencao', 'manutenção', 'atividades', 'work center'
]

def find_header_row_index(rows, max_rows_to_check=10):
    """
    Scans up to max_rows_to_check rows of a sheet to locate the actual header row.
    Ranks rows by keyword matches and count of non-empty text cells.
    """
    if not rows:
        return 0
    
    best_row_idx = 0
    best_score = -1
    
    for r_idx in range(min(max_rows_to_check, len(rows))):
        row = rows[r_idx]
        if not row:
            continue
        
        non_empty_count = 0
        keyword_matches = 0
        
        for cell in row:
            if cell is not None:
                cell_str = str(cell).strip().lower()
                if cell_str != '' and cell_str != '#n/a':
                    non_empty_count += 1
                    if any(kw in cell_str for kw in HEADER_KEYWORDS):
                        keyword_matches += 1
                        
        score = (keyword_matches * 10) + non_empty_count
        if score > best_score and non_empty_count > 0:
            best_score = score
            best_row_idx = r_idx
            
    return best_row_idx

def extract_headers_from_rows(rows):
    """Returns (headers_list, header_row_index) by scanning the sheet for the header row."""
    if not rows:
        return [], 0
    hdr_idx = find_header_row_index(rows)
    header_row = rows[hdr_idx]
    
    headers = []
    for i, cell in enumerate(header_row):
        if cell is not None and str(cell).strip() != '' and str(cell).strip() != '#N/A':
            headers.append(str(cell).strip())
        else:
            headers.append(f"Coluna {i+1}")
    return headers, hdr_idx

def find_best_sheet(sheet_names, keywords, fallback_index=0):
    """Finds the best matching sheet name by exact matching, substring inclusion,
    and fuzzy similarity (SequenceMatcher). Falls back to sheet index if specified."""
    import difflib
    import unicodedata

    def norm(s):
        if not s:
            return ""
        s = str(s).lower().strip()
        s = ''.join(c for c in unicodedata.normalize('NFD', s) if unicodedata.category(c) != 'Mn')
        return s.replace(' ', '').replace('.', '').replace('-', '').replace('_', '').replace('/', '')

    norm_names = [(norm(n), n) for n in sheet_names if n]

    # 1. Exact or Substring match
    for kw in keywords:
        kw_norm = norm(kw)
        if not kw_norm:
            continue
        for norm_name, original in norm_names:
            if kw_norm == norm_name:
                return original
        for norm_name, original in norm_names:
            if kw_norm in norm_name or norm_name in kw_norm:
                return original

    # 2. Fuzzy similarity (difflib)
    best_sheet = None
    highest_ratio = 0.55
    for kw in keywords:
        kw_norm = norm(kw)
        if not kw_norm:
            continue
        for norm_name, original in norm_names:
            ratio = difflib.SequenceMatcher(None, kw_norm, norm_name).ratio()
            if ratio > highest_ratio:
                highest_ratio = ratio
                best_sheet = original

    if best_sheet:
        return best_sheet

    # 3. Fallback by position
    if fallback_index >= 0 and fallback_index < len(sheet_names):
        return sheet_names[fallback_index]
    return None

def normalize_header_key(value):
    """Normalize spreadsheet headers for resilient round-trip matching.

    Handles case, non-breaking spaces, repeated whitespace and harmless spacing
    around parentheses/slashes. This keeps PM13 helper columns detectable even
    after Excel or a corporate template slightly reformats their titles.
    """
    if value is None:
        return ''
    text = str(value).replace('\xa0', ' ').replace('\r', ' ').replace('\n', ' ')
    text = re.sub(r'\s+', ' ', text).strip().casefold()
    text = re.sub(r'\s*([()/])\s*', r'\1', text)
    return text


def parse_header(header_row):
    """Maps header columns using a normalized, tolerant key."""
    mapped = {}
    for idx, col in enumerate(header_row):
        if col is None:
            continue
        normalized = normalize_header_key(col)
        if normalized:
            mapped[normalized] = idx
    return mapped

def get_file_headers(file_path):
    """Reads Excel file headers and returns available sheets, detected sheets, and headers list for ALL sheets."""
    reader = XLSXReader(file_path)
    sheet_names = reader.get_sheet_names()
    if not sheet_names:
        raise ValueError("O arquivo Excel não possui planilhas válidas.")

    PLAN_KEYWORDS = ['codplanos', 'codplano', 'codigo', 'código', 'cadastroplano', 'listaplano', 'planos', 'plano', 'pm13', 'pm11', 'planospm', 'plano_reparo', 'planos_de_reparo', 'plano_de_manutencao', 'planos_manutencao']
    ITEM_KEYWORDS = ['itens', 'item', 'posicao', 'posição', 'manutencao', 'manutenção', 'ordem', 'ordens', 'equipamentos', 'listaitens', 'pm13itens', 'pm11itens', 'itens_manutencao', 'itens_de_manutencao']
    OP_KEYWORDS = ['operacao', 'operação', 'operacoes', 'operações', 'oper', 'operacao_reparo', 'operações_reparo', 'atividades_sap', 'operacoes_sap', 'operações_sap', 'atividades']
    LT_KEYWORDS = ['textolongo', 'texto_longo', 'textos_longos', 'textolongoreparo', 'texto_longo_reparo', 'textoslongos', 'procedimentos', 'procedimento', 'procedimento_tecnico', 'texto']

    plan_sheet = find_best_sheet(sheet_names, PLAN_KEYWORDS, fallback_index=0)
    remaining_1 = [n for n in sheet_names if n != plan_sheet]
    item_sheet = find_best_sheet(remaining_1, ITEM_KEYWORDS, fallback_index=0) if remaining_1 else plan_sheet

    remaining_2 = [n for n in sheet_names if n not in (plan_sheet, item_sheet)]
    op_sheet = find_best_sheet(remaining_2, OP_KEYWORDS, fallback_index=-1) if remaining_2 else None

    remaining_3 = [n for n in sheet_names if n not in (plan_sheet, item_sheet, op_sheet)]
    lt_sheet = find_best_sheet(remaining_3, LT_KEYWORDS, fallback_index=-1) if remaining_3 else None

    sheets_headers = {}
    for sheet in sheet_names:
        try:
            # Header detection only needs the first rows. Avoid reading the full
            # worksheet, which may contain a bloated Excel used range.
            rows = reader.read_sheet(sheet, max_rows=20)
            headers, _ = extract_headers_from_rows(rows)
            sheets_headers[sheet] = headers
        except Exception:
            sheets_headers[sheet] = []

    plan_headers_norm = {str(x).strip().lower() for x in sheets_headers.get(plan_sheet, [])}
    item_headers_norm = {str(x).strip().lower() for x in sheets_headers.get(item_sheet, [])}
    standard_match = ('plano' in plan_headers_norm and 'descrição do plano' in plan_headers_norm
                      and 'identificador' in item_headers_norm and 'plano reparo' in item_headers_norm)

    return {
        'sheet_names': sheet_names,
        'detected_plan_sheet': plan_sheet,
        'detected_item_sheet': item_sheet,
        'sheets_headers': sheets_headers,
        'standard_match': standard_match,
        'detected_operation_sheet': op_sheet,
        'detected_long_text_sheet': lt_sheet,
        'detected_entities': {'plans': bool(plan_sheet), 'items': bool(item_sheet),
                              'operations': bool(op_sheet), 'long_texts': bool(lt_sheet)}
    }


def parse_operation_sheets(reader, sheet_names, column_mapping=None, selected_entities=None):
    """Parse the two optional standard SAP relationship sheets with robust sheet and header detection."""
    operations, texts = [], []
    selected_set = set(normalize_selected_entities(selected_entities)) if selected_entities is not None else set(IMPORT_ENTITY_ORDER)
    
    def detect_headers(rows):
        if not rows: return None, 0
        for idx in range(min(10, len(rows))):
            r = [str(c).lower().strip() if c is not None else '' for c in rows[idx]]
            if any('identificador' in c or c == 'id' for c in r) and any('oper' in c or 'texto' in c or 'centro' in c or 'descri' in c for c in r):
                h = {}
                for col_idx, cell in enumerate(r):
                    if cell: h[cell] = col_idx
                return h, idx + 1
        hdr_idx = find_header_row_index(rows)
        h = {}
        if hdr_idx < len(rows) and rows[hdr_idx]:
            for col_idx, cell in enumerate(rows[hdr_idx]):
                if cell: h[str(cell).lower().strip()] = col_idx
        return h, hdr_idx + 1

    def find_val(row, headers, *names):
        for name in names:
            for k, idx in headers.items():
                if name in k and idx < len(row):
                    v = row[idx]
                    if v is not None and str(v).strip() != '':
                        # Long text is formatting-sensitive. Do not use the
                        # generic value normalizer, which strips outer newlines.
                        return v
        return None

    def find_exact_val(row, headers, *names):
        # Candidate order is significant.  In long-text sheets both
        # "OPERAÇÃO" (description) and "oper" (numeric code) may exist;
        # prefer the explicitly requested header instead of the leftmost one.
        for name in names:
            wanted = name.strip().lower()
            for key, idx in headers.items():
                if key.strip().lower() == wanted and idx < len(row):
                    value = row[idx]
                    if value is not None and str(value).strip() != '':
                        return normalize_value(value)
        return None

    def has_header(headers, *names, exact=False):
        if not headers:
            return False
        for name in names:
            wanted = name.strip().lower()
            for key in headers:
                current = key.strip().lower()
                matches = current == wanted if exact else wanted in current
                if matches:
                    return True
        return False

    def norm_op_sub(val):
        if val is None:
            return ''
        s = str(val).replace('.0', '').strip()
        if s in ('-', 'None', 'null', '#N/A', '#n/a'):
            return ''
        if s.isdigit():
            return s.zfill(4)
        return s

    # 1. Operation Sheet Detection
    op_sheet = None
    if 'operations' in selected_set and column_mapping and column_mapping.get('op_sheet_name'):
        op_sheet = column_mapping['op_sheet_name']
    if 'operations' in selected_set and (not op_sheet or op_sheet not in sheet_names):
        op_sheet = next((s for s in sheet_names if 'opera' in reader._normalize_name(s)), None)

    if 'operations' in selected_set and op_sheet and op_sheet in sheet_names:
        rows = reader.read_sheet(op_sheet)
        h, start_row = detect_headers(rows) if rows else (None, 0)
        op_map = (column_mapping or {}).get('operations', {}) if column_mapping else {}
        
        def get_op_col(row, mapping_key, candidates):
            if mapping_key in op_map and isinstance(op_map[mapping_key], int) and op_map[mapping_key] < len(row):
                return row[op_map[mapping_key]]
            if h:
                return find_val(row, h, *candidates)
            return None

        if rows and len(rows) > 1:
            header_offset = start_row if h else 1
            for rn in range(header_offset, len(rows)):
                row = rows[rn]
                if not row: continue
                ident = get_op_col(row, 'legacy_identifier', ['identificador', 'id'])
                code = get_op_col(row, 'operation_code', ['opera', 'oper', 'código', 'codigo'])
                short = get_op_col(row, 'short_text', ['texto breve', 'descri', 'texto'])
                if ident is None or code is None or short is None: continue
                sub_code = get_op_col(row, 'suboperation_code', ['sub opera', 'suboper', 'sub']) or ''
                wc = get_op_col(row, 'work_center', ['centro de trabalho', 'centro trabalho', 'ct']) or ''
                unit = get_op_col(row, 'unit', ['unidade', 'unid']) or 'H'
                hc = get_op_col(row, 'headcount', ['efetivo', 'homens', 'pess'])
                hours = get_op_col(row, 'hours', ['dura', 'horas', 'hora'])
                
                ident_str = normalize_identifier(ident)
                code_str = norm_op_sub(code)
                sub_str = norm_op_sub(sub_code)
                
                parsed_hc = None
                if hc is not None and str(hc).strip() != '':
                    try: parsed_hc = int(float(hc))
                    except: pass
                parsed_hours = None
                if hours is not None and str(hours).strip() != '':
                    try: parsed_hours = float(hours)
                    except: pass

                operations.append({
                    'row_number': rn + 1,
                    'legacy_identifier': ident_str,
                    'operation_code': code_str,
                    'suboperation_code': sub_str,
                    'work_center': str(wc).strip(),
                    'short_text': str(short).strip(),
                    'unit': str(unit).strip() or 'H',
                    'headcount': parsed_hc,
                    'hours': parsed_hours
                })

    # 2. Long Text Sheet Detection
    tx_sheet = None
    if 'long_texts' in selected_set and column_mapping and column_mapping.get('lt_sheet_name'):
        tx_sheet = column_mapping['lt_sheet_name']
    if 'long_texts' in selected_set and (not tx_sheet or tx_sheet not in sheet_names):
        tx_sheet = next((s for s in sheet_names if ('texto' in reader._normalize_name(s) and 'longo' in reader._normalize_name(s)) or 'textolongo' in reader._normalize_name(s)), None)

    if 'long_texts' in selected_set and tx_sheet and tx_sheet in sheet_names:
        rows = reader.read_sheet(tx_sheet)
        h, start_row = detect_headers(rows) if rows else (None, 0)
        lt_map = (column_mapping or {}).get('long_texts', {}) if column_mapping else {}

        def get_lt_col(row, mapping_key, candidates, is_exact=False):
            if mapping_key in lt_map and isinstance(lt_map[mapping_key], int) and lt_map[mapping_key] < len(row):
                val = row[lt_map[mapping_key]]
                if val is not None and str(val).strip() != '':
                    return val
            if h:
                return find_exact_val(row, h, *candidates) if is_exact else find_val(row, h, *candidates)
            return None

        def get_long_text_val(row, headers):
            if lt_map and 'text' in lt_map and isinstance(lt_map['text'], int) and lt_map['text'] < len(row):
                mapped_idx = lt_map['text']
                mapped_header = next((key for key, idx in (headers or {}).items() if idx == mapped_idx), '')
                # Never accept Texto breve as procedure content, even if an
                # older cached frontend mapped it by a broad "texto" match.
                if 'breve' not in mapped_header.lower():
                    v = row[mapped_idx]
                    if v is not None and str(v).strip() != '':
                        return normalize_value(v)
            if headers:
                for key, col_idx in headers.items():
                    k_lower = key.lower()
                    # Some PM13 sheets call the procedure column just "Texto".
                    # If it is not recognized, the positional fallback reads
                    # SUB OPER as text and drops every blank-suboperation row.
                    is_text_column = (
                        'longo' in k_lower or 'procedimento' in k_lower or
                        'detalhamento' in k_lower or k_lower.strip() == 'texto'
                    )
                    if is_text_column and 'breve' not in k_lower:
                        if col_idx < len(row):
                            val = row[col_idx]
                            if val is not None and str(val).strip() != '':
                                return val
            if len(row) > 6:
                val = row[6]
                if val is not None and str(val).strip() != '':
                    return val
            if len(row) > 7:
                val = row[7]
                if val is not None and str(val).strip() != '':
                    return val
            return None

        if rows and len(rows) > 1:
            header_offset = start_row if h else 1
            for rn in range(header_offset, len(rows)):
                row = rows[rn]
                if not row: continue
                ident = get_lt_col(row, 'legacy_identifier', ['identificador', 'id'])
                code_candidates = ['oper.', 'oper', 'operação', 'operacao']
                code = get_lt_col(row, 'operation_code', code_candidates, is_exact=True) or ''
                # Defensive correction for cached/legacy mappings that chose
                # the descriptive OPERAÇÃO column instead of numeric `oper`.
                if not str(code).strip().replace('.0', '').isdigit() and h:
                    numeric_code = find_exact_val(row, h, 'oper.', 'oper')
                    if numeric_code is not None and str(numeric_code).strip().replace('.0', '').isdigit():
                        code = numeric_code
                has_mapped_code = isinstance(lt_map.get('operation_code'), int)
                has_code_header = has_header(h, *code_candidates, exact=True)
                if not has_mapped_code and not has_code_header and (not str(code).strip().isdigit()) and len(row) > 4:
                    legacy_code = normalize_value(row[4])
                    if legacy_code is not None:
                        code = legacy_code
                
                sub_candidates = ['sub oper.', 'sub oper', 'suboper', 'sub']
                sub_code = get_lt_col(row, 'suboperation_code', sub_candidates) or ''
                has_mapped_sub = isinstance(lt_map.get('suboperation_code'), int)
                has_sub_header = has_header(h, *sub_candidates)
                if not has_mapped_sub and not has_sub_header and (not sub_code) and len(row) > 5:
                    legacy_sub = normalize_value(row[5])
                    if legacy_sub is not None and str(legacy_sub).strip().lower() not in ('none', 'null', 'nan', '#n/a', '-'):
                        sub_code = legacy_sub

                code_str = norm_op_sub(code)
                sub_str = norm_op_sub(sub_code)
                txt = get_long_text_val(row, h)
                # The main 0010 row is a visible long-text placeholder.  Its
                # text is intentionally empty, but the row itself must survive
                # the import so the long-text grid shows "0010 / -" before
                # the 0010 suboperations.
                is_empty_0010_header = code_str == '0010' and not sub_str
                if ident is None or ((txt is None or str(txt).strip() == '') and not is_empty_0010_header):
                    continue
                if is_empty_0010_header and (txt is None or str(txt).strip() == ''):
                    txt = ''

                grp = get_lt_col(row, 'group_code', ['grplistar.', 'geral'])
                num_grp = get_lt_col(row, 'group_counter', ['numgrprot'])
                
                ident_str = normalize_identifier(ident)
                raw_text = str(txt).replace('\r\n', '\n').replace('\r', '\n')
                parsed_structure = detect_structure(raw_text)
                texts.append({
                    'row_number': rn + 1,
                    'legacy_identifier': ident_str,
                    'operation_code': code_str,
                    'suboperation_code': sub_str,
                    'group_code': str(grp).strip() if grp is not None else None,
                    'group_counter': str(num_grp).strip() if num_grp is not None else None,
                    # If the source truly contains a hierarchy, normalize it now.
                    # Otherwise preserve it as clean free text without invented numbering.
                    'text': parsed_structure['rendered_text'],
                    'structure_mode': parsed_structure['mode'],
                    'structure_json': parsed_structure['structure_json'],
                    'source_text_original': raw_text,
                    'structure_confidence': parsed_structure.get('confidence', 0),
                })
                
    return operations, texts


IMPORT_ENTITY_ORDER = ('plans', 'items', 'operations', 'long_texts')


def normalize_selected_entities(selected_entities=None):
    """Return a stable, validated import scope (omitted means full import)."""
    if selected_entities is None:
        return list(IMPORT_ENTITY_ORDER)
    if not isinstance(selected_entities, (list, tuple, set)):
        raise ValueError("A selecao de entidades da importacao e invalida.")
    requested = {str(value).strip() for value in selected_entities}
    unknown = requested.difference(IMPORT_ENTITY_ORDER)
    if unknown:
        raise ValueError("Entidades de importacao desconhecidas: " + ', '.join(sorted(unknown)))
    selected = [name for name in IMPORT_ENTITY_ORDER if name in requested]
    if not selected:
        raise ValueError("Selecione pelo menos uma aba para importar.")
    return selected


def preview_import(file_path, default_headcount=1, column_mapping=None):
    """Loads spreadsheet, runs validations, and returns preview and diagnostic data.
    column_mapping: optional dict with explicit sheet name overrides and column index overrides:
      { 'plan_sheet_name': 'Cod Planos', 'item_sheet_name': 'Planos',
        'plans': {'legacy_code': 1, 'description': 2, ...},
        'items': {'legacy_identifier': 0, 'object_code': 1, ...} }
    """
    column_mapping = column_mapping or {}
    selected_entities = normalize_selected_entities(column_mapping.get('selected_entities'))
    selected_set = set(selected_entities)
    reader = XLSXReader(file_path)
    sheet_names = reader.get_sheet_names()

    # --- Keywords to detect Plans sheet (tries many naming variants) ---
    PLAN_KEYWORDS = [
        'codplanos', 'codplano', 'codigo', 'código', 'cadastroplano',
        'listaplano', 'planos', 'plano', 'pm13', 'pm11', 'planospm'
    ]
    # --- Keywords to detect Items sheet ---
    ITEM_KEYWORDS = [
        'itens', 'item', 'posicao', 'posição', 'planos', 'manutencao', 'manutenção',
        'ordem', 'ordens', 'operacoes', 'operações', 'atividades',
        'equipamentos', 'listaitens', 'pm13itens', 'pm11itens'
    ]

    # 1. Determine Plan Sheet
    if 'plans' not in selected_set:
        plan_sheet_name = column_mapping.get('plan_sheet_name') or (sheet_names[0] if sheet_names else None)
        plan_rows = []
        plan_hdr_idx = 0
        plan_header_map = {}
    elif column_mapping.get('plan_sheet_name'):
        plan_sheet_name = column_mapping['plan_sheet_name']
    else:
        plan_sheet_name = find_best_sheet(sheet_names, PLAN_KEYWORDS, fallback_index=0)

    if 'plans' in selected_set and (not plan_sheet_name or plan_sheet_name not in sheet_names):
        plan_sheet_name = sheet_names[0] if sheet_names else None

    if 'plans' in selected_set and not plan_sheet_name:
        raise ValueError(
            f"Não foi possível identificar a aba de Planos. Abas encontradas: {', '.join(sheet_names) if sheet_names else 'nenhuma'}."
        )

    plan_rows = reader.read_sheet(plan_sheet_name) if 'plans' in selected_set else []
    if 'plans' in selected_set and not plan_rows:
        raise ValueError(f"Aba '{plan_sheet_name}' está vazia.")

    plan_hdr_idx = find_header_row_index(plan_rows) if plan_rows else 0
    plan_header_map = parse_header(plan_rows[plan_hdr_idx]) if plan_rows else {}

    # Column mapping helper — checks explicit mapping first, then keyword search
    def get_col_val(row, header_map, candidates, mapping_key=None, sheet_key='plans', default=None):
        # 1. Explicit column index from user mapping
        if sheet_key in column_mapping and mapping_key:
            idx = column_mapping[sheet_key].get(mapping_key)
            if idx is not None and isinstance(idx, int) and idx < len(row):
                return row[idx]
        # 2. Search by normalized column name.
        for cand in candidates:
            key = normalize_header_key(cand)
            if key in header_map:
                idx = header_map[key]
                if idx < len(row):
                    return row[idx]
        return default

    # Mapped plans list
    parsed_plans = []
    import_errors = []
    
    # Track duplicates within import
    seen_plan_codes = set()
    
    # We read rows starting right after header row
    for r_idx in range(plan_hdr_idx + 1, len(plan_rows)):
        row = plan_rows[r_idx]
        if not row:
            continue
            
        plano_code = normalize_value(get_col_val(row, plan_header_map,
            ['plano', 'codigo plano', 'cod plano', 'cod_plano', 'código', 'codigo', 'code'],
            mapping_key='legacy_code', sheet_key='plans'))
        desc = normalize_value(get_col_val(row, plan_header_map,
            ['descrição do plano', 'descricao do plano', 'descricao', 'desc', 'descrição', 'description', 'nome'],
            mapping_key='description', sheet_key='plans'))
        ciclo = normalize_value(get_col_val(row, plan_header_map,
            ['ciclo', 'cycle'],
            mapping_key='cycle', sheet_key='plans'))
        unid = normalize_value(get_col_val(row, plan_header_map,
            ['unid.', 'unid', 'unidade', 'unit', 'und'],
            mapping_key='unit', sheet_key='plans'))
        texto_ciclo = normalize_value(get_col_val(row, plan_header_map,
            ['texto ciclo', 'texto do ciclo', 'cycle_text', 'texto'],
            mapping_key='cycle_text', sheet_key='plans'))
        horiz_abert = normalize_value(get_col_val(row, plan_header_map,
            ['horiz abertura', 'horizonte abertura', 'horizonte', 'horizon', 'horiz.'],
            mapping_key='opening_horizon', sheet_key='plans'))
        contador_ref = normalize_value(get_col_val(row, plan_header_map,
            ['parada início', 'parada inicio', 'parada de início', 'parada de inicio', 'parada inicial', 'parada', 'inicio', 'início', 'start', 'contador - planos de paradas', 'contador', 'counter', 'cont', 'ref', 'fase'],
            mapping_key='reference_counter', sheet_key='plans'))
        
        # If Plano and Desc are empty, skip (could be a separator row)
        if plano_code is None and desc is None:
            # Check if there is other data
            non_empty = [v for v in row if v is not None]
            if len(non_empty) > 1:
                import_errors.append({
                    'sheet_name': plan_sheet_name,
                    'row_number': r_idx + 1,
                    'field_name': 'Plano',
                    'severity': 'WARNING',
                    'message': 'Linha de separação ou formato inválido ignorada.',
                    'original_value': str(row[:5])
                })
            continue

        # Parse cycle, start stop, and detect divergence from description or code (e.g. 6P1, 5P1, 2P2, 3P1)
        desc_clean = str(desc).strip() if desc else ""
        ext_cycle, ext_start, ext_pattern = extract_cycle_and_start_from_text(desc_clean)
        if not ext_cycle and plano_code:
            ext_cycle, ext_start, ext_pattern = extract_cycle_and_start_from_text(plano_code)

        # Convert cycle
        c_val = None
        if ciclo is not None:
            try:
                c_val = int(float(str(ciclo)))
            except ValueError:
                pass
        elif ext_cycle is not None:
            c_val = ext_cycle
                
        # Convert opening horizon
        h_val = 0.0
        if horiz_abert is not None:
            try:
                h_val = float(str(horiz_abert).replace(',', '.'))
            except ValueError:
                pass

        # Convert reference counter / start stop
        cnt_val = None
        auto_start_filled = False
        if contador_ref is not None and str(contador_ref).strip() != '':
            try:
                cnt_val = int(float(str(contador_ref)))
            except ValueError:
                pass
        
        # If empty in spreadsheet, auto-fill from extracted pattern (e.g. 2P1 -> 1, 2P2 -> 2, 6P1 -> 1)
        if cnt_val is None and ext_start is not None:
            cnt_val = ext_start
            auto_start_filled = True

        divergence = False
        divergence_msg = None

        # Check for cycle divergence between spreadsheet column and description pattern (e.g. 6P vs ciclo 5)
        if ext_cycle is not None and c_val is not None and c_val != ext_cycle:
            divergence = True
            divergence_msg = f"Divergência de Ciclo: A descrição indica ciclo de {ext_cycle} paradas ({ext_pattern}), mas a coluna Ciclo informa {c_val}."
            import_errors.append({
                'sheet_name': plan_sheet_name,
                'row_number': r_idx + 1,
                'field_name': 'Ciclo / Descrição',
                'severity': 'WARNING',
                'message': divergence_msg,
                'original_value': f"Descrição='{desc_clean}' | Ciclo={c_val}"
            })
        elif ext_start is not None and not auto_start_filled and cnt_val is not None and cnt_val != ext_start:
            divergence = True
            divergence_msg = f"Divergência de Início: A descrição indica início na parada {ext_start} ({ext_pattern}), mas a coluna Parada Início informa {cnt_val}."
            import_errors.append({
                'sheet_name': plan_sheet_name,
                'row_number': r_idx + 1,
                'field_name': 'Parada Início / Descrição',
                'severity': 'WARNING',
                'message': divergence_msg,
                'original_value': f"Descrição='{desc_clean}' | Início={cnt_val}"
            })
        elif c_val is not None and ext_start is not None and ext_start > c_val:
            divergence = True
            divergence_msg = f"Inconsistência de Início: Parada de início ({ext_start}) é maior que o ciclo ({c_val} paradas)."
            import_errors.append({
                'sheet_name': plan_sheet_name,
                'row_number': r_idx + 1,
                'field_name': 'Parada Início',
                'severity': 'WARNING',
                'message': divergence_msg,
                'original_value': f"Início={ext_start} > Ciclo={c_val}"
            })

        # Run validators
        row_issues = validate_plan_row(r_idx + 1, plano_code, desc, ciclo, unid, texto_ciclo, horiz_abert, contador_ref)
        for issue in row_issues:
            import_errors.append({
                'sheet_name': plan_sheet_name,
                'row_number': r_idx + 1,
                'field_name': issue['field'],
                'severity': issue['severity'],
                'message': issue['message'],
                'original_value': str(issue['value'])
            })
            
        plano_code_upper = str(plano_code).upper().strip() if plano_code else ""
        
        # Deduplicate plans: multiple rows referencing the same plan code is normal
        if plano_code_upper:
            if plano_code_upper in seen_plan_codes:
                continue # Skip adding duplicate plan entry
            seen_plan_codes.add(plano_code_upper)

        parsed_plans.append({
            'row_number': r_idx + 1,
            'legacy_code': plano_code_upper,
            'description': desc_clean,
            'character_count': len(desc_clean),
            'cycle': c_val,
            'unit': str(unid).strip() if unid else "PRD",
            'cycle_text': str(texto_ciclo).strip() if texto_ciclo else (f"{c_val} PARADAS" if c_val else ""),
            'opening_horizon': h_val if h_val > 0 else 12.0,
            'reference_counter': cnt_val,
            'extracted_cycle': ext_cycle,
            'extracted_start_stop': ext_start,
            'extracted_pattern': ext_pattern,
            'auto_start_filled': auto_start_filled,
            'divergence': divergence,
            'divergence_message': divergence_msg,
            'is_duplicate': False,
            'is_valid': not any(x['severity'] == 'ERROR' for x in row_issues)
        })

    # 2. Determine Item Sheet
    if 'items' not in selected_set:
        item_sheet_name = column_mapping.get('item_sheet_name') or plan_sheet_name
    elif column_mapping.get('item_sheet_name'):
        item_sheet_name = column_mapping['item_sheet_name']
    else:
        remaining = [n for n in sheet_names if n != plan_sheet_name]
        item_sheet_name = find_best_sheet(remaining, ITEM_KEYWORDS, fallback_index=0) if remaining else plan_sheet_name

    if not item_sheet_name or item_sheet_name not in sheet_names:
        item_sheet_name = plan_sheet_name

    item_rows = reader.read_sheet(item_sheet_name) if 'items' in selected_set else []
    if 'items' in selected_set and not item_rows:
        raise ValueError(f"Aba '{item_sheet_name}' está vazia.")

    item_hdr_idx = find_header_row_index(item_rows) if item_rows else 0
    item_header_map = parse_header(item_rows[item_hdr_idx]) if item_rows else {}

    # Some corporate workbooks keep manpower in a separate BALANCEAMENTO tab
    # instead of the item tab.  Use the item description as the linking key so
    # those files preserve their original HH (hours x people) during import.
    balance_headcount_by_description = {}
    balance_sheet_name = next((s for s in sheet_names if 'balanceamento' in s.lower()), None)
    if 'items' in selected_set and balance_sheet_name and balance_sheet_name != item_sheet_name:
        try:
            balance_rows = reader.read_sheet(balance_sheet_name)
            balance_header_idx = next((idx for idx, candidate in enumerate(balance_rows[:10])
                                       if 'homem' in parse_header(candidate) and
                                       any(k in parse_header(candidate) for k in ('descrição item', 'descricao item'))), None)
            if balance_header_idx is not None:
                balance_headers = parse_header(balance_rows[balance_header_idx])
                desc_col = balance_headers.get('descrição item', balance_headers.get('descricao item'))
                people_col = balance_headers.get('homem')
                for balance_row in balance_rows[balance_header_idx + 1:]:
                    if desc_col is None or people_col is None or desc_col >= len(balance_row) or people_col >= len(balance_row):
                        continue
                    description_key = str(normalize_value(balance_row[desc_col]) or '').strip().casefold()
                    people_value = normalize_value(balance_row[people_col])
                    if description_key and people_value not in (None, ''):
                        try:
                            balance_headcount_by_description[description_key] = int(float(str(people_value).replace(',', '.')))
                        except (TypeError, ValueError):
                            pass
        except Exception:
            balance_headcount_by_description = {}

    parsed_items = []
    seen_item_identifiers = set()
    
    # We read rows starting right after detected item header row
    for r_idx in range(item_hdr_idx + 1, len(item_rows)):
        row = item_rows[r_idx]
        if not row:
            continue
            
        local_instal = format_code(get_col_val(row, item_header_map,
            ['local de instalação', 'local de instalacao', 'local instalacao', 'equipamento',
             'local', 'objeto', 'object', 'equip', 'codigo equip', 'cod equip', 'floc', 'functional location'],
            mapping_key='object_code', sheet_key='items'))
        gpm = format_code(get_col_val(row, item_header_map,
            ['gpm', 'tecnico', 'técnico', 'resp', 'responsavel', 'responsável'],
            mapping_key='gpm', sheet_key='items'))
        centro = normalize_value(get_col_val(row, item_header_map,
            ['centro de trabalho', 'centro trabalho', 'equipe', 'work center', 'workcenter', 'ct', 'centro'],
            mapping_key='work_center', sheet_key='items'))
        condicao = normalize_value(get_col_val(row, item_header_map,
            ['condição', 'condicao', 'condition', 'cond'],
            mapping_key='condition_code', sheet_key='items'))
        prioridade = normalize_value(get_col_val(row, item_header_map,
            ['prioridade', 'priority', 'prior', 'prio'],
            mapping_key='priority', sheet_key='items'))
        plano_reparo = normalize_value(get_col_val(row, item_header_map,
            ['plano inspeção', 'plano inspecao', 'plano inspeçao', 'plano inspecão',
             'plano reparo', 'plano', 'plan', 'plano de reparo', 'cod plano', 'inspeção', 'inspeçao'],
            mapping_key='plan_code', sheet_key='items'))
        identificador = normalize_value(get_col_val(row, item_header_map,
            ['identificador', 'id item', 'id', 'identifier', 'ident', 'numero', 'número', 'num', 'nro'],
            mapping_key='legacy_identifier', sheet_key='items'))
        contador_start = normalize_value(get_col_val(row, item_header_map,
            ['contador', 'inicio', 'início', 'start', 'cont inicio', 'contador inicio'],
            mapping_key='start_counter', sheet_key='items'))
        desc_item = normalize_value(get_col_val(row, item_header_map,
            ['descrição item', 'descricao item', 'descricao', 'descrição', 'description',
             'desc', 'titulo', 'título', 'text', 'texto'],
            mapping_key='description', sheet_key='items'))
        duracao = normalize_value(get_col_val(row, item_header_map,
            ['t(h)', 'duracao', 'duração', 'horas', 'duration', 'tempo', 'h', 'th'],
            mapping_key='duration_hours', sheet_key='items'))
        efetivo_raw = normalize_value(get_col_val(row, item_header_map,
            ['homem', 'homens', 'efetivo', 'headcount', 'pessoas', 'qtd pessoas', 'quantidade pessoas'],
            mapping_key='headcount', sheet_key='items'))

        # PM13 round-trip helper columns. They are intentionally marked (apagar)
        # in the corporate workbook because SAP/corporate loaders do not consume
        # them, but the PM13 importer uses them to preserve discipline workload.
        ele_headcount = _optional_number(get_col_val(row, item_header_map,
            ['ele efetivo (apagar)', 'ele efetivo', 'efetivo ele (apagar)', 'efetivo ele']), integer=True)
        ele_hours = _optional_number(get_col_val(row, item_header_map,
            ['ele horas (apagar)', 'ele horas', 'horas ele (apagar)', 'horas ele']))
        mec_headcount = _optional_number(get_col_val(row, item_header_map,
            ['mec efetivo (apagar)', 'mec efetivo', 'efetivo mec (apagar)', 'efetivo mec']), integer=True)
        mec_hours = _optional_number(get_col_val(row, item_header_map,
            ['mec horas (apagar)', 'mec horas', 'horas mec (apagar)', 'horas mec']))
        sol_headcount = _optional_number(get_col_val(row, item_header_map,
            ['sol efetivo (apagar)', 'sol efetivo', 'efetivo sol (apagar)', 'efetivo sol']), integer=True)
        sol_hours = _optional_number(get_col_val(row, item_header_map,
            ['sol horas (apagar)', 'sol horas', 'horas sol (apagar)', 'horas sol']))
        specialty_header_aliases = (
            'ele efetivo (apagar)', 'ele efetivo', 'efetivo ele (apagar)', 'efetivo ele',
            'ele horas (apagar)', 'ele horas', 'horas ele (apagar)', 'horas ele',
            'mec efetivo (apagar)', 'mec efetivo', 'efetivo mec (apagar)', 'efetivo mec',
            'mec horas (apagar)', 'mec horas', 'horas mec (apagar)', 'horas mec',
            'sol efetivo (apagar)', 'sol efetivo', 'efetivo sol (apagar)', 'efetivo sol',
            'sol horas (apagar)', 'sol horas', 'horas sol (apagar)', 'horas sol')
        specialty_columns_present = any(normalize_header_key(k) in item_header_map
                                        for k in specialty_header_aliases)

        item_status = _normalize_item_status(get_col_val(row, item_header_map,
            ['status (apagar)', 'status item (apagar)', 'status', 'ativo/inativo', 'ativo inativo']))

        efetivo = default_headcount
        if efetivo_raw not in (None, ''):
            try:
                # Zero is an explicit manpower value, not a missing value.
                # Preserve it so duration x headcount also remains zero HH.
                efetivo = int(float(str(efetivo_raw).replace(',', '.')))
            except (TypeError, ValueError):
                efetivo = default_headcount
        elif desc_item:
            efetivo = balance_headcount_by_description.get(str(desc_item).strip().casefold(), default_headcount)

        # Ignore residual formatting/formula tails that do not describe an item.
        # A work center alone (the pattern seen in million-line corrupted tails)
        # is not enough to create a maintenance item.
        source_has_item_identity = any(v not in (None, '') for v in
                                       (local_instal, desc_item, plano_reparo, identificador))
        if not source_has_item_identity:
            continue

        # Fallback defaults for missing/empty fields
        if not identificador:
            identificador = str(r_idx)
        if not local_instal:
            local_instal = "SEM_EQUIPAMENTO"
        if not gpm:
            gpm = "000"
        if not centro:
            centro = "GERAL"
        if not condicao:
            condicao = "Q"

        # If everything except auto-assigned defaults is empty, skip empty separator row
        if local_instal == "SEM_EQUIPAMENTO" and gpm == "000" and centro == "GERAL" and not desc_item and not plano_reparo:
            continue
            
        # Run validations
        row_issues = validate_item_row(r_idx + 1, local_instal, gpm, centro, condicao, prioridade, plano_reparo, identificador, contador_start, desc_item, duracao, efetivo)
        for issue in row_issues:
            # We don't want to log "efetivo pendente" as a critical warning blocking previews
            import_errors.append({
                'sheet_name': item_sheet_name,
                'row_number': r_idx + 1,
                'field_name': issue['field'],
                'severity': issue['severity'],
                'message': issue['message'],
                'original_value': str(issue['value'])
            })
            
        # Parse data types
        id_str = normalize_identifier(identificador)
        plano_reparo_upper = str(plano_reparo).upper().strip() if plano_reparo else ""
        
        # Check duplicate identifier within import
        is_duplicate = False
        if id_str:
            if id_str in seen_item_identifiers:
                is_duplicate = True
                import_errors.append({
                    'sheet_name': item_sheet_name,
                    'row_number': r_idx + 1,
                    'field_name': 'Identificador',
                    'severity': 'WARNING',
                    'message': f"Identificador do item duplicado na planilha: {id_str}.",
                    'original_value': id_str
                })
            else:
                seen_item_identifiers.add(id_str)
                
        # Resolve object type based on format (only numbers -> EQUIPAMENTO, alphabetic with hinfens -> LOCAL)
        object_type = 'LOCAL DE INSTALAÇÃO'
        if local_instal.isdigit():
            object_type = 'EQUIPAMENTO'
            
        # Convert duration.  The PM13 export uses T(h), which is explicitly
        # expressed in HOURS and must round-trip without the generic import
        # wizard default (MINUTES) dividing it by 60.  Other ambiguous headers
        # continue to honor the unit chosen by the user in the import wizard.
        explicit_hour_headers = {
            't(h)', 't (h)', 'tempo(h)', 'tempo (h)', 'duração(h)', 'duração (h)',
            'duracao(h)', 'duracao (h)', 'duration(h)', 'duration (h)'
        }
        detected_duration_is_hours = any(normalize_header_key(header) in item_header_map
                                         for header in explicit_hour_headers)
        duration_unit = ('HOURS' if detected_duration_is_hours else
                         (column_mapping.get('duration_unit', 'MINUTES') if column_mapping else 'MINUTES'))
        d_val = 0.0
        if duracao is not None:
            try:
                raw_dur = float(str(duracao).replace(',', '.'))
                if duration_unit == 'MINUTES':
                    d_val = round(raw_dur / 60.0, 2)
                else:
                    d_val = round(raw_dur, 2)
            except ValueError:
                pass
                
        # Convert priority
        p_val = 3
        if prioridade is not None:
            try:
                p_val = int(float(str(prioridade)))
            except ValueError:
                pass
                
        # Convert start counter
        cnt_start = None
        if contador_start is not None:
            try:
                cnt_start = int(float(str(contador_start)))
            except ValueError:
                pass

        # Check if plano reparo exists in plans; if not, auto-register plan from item row
        plan_not_found = False
        if plano_reparo_upper and 'plans' in selected_set:
            if plano_reparo_upper not in seen_plan_codes:
                seen_plan_codes.add(plano_reparo_upper)
                plan_desc_val = normalize_value(get_col_val(row, item_header_map,
                    ['descrição do plano', 'descricao do plano', 'descricao plano', 'desc plano'],
                    mapping_key='description', sheet_key='plans')) or f"Plano {plano_reparo_upper}"
                ext_c, ext_s, ext_pat = extract_cycle_and_start_from_text(plan_desc_val)
                if not ext_c:
                    ext_c, ext_s, ext_pat = extract_cycle_and_start_from_text(plano_reparo_upper)
                
                auto_cyc = ext_c or 3
                auto_start = ext_s or 1
                parsed_plans.append({
                    'row_number': r_idx + 1,
                    'legacy_code': plano_reparo_upper,
                    'description': str(plan_desc_val).strip(),
                    'character_count': len(str(plan_desc_val).strip()),
                    'cycle': auto_cyc,
                    'unit': 'PRD',
                    'cycle_text': f"{auto_cyc} PARADAS",
                    'opening_horizon': 12.0,
                    'reference_counter': auto_start,
                    'extracted_cycle': ext_c,
                    'extracted_start_stop': ext_s,
                    'extracted_pattern': ext_pat,
                    'auto_start_filled': True,
                    'divergence': False,
                    'divergence_message': None,
                    'is_duplicate': False,
                    'is_valid': True
                })

        parsed_items.append({
            'row_number': r_idx + 1,
            'legacy_identifier': id_str,
            'plano_reparo_code': plano_reparo_upper,
            'object_type': object_type,
            'object_code': local_instal,
            'gpm': gpm,
            'work_center': str(centro).strip() if centro else "",
            'condition_code': str(condicao).upper().strip() if condicao else "Q",
            'priority': p_val,
            'legacy_start': cnt_start,
            'description': str(desc_item).strip() if desc_item else "",
            'character_count': len(str(desc_item).strip()) if desc_item else 0,
            'duration_hours': d_val,
            'headcount': efetivo,
            'ele_headcount': ele_headcount,
            'ele_hours': ele_hours,
            'mec_headcount': mec_headcount,
            'mec_hours': mec_hours,
            'sol_headcount': sol_headcount,
            'sol_hours': sol_hours,
            'status': item_status,
            'specialty_columns_present': specialty_columns_present,
            'is_duplicate': is_duplicate,
            'validation_status': ('ERROR' if any(x['severity'] == 'ERROR' for x in row_issues)
                                  else 'WARNING' if row_issues or is_duplicate else 'OK'),
            'validation_issues': ([{'code': 'duplicate_identifier', 'severity': 'WARNING',
                                    'message': 'Identificador repetido na planilha; renumerado automaticamente.'}]
                                  if is_duplicate else []) +
                                 [{'code': str(x.get('field') or 'validation'), 'severity': x['severity'],
                                   'message': x['message']} for x in row_issues],
            'plan_not_found': plan_not_found,
            'is_valid': not any(x['severity'] == 'ERROR' for x in row_issues)
        })

    # Compile suggested cycles for catalog
    unique_cycles = {}
    # Prefill 1 to 20 PRD cycles so they are always available in the catalog
    for i in range(1, 21):
        unique_cycles[(i, 'PRD')] = {
            'cycle': i,
            'unit': 'PRD',
            'cycle_text': 'PARADA' if i == 1 else f"{i} PARADAS",
            'opening_horizon': 100.0
        }
        
    for p in parsed_plans:
        if p['is_valid'] and p['cycle'] is not None and p['unit']:
            key = (p['cycle'], p['unit'])
            if key not in unique_cycles:
                unique_cycles[key] = {
                    'cycle': p['cycle'],
                    'unit': p['unit'],
                    'cycle_text': p['cycle_text'],
                    'opening_horizon': p['opening_horizon']
                }

    # Count issues
    err_count = sum(1 for x in import_errors if x['severity'] == 'ERROR')
    warn_count = sum(1 for x in import_errors if x['severity'] == 'WARNING')
    
    specialty_helper_rows = sum(1 for x in parsed_items if x.get('specialty_columns_present'))
    specialty_helper_nonzero_rows = sum(
        1 for x in parsed_items
        if x.get('specialty_columns_present') and any(
            float(x.get(field) or 0) != 0
            for field in ('ele_headcount', 'ele_hours', 'mec_headcount', 'mec_hours', 'sol_headcount', 'sol_hours')
        )
    )
    specialty_helper_headers = sorted(
        key for key in item_header_map
        if any(token in key for token in ('ele efetivo', 'ele horas', 'mec efetivo', 'mec horas', 'sol efetivo', 'sol horas'))
    )

    summary = {
        'filename': os.path.basename(file_path),
        'file_hash': compute_file_hash(file_path),
        'total_plans': len(parsed_plans) if 'plans' in selected_set else 0,
        'valid_plans': sum(1 for x in parsed_plans if x['is_valid']) if 'plans' in selected_set else 0,
        'total_items': len(parsed_items) if 'items' in selected_set else 0,
        'valid_items': sum(1 for x in parsed_items if x['is_valid']) if 'items' in selected_set else 0,
        'duplicate_plans': sum(1 for x in parsed_plans if x['is_duplicate']),
        'duplicate_items': sum(1 for x in parsed_items if x['is_duplicate']),
        'error_count': err_count,
        'warning_count': warn_count,
        'sheet_names': reader.get_sheet_names(),
        'specialty_helper_rows': specialty_helper_rows if 'items' in selected_set else 0,
        'specialty_helper_nonzero_rows': specialty_helper_nonzero_rows if 'items' in selected_set else 0,
        'specialty_helper_headers': specialty_helper_headers if 'items' in selected_set else []
    }
    
    parsed_operations, parsed_long_texts = parse_operation_sheets(
        reader, sheet_names, column_mapping=column_mapping, selected_entities=selected_entities)
    if 'operations' not in selected_set:
        parsed_operations = []
    if 'long_texts' not in selected_set:
        parsed_long_texts = []
    text_counts = {}
    for text_row in parsed_long_texts:
        # Empty 0010 header placeholders are displayed in the long-text grid,
        # but they are not actual procedure content for validation purposes.
        if not str(text_row.get('text') or '').strip():
            continue
        key = (text_row['legacy_identifier'], text_row['operation_code'], text_row['suboperation_code'])
        text_counts[key] = text_counts.get(key, 0) + 1
    suboperations_by_item = {}
    operation_keys = set()
    for operation in parsed_operations if 'operations' in selected_set else []:
        key = (operation['legacy_identifier'], operation['operation_code'], operation['suboperation_code'])
        operation_keys.add(key)
        if operation['operation_code'] == '0010' and operation['suboperation_code']:
            suboperations_by_item.setdefault(operation['legacy_identifier'], set()).add(operation['suboperation_code'])
    for operation in parsed_operations:
        key = (operation['legacy_identifier'], operation['operation_code'], operation['suboperation_code'])
        issues = validate_operation_structure(
            operation['operation_code'], operation['suboperation_code'], operation['short_text'],
            text_counts.get(key, 0), suboperations_by_item.get(operation['legacy_identifier']))
        if 'long_texts' not in selected_set:
            issues = [issue for issue in issues
                      if issue.get('code') not in ('missing_long_text', 'header_has_long_text')]
        for issue in issues:
            import_errors.append({
                'sheet_name': 'OPERAÇÃO', 'row_number': operation['row_number'],
                'field_name': 'Estrutura da operação', 'severity': issue['severity'],
                'message': issue['message'],
                'original_value': f"{operation['operation_code']}/{operation['suboperation_code'] or '-'}"
            })
    for text_row in parsed_long_texts if {'operations', 'long_texts'}.issubset(selected_set) else []:
        key = (text_row['legacy_identifier'], text_row['operation_code'], text_row['suboperation_code'])
        if key not in operation_keys:
            import_errors.append({
                'sheet_name': 'TEXTO LONGO', 'row_number': text_row['row_number'],
                'field_name': 'Vínculo da operação', 'severity': 'ERROR',
                'message': 'Texto longo sem correspondência exata com item, operação e suboperação.',
                'original_value': f"{text_row['legacy_identifier']} / {text_row['operation_code']} / {text_row['suboperation_code'] or '-'}"
            })
    summary['error_count'] = sum(1 for issue in import_errors if issue['severity'] == 'ERROR')
    summary['warning_count'] = sum(1 for issue in import_errors if issue['severity'] == 'WARNING')
    summary['selected_entities'] = selected_entities
    summary['skipped_entities'] = [name for name in IMPORT_ENTITY_ORDER if name not in selected_set]
    summary['total_operations'] = len(parsed_operations) if 'operations' in selected_set else 0
    summary['total_long_texts'] = len(parsed_long_texts) if 'long_texts' in selected_set else 0
    return {
        'summary': summary,
        'selected_entities': selected_entities,
        'plans': parsed_plans if 'plans' in selected_set else [],
        'items': parsed_items if 'items' in selected_set else [],
        'operations': parsed_operations if 'operations' in selected_set else [],
        'long_texts': parsed_long_texts if 'long_texts' in selected_set else [],
        'errors': import_errors,
        'suggested_cycles': list(unique_cycles.values()) if 'plans' in selected_set else []
    }

def _verify_imported_specialty_helpers(cursor, project_id, preview_items, item_id_lookup=None):
    """Abort/rollback if explicit gray helper columns were silently lost.

    This is intentionally strict only for rows where the PM13 helper columns
    were detected in the source workbook. Corporate workbooks without these
    columns keep the historical behavior and are not forced to contain them.
    """
    mismatches = []
    checked = 0
    for row in preview_items or []:
        if not row.get('is_valid', True) or not row.get('specialty_columns_present'):
            continue
        source_ident = normalize_identifier(row.get('legacy_identifier'))
        db_row = None
        if item_id_lookup and source_ident in item_id_lookup:
            db_row = cursor.execute(
                """SELECT legacy_identifier,ele_headcount,ele_hours,mec_headcount,mec_hours,sol_headcount,sol_hours
                   FROM maintenance_items WHERE id=? AND project_id=?""",
                (item_id_lookup[source_ident], project_id)).fetchone()
        if db_row is None:
            db_row = cursor.execute(
                """SELECT legacy_identifier,ele_headcount,ele_hours,mec_headcount,mec_hours,sol_headcount,sol_hours
                   FROM maintenance_items WHERE project_id=? AND legacy_identifier=? AND deleted_at IS NULL
                   ORDER BY id DESC LIMIT 1""",
                (project_id, source_ident)).fetchone()
        if db_row is None:
            mismatches.append(f'{source_ident}: item nao localizado apos gravacao')
            continue
        checked += 1
        expected = {
            'ele_headcount': int(row.get('ele_headcount') or 0),
            'ele_hours': float(row.get('ele_hours') or 0),
            'mec_headcount': int(row.get('mec_headcount') or 0),
            'mec_hours': float(row.get('mec_hours') or 0),
            'sol_headcount': int(row.get('sol_headcount') or 0),
            'sol_hours': float(row.get('sol_hours') or 0),
        }
        actual = {
            'ele_headcount': int(db_row['ele_headcount'] or 0),
            'ele_hours': float(db_row['ele_hours'] or 0),
            'mec_headcount': int(db_row['mec_headcount'] or 0),
            'mec_hours': float(db_row['mec_hours'] or 0),
            'sol_headcount': int(db_row['sol_headcount'] or 0),
            'sol_hours': float(db_row['sol_hours'] or 0),
        }
        if any(abs(float(expected[k]) - float(actual[k])) > 1e-9 for k in expected):
            mismatches.append(f"{source_ident}: esperado={expected} gravado={actual}")
        if len(mismatches) >= 10:
            break
    if mismatches:
        raise RuntimeError(
            'A importacao foi cancelada porque as colunas cinza ELE/MEC/SOL foram detectadas, '
            'mas os valores nao foram preservados no banco. Nenhum dado parcial foi mantido. '
            'Amostra: ' + ' | '.join(mismatches))
    return checked


def confirm_import(project_id, preview_data, merge_mode='replace'):
    """Performs the actual database inserts under a single SQLite transaction."""
    if merge_mode not in ('replace', 'merge'):
        raise ValueError("Modo de importação inválido. Use 'replace' ou 'merge'.")
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("BEGIN IMMEDIATE")
        entity_tables = {
            'long_texts': 'operation_long_texts',
            'operations': 'item_operations',
            'items': 'maintenance_items',
            'plans': 'plans',
            'cycles': 'cycle_catalog',
        }
        counts_before = {}
        for label, table in entity_tables.items():
            cursor.execute(f"SELECT COUNT(*) FROM {table} WHERE project_id=?", (project_id,))
            counts_before[label] = cursor.fetchone()[0]
        
        # 1. If replace, clear existing data
        if merge_mode == 'replace':
            # A replacement changes the item identity set. Any open manual
            # balance draft belongs to the previous catalog and must not leak
            # into the newly imported scenario.
            cursor.execute("""UPDATE manual_balance_sessions
                SET status='DISCARDED',updated_at=CURRENT_TIMESTAMP
                WHERE project_id=? AND status='DRAFT'""", (project_id,))
            # Delete children first as an explicit, auditable replacement.
            # The whole routine is one transaction: any later failure restores
            # the original project automatically through rollback.
            cursor.execute("DELETE FROM operation_long_texts WHERE project_id = ?;", (project_id,))
            cursor.execute("DELETE FROM item_operations WHERE project_id = ?;", (project_id,))
            cursor.execute("DELETE FROM maintenance_items WHERE project_id = ?;", (project_id,))
            cursor.execute("DELETE FROM plans WHERE project_id = ?;", (project_id,))
            cursor.execute("DELETE FROM cycle_catalog WHERE project_id = ?;", (project_id,))
            for label, table in entity_tables.items():
                cursor.execute(f"SELECT COUNT(*) FROM {table} WHERE project_id=?", (project_id,))
                if cursor.fetchone()[0] != 0:
                    raise RuntimeError(f"Falha ao limpar {label} antes da substituição.")
            
        # 2. Insert import record
        summary = preview_data['summary']
        cursor.execute("""
        INSERT INTO imports (project_id, filename, file_hash, status, summary_json)
        VALUES (?, ?, ?, ?, ?);
        """, (project_id, summary['filename'], summary['file_hash'], 'SUCCESS', json.dumps(summary)))
        import_id = cursor.lastrowid

        # Insert import errors/warnings
        for err in preview_data['errors']:
            cursor.execute("""
            INSERT INTO import_errors (import_id, sheet_name, row_number, field_name, severity, message, original_value)
            VALUES (?, ?, ?, ?, ?, ?, ?);
            """, (import_id, err['sheet_name'], err['row_number'], err['field_name'], err['severity'], err['message'], err['original_value']))

        # 3. Insert cycle catalog entries
        for cyc in preview_data['suggested_cycles']:
            cursor.execute("""
            INSERT OR IGNORE INTO cycle_catalog (project_id, cycle, unit, cycle_text, opening_horizon, active)
            VALUES (?, ?, ?, ?, ?, 1);
            """, (project_id, cyc['cycle'], cyc['unit'], cyc['cycle_text'], cyc['opening_horizon']))

        # 4. Insert Plans and map legacy_code -> DB id. During aggregation an
        # existing plan is reused, never replaced or duplicated.
        plan_id_map = {} # legacy_code -> DB plan_id
        cursor.execute("SELECT current_counter FROM projects WHERE id=?", (project_id,))
        project_row = cursor.fetchone()
        current_counter = int(project_row['current_counter'] or 0) if project_row else 0
        if merge_mode == 'merge':
            cursor.execute("SELECT id, legacy_code FROM plans WHERE project_id=? AND deleted_at IS NULL", (project_id,))
            plan_id_map.update({str(r['legacy_code']).upper().strip(): r['id'] for r in cursor.fetchall()})
        for p in preview_data['plans']:
            if not p['is_valid']:
                continue
            code = str(p['legacy_code']).upper().strip()
            # In aggregate mode the same plan may already belong to the
            # project. Reuse it instead of attempting a duplicate INSERT.
            if code in plan_id_map:
                continue
            start_stop = int(p['reference_counter']) if p.get('reference_counter') is not None else None
            if start_stop is None and p.get('extracted_start_stop') is not None:
                try: start_stop = int(p['extracted_start_stop'])
                except (ValueError, TypeError): pass
            if start_stop is None:
                ext_c, ext_s, _ = extract_cycle_and_start_from_text(p.get('description', '') or p.get('legacy_code', ''))
                start_stop = ext_s or 1
            internal_counter = current_counter + start_stop if start_stop is not None else None
            phase_val = start_stop if start_stop is not None else 1
            cursor.execute("""
            INSERT INTO plans (project_id, legacy_code, description, character_count, cycle, unit, cycle_text, opening_horizon, reference_counter, phase, status, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'ACTIVE', 'Importado via planilha');
            """, (project_id, p['legacy_code'], p['description'], p['character_count'], p['cycle'], p['unit'], p['cycle_text'], p['opening_horizon'], internal_counter, phase_val))
            plan_id_map[code] = cursor.lastrowid

        # 5. Insert Items and link to Plans. An aggregate import receives a
        # fresh contiguous identifier range. The old->new mapping below is the
        # single source of truth for items, operations and long texts.
        item_id_map = {}
        inserted_item_count = 0
        identifier_remap = {}
        identifier_remap_rows = []
        used_identifiers = set()
        next_identifier = 1
        if merge_mode == 'merge':
            cursor.execute("SELECT legacy_identifier FROM maintenance_items WHERE project_id=? AND deleted_at IS NULL", (project_id,))
            numeric_ids = []
            for row in cursor.fetchall():
                existing_identifier = normalize_identifier(row['legacy_identifier'])
                used_identifiers.add(existing_identifier)
                try: numeric_ids.append(int(existing_identifier))
                except (TypeError, ValueError): pass
            next_identifier = (max(numeric_ids) + 1) if numeric_ids else 1
        else:
            # When replacing, preserve valid source identifiers. If the source
            # itself repeats an ID, allocate the duplicate after its highest
            # numeric identifier so the whole file can still be imported.
            source_numeric_ids = []
            for source_item in preview_data['items']:
                try: source_numeric_ids.append(int(normalize_identifier(source_item.get('legacy_identifier'))))
                except (TypeError, ValueError): pass
            next_identifier = (max(source_numeric_ids) + 1) if source_numeric_ids else 1
        for item in preview_data['items']:
            if not item['is_valid']:
                continue
            source_identifier = normalize_identifier(item['legacy_identifier'])
            if merge_mode == 'merge' or source_identifier in used_identifiers:
                while str(next_identifier) in used_identifiers:
                    next_identifier += 1
                target_identifier = str(next_identifier)
                next_identifier += 1
            else:
                target_identifier = source_identifier
            used_identifiers.add(target_identifier)
            # A repeated source ID is ambiguous for child sheets. Operations
            # and texts stay attached to its first occurrence; every physical
            # item row still receives a unique target identifier.
            identifier_remap.setdefault(source_identifier, target_identifier)
            identifier_remap_rows.append({'source': source_identifier, 'target': target_identifier,
                                          'row_number': item.get('row_number')})
                
            # Find DB plan_id from mapped legacy code
            db_plan_id = plan_id_map.get(str(item['plano_reparo_code']).upper().strip())
            
            # Prefer the explicit PM13 discipline helper columns when present.
            # Otherwise preserve the generic corporate T(H) x effective behavior;
            # operations can still backfill discipline workload later in this transaction.
            specialty_pairs = [
                (item.get('ele_headcount'), item.get('ele_hours')),
                (item.get('mec_headcount'), item.get('mec_hours')),
                (item.get('sol_headcount'), item.get('sol_hours')),
            ]
            has_specialty_values = item.get('specialty_columns_present') and any(
                hc is not None or hrs is not None for hc, hrs in specialty_pairs)
            if has_specialty_values:
                specialty_hc = sum(int(hc or 0) for hc, _ in specialty_pairs)
                specialty_hh = sum(float(hc or 0) * float(hrs or 0) for hc, hrs in specialty_pairs)
                generic_headcount = specialty_hc
                hh_val = specialty_hh
            else:
                generic_headcount = item['headcount']
                hh_val = item['duration_hours'] * item['headcount']

            cursor.execute("""
            INSERT INTO maintenance_items (
                project_id, legacy_identifier, plan_id, object_type, object_code,
                gpm, work_center, condition_code, priority, legacy_start,
                description, character_count, duration_hours, headcount, hh,
                ele_headcount,ele_hours,mec_headcount,mec_hours,sol_headcount,sol_hours,
                order_type, status, notes, validation_status, validation_issues_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                      'PM13', ?, 'Importado via planilha', ?, ?);
            """, (
                project_id, target_identifier, db_plan_id, item['object_type'], item['object_code'],
                item['gpm'], item['work_center'], item['condition_code'], item['priority'], item['legacy_start'],
                item['description'], item['character_count'], item['duration_hours'], generic_headcount, hh_val,
                int(item.get('ele_headcount') or 0), float(item.get('ele_hours') or 0),
                int(item.get('mec_headcount') or 0), float(item.get('mec_hours') or 0),
                int(item.get('sol_headcount') or 0), float(item.get('sol_hours') or 0),
                item.get('status') or 'ACTIVE',
                item.get('validation_status', 'OK'), json.dumps(item.get('validation_issues', []), ensure_ascii=False)
            ))
            inserted_item_count += 1
            item_id_map.setdefault(source_identifier, cursor.lastrowid)

        # 6. Operations and long texts (optional for backwards compatibility)
        # Child rows may only reference source items that were accepted by the preview.
        # If an item exists in the source workbook but was rejected (for example due
        # to a missing duration), creating an automatic placeholder here is unsafe:
        # in merge mode its source identifier can already exist in the destination,
        # which previously surfaced as a misleading UNIQUE constraint error.
        source_item_identifiers = {normalize_identifier(row.get('legacy_identifier'))
                                   for row in preview_data.get('items', [])}
        invalid_source_item_identifiers = {normalize_identifier(row.get('legacy_identifier'))
                                           for row in preview_data.get('items', [])
                                           if not row.get('is_valid', True)}
        invalid_child_refs = sorted({normalize_identifier(row.get('legacy_identifier'))
                                     for row in (preview_data.get('operations', []) +
                                                 preview_data.get('long_texts', []))
                                     if normalize_identifier(row.get('legacy_identifier'))
                                     in invalid_source_item_identifiers})
        if invalid_child_refs:
            sample = ', '.join(invalid_child_refs[:20])
            extra = '' if len(invalid_child_refs) <= 20 else f' (+{len(invalid_child_refs)-20})'
            raise ValueError(
                'A importacao foi bloqueada porque existem operacoes/textos vinculados a '
                f'itens rejeitados na validacao: {sample}{extra}. Corrija os campos '
                'obrigatorios desses itens (por exemplo T(h)/duracao) e gere a previa novamente.'
            )

        operation_id_map = {}
        processed_operation_ids = set()
        for op in preview_data.get('operations', []):
            op_ident = normalize_identifier(op['legacy_identifier'])
            item_id = item_id_map.get(op_ident)
            if not item_id:
                orphan_issue = {
                    'code': 'operation_without_item', 'severity': 'ERROR',
                    'message': f'Operacao importada sem item correspondente ({op_ident}).'
                }
                # A truly orphan operation is preserved, but in aggregate/merge mode
                # its placeholder must also receive a fresh destination identifier.
                # This keeps the promise that "Adicionar e Unificar" never overwrites
                # or collides with an existing item identifier.
                placeholder_identifier = op_ident
                if merge_mode == 'merge' or placeholder_identifier in used_identifiers:
                    while str(next_identifier) in used_identifiers:
                        next_identifier += 1
                    placeholder_identifier = str(next_identifier)
                    next_identifier += 1
                used_identifiers.add(placeholder_identifier)
                identifier_remap.setdefault(op_ident, placeholder_identifier)
                cursor.execute("""INSERT INTO maintenance_items
                    (project_id,legacy_identifier,plan_id,object_type,object_code,gpm,work_center,
                     condition_code,priority,description,character_count,duration_hours,headcount,hh,
                     order_type,status,notes,validation_status,validation_issues_json)
                    VALUES (?,?,NULL,'EQUIPAMENTO','ITEM_PENDENTE','000','PENDENTE','Q',3,?,0,0,1,0,
                            'PM13','ACTIVE','Criado automaticamente para receber operacao sem item','ERROR',?)""",
                    (project_id, placeholder_identifier, f'Item pendente de correcao ({op_ident})',
                     json.dumps([orphan_issue], ensure_ascii=False)))
                item_id = cursor.lastrowid
                item_id_map[op_ident] = item_id
                inserted_item_count += 1
                cursor.execute("""INSERT INTO import_errors
                    (import_id,sheet_name,row_number,field_name,severity,message,original_value)
                    VALUES (?,'Operacoes',?,'legacy_identifier','ERROR',?,?)""",
                    (import_id, op.get('row_number'), orphan_issue['message'], op_ident))
                op = dict(op)
                op['validation_status'] = 'ERROR'
                op['validation_issues'] = list(op.get('validation_issues', [])) + [orphan_issue]
            op_code = str(op['operation_code'])
            sub_code = str(op.get('suboperation_code') or '')
            cursor.execute("""INSERT INTO item_operations
                (project_id,item_id,operation_code,suboperation_code,work_center,short_text,unit,headcount,hours,status,validation_status,validation_issues_json)
                VALUES (?,?,?,?,?,?,?,?,?,'ACTIVE',?,?)
                ON CONFLICT(item_id,operation_code,suboperation_code) DO UPDATE SET
                    project_id=excluded.project_id, work_center=excluded.work_center,
                    short_text=excluded.short_text, unit=excluded.unit,
                    headcount=excluded.headcount, hours=excluded.hours,
                    status='ACTIVE', validation_status=excluded.validation_status,
                    validation_issues_json=excluded.validation_issues_json""", (
                project_id,item_id,op_code,sub_code,
                op.get('work_center'),op['short_text'],op.get('unit') or 'H',op.get('headcount'),op.get('hours'),
                op.get('validation_status', 'OK'), json.dumps(op.get('validation_issues', []), ensure_ascii=False)
            ))
            cursor.execute("""SELECT id FROM item_operations
                              WHERE item_id=? AND operation_code=? AND suboperation_code=?""",
                           (item_id, op_code, sub_code))
            oid = cursor.fetchone()[0]
            processed_operation_ids.add(oid)
            operation_id_map[(op_ident, op_code, sub_code)] = oid
            operation_id_map.setdefault((op_ident, op_code), oid)
            operation_id_map.setdefault(op_ident, oid)

        line_by_operation = {}
        orphan_long_text_operation_ids = set()
        for tx in preview_data.get('long_texts', []):
            tx_ident = normalize_identifier(tx['legacy_identifier'])
            tx_op = str(tx.get('operation_code') or '').strip()
            tx_sub = str(tx.get('suboperation_code') or '').strip()
            operation_id = operation_id_map.get((tx_ident, tx_op, tx_sub))
            if not operation_id:
                operation_id, item_created = _ensure_operation_for_orphan_long_text(
                    cursor, project_id, import_id, item_id_map, operation_id_map, tx)
                processed_operation_ids.add(operation_id)
                orphan_long_text_operation_ids.add(operation_id)
                if item_created:
                    inserted_item_count += 1
                validation_status, validation_issues = _orphan_long_text_validation(tx)
            elif operation_id in orphan_long_text_operation_ids:
                validation_status, validation_issues = _orphan_long_text_validation(tx)
            else:
                validation_status = tx.get('validation_status', 'OK')
                validation_issues = tx.get('validation_issues', [])
            line_by_operation[operation_id] = line_by_operation.get(operation_id, 0) + 1
            cursor.execute("""INSERT INTO operation_long_texts
                (project_id,operation_id,group_code,group_counter,line_sequence,text,structure_mode,structure_json,source_text_original,
                 validation_status,validation_issues_json)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(operation_id,line_sequence) DO UPDATE SET
                    project_id=excluded.project_id, group_code=excluded.group_code,
                    group_counter=excluded.group_counter, text=excluded.text,
                    structure_mode=excluded.structure_mode,structure_json=excluded.structure_json,
                    source_text_original=excluded.source_text_original,
                    validation_status=excluded.validation_status,
                    validation_issues_json=excluded.validation_issues_json""", (
                project_id,operation_id,tx.get('group_code'),tx.get('group_counter'),line_by_operation[operation_id],tx['text'],
                tx.get('structure_mode','FREE'),tx.get('structure_json'),tx.get('source_text_original'),
                validation_status, json.dumps(validation_issues, ensure_ascii=False)
            ))

        # Rebuild the item-level discipline workload from the SAP operation
        # rows exported by this application.  This makes a full project round-trip
        # preserve ELE/MEC/SOL effective and hours instead of importing the item
        # with only the generic default headcount.
        workload_by_source = {}
        explicit_workload_by_source = {}
        source_item_by_identifier = {}
        for source_item in preview_data.get('items', []):
            source_ident = normalize_identifier(source_item.get('legacy_identifier'))
            source_item_by_identifier.setdefault(source_ident, source_item)
            if not source_item.get('specialty_columns_present'):
                continue
            explicit_workload_by_source[source_ident] = {
                'ele': (source_item.get('ele_headcount'), source_item.get('ele_hours')),
                'mec': (source_item.get('mec_headcount'), source_item.get('mec_hours')),
                'sol': (source_item.get('sol_headcount'), source_item.get('sol_hours')),
            }
        for op in preview_data.get('operations', []):
            source_ident = normalize_identifier(op.get('legacy_identifier'))
            code = str(op.get('operation_code') or '').strip().zfill(4)
            raw_sub = str(op.get('suboperation_code') or '').strip()
            sub = raw_sub.zfill(4) if raw_sub.isdigit() else raw_sub
            try:
                hc = int(float(op.get('headcount') or 0))
            except (TypeError, ValueError):
                hc = 0
            try:
                hours = float(op.get('hours') or 0)
            except (TypeError, ValueError):
                hours = 0.0
            trade = None
            if code == '0010' and sub == '0010':
                trade = 'sol'
            elif code == '0010' and not sub:
                wc = str(op.get('work_center') or '').upper().strip()
                if 'R55E' in wc or 'ELE' in wc or 'ELÉ' in wc:
                    trade = 'ele'
                elif 'R55M' in wc or 'MEC' in wc:
                    trade = 'mec'
            if trade:
                workload_by_source.setdefault(source_ident, {})[trade] = (hc, hours)

        all_workload_sources = set(workload_by_source) | set(explicit_workload_by_source)
        for source_ident in all_workload_sources:
            item_id = item_id_map.get(source_ident)
            if not item_id:
                continue
            trades = workload_by_source.get(source_ident, {})
            explicit = explicit_workload_by_source.get(source_ident, {})

            def resolved_trade(name):
                exp_hc, exp_hours = explicit.get(name, (None, None))
                op_hc, op_hours = trades.get(name, (0, 0.0))
                # A column that exists and explicitly contains zero must remain zero.
                return (int(exp_hc or 0), float(exp_hours or 0)) if (exp_hc is not None or exp_hours is not None) else (op_hc, op_hours)

            ele_hc, ele_hours = resolved_trade('ele')
            mec_hc, mec_hours = resolved_trade('mec')
            sol_hc, sol_hours = resolved_trade('sol')
            specialty_total_hc = ele_hc + mec_hc + sol_hc
            specialty_total_hh = (ele_hc * ele_hours) + (mec_hc * mec_hours) + (sol_hc * sol_hours)
            source_item = source_item_by_identifier.get(source_ident, {})
            update_generic = bool(source_item.get('specialty_columns_present'))
            cursor.execute("""UPDATE maintenance_items SET
                ele_headcount=?, ele_hours=?, mec_headcount=?, mec_hours=?, sol_headcount=?, sol_hours=?,
                headcount=CASE WHEN ? THEN ? ELSE headcount END,
                hh=CASE WHEN ? THEN ? ELSE hh END,
                updated_at=CURRENT_TIMESTAMP
                WHERE id=?""",
                (ele_hc, ele_hours, mec_hc, mec_hours, sol_hc, sol_hours,
                 int(update_generic), specialty_total_hc, int(update_generic), specialty_total_hh, item_id))

        # Hard guarantee for PM13 round-trip helper columns. If the workbook
        # explicitly supplied ELE/MEC/SOL values, never silently finish with zeroes.
        _verify_imported_specialty_helpers(cursor, project_id, preview_data.get('items', []), item_id_map)

        # 7. Audit Log
        counts_after = {}
        for label, table in entity_tables.items():
            cursor.execute(f"SELECT COUNT(*) FROM {table} WHERE project_id=?", (project_id,))
            counts_after[label] = cursor.fetchone()[0]
        imported_long_text_count = sum(line_by_operation.values())
        if imported_long_text_count != len(preview_data.get('long_texts', [])):
            raise RuntimeError("Nem todos os textos longos da previa foram gravados.")
        if merge_mode == 'replace':
            expected_counts = {
                'plans': len(plan_id_map),
                'items': inserted_item_count,
                'operations': len(processed_operation_ids),
                'long_texts': imported_long_text_count,
            }
            mismatches = {
                key: {'expected': expected, 'actual': counts_after[key]}
                for key, expected in expected_counts.items()
                if counts_after[key] != expected
            }
            if mismatches:
                raise RuntimeError(
                    'A substituição não gravou todas as entidades: ' + json.dumps(mismatches)
                )
        summary['identifier_remap'] = identifier_remap
        summary['identifier_remap_rows'] = identifier_remap_rows
        summary['operations_imported'] = len(processed_operation_ids)
        summary['long_texts_imported'] = imported_long_text_count
        summary['database_counts_before'] = counts_before
        summary['database_counts_after'] = counts_after
        if merge_mode == 'replace':
            summary['replacement_deleted_counts'] = counts_before
        cursor.execute("""SELECT severity,COUNT(*) AS qty FROM import_errors
            WHERE import_id=? GROUP BY severity""", (import_id,))
        issue_counts = {row['severity']: row['qty'] for row in cursor.fetchall()}
        summary['error_count'] = issue_counts.get('ERROR', 0)
        summary['warning_count'] = issue_counts.get('WARNING', 0)
        cursor.execute("UPDATE imports SET summary_json=? WHERE id=?", (json.dumps(summary), import_id))
        cursor.execute("""
        INSERT INTO audit_log (project_id, entity_type, entity_id, action, previous_data_json, new_data_json)
        VALUES (?, 'PROJECT', ?, 'IMPORT_CONFIRM', NULL, ?);
        """, (project_id, project_id, json.dumps({'filename': summary['filename'], 'merge_mode': merge_mode,
                                                    'identifier_remap': identifier_remap,
                                                    'counts_before': counts_before,
                                                    'counts_after': counts_after})))

        conn.commit()
        return import_id
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()


# Keep the complete-import behaviour above available for older callers while
# routing scoped imports through an FK-safe synchronizer.  Defining this after
# the legacy implementation intentionally replaces the public name.
_confirm_full_import_legacy = confirm_import


def _scoped_entity_counts(cursor, project_id):
    tables = {
        'plans': 'plans', 'items': 'maintenance_items',
        'operations': 'item_operations', 'long_texts': 'operation_long_texts',
    }
    result = {}
    for name, table in tables.items():
        cursor.execute(f"SELECT COUNT(*) FROM {table} WHERE project_id=?", (project_id,))
        result[name] = cursor.fetchone()[0]
    return result


def _lookup_item_map(cursor, project_id):
    cursor.execute("SELECT id, legacy_identifier FROM maintenance_items WHERE project_id=? AND deleted_at IS NULL",
                   (project_id,))
    return {normalize_identifier(row['legacy_identifier']): row['id'] for row in cursor.fetchall()}


def _lookup_operation_map(cursor, project_id):
    cursor.execute("""SELECT o.id, i.legacy_identifier, o.operation_code, o.suboperation_code
                      FROM item_operations o JOIN maintenance_items i ON i.id=o.item_id
                      WHERE o.project_id=? AND i.deleted_at IS NULL""", (project_id,))
    return {(normalize_identifier(row['legacy_identifier']), str(row['operation_code']).strip(),
             str(row['suboperation_code'] or '').strip()): row['id'] for row in cursor.fetchall()}


def _insert_import_error_once(cursor, import_id, sheet_name, row_number,
                              field_name, message, original_value):
    cursor.execute("""SELECT 1 FROM import_errors
        WHERE import_id=? AND field_name=? AND COALESCE(original_value,'')=? LIMIT 1""",
        (import_id, field_name, str(original_value or '')))
    if cursor.fetchone():
        return
    cursor.execute("""INSERT INTO import_errors
        (import_id,sheet_name,row_number,field_name,severity,message,original_value)
        VALUES (?,?,?,?, 'ERROR',?,?)""",
        (import_id, sheet_name, row_number, field_name, message, original_value))


def _ensure_operation_for_orphan_long_text(cursor, project_id, import_id,
                                           item_map, operation_map, text_row):
    """Create an ERROR placeholder chain so orphan procedure text is preserved."""
    identifier = normalize_identifier(text_row.get('legacy_identifier'))
    operation_code = str(text_row.get('operation_code') or '').strip()
    suboperation_code = str(text_row.get('suboperation_code') or '').strip()
    key = (identifier, operation_code, suboperation_code)
    existing = operation_map.get(key)
    if existing:
        return existing, False

    item_id = item_map.get(identifier)
    item_created = False
    if not item_id:
        item_issue = {
            'code': 'long_text_without_item', 'severity': 'ERROR',
            'message': f'Texto longo importado sem item correspondente ({identifier}).'
        }
        cursor.execute("""INSERT INTO maintenance_items
            (project_id,legacy_identifier,plan_id,object_type,object_code,gpm,work_center,
             condition_code,priority,description,character_count,duration_hours,headcount,hh,
             order_type,status,notes,validation_status,validation_issues_json)
            VALUES (?,?,NULL,'EQUIPAMENTO','ITEM_PENDENTE','000','PENDENTE','Q',3,?,0,0,1,0,
                    'PM13','ACTIVE','Criado para preservar texto longo sem item','ERROR',?)""",
            (project_id, identifier, f'Item pendente de correção ({identifier})',
             json.dumps([item_issue], ensure_ascii=False)))
        item_id = cursor.lastrowid
        item_map[identifier] = item_id
        item_created = True
        _insert_import_error_once(
            cursor, import_id, 'TEXTO LONGO', text_row.get('row_number'),
            'Vínculo do item', item_issue['message'], identifier)

    label = '/'.join((identifier, operation_code, suboperation_code or '-'))
    operation_issue = {
        'code': 'long_text_without_operation', 'severity': 'ERROR',
        'message': f'Texto longo importado sem operação correspondente ({label}).'
    }
    cursor.execute("""INSERT INTO item_operations
        (project_id,item_id,operation_code,suboperation_code,work_center,short_text,unit,
         headcount,hours,status,validation_status,validation_issues_json)
        VALUES (?,?,?,?,? ,?,'H',NULL,NULL,'ACTIVE','ERROR',?)
        ON CONFLICT(item_id,operation_code,suboperation_code) DO UPDATE SET
          validation_status='ERROR',validation_issues_json=excluded.validation_issues_json,
          updated_at=CURRENT_TIMESTAMP""",
        (project_id, item_id, operation_code, suboperation_code, 'PENDENTE',
         'OPERAÇÃO PENDENTE — TEXTO LONGO SEM CORRESPONDÊNCIA',
         json.dumps([operation_issue], ensure_ascii=False)))
    cursor.execute("""SELECT id FROM item_operations
        WHERE item_id=? AND operation_code=? AND suboperation_code=?""",
        (item_id, operation_code, suboperation_code))
    operation_id = cursor.fetchone()[0]
    operation_map[key] = operation_id
    _insert_import_error_once(
        cursor, import_id, 'TEXTO LONGO', text_row.get('row_number'),
        'Vínculo da operação', operation_issue['message'], label)
    return operation_id, item_created


def _orphan_long_text_validation(text_row):
    identifier = normalize_identifier(text_row.get('legacy_identifier'))
    operation_code = str(text_row.get('operation_code') or '').strip()
    suboperation_code = str(text_row.get('suboperation_code') or '').strip()
    label = '/'.join((identifier, operation_code, suboperation_code or '-'))
    issue = {
        'code': 'long_text_without_operation', 'severity': 'ERROR',
        'message': f'Texto longo preservado com operação provisória ({label}). Corrija o vínculo da operação.'
    }
    issues = list(text_row.get('validation_issues', []))
    if not any(row.get('code') == issue['code'] for row in issues):
        issues.append(issue)
    return 'ERROR', issues


def confirm_import(project_id, preview_data, merge_mode='replace', selected_entities=None):
    """Import selected entities atomically while preserving unselected data.

    A full import keeps the established implementation. Scoped replacement is
    a natural-key synchronization: existing parent IDs remain stable, so FKs
    belonging to unselected children are never broken.
    """
    preview_selection_raw = preview_data.get(
        'selected_entities', preview_data.get('summary', {}).get('selected_entities'))
    preview_selection = normalize_selected_entities(preview_selection_raw)
    selected = normalize_selected_entities(
        selected_entities if selected_entities is not None else preview_selection_raw)
    if selected_entities is not None and selected != preview_selection:
        raise ValueError("A selecao confirmada difere da selecao usada no diagnostico. Gere a previa novamente.")
    selected_set = set(selected)
    # A complete replacement can safely use the established delete-and-build
    # path because no unselected FK dependants need preserving. Its preview is
    # preflighted here so the legacy routine cannot silently skip a broken
    # relationship or use an inexact text fallback.
    if selected == list(IMPORT_ENTITY_ORDER):
        valid_item_ids = {normalize_identifier(row.get('legacy_identifier'))
                          for row in preview_data.get('items', []) if row.get('is_valid', True)}
        op_keys = set()
        unresolved_operations = []
        for row in preview_data.get('operations', []):
            ident = normalize_identifier(row.get('legacy_identifier'))
            key = (ident, str(row.get('operation_code') or '').strip(),
                   str(row.get('suboperation_code') or '').strip())
            op_keys.add(key)
            if ident not in valid_item_ids:
                unresolved_operations.append('/'.join((key[0], key[1], key[2] or '-')))
        return _confirm_full_import_legacy(project_id, preview_data, merge_mode)
    if merge_mode not in ('replace', 'merge'):
        raise ValueError("Modo de importacao invalido. Use 'replace' ou 'merge'.")

    # Matching natural keys are upserted to preserve stable IDs. In replace,
    # extra rows in the selected scope are removed only after FK preflight.
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("BEGIN IMMEDIATE")
        counts_before = _scoped_entity_counts(cursor, project_id)
        summary = dict(preview_data.get('summary') or {})
        summary['selected_entities'] = selected
        summary['merge_mode'] = merge_mode

        # Validate dependencies before changing any row.
        item_map = _lookup_item_map(cursor, project_id)
        cursor.execute("SELECT legacy_code FROM plans WHERE project_id=? AND deleted_at IS NULL", (project_id,))
        existing_plan_codes = {str(row['legacy_code']).upper().strip() for row in cursor.fetchall()}
        incoming_plan_codes = {str(row.get('legacy_code', '')).upper().strip()
                               for row in preview_data.get('plans', []) if row.get('is_valid', True)}
        if 'items' in selected_set:
            duplicate_ids = [normalize_identifier(row.get('legacy_identifier'))
                             for row in preview_data.get('items', []) if row.get('is_duplicate')]
            if duplicate_ids:
                raise ValueError("Itens com identificador duplicado nao podem ser importados parcialmente: " +
                                 ', '.join(sorted(set(duplicate_ids))[:20]))
            unresolved_plans = sorted({str(row.get('plano_reparo_code', '')).upper().strip()
                                       for row in preview_data.get('items', []) if row.get('is_valid', True)
                                       and str(row.get('plano_reparo_code', '')).strip()
                                       and str(row.get('plano_reparo_code', '')).upper().strip() not in existing_plan_codes
                                       and str(row.get('plano_reparo_code', '')).upper().strip() not in incoming_plan_codes})
            if unresolved_plans:
                raise ValueError("Itens sem plano existente ou selecionado: " + ', '.join(unresolved_plans[:20]))
        incoming_item_ids = {normalize_identifier(row.get('legacy_identifier'))
                             for row in preview_data.get('items', []) if row.get('is_valid', True)}
        cursor.execute("""INSERT INTO imports (project_id,filename,file_hash,status,summary_json)
                          VALUES (?,?,?,'SUCCESS',?)""",
                       (project_id, summary.get('filename', 'importacao_parcial.xlsx'),
                        summary.get('file_hash', ''), json.dumps(summary)))
        import_id = cursor.lastrowid
        for err in preview_data.get('errors', []):
            cursor.execute("""INSERT INTO import_errors
                              (import_id,sheet_name,row_number,field_name,severity,message,original_value)
                              VALUES (?,?,?,?,?,?,?)""",
                           (import_id, err.get('sheet_name', ''), err.get('row_number'),
                            err.get('field_name'), err.get('severity', 'WARNING'),
                            err.get('message', ''), err.get('original_value')))

        # Plans: upsert source keys; replace removes extras after dependency preflight.
        plan_map = {}
        cursor.execute("SELECT id,legacy_code FROM plans WHERE project_id=? AND deleted_at IS NULL", (project_id,))
        plan_map.update({str(row['legacy_code']).upper().strip(): row['id'] for row in cursor.fetchall()})
        if 'plans' in selected_set:
            cursor.execute("SELECT current_counter FROM projects WHERE id=?", (project_id,))
            project_row = cursor.fetchone()
            current_counter = int(project_row['current_counter'] or 0) if project_row else 0
            for row in preview_data.get('plans', []):
                if not row.get('is_valid', True):
                    continue
                code = str(row.get('legacy_code', '')).upper().strip()
                start = row.get('reference_counter') or row.get('extracted_start_stop') or 1
                values = (row.get('description', ''), row.get('character_count', 0), row.get('cycle') or 1,
                          row.get('unit') or 'PRD', row.get('cycle_text') or '', row.get('opening_horizon') or 12,
                          current_counter + int(start), int(start))

                # A deleted plan may legally share its code with an active one.
                # Update exactly one row: prefer the active plan; otherwise
                # reactivate the most recently deleted tombstone to preserve ID.
                cursor.execute("""SELECT id FROM plans
                                  WHERE project_id=? AND legacy_code=? AND deleted_at IS NULL
                                  ORDER BY id DESC LIMIT 1""", (project_id, code))
                target = cursor.fetchone()
                if not target:
                    cursor.execute("""SELECT id FROM plans
                                      WHERE project_id=? AND legacy_code=? AND deleted_at IS NOT NULL
                                      ORDER BY deleted_at DESC, id DESC LIMIT 1""", (project_id, code))
                    target = cursor.fetchone()

                if target:
                    target_id = target['id']
                    cursor.execute("""UPDATE plans SET legacy_code=?,description=?,character_count=?,cycle=?,unit=?,
                                      cycle_text=?,opening_horizon=?,reference_counter=?,phase=?,status='ACTIVE',
                                      deleted_at=NULL,updated_at=CURRENT_TIMESTAMP WHERE id=?""",
                                   (code, *values, target_id))
                    plan_map[code] = target_id
                else:
                    cursor.execute("""INSERT INTO plans
                                      (project_id,legacy_code,description,character_count,cycle,unit,cycle_text,
                                       opening_horizon,reference_counter,phase,status,notes)
                                      VALUES (?,?,?,?,?,?,?,?,?,?,'ACTIVE','Importado via planilha')""",
                                   (project_id, code, *values))
                    plan_map[code] = cursor.lastrowid
            if merge_mode == 'replace':
                source_codes = {str(row.get('legacy_code', '')).upper().strip()
                                for row in preview_data.get('plans', []) if row.get('is_valid', True)}
                if 'items' not in selected_set:
                    where_extra = (" AND p.legacy_code NOT IN (" + ','.join('?' for _ in source_codes) + ")"
                                   if source_codes else '')
                    cursor.execute("""SELECT COUNT(*) FROM maintenance_items i JOIN plans p ON p.id=i.plan_id
                                      WHERE p.project_id=?""" + where_extra,
                                   (project_id, *source_codes) if source_codes else (project_id,))
                    dependent_items = cursor.fetchone()[0]
                    if dependent_items:
                        raise ValueError(
                            "Nao e seguro substituir planos sem selecionar Itens: "
                            f"{dependent_items} item(ns) dependem dos planos removidos.")
                if source_codes:
                    placeholders = ','.join('?' for _ in source_codes)
                    cursor.execute(f"DELETE FROM plans WHERE project_id=? AND legacy_code NOT IN ({placeholders})",
                                   (project_id, *source_codes))
                else:
                    cursor.execute("DELETE FROM plans WHERE project_id=?", (project_id,))

        # Items: natural-key upsert preserves operation IDs and their texts.
        if 'items' in selected_set:
            if merge_mode == 'replace':
                cursor.execute("""UPDATE manual_balance_sessions
                    SET status='DISCARDED',updated_at=CURRENT_TIMESTAMP
                    WHERE project_id=? AND status='DRAFT'""", (project_id,))
            for row in preview_data.get('items', []):
                if not row.get('is_valid', True):
                    continue
                ident = normalize_identifier(row.get('legacy_identifier'))
                plan_id = plan_map.get(str(row.get('plano_reparo_code', '')).upper().strip())
                specialty_pairs = [
                    (row.get('ele_headcount'), row.get('ele_hours')),
                    (row.get('mec_headcount'), row.get('mec_hours')),
                    (row.get('sol_headcount'), row.get('sol_hours')),
                ]
                has_specialty_values = row.get('specialty_columns_present') and any(
                    hc is not None or hrs is not None for hc, hrs in specialty_pairs)
                generic_headcount = (sum(int(hc or 0) for hc, _ in specialty_pairs)
                                     if has_specialty_values else row.get('headcount'))
                generic_hh = (sum(float(hc or 0) * float(hrs or 0) for hc, hrs in specialty_pairs)
                              if has_specialty_values else
                              row.get('duration_hours', 0) * (row.get('headcount') if row.get('headcount') is not None else 1))
                values = (plan_id, row.get('object_type') or 'EQUIPAMENTO', row.get('object_code') or 'SEM_EQUIPAMENTO',
                          row.get('gpm') or '000', row.get('work_center') or 'GERAL', row.get('condition_code') or 'Q',
                          row.get('priority', 3), row.get('legacy_start'), row.get('description') or '',
                          row.get('character_count', 0), row.get('duration_hours', 0), generic_headcount, generic_hh,
                          row.get('validation_status', 'OK'), json.dumps(row.get('validation_issues', []), ensure_ascii=False))
                helper_present = bool(row.get('specialty_columns_present'))
                clear_specialties = (not helper_present and row.get('headcount') == 0)
                touch_specialties = helper_present or clear_specialties
                cursor.execute("""UPDATE maintenance_items SET plan_id=?,object_type=?,object_code=?,gpm=?,work_center=?,
                                  condition_code=?,priority=?,legacy_start=?,description=?,character_count=?,duration_hours=?,
                                  headcount=?,hh=?,validation_status=?,validation_issues_json=?,status=?,deleted_at=NULL,
                                  ele_headcount=CASE WHEN ? THEN ? ELSE ele_headcount END,
                                  ele_hours=CASE WHEN ? THEN ? ELSE ele_hours END,
                                  mec_headcount=CASE WHEN ? THEN ? ELSE mec_headcount END,
                                  mec_hours=CASE WHEN ? THEN ? ELSE mec_hours END,
                                  sol_headcount=CASE WHEN ? THEN ? ELSE sol_headcount END,
                                  sol_hours=CASE WHEN ? THEN ? ELSE sol_hours END,
                                  updated_at=CURRENT_TIMESTAMP WHERE project_id=? AND legacy_identifier=?""",
                               (*values, row.get('status') or 'ACTIVE',
                                int(touch_specialties), int(row.get('ele_headcount') or 0),
                                int(touch_specialties), float(row.get('ele_hours') or 0),
                                int(touch_specialties), int(row.get('mec_headcount') or 0),
                                int(touch_specialties), float(row.get('mec_hours') or 0),
                                int(touch_specialties), int(row.get('sol_headcount') or 0),
                                int(touch_specialties), float(row.get('sol_hours') or 0),
                                project_id, ident))
                if not cursor.rowcount:
                    cursor.execute("""INSERT INTO maintenance_items
                                      (project_id,legacy_identifier,plan_id,object_type,object_code,gpm,work_center,
                                       condition_code,priority,legacy_start,description,character_count,duration_hours,
                                       headcount,hh,ele_headcount,ele_hours,mec_headcount,mec_hours,sol_headcount,sol_hours,
                                       order_type,status,notes,validation_status,validation_issues_json)
                                      VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'PM13',?,'Importado via planilha',?,?)""",
                                   (project_id, ident, *values[:13],
                                    int(row.get('ele_headcount') or 0), float(row.get('ele_hours') or 0),
                                    int(row.get('mec_headcount') or 0), float(row.get('mec_hours') or 0),
                                    int(row.get('sol_headcount') or 0), float(row.get('sol_hours') or 0),
                                    row.get('status') or 'ACTIVE', values[13], values[14]))
            if merge_mode == 'replace':
                source_ids = {normalize_identifier(row.get('legacy_identifier'))
                              for row in preview_data.get('items', []) if row.get('is_valid', True)}
                if 'operations' not in selected_set:
                    where_extra = (" AND i.legacy_identifier NOT IN (" + ','.join('?' for _ in source_ids) + ")"
                                   if source_ids else '')
                    cursor.execute("""SELECT COUNT(*) FROM item_operations o
                                      JOIN maintenance_items i ON i.id=o.item_id
                                      WHERE i.project_id=?""" + where_extra,
                                   (project_id, *source_ids) if source_ids else (project_id,))
                    dependent_operations = cursor.fetchone()[0]
                    if dependent_operations:
                        raise ValueError(
                            "Nao e seguro substituir itens sem selecionar Operacoes: "
                            f"{dependent_operations} operacao(oes) dependem dos itens removidos.")
                if source_ids:
                    placeholders = ','.join('?' for _ in source_ids)
                    cursor.execute(f"DELETE FROM maintenance_items WHERE project_id=? AND legacy_identifier NOT IN ({placeholders})",
                                   (project_id, *source_ids))
                else:
                    cursor.execute("DELETE FROM maintenance_items WHERE project_id=?", (project_id,))
            item_map = _lookup_item_map(cursor, project_id)
            _verify_imported_specialty_helpers(cursor, project_id, preview_data.get('items', []))

        # Operations: upsert matching keys; replace removes extras only when
        # no unselected long text would be lost.
        if 'operations' in selected_set:
            incoming_operation_keys = set()
            for row in preview_data.get('operations', []):
                ident = normalize_identifier(row.get('legacy_identifier'))
                item_id = item_map.get(ident)
                if not item_id:
                    orphan_issue = {
                        'code': 'operation_without_item', 'severity': 'ERROR',
                        'message': f'Operacao importada sem item correspondente ({ident}).'
                    }
                    cursor.execute("""INSERT INTO maintenance_items
                        (project_id,legacy_identifier,plan_id,object_type,object_code,gpm,work_center,
                         condition_code,priority,description,character_count,duration_hours,headcount,hh,
                         order_type,status,notes,validation_status,validation_issues_json)
                        VALUES (?,?,NULL,'EQUIPAMENTO','ITEM_PENDENTE','000','PENDENTE','Q',3,?,0,0,1,0,
                                'PM13','ACTIVE','Criado automaticamente para receber operacao sem item','ERROR',?)""",
                        (project_id, ident, f'Item pendente de correcao ({ident})',
                         json.dumps([orphan_issue], ensure_ascii=False)))
                    item_id = cursor.lastrowid
                    item_map[ident] = item_id
                    cursor.execute("""INSERT INTO import_errors
                        (import_id,sheet_name,row_number,field_name,severity,message,original_value)
                        VALUES (?,'Operacoes',?,'legacy_identifier','ERROR',?,?)""",
                        (import_id, row.get('row_number'), orphan_issue['message'], ident))
                    row = dict(row)
                    row['validation_status'] = 'ERROR'
                    row['validation_issues'] = list(row.get('validation_issues', [])) + [orphan_issue]
                op = str(row.get('operation_code') or '').strip()
                sub = str(row.get('suboperation_code') or '').strip()
                incoming_operation_keys.add((item_id, op, sub))
                cursor.execute("""INSERT INTO item_operations
                                  (project_id,item_id,operation_code,suboperation_code,work_center,short_text,unit,
                                   headcount,hours,status,validation_status,validation_issues_json)
                                  VALUES (?,?,?,?,?,?,?,?,?,'ACTIVE',?,?)
                                  ON CONFLICT(item_id,operation_code,suboperation_code) DO UPDATE SET
                                  work_center=excluded.work_center,short_text=excluded.short_text,unit=excluded.unit,
                                  headcount=excluded.headcount,hours=excluded.hours,status='ACTIVE',
                                  validation_status=excluded.validation_status,
                                  validation_issues_json=excluded.validation_issues_json""",
                               (project_id, item_id, op, sub, row.get('work_center'), row.get('short_text') or '',
                                row.get('unit') or 'H', row.get('headcount'), row.get('hours'),
                                row.get('validation_status', 'OK'),
                                json.dumps(row.get('validation_issues', []), ensure_ascii=False)))
            if merge_mode == 'replace':
                cursor.execute("""SELECT o.id,o.item_id,o.operation_code,o.suboperation_code,
                                  EXISTS(SELECT 1 FROM operation_long_texts t WHERE t.operation_id=o.id) AS has_text
                                  FROM item_operations o WHERE o.project_id=?""", (project_id,))
                stale = [row for row in cursor.fetchall()
                         if (row['item_id'], str(row['operation_code']), str(row['suboperation_code'] or ''))
                         not in incoming_operation_keys]
                protected = [row['id'] for row in stale if row['has_text'] and 'long_texts' not in selected_set]
                if protected:
                    raise ValueError(
                        "Nao e seguro substituir operacoes sem selecionar Textos longos: "
                        f"{len(protected)} operacao(oes) removida(s) possuem textos. Selecione tambem Textos longos.")
                if stale:
                    placeholders = ','.join('?' for _ in stale)
                    cursor.execute(f"DELETE FROM item_operations WHERE id IN ({placeholders})",
                                   tuple(row['id'] for row in stale))

        operation_map = _lookup_operation_map(cursor, project_id)
        placeholder_operation_ids = set()
        placeholder_item_identifiers = set()
        if 'long_texts' in selected_set:
            grouped = {}
            cursor.execute("""SELECT id,validation_issues_json FROM item_operations
                WHERE project_id=? AND validation_status='ERROR'""", (project_id,))
            for existing_operation in cursor.fetchall():
                if 'long_text_without_operation' in str(existing_operation['validation_issues_json'] or ''):
                    placeholder_operation_ids.add(existing_operation['id'])
            for row in preview_data.get('long_texts', []):
                key = (normalize_identifier(row.get('legacy_identifier')),
                       str(row.get('operation_code') or '').strip(),
                       str(row.get('suboperation_code') or '').strip())
                operation_id = operation_map.get(key)
                if not operation_id:
                    operation_id, item_created = _ensure_operation_for_orphan_long_text(
                        cursor, project_id, import_id, item_map, operation_map, row)
                    placeholder_operation_ids.add(operation_id)
                    if item_created:
                        placeholder_item_identifiers.add(key[0])
                if operation_id in placeholder_operation_ids:
                    row = dict(row)
                    row['validation_status'], row['validation_issues'] = _orphan_long_text_validation(row)
                grouped.setdefault(operation_id, []).append(row)
            # A selected Textos Longos tab is one complete replacement scope,
            # including an intentionally empty source.
            if merge_mode == 'replace':
                cursor.execute("DELETE FROM operation_long_texts WHERE project_id=?", (project_id,))
            for operation_id, rows in grouped.items():
                for sequence, row in enumerate(rows, 1):
                    cursor.execute("""INSERT INTO operation_long_texts
                                      (project_id,operation_id,group_code,group_counter,line_sequence,text,
                                       structure_mode,structure_json,source_text_original,
                                       validation_status,validation_issues_json) VALUES (?,?,?,?,?,?,?,?,?,?,?)
                                      ON CONFLICT(operation_id,line_sequence) DO UPDATE SET text=excluded.text,
                                      group_code=excluded.group_code,group_counter=excluded.group_counter,
                                      structure_mode=excluded.structure_mode,structure_json=excluded.structure_json,
                                      source_text_original=excluded.source_text_original,
                                      validation_status=excluded.validation_status,
                                      validation_issues_json=excluded.validation_issues_json""",
                                   (project_id, operation_id, row.get('group_code'), row.get('group_counter'), sequence,
                                    row.get('text') or '', row.get('structure_mode','FREE'), row.get('structure_json'),
                                    row.get('source_text_original'), row.get('validation_status', 'OK'),
                                    json.dumps(row.get('validation_issues', []), ensure_ascii=False)))

        counts_after = _scoped_entity_counts(cursor, project_id)
        if merge_mode == 'replace' and 'long_texts' in selected_set:
            expected_texts = len(preview_data.get('long_texts', []))
            if counts_after['long_texts'] != expected_texts:
                raise RuntimeError(
                    f"Substituicao de textos incompleta: esperado {expected_texts}, gravado {counts_after['long_texts']}.")
        if merge_mode == 'replace' and 'operations' in selected_set:
            expected_operations = len({
                (normalize_identifier(row.get('legacy_identifier')), str(row.get('operation_code') or '').strip(),
                 str(row.get('suboperation_code') or '').strip())
                for row in preview_data.get('operations', [])
            }) + len(placeholder_operation_ids)
            if counts_after['operations'] != expected_operations:
                raise RuntimeError(
                    f"Substituicao de operacoes incompleta: esperado {expected_operations}, gravado {counts_after['operations']}.")
        if merge_mode == 'replace' and 'items' in selected_set:
            expected_items = len({normalize_identifier(row.get('legacy_identifier'))
                                  for row in preview_data.get('items', []) if row.get('is_valid', True)})
            if 'operations' in selected_set:
                expected_items += len({normalize_identifier(row.get('legacy_identifier'))
                                       for row in preview_data.get('operations', [])
                                       if normalize_identifier(row.get('legacy_identifier')) not in incoming_item_ids})
            expected_items += len({identifier for identifier in placeholder_item_identifiers
                                   if identifier not in incoming_item_ids})
            if counts_after['items'] != expected_items:
                raise RuntimeError(
                    f"Substituicao de itens incompleta: esperado {expected_items}, gravado {counts_after['items']}.")
        if merge_mode == 'replace' and 'plans' in selected_set:
            expected_plans = len({str(row.get('legacy_code', '')).upper().strip()
                                  for row in preview_data.get('plans', []) if row.get('is_valid', True)})
            if counts_after['plans'] != expected_plans:
                raise RuntimeError(
                    f"Substituicao de planos incompleta: esperado {expected_plans}, gravado {counts_after['plans']}.")
        summary.update({'database_counts_before': counts_before, 'database_counts_after': counts_after,
                        'preserved_entities': [name for name in IMPORT_ENTITY_ORDER if name not in selected_set]})
        cursor.execute("""SELECT severity,COUNT(*) AS qty FROM import_errors
            WHERE import_id=? GROUP BY severity""", (import_id,))
        issue_counts = {row['severity']: row['qty'] for row in cursor.fetchall()}
        summary['error_count'] = issue_counts.get('ERROR', 0)
        summary['warning_count'] = issue_counts.get('WARNING', 0)
        cursor.execute("UPDATE imports SET summary_json=? WHERE id=?", (json.dumps(summary), import_id))
        cursor.execute("""INSERT INTO audit_log
                          (project_id,entity_type,entity_id,action,previous_data_json,new_data_json)
                          VALUES (?,'PROJECT',?,'IMPORT_CONFIRM',NULL,?)""",
                       (project_id, project_id, json.dumps({'filename': summary.get('filename'),
                        'merge_mode': merge_mode, 'selected_entities': selected,
                        'counts_before': counts_before, 'counts_after': counts_after})))
        conn.commit()
        return import_id
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
