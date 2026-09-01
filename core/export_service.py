import io
import datetime
import zipfile
from xml.sax.saxutils import escape
from core.long_text_structure import materialize_record

def format_excel_csv_value(val):
    """Formats a value for Portuguese Excel CSV.
    - Semicolon is the separator.
    - Decimals use comma.
    - Long numeric values or strings with leading zeros are wrapped in =\"value\" to preserve leading zeros and prevent scientific notation.
    """
    if val is None:
        return ""
        
    val_str = str(val).strip()
    
    # Check if we should force text representation in Excel
    # e.g., if GPM like '041', or long codes like '10380837'
    is_numeric_string_with_leading_zero = val_str.isdigit() and len(val_str) > 1 and val_str.startswith('0')
    is_long_number = val_str.isdigit() and len(val_str) >= 8
    
    # Escape quotes
    escaped = val_str.replace('"', '""')
    
    # Handle decimals
    if isinstance(val, float):
        return f"{val_str.replace('.', ',')}"
        
    # If it is numeric string and matches our special text forcing condition
    if is_numeric_string_with_leading_zero or is_long_number:
        return f'="{escaped}"'
        
    # Wrap in quotes if it contains separator or linebreaks
    if ';' in escaped or '\n' in escaped or '\r' in escaped or '"' in escaped:
        return f'"{escaped}"'
        
    return escaped

def export_plans_csv(plans_list):
    """Exports plans to CSV bytes (UTF-8 with BOM, semicolon delimiter)."""
    output = io.StringIO()
    # UTF-8 BOM
    output.write("\ufeff")
    
    headers = [
        "Código Plano", "Descrição do Plano", "Quantidade Caracteres", 
        "Ciclo", "Unidade", "Texto do Ciclo", "Horizonte de Abertura", 
        "Contador de Referência", "Status", "Observações"
    ]
    output.write(";".join(headers) + "\n")
    
    for plan in plans_list:
        row = [
            plan.get('legacy_code', ''),
            plan.get('description', ''),
            plan.get('character_count', 0),
            plan.get('cycle', ''),
            plan.get('unit', ''),
            plan.get('cycle_text', ''),
            plan.get('opening_horizon', ''),
            plan.get('reference_counter', '') if plan.get('reference_counter') is not None else '',
            plan.get('status', 'ACTIVE'),
            plan.get('notes', '')
        ]
        formatted_row = [format_excel_csv_value(v) for v in row]
        output.write(";".join(formatted_row) + "\n")
        
    return output.getvalue().encode('utf-8-sig')

def export_items_csv(items_list):
    """Exports items to CSV bytes (UTF-8 with BOM, semicolon delimiter)."""
    output = io.StringIO()
    output.write("\ufeff")
    
    headers = [
        "Identificador Legado", "Equipamento/Local", "Tipo de Objeto", 
        "GPM", "Centro de Trabalho", "Condição", "Prioridade", 
        "Código do Plano Vinculado", "Descrição do Plano", 
        "Descrição do Item", "Quantidade Caracteres", 
        "Duração t(H)", "Efetivo", "HH Calculado", 
        "Início Legado", "Tipo de Ordem", "Status", "Observações"
    ]
    output.write(";".join(headers) + "\n")
    
    for item in items_list:
        row = [
            item.get('legacy_identifier', ''),
            item.get('object_code', ''),
            item.get('object_type', ''),
            item.get('gpm', ''),
            item.get('work_center', ''),
            item.get('condition_code', ''),
            item.get('priority', ''),
            item.get('plan_code', '') or item.get('plano_reparo_code', ''),
            item.get('plan_description', '') or item.get('descricao_plano', ''),
            item.get('description', ''),
            item.get('character_count', 0),
            item.get('duration_hours', 0.0),
            item.get('headcount', '') if item.get('headcount') is not None else '',
            item.get('hh', 0.0),
            item.get('legacy_start', '') if item.get('legacy_start') is not None else '',
            item.get('order_type', 'PM13'),
            item.get('status', 'ACTIVE'),
            item.get('notes', '')
        ]
        formatted_row = [format_excel_csv_value(v) for v in row]
        output.write(";".join(formatted_row) + "\n")
        
    return output.getvalue().encode('utf-8-sig')

def export_orders_csv(orders_list, stop_counter):
    """Exports projected orders for a specific stop counter to CSV."""
    output = io.StringIO()
    output.write("\ufeff")
    
    headers = [
        "Parada", "Contador", "Identificador Legado", "Equipamento/Local", 
        "Tipo de Objeto", "Descrição do Item", "Código Plano", 
        "GPM", "Centro de Trabalho", "Condição", "Prioridade", 
        "Duração t(H)", "Efetivo", "HH"
    ]
    output.write(";".join(headers) + "\n")
    
    for o in orders_list:
        row = [
            f"Parada {o.get('stop_num', '')}",
            stop_counter,
            o.get('legacy_identifier', ''),
            o.get('object_code', ''),
            o.get('object_type', ''),
            o.get('description', ''),
            o.get('plan_code', ''),
            o.get('gpm', ''),
            o.get('work_center', ''),
            o.get('condition_code', ''),
            o.get('priority', ''),
            o.get('duration_hours', 0.0),
            o.get('headcount', 1),
            o.get('hh', 0.0)
        ]
        formatted_row = [format_excel_csv_value(v) for v in row]
        output.write(";".join(formatted_row) + "\n")
        
    return output.getvalue().encode('utf-8-sig')


def _xlsx_col_name(index):
    name = ''
    while index:
        index, remainder = divmod(index - 1, 26)
        name = chr(65 + remainder) + name
    return name


def _xlsx_clean_text(value):
    text = '' if value is None else str(value)
    # XML 1.0 forbids most control characters.
    return ''.join(ch for ch in text if ord(ch) in (9, 10, 13) or ord(ch) >= 32)


def _xlsx_cell(ref, value, style=0, numeric=False):
    if numeric and value not in (None, ''):
        try:
            return f'<c r="{ref}" s="{style}"><v>{float(value)}</v></c>'
        except (TypeError, ValueError):
            pass
    safe = escape(_xlsx_clean_text(value))
    preserve = ' xml:space="preserve"' if safe != safe.strip() else ''
    return f'<c r="{ref}" s="{style}" t="inlineStr"><is><t{preserve}>{safe}</t></is></c>'


def export_orders_xlsx(orders_list, stop_counter, project=None, stop_info=None):
    """Builds a styled, genuine XLSX workbook using only Python stdlib."""
    project = project or {}
    stop_info = stop_info or {}
    headers = [
        'Parada', 'Contador', 'Item / ID', 'Equipamento / Local', 'Tipo de Objeto',
        'Descrição do Item', 'Plano Atrelado', 'Descrição do Plano', 'Ciclo', 'GPM',
        'Centro de Trabalho', 'Condição', 'Prioridade', 'Duração (h)', 'Efetivo', 'Carga HH'
    ]
    widths = [11, 12, 18, 20, 17, 42, 20, 42, 11, 14, 20, 13, 12, 14, 12, 14]
    last_col = _xlsx_col_name(len(headers))

    rows_xml = []
    rows_xml.append(
        f'<row r="1" ht="30" customHeight="1">{_xlsx_cell("A1", "LISTA DE ORDENS DE MANUTENÇÃO PROGRAMADA", 1)}</row>')
    project_name = project.get('name') or 'Projeto PM13'
    stop_num = stop_info.get('stop_num', '')
    subtitle = f'{project_name}  •  Parada {stop_num or "-"}  •  Contador {stop_counter}'
    rows_xml.append(f'<row r="2" ht="22" customHeight="1">{_xlsx_cell("A2", subtitle, 2)}</row>')

    total_hh = sum((float(o.get('duration_hours') or 0) *
                    int(o.get('headcount') if o.get('headcount') is not None else 1))
                   for o in orders_list)
    summary = [
        ('A3', 'TOTAL DE ORDENS', 3), ('B3', len(orders_list), 4),
        ('D3', 'HH TOTAL', 3), ('E3', round(total_hh, 1), 9),
        ('G3', 'GERADO EM', 3), ('H3', datetime.datetime.now().strftime('%d/%m/%Y %H:%M'), 4)
    ]
    rows_xml.append('<row r="3" ht="22" customHeight="1">' + ''.join(
        _xlsx_cell(ref, val, style, numeric=style in (4, 9) and isinstance(val, (int, float)))
        for ref, val, style in summary) + '</row>')

    header_cells = ''.join(_xlsx_cell(f'{_xlsx_col_name(i)}5', value, 5) for i, value in enumerate(headers, 1))
    rows_xml.append(f'<row r="5" ht="28" customHeight="1">{header_cells}</row>')

    for row_index, order in enumerate(orders_list, 6):
        headcount = int(order.get('headcount') if order.get('headcount') is not None else 1)
        duration = float(order.get('duration_hours') or 0)
        hh = duration * headcount
        values = [
            f"Parada {order.get('stop_num', stop_num)}", stop_counter,
            order.get('legacy_identifier', ''), order.get('object_code', ''),
            order.get('object_type', ''), order.get('description', ''),
            order.get('plan_code', ''), order.get('plan_description', ''),
            f"{order.get('cycle', '')} {order.get('unit', '')}".strip(),
            order.get('gpm', ''), order.get('work_center', ''),
            order.get('condition_code', ''), order.get('priority', ''),
            duration, headcount, hh
        ]
        base_style = 8 if row_index % 2 == 0 else 6
        cells = []
        for col_index, value in enumerate(values, 1):
            style = base_style
            numeric = False
            if col_index in (14, 15):
                style, numeric = 7, True
            elif col_index == 16:
                style, numeric = 9, True
            cells.append(_xlsx_cell(f'{_xlsx_col_name(col_index)}{row_index}', value, style, numeric))
        rows_xml.append(f'<row r="{row_index}" ht="30" customHeight="1">{"".join(cells)}</row>')

    last_row = max(5, len(orders_list) + 5)
    cols_xml = ''.join(
        f'<col min="{i}" max="{i}" width="{width}" customWidth="1"/>'
        for i, width in enumerate(widths, 1))
    sheet_xml = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <sheetViews><sheetView showGridLines="0" workbookViewId="0"><pane ySplit="5" topLeftCell="A6" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews>
  <sheetFormatPr defaultRowHeight="18"/>
  <cols>{cols_xml}</cols>
  <sheetData>{''.join(rows_xml)}</sheetData>
  <mergeCells count="2"><mergeCell ref="A1:{last_col}1"/><mergeCell ref="A2:{last_col}2"/></mergeCells>
  <autoFilter ref="A5:{last_col}{last_row}"/>
  <pageMargins left="0.25" right="0.25" top="0.5" bottom="0.5" header="0.2" footer="0.2"/>
  <pageSetup orientation="landscape" fitToWidth="1" fitToHeight="0"/>
</worksheet>'''

    styles_xml = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <numFmts count="2"><numFmt numFmtId="164" formatCode="0.0"/><numFmt numFmtId="165" formatCode="0.0 &quot;HH&quot;"/></numFmts>
  <fonts count="4">
    <font><sz val="10"/><name val="Calibri"/><color rgb="FF334155"/></font>
    <font><b/><sz val="18"/><name val="Calibri"/><color rgb="FFFFFFFF"/></font>
    <font><b/><sz val="10"/><name val="Calibri"/><color rgb="FFFFFFFF"/></font>
    <font><b/><sz val="10"/><name val="Calibri"/><color rgb="FF365E00"/></font>
  </fonts>
  <fills count="6">
    <fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill>
    <fill><patternFill patternType="solid"><fgColor rgb="FF365E00"/><bgColor indexed="64"/></patternFill></fill>
    <fill><patternFill patternType="solid"><fgColor rgb="FF5F8500"/><bgColor indexed="64"/></patternFill></fill>
    <fill><patternFill patternType="solid"><fgColor rgb="FFEAF4D8"/><bgColor indexed="64"/></patternFill></fill>
    <fill><patternFill patternType="solid"><fgColor rgb="FFF6FAEF"/><bgColor indexed="64"/></patternFill></fill>
  </fills>
  <borders count="2"><border/><border><left style="thin"><color rgb="FFDCE6D5"/></left><right style="thin"><color rgb="FFDCE6D5"/></right><top style="thin"><color rgb="FFDCE6D5"/></top><bottom style="thin"><color rgb="FFDCE6D5"/></bottom></border></borders>
  <cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
  <cellXfs count="10">
    <xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>
    <xf numFmtId="0" fontId="1" fillId="2" borderId="0" xfId="0"><alignment vertical="center"/></xf>
    <xf numFmtId="0" fontId="3" fillId="4" borderId="0" xfId="0"><alignment vertical="center"/></xf>
    <xf numFmtId="0" fontId="3" fillId="4" borderId="1" xfId="0"><alignment vertical="center"/></xf>
    <xf numFmtId="0" fontId="3" fillId="0" borderId="1" xfId="0"><alignment horizontal="center" vertical="center"/></xf>
    <xf numFmtId="0" fontId="2" fillId="3" borderId="1" xfId="0"><alignment horizontal="center" vertical="center" wrapText="1"/></xf>
    <xf numFmtId="0" fontId="0" fillId="0" borderId="1" xfId="0"><alignment vertical="center" wrapText="1"/></xf>
    <xf numFmtId="164" fontId="0" fillId="0" borderId="1" xfId="0"><alignment horizontal="right" vertical="center"/></xf>
    <xf numFmtId="0" fontId="0" fillId="5" borderId="1" xfId="0"><alignment vertical="center" wrapText="1"/></xf>
    <xf numFmtId="165" fontId="3" fillId="5" borderId="1" xfId="0"><alignment horizontal="right" vertical="center"/></xf>
  </cellXfs>
  <cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>
</styleSheet>'''

    content_types = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/><Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/></Types>'''
    root_rels = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>'''
    workbook = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Ordens da Parada" sheetId="1" r:id="rId1"/></sheets></workbook>'''
    workbook_rels = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>'''

    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as book:
        book.writestr('[Content_Types].xml', content_types)
        book.writestr('_rels/.rels', root_rels)
        book.writestr('xl/workbook.xml', workbook)
        book.writestr('xl/_rels/workbook.xml.rels', workbook_rels)
        book.writestr('xl/styles.xml', styles_xml)
        book.writestr('xl/worksheets/sheet1.xml', sheet_xml)
    return output.getvalue()

def export_balance_csv(balance_data):
    """Exports stop balancing matrix (Stops summaries) to CSV."""
    output = io.StringIO()
    output.write("\ufeff")
    
    headers = [
        "Parada", "Contador Real", "Quantidade Ordens", 
        "Duração Total (H)", "HH Total", "Efetivo Médio Necessário"
    ]
    output.write(";".join(headers) + "\n")
    
    for s in balance_data['stops']:
        row = [
            f"Parada {s['stop_num']}",
            s['counter'],
            s['total_orders'],
            s['total_duration'],
            s['total_hh'],
            s['headcount_needed']
        ]
        formatted_row = [format_excel_csv_value(v) for v in row]
        output.write(";".join(formatted_row) + "\n")
        
    return output.getvalue().encode('utf-8-sig')


def export_balance_managerial_xlsx(balance, orders_by_stop, project=None, filters=None,
                                    capacities=None, headcount_status=''):
    """Create a polished balance report.

    Sheets:
      1. Resumo
      2. Ordens por Parada (layout original, kept unchanged)
      3. Paradas + Efetivos (expanded horizontal matrix with Item/ID, Plano,
         order detail and MEC/SOL/ELE headcount + hours)
    """
    project, filters, capacities = project or {}, filters or {}, capacities or {}
    stops = balance.get('stops', [])
    kpis = balance.get('kpis', {})
    hours = balance.get('capacity_hours_per_person') or {}
    ambiguous = balance.get('capacity_hours_ambiguous') or {}
    available_hh = 0.0
    capacity_valid = False
    configured = [t for t in ('ele', 'mec', 'sol') if capacities.get(t) is not None]
    if configured and all(not ambiguous.get(t) and float(hours.get(t) or 0) > 0 for t in configured):
        available_hh = sum(float(capacities[t]) * float(hours[t]) for t in configured)
        capacity_valid = True
    avg_hh = float(kpis.get('avg_hh') or 0)
    utilization = avg_hh / available_hh * 100 if capacity_valid and available_hh else None
    max_hh, min_hh = float(kpis.get('max_hh') or 0), float(kpis.get('min_hh') or 0)
    variation = max_hh - min_hh

    filter_bits = [f"Horizonte: {filters.get('horizon', len(stops))} paradas"]
    labels = [('work_center', 'CT'), ('gpm', 'GPM'),
              ('condition_code', 'Condição'), ('item_identifiers', 'IDs')]
    for key, label in labels:
        if filters.get(key): filter_bits.append(f'{label}: {filters[key]}')
    if headcount_status: filter_bits.append(f'Situação: {headcount_status}')
    filter_text = '  |  '.join(filter_bits)

    # Shared managerial styles. Styles 0..13 are referenced below.
    styles = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
<numFmts count="3"><numFmt numFmtId="164" formatCode="0.0 &quot;HH&quot;"/><numFmt numFmtId="165" formatCode="0.0%"/><numFmt numFmtId="166" formatCode="0.0"/></numFmts>
<fonts count="6"><font><sz val="10"/><name val="Calibri"/><color rgb="FF334155"/></font><font><b/><sz val="20"/><name val="Calibri"/><color rgb="FFFFFFFF"/></font><font><b/><sz val="9"/><name val="Calibri"/><color rgb="FF64748B"/></font><font><b/><sz val="15"/><name val="Calibri"/><color rgb="FF1E293B"/></font><font><b/><sz val="10"/><name val="Calibri"/><color rgb="FFFFFFFF"/></font><font><b/><sz val="11"/><name val="Calibri"/><color rgb="FF365E00"/></font></fonts>
<fills count="8"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill><fill><patternFill patternType="solid"><fgColor rgb="FF365E00"/></patternFill></fill><fill><patternFill patternType="solid"><fgColor rgb="FFF4F8ED"/></patternFill></fill><fill><patternFill patternType="solid"><fgColor rgb="FFEDF4E2"/></patternFill></fill><fill><patternFill patternType="solid"><fgColor rgb="FF73B900"/></patternFill></fill><fill><patternFill patternType="solid"><fgColor rgb="FFFFF7E0"/></patternFill></fill><fill><patternFill patternType="solid"><fgColor rgb="FFF8FAFC"/></patternFill></fill></fills>
<borders count="3"><border/><border><left style="thin"><color rgb="FFDCE6D5"/></left><right style="thin"><color rgb="FFDCE6D5"/></right><top style="thin"><color rgb="FFDCE6D5"/></top><bottom style="thin"><color rgb="FFDCE6D5"/></bottom></border><border><bottom style="medium"><color rgb="FF73B900"/></bottom></border></borders>
<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs><cellXfs count="14">
<xf numFmtId="0" fontId="0" fillId="0" borderId="0"/><xf numFmtId="0" fontId="1" fillId="2" borderId="0"><alignment vertical="center"/></xf><xf numFmtId="0" fontId="5" fillId="3" borderId="0"><alignment vertical="center"/></xf>
<xf numFmtId="0" fontId="2" fillId="7" borderId="1"><alignment horizontal="center" vertical="center" wrapText="1"/></xf><xf numFmtId="0" fontId="3" fillId="7" borderId="1"><alignment horizontal="center" vertical="center"/></xf><xf numFmtId="164" fontId="3" fillId="7" borderId="1"><alignment horizontal="center" vertical="center"/></xf><xf numFmtId="165" fontId="3" fillId="7" borderId="1"><alignment horizontal="center" vertical="center"/></xf>
<xf numFmtId="0" fontId="4" fillId="2" borderId="1"><alignment horizontal="center" vertical="center" wrapText="1"/></xf><xf numFmtId="0" fontId="0" fillId="0" borderId="1"><alignment vertical="top" wrapText="1"/></xf><xf numFmtId="0" fontId="0" fillId="3" borderId="1"><alignment vertical="top" wrapText="1"/></xf><xf numFmtId="164" fontId="0" fillId="0" borderId="1"><alignment horizontal="right"/></xf><xf numFmtId="0" fontId="5" fillId="4" borderId="1"><alignment horizontal="center" vertical="center" wrapText="1"/></xf><xf numFmtId="166" fontId="0" fillId="0" borderId="1"><alignment horizontal="right"/></xf><xf numFmtId="0" fontId="2" fillId="6" borderId="1"><alignment horizontal="center" vertical="center" wrapText="1"/></xf>
</cellXfs><cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles></styleSheet>'''

    # Sheet 1: title, filter context, KPI cards, chart and its source table.
    summary_rows = [f'<row r="1" ht="34" customHeight="1">{_xlsx_cell("A1", "RELATÓRIO GERENCIAL DE BALANCEAMENTO", 1)}</row>',
                    f'<row r="2" ht="24" customHeight="1">{_xlsx_cell("A2", project.get("name") or "Projeto", 2)}</row>',
                    f'<row r="3" ht="26" customHeight="1">{_xlsx_cell("A3", filter_text, 13)}</row>']
    available_people = sum(float(capacities[t]) for t in configured)
    cards = [('HH TOTAL PROJETADO', kpis.get('total_hh', 0), 5, True),
             ('HH MÉDIO / PARADA', avg_hh, 5, True),
             ('UTILIZAÇÃO DA CAPACIDADE', (utilization or 0) / 100, 6, True),
             ('EFETIVO DISPONÍVEL', available_people if configured else 'Não informado', 4, bool(configured)),
             ('HH DISPONÍVEL', available_hh if capacity_valid else 'Não calculado', 5, capacity_valid),
             ('EFETIVO MÉDIO', kpis.get('avg_headcount', 0), 4, True),
             ('EFETIVO DE PICO', kpis.get('max_headcount', 0), 4, True),
             ('VARIAÇÃO MÁXIMA', variation, 5, True)]
    card_columns = (1, 4, 7, 10)
    card_merges = []
    for idx, (label, value, value_style, numeric) in enumerate(cards):
        row = 5 if idx < 4 else 8
        start = card_columns[idx % 4]
        col1, col2 = _xlsx_col_name(start), _xlsx_col_name(start + 2)
        summary_rows.append(f'<row r="{row}" ht="20" customHeight="1">{_xlsx_cell(col1 + str(row), label, 3)}</row>')
        summary_rows.append(f'<row r="{row + 1}" ht="30" customHeight="1">{_xlsx_cell(col1 + str(row + 1), value, value_style, numeric)}</row>')
        card_merges.extend((f'<mergeCell ref="{col1}{row}:{col2}{row}"/>',
                            f'<mergeCell ref="{col1}{row + 1}:{col2}{row + 1}"/>'))
    # Duplicate row numbers above are legal only when combined; consolidate by sorting/grouping cells.
    by_row = {}
    for xml in summary_rows:
        import re as _re
        row_no = int(_re.search(r'<row r="(\d+)"', xml).group(1))
        cells = xml[xml.find('>') + 1:xml.rfind('</row>')]
        ht = _re.search(r' ht="([^"]+)"', xml)
        by_row.setdefault(row_no, {'cells': [], 'ht': ht.group(1) if ht else '20'})['cells'].append(cells)
    summary_rows = [f'<row r="{r}" ht="{v["ht"]}" customHeight="1">{"".join(v["cells"])}</row>' for r, v in sorted(by_row.items())]
    summary_rows.append(f'<row r="11" ht="24" customHeight="1">{_xlsx_cell("A11", "HH PROJETADO POR PARADA", 11)}</row>')
    peak_for_bar = max([float(stop.get('total_hh') or 0) for stop in stops] +
                       ([available_hh] if capacity_valid else [1.0])) or 1.0
    graph_width = 48
    limit_pos = min(graph_width, max(1, round((available_hh / peak_for_bar) * graph_width))) if capacity_valid else None
    for row_no, stop in enumerate(stops, 12):
        hh_value = float(stop.get('total_hh') or 0)
        bar_len = max(1, round((hh_value / peak_for_bar) * graph_width)) if hh_value else 0
        graph_chars = []
        for position in range(1, graph_width + 1):
            if limit_pos and position == limit_pos:
                graph_chars.append('│')
            elif position <= bar_len:
                graph_chars.append('█')
            else:
                graph_chars.append('─')
        data_label = f"  {hh_value:.1f} HH".replace('.', ',')
        blocks = ''.join(graph_chars) + data_label
        bar_cells = _xlsx_cell(f'A{row_no}', f"P{stop.get('stop_num')}", 11)
        bar_cells += _xlsx_cell(f'B{row_no}', hh_value, 10, True)
        bar_cells += _xlsx_cell(f'C{row_no}', blocks, 2)
        summary_rows.append(f'<row r="{row_no}" ht="19" customHeight="1">{bar_cells}</row>')
    source_start = max(32, 14 + len(stops))
    summary_rows.append(f'<row r="{source_start}" ht="24" customHeight="1">{_xlsx_cell("A"+str(source_start), "PARADA", 7)}{_xlsx_cell("B"+str(source_start), "HH PROJETADO", 7)}{_xlsx_cell("C"+str(source_start), "HH DISPONÍVEL", 7)}{_xlsx_cell("D"+str(source_start), "ORDENS", 7)}</row>')
    for pos, stop in enumerate(stops, source_start + 1):
        cells = _xlsx_cell(f'A{pos}', f"P{stop.get('stop_num')}", 8)
        cells += _xlsx_cell(f'B{pos}', stop.get('total_hh', 0), 10, True)
        cells += _xlsx_cell(f'C{pos}', available_hh if capacity_valid else '', 10, capacity_valid)
        cells += _xlsx_cell(f'D{pos}', stop.get('total_orders', 0), 12, True)
        summary_rows.append(f'<row r="{pos}">{cells}</row>')
    last_source = max(source_start + 1, source_start + len(stops))
    chart_merges = ''.join(f'<mergeCell ref="C{row_no}:N{row_no}"/>' for row_no in range(12, 12 + len(stops)))
    capacity_caption = (f"  |  LIMITE DISPONÍVEL: {available_hh:.1f} HH / {available_people:g} pessoas".replace('.', ',')
                        if capacity_valid else '')
    summary_rows = [row.replace('HH PROJETADO POR PARADA', 'HH PROJETADO POR PARADA' + capacity_caption)
                    if 'HH PROJETADO POR PARADA' in row else row for row in summary_rows]
    summary_sheet = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetPr><tabColor rgb="FF73B900"/></sheetPr><sheetViews><sheetView showGridLines="0" tabSelected="1" workbookViewId="0"/></sheetViews><cols><col min="1" max="1" width="10" customWidth="1"/><col min="2" max="2" width="13" customWidth="1"/><col min="3" max="14" width="12" customWidth="1"/></cols><sheetData>{''.join(summary_rows)}</sheetData><mergeCells count="{20 + len(stops)}"><mergeCell ref="A1:N1"/><mergeCell ref="A2:N2"/><mergeCell ref="A3:N3"/><mergeCell ref="A11:N11"/>{''.join(card_merges)}{chart_merges}</mergeCells><pageMargins left="0.25" right="0.25" top="0.4" bottom="0.4" header="0.2" footer="0.2"/><pageSetup orientation="landscape" fitToWidth="1" fitToHeight="1"/></worksheet>'''

    # Sheet 2: one stop per column, with complete, wrapped order descriptions.
    order_rows = []
    headers = []
    max_orders = max([len(orders_by_stop.get(int(s['counter']), [])) for s in stops] or [0])
    for col_idx, stop in enumerate(stops, 1):
        ref = _xlsx_col_name(col_idx)
        header = f"PARADA {stop.get('stop_num')}\nContador {stop.get('counter')}  |  {float(stop.get('total_hh') or 0):.1f} HH\n{len(orders_by_stop.get(int(stop['counter']), []))} ordens"
        headers.append(_xlsx_cell(f'{ref}1', header, 7))
    order_rows.append(f'<row r="1" ht="54" customHeight="1">{"".join(headers)}</row>')
    for row_idx in range(max_orders):
        cells, row_lines = [], 1
        for col_idx, stop in enumerate(stops, 1):
            rows = orders_by_stop.get(int(stop['counter']), [])
            if row_idx >= len(rows): continue
            order = rows[row_idx]
            cycle = order.get('cycle') if order.get('cycle') is not None else order.get('plan_cycle', '')
            unit = order.get('unit') or order.get('plan_unit') or ''
            hh = float(order.get('hh') or (float(order.get('duration_hours') or 0) * float(order.get('headcount') or 1)))
            value = (f"{order.get('legacy_identifier') or '-'}  |  {order.get('description') or 'Sem descrição'}\n"
                     f"Plano: {order.get('plan_code') or '-'} — {order.get('plan_description') or ''}\n"
                     f"Ciclo: {cycle} {unit}  |  Carga: {hh:.1f} HH")
            row_lines = max(row_lines, 3 + len(value) // 55)
            cells.append(_xlsx_cell(f'{_xlsx_col_name(col_idx)}{row_idx+2}', value, 9 if row_idx % 2 else 8))
        order_rows.append(f'<row r="{row_idx+2}" ht="{min(90, max(48, row_lines*13))}" customHeight="1">{"".join(cells)}</row>')
    col_count = max(1, len(stops)); last_col = _xlsx_col_name(col_count)
    cols = ''.join(f'<col min="{i}" max="{i}" width="42" customWidth="1"/>' for i in range(1, col_count + 1))
    orders_sheet = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetViews><sheetView showGridLines="0" workbookViewId="0"><pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews><cols>{cols}</cols><sheetData>{''.join(order_rows)}</sheetData><autoFilter ref="A1:{last_col}{max(1,max_orders+1)}"/><pageMargins left="0.2" right="0.2" top="0.4" bottom="0.4" header="0.2" footer="0.2"/><pageSetup orientation="landscape" fitToWidth="1" fitToHeight="0"/></worksheet>'''

    # Sheet 3: expanded stop matrix. The original second sheet is intentionally
    # untouched; this is an additional operational view inspired by the planner's
    # horizontal stop worksheet. Each stop receives its own block of columns.
    #
    #   Item/ID | Plano | PARADA N | Mecânico | Horas | Soldador | Horas | Eletricista | Horas | separator
    #
    # The item detail remains in the PARADA column, while identifiers and plan code
    # are also exposed in dedicated columns to make filtering/copying easier.
    detail_rows = []
    detail_headers = []
    detail_block_width = 10
    detail_last_col_index = max(1, len(stops) * detail_block_width)
    detail_last_col = _xlsx_col_name(detail_last_col_index)

    for stop_idx, stop in enumerate(stops):
        base_col = stop_idx * detail_block_width + 1
        stop_orders = orders_by_stop.get(int(stop['counter']), [])
        stop_header = (f"PARADA {stop.get('stop_num')}\n"
                       f"Contador {stop.get('counter')}  |  {float(stop.get('total_hh') or 0):.1f} HH\n"
                       f"{len(stop_orders)} ordens")
        headers_for_block = [
            ('ITEM / ID', 7),
            ('PLANO', 7),
            (stop_header, 7),
            ('Mecânico', 7),
            ('Horas', 7),
            ('Soldador', 7),
            ('Horas', 7),
            ('Eletricista', 7),
            ('Horas', 7),
            ('', 3),
        ]
        for offset, (label, style_id) in enumerate(headers_for_block):
            col_ref = _xlsx_col_name(base_col + offset)
            detail_headers.append(_xlsx_cell(f'{col_ref}1', label, style_id))
    detail_rows.append(f'<row r="1" ht="54" customHeight="1">{"".join(detail_headers)}</row>')

    for row_idx in range(max_orders):
        cells = []
        row_lines = 1
        for stop_idx, stop in enumerate(stops):
            base_col = stop_idx * detail_block_width + 1
            rows = orders_by_stop.get(int(stop['counter']), [])
            if row_idx < len(rows):
                order = rows[row_idx]
                cycle = order.get('cycle') if order.get('cycle') is not None else order.get('plan_cycle', '')
                unit = order.get('unit') or order.get('plan_unit') or ''
                hh = float(order.get('hh') or (float(order.get('duration_hours') or 0) * float(order.get('headcount') or 1)))
                detail = (f"{order.get('description') or 'Sem descrição'}\n"
                          f"Equip./Local: {order.get('object_code') or '-'}\n"
                          f"Ciclo: {cycle} {unit}  |  Carga: {hh:.1f} HH")
                row_lines = max(row_lines, 3 + len(detail) // 58)
                style_id = 9 if row_idx % 2 else 8

                values = [
                    (order.get('legacy_identifier') or '-', False),
                    (order.get('plan_code') or '-', False),
                    (detail, False),
                    (order.get('mec_headcount') or 0, True),
                    (order.get('mec_hours') or 0, True),
                    (order.get('sol_headcount') or 0, True),
                    (order.get('sol_hours') or 0, True),
                    (order.get('ele_headcount') or 0, True),
                    (order.get('ele_hours') or 0, True),
                ]
                for offset, (value, numeric) in enumerate(values):
                    col_ref = _xlsx_col_name(base_col + offset)
                    cells.append(_xlsx_cell(f'{col_ref}{row_idx + 2}', value, style_id, numeric))
            # A narrow visual separator is always written so the stop blocks are
            # clearly delimited even when a given stop has fewer orders.
            sep_ref = _xlsx_col_name(base_col + 9)
            cells.append(_xlsx_cell(f'{sep_ref}{row_idx + 2}', '', 3))

        detail_rows.append(
            f'<row r="{row_idx + 2}" ht="{min(90, max(48, row_lines * 13))}" customHeight="1">'
            f'{"".join(cells)}</row>'
        )

    detail_cols = []
    for stop_idx, _stop in enumerate(stops):
        base_col = stop_idx * detail_block_width + 1
        widths = (13, 20, 42, 11, 10, 11, 10, 11, 10, 2.5)
        for offset, width in enumerate(widths):
            col_no = base_col + offset
            detail_cols.append(f'<col min="{col_no}" max="{col_no}" width="{width}" customWidth="1"/>')
    if not stops:
        detail_cols.append('<col min="1" max="1" width="18" customWidth="1"/>')

    detail_sheet = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetPr><tabColor rgb="FF365E00"/></sheetPr><sheetViews><sheetView showGridLines="0" workbookViewId="0"><pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews><cols>{"".join(detail_cols)}</cols><sheetData>{"".join(detail_rows)}</sheetData><pageMargins left="0.2" right="0.2" top="0.4" bottom="0.4" header="0.2" footer="0.2"/><pageSetup orientation="landscape" fitToWidth="0" fitToHeight="0"/></worksheet>'''

    drawing = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><xdr:wsDr xmlns:xdr="http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"><xdr:twoCellAnchor><xdr:from><xdr:col>0</xdr:col><xdr:colOff>0</xdr:colOff><xdr:row>10</xdr:row><xdr:rowOff>0</xdr:rowOff></xdr:from><xdr:to><xdr:col>13</xdr:col><xdr:colOff>0</xdr:colOff><xdr:row>29</xdr:row><xdr:rowOff>0</xdr:rowOff></xdr:to><xdr:graphicFrame macro=""><xdr:nvGraphicFramePr><xdr:cNvPr id="2" name="Balanceamento HH"/><xdr:cNvGraphicFramePr/></xdr:nvGraphicFramePr><xdr:xfrm/><a:graphic><a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/chart"><c:chart xmlns:c="http://schemas.openxmlformats.org/drawingml/2006/chart" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" r:id="rId1"/></a:graphicData></a:graphic></xdr:graphicFrame><xdr:clientData/></xdr:twoCellAnchor></xdr:wsDr>'''
    chart = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><c:chartSpace xmlns:c="http://schemas.openxmlformats.org/drawingml/2006/chart" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"><c:chart><c:title><c:tx><c:rich><a:bodyPr/><a:lstStyle/><a:p><a:r><a:rPr lang="pt-BR"/><a:t>HH Projetado por Parada</a:t></a:r></a:p></c:rich></c:tx></c:title><c:plotArea><c:layout/><c:barChart><c:barDir val="col"/><c:grouping val="clustered"/><c:varyColors val="0"/><c:ser><c:idx val="0"/><c:order val="0"/><c:tx><c:strRef><c:f>Resumo!$B${source_start}</c:f></c:strRef></c:tx><c:cat><c:strRef><c:f>Resumo!$A${source_start+1}:$A${last_source}</c:f></c:strRef></c:cat><c:val><c:numRef><c:f>Resumo!$B${source_start+1}:$B${last_source}</c:f></c:numRef></c:val></c:ser><c:ser><c:idx val="1"/><c:order val="1"/><c:tx><c:strRef><c:f>Resumo!$C${source_start}</c:f></c:strRef></c:tx><c:cat><c:strRef><c:f>Resumo!$A${source_start+1}:$A${last_source}</c:f></c:strRef></c:cat><c:val><c:numRef><c:f>Resumo!$C${source_start+1}:$C${last_source}</c:f></c:numRef></c:val></c:ser><c:axId val="100"/><c:axId val="200"/></c:barChart><c:catAx><c:axId val="100"/><c:scaling><c:orientation val="minMax"/></c:scaling><c:axPos val="b"/><c:crossAx val="200"/><c:crosses val="autoZero"/></c:catAx><c:valAx><c:axId val="200"/><c:scaling><c:orientation val="minMax"/></c:scaling><c:axPos val="l"/><c:crossAx val="100"/><c:crosses val="autoZero"/></c:valAx></c:plotArea><c:legend><c:legendPos val="b"/></c:legend><c:plotVisOnly val="1"/></c:chart></c:chartSpace>'''
    types = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/><Override PartName="/xl/worksheets/sheet2.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/><Override PartName="/xl/worksheets/sheet3.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/></Types>'''
    root_rels = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>'''
    workbook = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><bookViews><workbookView activeTab="0" firstSheet="0" showSheetTabs="1"/></bookViews><sheets><sheet name="Resumo" sheetId="1" state="visible" r:id="rId1"/><sheet name="Ordens por Parada" sheetId="2" state="visible" r:id="rId2"/><sheet name="Paradas + Efetivos" sheetId="3" state="visible" r:id="rId3"/></sheets></workbook>'''
    wb_rels = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet2.xml"/><Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet3.xml"/><Relationship Id="rId4" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>'''
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as book:
        files = {'[Content_Types].xml': types, '_rels/.rels': root_rels,
                 'xl/workbook.xml': workbook, 'xl/_rels/workbook.xml.rels': wb_rels,
                 'xl/styles.xml': styles, 'xl/worksheets/sheet1.xml': summary_sheet,
                 'xl/worksheets/sheet2.xml': orders_sheet,
                 'xl/worksheets/sheet3.xml': detail_sheet}
        for name, value in files.items(): book.writestr(name, value)
    return output.getvalue()


def _formula_cell(ref, formula, style=0, cached=0):
    return f'<c r="{ref}" s="{style}"><f>{escape(formula)}</f><v>{cached or 0}</v></c>'


def _content_width(value):
    """Approximate a comfortable Excel column width for a scalar value."""
    if value is None:
        return 0
    text = str(value).replace('\r', '')
    lines = text.split('\n') or ['']
    return max((len(line) for line in lines), default=0)


def _sap_sheet_widths(name, headers, rows):
    """Return stable, content-aware widths for the corporate SAP workbook.

    We intentionally cap descriptive/long-text columns so one large procedure
    does not create a sheet thousands of pixels wide; wrapText handles the rest.
    """
    # Corporate-friendly caps by sheet/column.  The values are Excel character widths.
    caps_by_sheet = {
        'Cod Planos': [20, 44, 14, 10, 10, 20, 18, 30],
        'ITENS': [30, 24, 10, 22, 14, 12, 22, 15, 12, 44, 16, 44, 10, 10, 20, 18, 12, 44, 10, 18, 16, 18, 16, 18, 16, 18],
        'OPERAÇÕES - REPARO': [15, 30, 24, 12, 14, 22, 46, 16, 15, 12, 12],
        'TEXTO LONGO REPARO.CSV': [15, 30, 24, 12, 12, 12, 12, 14, 90],
        'Balanceamento': [16, 18, 18, 20, 22, 26],
        'Priorímetro': [12, 42, 11, 11] + [9] * 13,
    }
    mins_by_sheet = {
        'Cod Planos': [16, 28, 12, 9, 9, 14, 14, 22],
        'ITENS': [20, 18, 8, 18, 11, 10, 18, 12, 10, 28, 13, 28, 9, 9, 14, 14, 10, 28, 8, 16, 14, 16, 14, 16, 14, 14],
        'OPERAÇÕES - REPARO': [12, 20, 18, 10, 12, 18, 28, 13, 12, 10, 10],
        'TEXTO LONGO REPARO.CSV': [12, 20, 18, 10, 10, 10, 10, 11, 55],
        'Balanceamento': [12, 14, 14, 16, 18, 20],
        'Priorímetro': [9, 28, 9, 9] + [8] * 13,
    }
    caps = caps_by_sheet.get(name, [48] * len(headers))
    mins = mins_by_sheet.get(name, [12] * len(headers))
    widths = []
    for idx, header in enumerate(headers):
        content_max = _content_width(header)
        for row in rows:
            if idx < len(row):
                content_max = max(content_max, _content_width(row[idx]))
        cap = caps[idx] if idx < len(caps) else 48
        min_width = mins[idx] if idx < len(mins) else 12
        widths.append(min(cap, max(min_width, content_max + 2)))
    return widths


def _work_center_trade(work_center):
    """Infer whether the principal 0010 row is electrical or mechanical."""
    wc = str(work_center or '').upper().strip()
    if not wc:
        return None
    # Common corporate patterns: R55E-041 / ELE..., R55M-... / MEC...
    if 'ELE' in wc or 'ELÉ' in wc or ('R55E' in wc):
        return 'ele'
    if 'MEC' in wc or ('R55M' in wc):
        return 'mec'
    return None


def _sap_operation_workload(operation, item):
    """Resolve EFETIVO/HORAS for the SAP operation export.

    Source-of-truth rule requested by the planner:
    * 0010 principal receives ELE or MEC workload from the item (according to CT,
      or the only populated main discipline when the CT is ambiguous).
    * 0010 / 0010 receives SOL workload from the item.
    * Other rows keep their operation-level values.

    Empty specialty fields do not erase valid legacy operation data, which keeps
    imported projects backwards-compatible.
    """
    current_hc = operation.get('headcount')
    current_hours = operation.get('hours')
    if not item:
        return current_hc, current_hours

    code = str(operation.get('operation_code') or '').strip().zfill(4)
    raw_sub = str(operation.get('suboperation_code') or '').strip()
    sub = raw_sub.zfill(4) if raw_sub.isdigit() else raw_sub

    def pair(trade):
        hc = item.get(f'{trade}_headcount')
        hours = item.get(f'{trade}_hours')
        try:
            hc_num = int(hc or 0)
        except (TypeError, ValueError):
            hc_num = 0
        try:
            hours_num = float(hours or 0)
        except (TypeError, ValueError):
            hours_num = 0.0
        return hc_num, hours_num

    if code == '0010' and sub == '0010':
        sol_hc, sol_hours = pair('sol')
        return sol_hc, sol_hours

    if code == '0010' and not sub:
        ele = pair('ele')
        mec = pair('mec')
        trade = _work_center_trade(operation.get('work_center') or item.get('work_center'))
        if trade == 'ele' and (ele[0] > 0 or ele[1] > 0):
            return ele
        if trade == 'mec' and (mec[0] > 0 or mec[1] > 0):
            return mec
        populated = [value for value in (ele, mec) if value[0] > 0 or value[1] > 0]
        if len(populated) == 1:
            return populated[0]
    return current_hc, current_hours


def export_sap_workbook(plans, items, operations=None, long_texts=None,
                        balance=None, project=None, scope='full', template=False,
                        priorimeter_rows=None):
    """Create the standard SAP workbook (or a blank, match-ready model).

    The workbook deliberately uses the same sheet/header vocabulary as the
    corporate model.  It is dependency-free so the local application keeps
    working on machines where Office/Python packages are not installed.
    """
    operations, long_texts = operations or [], long_texts or []
    balance, project = balance or {'stops': []}, project or {}
    priorimeter_rows = priorimeter_rows or []
    if template:
        plans, items, operations, long_texts, priorimeter_rows = [], [], [], [], []

    plan_headers = ['Plano', 'Descrição do Plano', 'Qtd caracter', 'Ciclo', 'Unid.',
                    'Texto Ciclo', 'Horiz Abertura', 'Contador - Planos de Paradas']
    item_headers = ['Local de Instalação', 'Equipamento', 'GPM', 'CENTRO DE TRABALHO',
                    'CONDIÇÃO', 'PRIORIDADE', 'PLANO REPARO', 'Identificador', 'CONTADOR',
                    'DESCRIÇÃO ITEM', 'QTD CARACTERES', 'Descrição do Plano', 'Ciclo',
                    'unid.', 'Texto Ciclo', 'Horiz Abertura', 'T(H)', 'Itens', '',
                    'ELE EFETIVO (apagar)', 'ELE HORAS (apagar)',
                    'MEC EFETIVO (apagar)', 'MEC HORAS (apagar)',
                    'SOL EFETIVO (apagar)', 'SOL HORAS (apagar)',
                    'STATUS (apagar)']
    op_headers = ['Identificador', 'Local de Instalação', 'Equipamento', 'Operação',
                  'Sub Operação', 'Centro de trabalho', 'Texto breve', 'QTD CARACTERES',
                  'UNIDADE MEDI', 'EFETIVO', 'HORAS']
    text_headers = ['Identificador', 'Local de instalação', 'Equipamento', 'Geral',
                    'GrpLisTar.', 'NumGrpRot', 'OPER', 'SUB OPER', 'Descrição da operação']

    plan_rows = [[p.get('legacy_code'), p.get('description'), p.get('character_count'),
                  p.get('cycle'), p.get('unit'), p.get('cycle_text'), 0 if str(p.get('unit') or '').upper()=='PRD' else p.get('opening_horizon'),
                  str(p.get('phase') or '').zfill(3) if p.get('phase') else ''] for p in plans]
    item_rows = []
    for i in items:
        is_equip = str(i.get('object_type', '')).upper().startswith('EQUIP')
        item_rows.append([None if is_equip else i.get('object_code'), i.get('object_code') if is_equip else None,
            i.get('gpm'), i.get('work_center'), i.get('condition_code'), i.get('priority'),
            i.get('plan_code') or '', i.get('legacy_identifier'), i.get('legacy_start'),
            i.get('description'), i.get('character_count'), i.get('plan_description') or '',
            i.get('plan_cycle') or '', i.get('plan_unit') or '', i.get('plan_cycle_text') or '',
            i.get('plan_opening_horizon') or '', i.get('duration_hours') or 0,
            i.get('description'), 'CR01',
            i.get('ele_headcount') or 0, i.get('ele_hours') or 0,
            i.get('mec_headcount') or 0, i.get('mec_hours') or 0,
            i.get('sol_headcount') or 0, i.get('sol_hours') or 0,
            'INATIVO' if str(i.get('status') or 'ACTIVE').upper() == 'INACTIVE' else 'ATIVO'])
    item_by_id = {i.get('id'): i for i in items if i.get('id') is not None}
    op_rows = []
    for o in operations:
        export_headcount, export_hours = _sap_operation_workload(o, item_by_id.get(o.get('item_id')))
        op_rows.append([
            o.get('legacy_identifier'),
            None if o.get('object_type') == 'EQUIPAMENTO' else o.get('object_code'),
            o.get('object_code') if o.get('object_type') == 'EQUIPAMENTO' else None,
            o.get('operation_code'), o.get('suboperation_code'), o.get('work_center'),
            o.get('short_text'), len(o.get('short_text') or ''), o.get('unit') or 'H',
            export_headcount, export_hours
        ])
    text_rows = [[t.get('legacy_identifier'), None if t.get('object_type') == 'EQUIPAMENTO' else t.get('object_code'),
                  t.get('object_code') if t.get('object_type') == 'EQUIPAMENTO' else None, None,
                  t.get('group_code'), t.get('group_counter'), t.get('operation_code'),
                  t.get('suboperation_code'), materialize_record(t)] for t in long_texts]

    all_specs = [('Cod Planos', plan_headers, plan_rows), ('ITENS', item_headers, item_rows),
                 ('OPERAÇÕES - REPARO', op_headers, op_rows), ('TEXTO LONGO REPARO.CSV', text_headers, text_rows)]
    scope_names = {'plans': {'Cod Planos'}, 'items': {'ITENS'}, 'operations': {'OPERAÇÕES - REPARO'},
                   'long_texts': {'TEXTO LONGO REPARO.CSV'}}
    specs = all_specs if scope == 'full' else [x for x in all_specs if x[0] in scope_names.get(scope, set())]
    if scope == 'full':
        bal_headers = ['Parada', 'Índice da Parada', 'Itens / Ordens', 'HH Planejado', 'Efetivo Necessário', 'HH Disponível (Meta)']
        bal_rows = [[f"Parada {s.get('stop_num')}", s.get('stop_num'), s.get('total_orders'),
                     s.get('total_hh'), s.get('headcount_needed'), s.get('available_hh', '')]
                    for s in balance.get('stops', [])]
        specs.append(('Balanceamento', bal_headers, bal_rows))

        priorimeter_headers = [
            'ITENS', 'ITEM', 'Probabilidade de Falha', 'Impacto da Manutenção',
            '>1 evento/ano', 'Carga assimétrica', 'Içamento múltiplo',
            'Sobrecarga térmica', 'Tanques / gases', 'Vazamento / exposição',
            'Pressurizados', 'Elétrico energizado', 'Espaço confinado',
            'Altura >2 m', 'Metal quente', 'Conhecimento específico', 'Macaco hidráulico'
        ]
        priorimeter_fields = [
            'legacy_identifier', 'item_description', 'failure_probability', 'maintenance_impact',
            'events_over_one', 'asymmetric_lifting', 'multi_lifting', 'thermal_overload',
            'tanks_gases', 'leak_exposure', 'pressurized_systems', 'energized_electrical',
            'confined_spaces', 'height_over_2m', 'hot_metal', 'difficult_technical', 'hydraulic_jack'
        ]
        priorimeter_data = [[row.get(field, '') for field in priorimeter_fields] for row in priorimeter_rows]
        specs.append(('Priorímetro', priorimeter_headers, priorimeter_data))

    worksheets = []
    for sheet_idx, (name, headers, rows) in enumerate(specs, 1):
        # The PM13-only helper columns are deliberately gray and marked
        # (apagar), making it visually obvious that the corporate/SAP load does
        # not consume them. T:Y preserve discipline workload and Z preserves item status
        # so export→import round-trips keep ACTIVE/INACTIVE state.
        helper_cols = set(range(20, 27)) if name == 'ITENS' else set()  # 1-based T:Z; corporate A:S stays untouched
        header_cells = []
        for c, h in enumerate(headers, 1):
            if name == 'Priorímetro':
                header_style = 1 if c <= 4 else 7
            else:
                header_style = 4 if c in helper_cols else 1
            header_cells.append(_xlsx_cell(f'{_xlsx_col_name(c)}1', h, header_style))
        row_xml = ['<row r="1" ht="28" customHeight="1">' + ''.join(header_cells) + '</row>']
        for r_idx, values in enumerate(rows, 2):
            cells=[]
            for c_idx, val in enumerate(values,1):
                # Balanceamento is exported as a calculated snapshot.  The previous
                # implementation expanded one IF/COUNTIF term per plan; with large
                # projects those formulas exceeded Excel's 8,192-character limit
                # (sheet5.xml), causing the "conteúdo ilegível / fórmula removida" repair.
                # The application has already calculated these values server-side, so
                # writing the cached numbers directly is both safer and deterministic.
                numeric=isinstance(val,(int,float)) and not isinstance(val,bool)
                if name == 'Priorímetro':
                    style = 5 if c_idx <= 2 else 6
                else:
                    style = 5 if c_idx in helper_cols else (3 if r_idx%2==0 else 2)
                cells.append(_xlsx_cell(f'{_xlsx_col_name(c_idx)}{r_idx}', val, style, numeric))
            row_xml.append(f'<row r="{r_idx}">{"".join(cells)}</row>')
        last=max(2,len(rows)+1); last_col=_xlsx_col_name(len(headers))
        widths = _sap_sheet_widths(name, headers, rows)
        cols=''.join(f'<col min="{i}" max="{i}" width="{width}" customWidth="1"/>'
                     for i, width in enumerate(widths, 1))
        drawing = '<drawing r:id="rId1"/>' if name == 'Balanceamento' and rows else ''
        relns = ' xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"' if drawing else ''
        validations = ''
        if name == 'Priorímetro':
            validations = (f'<dataValidations count="3">'
                           f'<dataValidation type="list" allowBlank="1" showErrorMessage="1" sqref="C2:C{last}"><formula1>"1,2,3,4,5"</formula1></dataValidation>'
                           f'<dataValidation type="list" allowBlank="1" showErrorMessage="1" sqref="D2:D{last}"><formula1>"1,2,3,4,6,8"</formula1></dataValidation>'
                           f'<dataValidation type="list" allowBlank="1" showErrorMessage="1" sqref="E2:Q{last}"><formula1>"S,N"</formula1></dataValidation>'
                           f'</dataValidations>')
        xml=f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"{relns}><sheetViews><sheetView showGridLines="0" workbookViewId="0"><pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews><cols>{cols}</cols><sheetData>{''.join(row_xml)}</sheetData><autoFilter ref="A1:{last_col}{last}"/>{validations}{drawing}</worksheet>'''
        worksheets.append((name,xml,last))

    styles='''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><fonts count="4"><font><sz val="10"/><name val="Calibri"/></font><font><b/><color rgb="FFFFFFFF"/><sz val="10"/></font><font><b/><color rgb="FF365E00"/></font><font><b/><color rgb="FF404040"/><sz val="10"/></font></fonts><fills count="9"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill><fill><patternFill patternType="solid"><fgColor rgb="FF5F8500"/></patternFill></fill><fill><patternFill patternType="solid"><fgColor rgb="FFF6FAEF"/></patternFill></fill><fill><patternFill patternType="solid"><fgColor rgb="FFEAF4D8"/></patternFill></fill><fill><patternFill patternType="solid"><fgColor rgb="FFBFBFBF"/></patternFill></fill><fill><patternFill patternType="solid"><fgColor rgb="FFE7E6E6"/></patternFill></fill><fill><patternFill patternType="solid"><fgColor rgb="FFFFF200"/></patternFill></fill><fill><patternFill patternType="solid"><fgColor rgb="FFF4E7F4"/></patternFill></fill></fills><borders count="2"><border/><border><left style="thin"/><right style="thin"/><top style="thin"/><bottom style="thin"/></border></borders><cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs><cellXfs count="8"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/><xf numFmtId="0" fontId="1" fillId="2" borderId="1"><alignment wrapText="1" vertical="center"/></xf><xf numFmtId="0" fontId="0" fillId="3" borderId="1"><alignment wrapText="1" vertical="top"/></xf><xf numFmtId="0" fontId="0" fillId="4" borderId="1"><alignment wrapText="1" vertical="top"/></xf><xf numFmtId="0" fontId="3" fillId="5" borderId="1"><alignment wrapText="1" vertical="center"/></xf><xf numFmtId="0" fontId="0" fillId="6" borderId="1"><alignment wrapText="1" vertical="top"/></xf><xf numFmtId="0" fontId="0" fillId="7" borderId="1"><alignment horizontal="center" vertical="center" wrapText="1"/></xf><xf numFmtId="0" fontId="3" fillId="8" borderId="1"><alignment horizontal="center" vertical="center" wrapText="1"/></xf></cellXfs><cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles></styleSheet>'''
    sheet_tags=''.join(f'<sheet name="{escape(n)}" sheetId="{i}" r:id="rId{i}"/>' for i,(n,_,_) in enumerate(worksheets,1))
    wb=f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>{sheet_tags}</sheets><calcPr calcId="191029" fullCalcOnLoad="1"/></workbook>'''
    rels=''.join(f'<Relationship Id="rId{i}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{i}.xml"/>' for i in range(1,len(worksheets)+1))
    rels += f'<Relationship Id="rId{len(worksheets)+1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
    wb_rels=f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">{rels}</Relationships>'''
    balance_idx = next((i for i,(n,_,_) in enumerate(worksheets,1) if n == 'Balanceamento'), None)
    overrides=''.join(f'<Override PartName="/xl/worksheets/sheet{i}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>' for i in range(1,len(worksheets)+1))
    chart_types = ('<Override PartName="/xl/drawings/drawing1.xml" ContentType="application/vnd.openxmlformats-officedocument.drawing+xml"/>'
                   '<Override PartName="/xl/charts/chart1.xml" ContentType="application/vnd.openxmlformats-officedocument.drawingml.chart+xml"/>') if balance_idx and worksheets[balance_idx-1][2] > 1 else ''
    types=f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>{overrides}{chart_types}</Types>'''
    rootrels='''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>'''
    out=io.BytesIO()
    with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
        z.writestr('[Content_Types].xml',types); z.writestr('_rels/.rels',rootrels)
        z.writestr('xl/workbook.xml',wb); z.writestr('xl/_rels/workbook.xml.rels',wb_rels); z.writestr('xl/styles.xml',styles)
        for i,(_,xml,_) in enumerate(worksheets,1): z.writestr(f'xl/worksheets/sheet{i}.xml',xml)
        if balance_idx and worksheets[balance_idx-1][2] > 1:
            last = worksheets[balance_idx-1][2]
            sheet_rel='''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/drawing" Target="../drawings/drawing1.xml"/></Relationships>'''
            drawing='''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><xdr:wsDr xmlns:xdr="http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"><xdr:twoCellAnchor><xdr:from><xdr:col>7</xdr:col><xdr:colOff>0</xdr:colOff><xdr:row>1</xdr:row><xdr:rowOff>0</xdr:rowOff></xdr:from><xdr:to><xdr:col>15</xdr:col><xdr:colOff>0</xdr:colOff><xdr:row>20</xdr:row><xdr:rowOff>0</xdr:rowOff></xdr:to><xdr:graphicFrame macro=""><xdr:nvGraphicFramePr><xdr:cNvPr id="2" name="Balanceamento HH"/><xdr:cNvGraphicFramePr/></xdr:nvGraphicFramePr><xdr:xfrm/><a:graphic><a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/chart"><c:chart xmlns:c="http://schemas.openxmlformats.org/drawingml/2006/chart" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" r:id="rId1"/></a:graphicData></a:graphic></xdr:graphicFrame><xdr:clientData/></xdr:twoCellAnchor></xdr:wsDr>'''
            drawing_rel='''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/chart" Target="../charts/chart1.xml"/></Relationships>'''
            chart=f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><c:chartSpace xmlns:c="http://schemas.openxmlformats.org/drawingml/2006/chart" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"><c:chart><c:title><c:tx><c:rich><a:bodyPr/><a:lstStyle/><a:p><a:r><a:rPr lang="pt-BR"/><a:t>Balanceamento de HH por Parada</a:t></a:r></a:p></c:rich></c:tx></c:title><c:plotArea><c:layout/><c:barChart><c:barDir val="col"/><c:grouping val="clustered"/><c:varyColors val="0"/><c:ser><c:idx val="0"/><c:order val="0"/><c:tx><c:strRef><c:f>Balanceamento!$D$1</c:f></c:strRef></c:tx><c:cat><c:strRef><c:f>Balanceamento!$A$2:$A${last}</c:f></c:strRef></c:cat><c:val><c:numRef><c:f>Balanceamento!$D$2:$D${last}</c:f></c:numRef></c:val></c:ser><c:ser><c:idx val="1"/><c:order val="1"/><c:tx><c:strRef><c:f>Balanceamento!$F$1</c:f></c:strRef></c:tx><c:cat><c:strRef><c:f>Balanceamento!$A$2:$A${last}</c:f></c:strRef></c:cat><c:val><c:numRef><c:f>Balanceamento!$F$2:$F${last}</c:f></c:numRef></c:val></c:ser><c:axId val="100"/><c:axId val="200"/></c:barChart><c:catAx><c:axId val="100"/><c:scaling><c:orientation val="minMax"/></c:scaling><c:axPos val="b"/><c:crossAx val="200"/><c:crosses val="autoZero"/></c:catAx><c:valAx><c:axId val="200"/><c:scaling><c:orientation val="minMax"/></c:scaling><c:axPos val="l"/><c:crossAx val="100"/><c:crosses val="autoZero"/></c:valAx></c:plotArea><c:legend><c:legendPos val="b"/></c:legend><c:plotVisOnly val="1"/></c:chart></c:chartSpace>'''
            z.writestr(f'xl/worksheets/_rels/sheet{balance_idx}.xml.rels',sheet_rel)
            z.writestr('xl/drawings/drawing1.xml',drawing); z.writestr('xl/drawings/_rels/drawing1.xml.rels',drawing_rel); z.writestr('xl/charts/chart1.xml',chart)
    return out.getvalue()

# ==========================================
# PRIORÍMETRO SAP
# ==========================================

def export_priorimeter_xlsx(rows):
    """Exporta o Priorímetro SAP em formato compacto.

    A coluna ITENS leva o identificador do item e a coluna ITEM leva a descrição.
    A coluna de equipamento/local foi removida conforme o fluxo atual. Os campos
    S/N permanecem estreitos e editáveis por lista suspensa.
    """
    headers = [
        'ITENS',
        'ITEM',
        'Probabilidade\nFalha',
        'Impacto da\nManutenção',
        'Quantidade Eventos\nem 1 ano > 1?',
        'Carga\nassimétrica',
        'Içamento\nmúltiplo',
        'Sobrecarga\ntérmica',
        'Tanques /\ngases',
        'Vazamento /\nexposição',
        'Sistemas\npressurizados',
        'Elétrico\nenergizado',
        'Espaço\nconfinado',
        'Altura\n> 2 m',
        'Metal\nquente',
        'Conhecimento\nespecífico',
        'Macaco\nhidráulico',
    ]
    fields = [
        'legacy_identifier', 'item_description', 'failure_probability', 'maintenance_impact',
        'events_over_one', 'asymmetric_lifting', 'multi_lifting', 'thermal_overload',
        'tanks_gases', 'leak_exposure', 'pressurized_systems', 'energized_electrical',
        'confined_spaces', 'height_over_2m', 'hot_metal', 'difficult_technical', 'hydraulic_jack',
    ]
    widths = [11, 42, 11, 11] + [9] * 13

    row_xml = []
    header_cells = []
    for idx, header in enumerate(headers, 1):
        style = 1 if idx <= 4 else 3
        header_cells.append(_xlsx_cell(f'{_xlsx_col_name(idx)}1', header, style))
    row_xml.append('<row r="1" ht="74" customHeight="1">' + ''.join(header_cells) + '</row>')

    for r_idx, row in enumerate(rows or [], 2):
        cells = []
        for c_idx, field in enumerate(fields, 1):
            value = row.get(field, '')
            style = 4 if c_idx <= 2 else 5
            numeric = c_idx in (3, 4) and value not in (None, '')
            cells.append(_xlsx_cell(f'{_xlsx_col_name(c_idx)}{r_idx}', value, style, numeric=numeric))
        row_xml.append(f'<row r="{r_idx}" ht="22" customHeight="1">{"".join(cells)}</row>')

    # Legenda lateral. A tabela termina em Q; R fica livre e a legenda usa S/T.
    legend = {
        4: ('Probabilidade de Falha', 6),
        5: ('1', 'Muito Baixo (Acima de 30 dias)'),
        6: ('2', 'Baixa (16 a 30 dias)'),
        7: ('3', 'Média (8 a 15 dias)'),
        8: ('4', 'Alta (3 a 7 dias)'),
        9: ('5', 'Muito Alta (0 a 2 dias)'),
        11: ('Impacto da Manutenção', 6),
        12: ('1', 'Não Influencia na Linha de Produção'),
        13: ('2', 'Equipamento Stand By não Crítico'),
        14: ('3', 'Equipamento Stand By Crítico'),
        15: ('4', 'Parada de Circuito e/ou Perda'),
        16: ('6', 'Parada de Processo Produtivo'),
        17: ('8', 'Parada de Usina (Crítico 1)'),
        19: ('Quantidade Eventos em 1 ano > 1?', 7),
        20: ('S', 'Sim'),
        21: ('N', 'Não'),
        24: ('Fatores de Criticidade', 7),
    }
    factor_texts = [
        'Elevação e movimentação de carga assimétrica e/ou peso acima de 5t, com talhas manuais e similares ou guindastes.',
        'Elevação e/ou movimentação de carga com 2 ou mais meios de içamento (ex.: ponte rolante mais guindaste).',
        'Atividades realizadas com exposição a sobrecarga térmica acima dos limites de tolerância.',
        'Atividades realizadas em equipamentos com líquidos ou gases com risco de explosão ou incêndio.',
        'Atividades realizadas com risco de vazamento/exposição a produtos perigosos.',
        'Atividades realizadas em sistemas pressurizados.',
        'Atividades realizadas em sistemas elétricos energizados.',
        'Atividades realizadas em espaços confinados.',
        'Atividades realizadas com desnível superior a 2 metros.',
        'Atividades realizadas com risco de exposição, contato ou projeção de metal quente.',
        'Atividades que exigem conhecimentos técnicos específicos de difícil realização com risco de perdas relevantes ou acidentes graves.',
        'Manutenção com macaco hidráulico: acionamento simultâneo e/ou fora do centro de gravidade.',
    ]
    for pos, text in enumerate(factor_texts, 25):
        legend[pos] = ('S/N', text)

    sparse = {}
    for r, values in legend.items():
        if len(values) == 2 and isinstance(values[1], int):
            sparse[r] = _xlsx_cell(f'S{r}', values[0], values[1])
        else:
            sparse[r] = _xlsx_cell(f'S{r}', values[0], 8) + _xlsx_cell(f'T{r}', values[1], 8)

    main_by_row = {}
    for xml in row_xml:
        import re as _re
        match = _re.search(r'<row r="(\d+)"[^>]*>(.*)</row>', xml, _re.S)
        if match:
            main_by_row[int(match.group(1))] = (xml[:match.start(2)], match.group(2), xml[match.end(2):])
    max_row = max([len(rows or []) + 1, 36])
    combined_rows = []
    for r in range(1, max_row + 1):
        if r in main_by_row:
            prefix, body, suffix = main_by_row[r]
            combined_rows.append(prefix + body + sparse.get(r, '') + suffix)
        elif r in sparse:
            combined_rows.append(f'<row r="{r}" ht="22" customHeight="1">{sparse[r]}</row>')

    cols = ''.join(
        f'<col min="{i}" max="{i}" width="{width}" customWidth="1"/>'
        for i, width in enumerate(widths, 1)
    ) + '<col min="19" max="19" width="16" customWidth="1"/><col min="20" max="20" width="72" customWidth="1"/>'
    data_last = max(2, len(rows or []) + 1)
    validations = f'''<dataValidations count="3">
      <dataValidation type="list" allowBlank="1" showErrorMessage="1" sqref="C2:C{data_last}"><formula1>"1,2,3,4,5"</formula1></dataValidation>
      <dataValidation type="list" allowBlank="1" showErrorMessage="1" sqref="D2:D{data_last}"><formula1>"1,2,3,4,6,8"</formula1></dataValidation>
      <dataValidation type="list" allowBlank="1" showErrorMessage="1" sqref="E2:Q{data_last}"><formula1>"S,N"</formula1></dataValidation>
    </dataValidations>'''
    sheet_xml = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews>
  <cols>{cols}</cols>
  <sheetData>{''.join(combined_rows)}</sheetData>
  <autoFilter ref="A1:Q{data_last}"/>
  {validations}
  <pageMargins left="0.2" right="0.2" top="0.4" bottom="0.4" header="0.2" footer="0.2"/>
  <pageSetup orientation="landscape" fitToWidth="1" fitToHeight="0"/>
</worksheet>'''

    styles = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <fonts count="3">
    <font><sz val="10"/><name val="Calibri"/></font>
    <font><b/><sz val="10"/><name val="Calibri"/></font>
    <font><b/><sz val="9"/><name val="Calibri"/><color rgb="FFFFFFFF"/></font>
  </fonts>
  <fills count="8">
    <fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill>
    <fill><patternFill patternType="solid"><fgColor rgb="FF8DD36F"/><bgColor indexed="64"/></patternFill></fill>
    <fill><patternFill patternType="solid"><fgColor rgb="FFD9F0CF"/><bgColor indexed="64"/></patternFill></fill>
    <fill><patternFill patternType="solid"><fgColor rgb="FFE9C5E7"/><bgColor indexed="64"/></patternFill></fill>
    <fill><patternFill patternType="solid"><fgColor rgb="FFFFF200"/><bgColor indexed="64"/></patternFill></fill>
    <fill><patternFill patternType="solid"><fgColor rgb="FFF2F2F2"/><bgColor indexed="64"/></patternFill></fill>
    <fill><patternFill patternType="solid"><fgColor rgb="FFFFC000"/><bgColor indexed="64"/></patternFill></fill>
  </fills>
  <borders count="2"><border/><border><left style="thin"><color rgb="FF000000"/></left><right style="thin"><color rgb="FF000000"/></right><top style="thin"><color rgb="FF000000"/></top><bottom style="thin"><color rgb="FF000000"/></bottom></border></borders>
  <cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
  <cellXfs count="9">
    <xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>
    <xf numFmtId="0" fontId="1" fillId="2" borderId="1" xfId="0" applyAlignment="1"><alignment horizontal="center" vertical="center" wrapText="1"/></xf>
    <xf numFmtId="0" fontId="1" fillId="3" borderId="1" xfId="0" applyAlignment="1"><alignment horizontal="center" vertical="center" wrapText="1"/></xf>
    <xf numFmtId="0" fontId="1" fillId="4" borderId="1" xfId="0" applyAlignment="1"><alignment horizontal="center" vertical="center" wrapText="1"/></xf>
    <xf numFmtId="0" fontId="0" fillId="6" borderId="1" xfId="0" applyAlignment="1"><alignment horizontal="center" vertical="center"/></xf>
    <xf numFmtId="0" fontId="0" fillId="5" borderId="1" xfId="0" applyAlignment="1"><alignment horizontal="center" vertical="center"/></xf>
    <xf numFmtId="0" fontId="1" fillId="2" borderId="1" xfId="0" applyAlignment="1"><alignment horizontal="center" vertical="center"/></xf>
    <xf numFmtId="0" fontId="1" fillId="7" borderId="1" xfId="0" applyAlignment="1"><alignment horizontal="center" vertical="center"/></xf>
    <xf numFmtId="0" fontId="0" fillId="0" borderId="1" xfId="0" applyAlignment="1"><alignment vertical="center" wrapText="1"/></xf>
  </cellXfs>
</styleSheet>'''
    content_types = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/><Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/></Types>'''
    root_rels = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>'''
    workbook = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Priorímetro" sheetId="1" r:id="rId1"/></sheets></workbook>'''
    workbook_rels = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>'''

    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as book:
        book.writestr('[Content_Types].xml', content_types)
        book.writestr('_rels/.rels', root_rels)
        book.writestr('xl/workbook.xml', workbook)
        book.writestr('xl/_rels/workbook.xml.rels', workbook_rels)
        book.writestr('xl/styles.xml', styles)
        book.writestr('xl/worksheets/sheet1.xml', sheet_xml)
    return output.getvalue()


def export_pm13_systems_xlsx(project_id):
    from core.database import get_db_connection
    from core.models import list_priorimeter
    from core_pm11.sap_standards import get_sap_cycle_info, generate_nponto_hash
    from core_pm11.xlsx_io import build_xlsx
    import datetime
    import random

    conn = get_db_connection()
    try:
        plans_rows = conn.execute("SELECT * FROM plans WHERE project_id=? AND (deleted_at IS NULL OR deleted_at='') ORDER BY legacy_code", (project_id,)).fetchall()
        plans = [dict(r) for r in plans_rows]

        items_rows = conn.execute("""
            SELECT i.*, p.legacy_code as plan_code, p.description as plan_description
            FROM maintenance_items i
            LEFT JOIN plans p ON p.id = i.plan_id
            WHERE i.project_id=? AND (i.deleted_at IS NULL OR i.deleted_at='')
            ORDER BY i.legacy_identifier
        """, (project_id,)).fetchall()
        items = [dict(r) for r in items_rows]

        operations = [dict(r) for r in conn.execute("""SELECT o.*,i.legacy_identifier,i.object_type,i.object_code,i.work_center item_work_center
            FROM item_operations o JOIN maintenance_items i ON i.id=o.item_id
            WHERE o.project_id=? ORDER BY i.legacy_identifier,COALESCE(o.display_order,o.id),o.id""",(project_id,)).fetchall()]
        long_texts = [dict(r) for r in conn.execute("""SELECT t.*,o.item_id,o.operation_code,o.suboperation_code,i.legacy_identifier,i.object_type,i.object_code
            FROM operation_long_texts t JOIN item_operations o ON o.id=t.operation_id JOIN maintenance_items i ON i.id=o.item_id
            WHERE t.project_id=? ORDER BY i.legacy_identifier,o.id,COALESCE(t.display_order,t.line_sequence),t.id""",(project_id,)).fetchall()]

        def clean_object_code(value):
            value = str(value or '').strip()
            if value.upper() in {'SEM_EQUIPAMENTO', 'SEM EQUIPAMENTO', 'N/A', 'NONE', 'NULL'}:
                return ''
            return value

        def route_description(item):
            route = str(item.get('legacy_start') or '').strip()
            description = str(item.get('plan_description') or item.get('description') or '').strip()
            return ' '.join(part for part in (route, description) if part)

        now = datetime.datetime.now()
        seed = random.randint(0, 99)
        nponto_map = {}
        for idx, it in enumerate(items, 1):
            nponto_map[it['id']] = generate_nponto_hash(project_id, it['id'], idx, now, clean_object_code(it.get('object_code')), seed)

        # 1. ABA PLANO
        sheet_plano_headers = [
            'Cód. Plano', 'Categoria', 'Ciclo', 'unid.', 'Texto Ciclo',
            'No.ACOM Objeto com contador ou branco = plano por tempo', 'Offset',
            'Txt. Descritivo', 'Conf. Obrigatória', 'FD atras.', 'Tol.conf.atr.',
            'FD adiant.', 'Tol.conf.adiant.', 'Interv. Solicitação', 'unid.',
            'Horiz. Abertura', 'Data Inicio/Pos. Contador', 'Código de programação', 'Calendário'
        ]
        plano_rows = [sheet_plano_headers]
        for p in plans:
            sap_info = get_sap_cycle_info(p.get('cycle_text'))
            interv = sap_info['interval'] if sap_info else p.get('cycle')
            unid_solic = sap_info['unid_solic'] if sap_info else (p.get('unit') or 'SMS')
            horiz = 0 if str(p.get('unit') or '').upper() == 'PRD' else (sap_info['horiz_insp'] if sap_info else (p.get('opening_horizon') or 50))
            plano_rows.append([
                p.get('legacy_code', ''),
                'PM',
                p.get('cycle', ''),
                p.get('unit', ''),
                p.get('cycle_text', ''),
                '',
                '',
                p.get('description', ''),
                '', '', '', '', '',
                interv,
                unid_solic,
                horiz,
                '', '', ''
            ])

        # 2. ABA ITEM
        sheet_item_headers = [
            'Cód.Plano', 'Cat', 'Txt.Descritivo', 'cod equipamento', 'Centro', 'GPM',
            'Tipo Ordem', 'Atividade', 'CT Inspetor', 'Centro', 'Prioridade', 'N.PONTO',
            'MNAME_01 Característica', 'MNAME_01 Característica', 'Criticidade'
        ]
        item_rows = [sheet_item_headers]
        for it in items:
            txt_desc = route_description(it)
            nponto = nponto_map.get(it['id'], '')
            prio = it.get('priority')
            if prio is None or prio == '':
                prio = 0
            item_rows.append([
                it.get('plan_code', ''),
                'PM',
                txt_desc,
                clean_object_code(it.get('object_code')),
                'US01',
                it.get('gpm', ''),
                'PM13',
                '015',
                it.get('work_center', ''),
                'US01',
                prio,
                nponto,
                '', '', ''
            ])

        # 3. ABA CABEÇALHO
        sheet_cab_headers = [
            'EQUNREquipamento ACOM/LOC INST', 'PROFIDNETZ Perfil', 'STTAG Data fixada',
            'KTEXT Denominação Lista Tarefa', 'ARBPLCentro de trabalho', 'WERKS Centro',
            'VERWE Utilização', 'VAGRPGPM', 'STATU Status', 'ANLZU Conds. instal.',
            'SLWBEZ Campo ponto de controle', 'KLART Tipo de classe', 'CLASS_01 Classe',
            'MNAME_01 Característica', 'MNAME_02 Característica', 'MNAME_03 Característica',
            'MWERT_01 Valor da Caract', 'MWERT_02 Valor da Caract'
        ]
        cab_rows = [sheet_cab_headers]
        for it in items:
            txt_desc = route_description(it)
            nponto = nponto_map.get(it['id'], '')
            eq = clean_object_code(it.get('object_code'))
            slwbez = '300' if eq else '310'
            cab_rows.append([
                eq,
                'PM01',
                '',
                txt_desc,
                it.get('work_center', ''),
                'US01',
                'PR1',
                it.get('gpm', ''),
                '4',
                it.get('condition_code', ''),
                slwbez,
                '018',
                'USPM_LISTA_TAREFA',
                'SUPM_QUANTIDADE_DE_PONTOS',
                'SUPM_NUMERO_ACOM',
                'USPM_TECNICA_DE_PREDITIVA',
                '1',
                nponto
            ])

        # 4. ABA OPERAÇÃO
        sheet_oper_headers = [
            'Nº antigo do ACOM', 'VORNR Nº operação', 'UVORN Nº Sub operação',
            'ARBPL2 Centro de Trabalho', 'WERKS2 Centro', 'STEUS Chave de controle',
            'LTXA1 Txt breve operação', 'ARBEH Unidade de trabalho',
            'ANZZL Núm capacidades necessárias', 'DAUNO Duração da operação',
            'DAUNE Unidade da Duração', 'INDET Chave de Cálculo',
            'PRZNT Porcentagem aumento', 'LARNT Tipo de Atividade'
        ]
        oper_rows = [sheet_oper_headers]
        item_by_id = {it['id']: it for it in items}
        for op in operations:
            it = item_by_id.get(op.get('item_id'), {})
            nponto = nponto_map.get(op.get('item_id'), '')
            headcount, hours = _sap_operation_workload(op, it)
            oper_rows.append([
                nponto,
                str(op.get('operation_code') or '').zfill(4),
                str(op.get('suboperation_code') or '').zfill(4) if str(op.get('suboperation_code') or '').strip() else '',
                op.get('work_center') or it.get('work_center', ''),
                'US01',
                'PM01',
                op.get('short_text') or it.get('description', ''),
                'H',
                headcount,
                hours,
                'H',
                2,
                100,
                ''
            ])

        text_headers = ['Identificador', 'Local de instalação', 'Equipamento', 'Geral', 'GrpLisTar.', 'NumGrpRot', 'OPER', 'SUB OPER', 'Descrição da operação']
        text_rows = [text_headers]
        texts_by_operation = {}
        for tx in long_texts:texts_by_operation.setdefault(tx.get('operation_id'),[]).append(tx)
        for op in operations:
            it=item_by_id.get(op.get('item_id'),{});object_code=clean_object_code(it.get('object_code'));is_equipment=bool(object_code) and str(it.get('object_type') or '').upper().startswith('EQUIP')
            code=str(op.get('operation_code') or '').zfill(4);raw_sub=str(op.get('suboperation_code') or '').strip();sub=raw_sub.zfill(4) if raw_sub else ''
            if code=='0010' and sub=='0010':
                sol_hc=int(it.get('sol_headcount') or 0);sol_hours=float(it.get('sol_hours') or 0)
                texts=[f'{sol_hc} MECÂNICOS {sol_hours:g} HORAS' if (sol_hc or sol_hours) else '']
            else:texts=[materialize_record(tx) for tx in texts_by_operation.get(op.get('id'),[])]
            for text_value in texts:text_rows.append([nponto_map.get(op.get('item_id'),''),'' if is_equipment else object_code,object_code if is_equipment else '','','','',code,sub,text_value])

        # 5. ABA PRIORÍMETRO
        priorimeter_headers = [
            'ITENS', 'ITEM', 'Probabilidade de Falha', 'Impacto da Manutenção',
            '>1 evento/ano', 'Carga assimétrica', 'Içamento múltiplo',
            'Sobrecarga térmica', 'Tanques / gases', 'Vazamento / exposição',
            'Pressurizados', 'Elétrico energizado', 'Espaço confinado',
            'Altura >2 m', 'Metal quente', 'Conhecimento específico', 'Macaco hidráulico'
        ]
        priorimeter_fields = [
            'legacy_identifier', 'item_description', 'failure_probability', 'maintenance_impact',
            'events_over_one', 'asymmetric_lifting', 'multi_lifting', 'thermal_overload',
            'tanks_gases', 'leak_exposure', 'pressurized_systems', 'energized_electrical',
            'confined_spaces', 'height_over_2m', 'hot_metal', 'difficult_technical', 'hydraulic_jack'
        ]
        priorimeter_rows = [priorimeter_headers]
        for row in list_priorimeter(project_id, status=''):
            priorimeter_rows.append([row.get(field, '') for field in priorimeter_fields])

        sheets = [
            {'name': 'PLANO', 'rows': plano_rows},
            {'name': 'ITEM', 'rows': item_rows},
            {'name': 'CABEÇALHO', 'rows': cab_rows},
            {'name': 'OPERAÇÃO', 'rows': oper_rows},
            {'name': 'TEXTO LONGO', 'rows': text_rows},
            {'name': 'Priorímetro', 'rows': priorimeter_rows}
        ]

        return build_xlsx(sheets)
    finally:
        conn.close()
