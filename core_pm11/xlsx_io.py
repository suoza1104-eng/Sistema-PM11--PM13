import io, os, re, zipfile, xml.etree.ElementTree as ET, html, math, tempfile

NS='http://schemas.openxmlformats.org/spreadsheetml/2006/main'
RNS='http://schemas.openxmlformats.org/officeDocument/2006/relationships'
PNS='http://schemas.openxmlformats.org/package/2006/relationships'

def norm(s):
    import unicodedata
    s=unicodedata.normalize('NFD',str(s or ''))
    s=''.join(c for c in s if unicodedata.category(c)!='Mn').casefold()
    # Excel headers frequently contain line breaks/tabs and repeated spaces.
    return re.sub(r'\s+',' ',s).strip()

def col_num(ref):
    m=re.match(r'([A-Z]+)',ref or 'A');n=0
    for c in m.group(1):n=n*26+(ord(c)-64)
    return n

def col_letters(n):
    s=''
    while n:
        n,rem=divmod(n-1,26);s=chr(65+rem)+s
    return s

def read_workbook(path, target_sheets=None, max_meaningful_rows=200000, stop_blank_run=500, max_cells=500000, primary_cols_by_sheet=None, primary_min_nonblank_by_sheet=None, row_limit_per_sheet=None):
    if os.path.getsize(path)>80*1024*1024:raise ValueError('Arquivo XLSX muito grande (>80 MB). Revise a planilha antes de importar.')
    with zipfile.ZipFile(path) as z:
        if 'xl/workbook.xml' not in z.namelist():raise ValueError('Arquivo XLSX inválido.')
        ns={'m':NS,'r':RNS};relsns={'p':PNS}
        wb=ET.fromstring(z.read('xl/workbook.xml'));relroot=ET.fromstring(z.read('xl/_rels/workbook.xml.rels'))
        rels={r.attrib['Id']:r.attrib['Target'] for r in relroot.findall('p:Relationship',relsns)}
        sheets={}
        for s in wb.find('m:sheets',ns):
            name=s.attrib['name'];rid=s.attrib['{'+RNS+'}id'];target=rels[rid]
            if target.startswith('/'):target=target[1:]
            elif not target.startswith('xl/'):target='xl/'+target
            sheets[name]=target
        shared=[]
        if 'xl/sharedStrings.xml' in z.namelist():
            # Streaming shared strings; cap to protect malformed/inflated workbooks.
            count=0
            with z.open('xl/sharedStrings.xml') as sfh:
                for event,elem in ET.iterparse(sfh,events=('end',)):
                    if elem.tag=='{'+NS+'}si':
                        shared.append(''.join(t.text or '' for t in elem.iter('{'+NS+'}t')));count+=1;elem.clear()
                        if count>1200000:raise ValueError('Planilha contém quantidade excessiva de textos internos (>1,2 milhão). O arquivo parece inflado/corrompido.')
        result={};cell_counter=0
        for name,target in sheets.items():
            if target_sheets and name not in target_sheets:continue
            rows=[];blank_run=0;primary_blank_run=0;meaningful=0
            primary_cols=set((primary_cols_by_sheet or {}).get(name, []))
            primary_min=int((primary_min_nonblank_by_sheet or {}).get(name,1))
            current=[];row_num=None
            with z.open(target) as fh:
                for event,elem in ET.iterparse(fh,events=('end',)):
                    if elem.tag=='{'+NS+'}row':
                        row_num=int(elem.attrib.get('r','0') or 0);d={};has_value=False
                        for c in elem.findall('{'+NS+'}c'):
                            ref=c.attrib.get('r','');idx=col_num(ref);t=c.attrib.get('t');v=c.find('{'+NS+'}v');value=''
                            if t=='inlineStr':
                                isel=c.find('{'+NS+'}is');value=''.join(x.text or '' for x in isel.iter('{'+NS+'}t')) if isel is not None else ''
                            elif v is not None:
                                raw=v.text or ''
                                if t=='s':
                                    try:value=shared[int(raw)]
                                    except:value=raw
                                elif t=='b':value=True if raw=='1' else False
                                else:value=raw
                            if value not in ('',None):
                                d[idx]=value;has_value=True;cell_counter+=1
                                if cell_counter>max_cells:raise ValueError(f'Planilha possui mais de {max_cells:,} células com conteúdo. Importe uma versão reduzida/limpa.'.replace(',','.'))
                        primary_count=sum(1 for col in primary_cols if col in d and str(d.get(col,'')).strip() not in ('', '#N/A', '#VALUE!', '#REF!')) if primary_cols else (1 if has_value else 0)
                        primary_has = primary_count>=primary_min if primary_cols else has_value
                        if primary_cols:
                            if primary_has:
                                primary_blank_run=0
                            elif rows:
                                primary_blank_run+=1
                                if primary_blank_run>=stop_blank_run:
                                    break
                        if has_value:
                            rows.append((row_num,d));meaningful+=1;blank_run=0
                            if meaningful>max_meaningful_rows:raise ValueError(f'A aba {name} possui linhas úteis em excesso (> {max_meaningful_rows}).')
                        else:
                            blank_run+=1
                            if rows and blank_run>=stop_blank_run:break
                        elem.clear()
                        if row_limit_per_sheet and row_num >= int(row_limit_per_sheet):
                            break
            result[name]=rows
        return result

def rows_to_dicts(rows, header_row_index=0):
    if not rows:return []
    _,h=rows[header_row_index];headers={c:str(v).strip() for c,v in h.items() if str(v).strip()}
    out=[]
    for _,d in rows[header_row_index+1:]:
        rec={headers[c]:v for c,v in d.items() if c in headers}
        if rec:out.append(rec)
    return out

# ---------- Minimal XLSX writer (no external packages required) ----------
def _xml_text(v):return html.escape(str(v),quote=False)
def _cell(ref,value,style=0):
    if value is None:return ''
    if isinstance(value,bool):return f'<c r="{ref}" s="{style}" t="b"><v>{1 if value else 0}</v></c>'
    if isinstance(value,(int,float)) and not isinstance(value,bool) and math.isfinite(float(value)):
        return f'<c r="{ref}" s="{style}"><v>{value}</v></c>'
    return f'<c r="{ref}" s="{style}" t="inlineStr"><is><t xml:space="preserve">{_xml_text(value)}</t></is></c>'

def build_xlsx(sheets):
    # sheets: [{'name', 'rows': [[...]], 'widths': [...], 'gray_cols': set(int 1-based), 'freeze':1}]
    out=io.BytesIO()
    with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
        z.writestr('[Content_Types].xml','''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'''+''.join(f'<Override PartName="/xl/worksheets/sheet{i}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>' for i in range(1,len(sheets)+1))+'</Types>')
        z.writestr('_rels/.rels','''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>''')
        wb='''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>'''+''.join(f'<sheet name="{html.escape(s["name"],quote=True)}" sheetId="{i}" r:id="rId{i}"/>' for i,s in enumerate(sheets,1))+'</sheets></workbook>'
        z.writestr('xl/workbook.xml',wb)
        rel='''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'''+''.join(f'<Relationship Id="rId{i}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{i}.xml"/>' for i in range(1,len(sheets)+1))+'<Relationship Id="rIdStyles" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>'
        z.writestr('xl/_rels/workbook.xml.rels',rel)
        # 0 normal, 1 green header, 2 gray helper header, 3 gray body, 4 title
        styles='''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><fonts count="3"><font><sz val="10"/><name val="Calibri"/></font><font><b/><color rgb="FFFFFFFF"/><sz val="10"/><name val="Calibri"/></font><font><b/><color rgb="FF334155"/><sz val="10"/><name val="Calibri"/></font></fonts><fills count="5"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill><fill><patternFill patternType="solid"><fgColor rgb="FF365E00"/></patternFill></fill><fill><patternFill patternType="solid"><fgColor rgb="FFD9D9D9"/></patternFill></fill><fill><patternFill patternType="solid"><fgColor rgb="FF84BD00"/></patternFill></fill></fills><borders count="2"><border><left/><right/><top/><bottom/><diagonal/></border><border><left style="thin"><color rgb="FFD0D8CC"/></left><right style="thin"><color rgb="FFD0D8CC"/></right><top style="thin"><color rgb="FFD0D8CC"/></top><bottom style="thin"><color rgb="FFD0D8CC"/></bottom><diagonal/></border></borders><cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs><cellXfs count="5"><xf numFmtId="0" fontId="0" fillId="0" borderId="1" xfId="0" applyBorder="1"/><xf numFmtId="0" fontId="1" fillId="2" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1"><alignment horizontal="center" vertical="center" wrapText="1"/></xf><xf numFmtId="0" fontId="2" fillId="3" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1"><alignment horizontal="center" vertical="center" wrapText="1"/></xf><xf numFmtId="0" fontId="0" fillId="3" borderId="1" xfId="0" applyFill="1" applyBorder="1"/><xf numFmtId="0" fontId="1" fillId="4" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1"/></cellXfs><cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles></styleSheet>'''
        z.writestr('xl/styles.xml',styles)
        for si,s in enumerate(sheets,1):
            data=s.get('rows',[]);gray=set(s.get('gray_cols',[]));widths=s.get('widths') or []
            cols=''
            if widths:
                cols='<cols>'+''.join(f'<col min="{i}" max="{i}" width="{w}" customWidth="1"/>' for i,w in enumerate(widths,1))+'</cols>'
            pane=''
            if s.get('freeze',1):pane='<sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews>'
            xml=['<?xml version="1.0" encoding="UTF-8" standalone="yes"?><worksheet xmlns="'+NS+'">',pane,cols,'<sheetData>']
            for r_idx,rowv in enumerate(data,1):
                xml.append(f'<row r="{r_idx}"'+(' ht="30" customHeight="1"' if r_idx==1 else '')+'>')
                for c_idx,val in enumerate(rowv,1):
                    style=0
                    if r_idx==1:style=2 if c_idx in gray else 1
                    elif c_idx in gray:style=3
                    xml.append(_cell(f'{col_letters(c_idx)}{r_idx}',val,style))
                xml.append('</row>')
            xml.append('</sheetData><autoFilter ref="A1:'+col_letters(max((len(r) for r in data),default=1))+str(max(len(data),1))+'"/></worksheet>')
            z.writestr(f'xl/worksheets/sheet{si}.xml',''.join(xml))
    return out.getvalue()


def export_systems_xlsx(project_id):
    from .database import get_conn
    from .sap_standards import get_sap_cycle_info, generate_nponto_hash
    import datetime

    c = get_conn()
    try:
        plans_rows = c.execute("SELECT * FROM inspection_plans WHERE project_id=? AND status='ACTIVE' ORDER BY code", (project_id,)).fetchall()
        plans = [dict(r) for r in plans_rows]

        items_rows = c.execute("""
            SELECT i.*, p.code as plan_code, p.description as plan_description
            FROM inspection_items i
            JOIN inspection_plans p ON p.id = i.plan_id
            WHERE i.project_id=?
            ORDER BY i.legacy_identifier
        """, (project_id,)).fetchall()
        items = [dict(r) for r in items_rows]

        chars_rows = c.execute("""
            SELECT * FROM control_characteristics
            WHERE project_id=?
            ORDER BY item_id, id
        """, (project_id,)).fetchall()
        chars = [dict(r) for r in chars_rows]

        import random
        now = datetime.datetime.now()
        seed = random.randint(0, 99)
        nponto_map = {}
        for idx, it in enumerate(items, 1):
            nponto_map[it['id']] = generate_nponto_hash(project_id, it['id'], idx, now, it.get('equipment_code'), seed)

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
            sap_info = get_sap_cycle_info(p.get('text_cycle'))
            interv = sap_info['interval'] if sap_info else p.get('cycle_value')
            unid_solic = sap_info['unid_solic'] if sap_info else (p.get('unit') or 'SMS')
            horiz = 0 if str(p.get('unit') or '').upper() == 'PRD' else (sap_info['horiz_insp'] if sap_info else 50)
            plano_rows.append([
                p.get('code', ''),
                'PM',
                p.get('cycle_value', ''),
                p.get('unit', ''),
                p.get('text_cycle', ''),
                '',
                p.get('offset_days', '') if p.get('offset_days') is not None else '',
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
            txt_desc = f"{it.get('route', '')} {it.get('plan_description', '')}".strip()
            nponto = nponto_map.get(it['id'], '')
            prio = it.get('priority')
            if prio is None or prio == '':
                prio = 0
            item_rows.append([
                it.get('plan_code', ''),
                'PM',
                txt_desc,
                it.get('equipment_code', ''),
                'US01',
                it.get('gpm', ''),
                'PM11',
                '015',
                it.get('work_center', ''),
                'US01',
                prio,
                nponto,
                '', '', ''
            ])

        # 3. ABA CABEÇALHO
        sheet_cab_headers = [
            'EQUNREquipamento ACOM', 'PROFIDNETZ Perfil', 'STTAG Data fixada',
            'KTEXT Denominação Lista Tarefa', 'ARBPLCentro de trabalho', 'WERKS Centro',
            'VERWE Utilização', 'VAGRPGPM', 'STATU Status', 'ANLZU Conds. instal.',
            'SLWBEZ Campo ponto de controle', 'KLART Tipo de classe', 'CLASS_01 Classe',
            'MNAME_01 Característica', 'MNAME_02 Característica', 'MNAME_03 Característica',
            'MWERT_01 Valor da Caract', 'MWERT_02 Valor da Caract'
        ]
        cab_rows = [sheet_cab_headers]
        for it in items:
            txt_desc = f"{it.get('route', '')} {it.get('plan_description', '')}".strip()
            nponto = nponto_map.get(it['id'], '')
            eq = str(it.get('equipment_code') or '').strip()
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
        for it in items:
            txt_desc = f"{it.get('route', '')} {it.get('plan_description', '')}".strip()
            nponto = nponto_map.get(it['id'], '')
            hours = float(it.get('inspection_minutes') or 0) / 60.0
            oper_rows.append([
                nponto,
                '0010',
                '',
                it.get('work_center', ''),
                'US01',
                'PM01',
                txt_desc,
                'H',
                1,
                hours,
                'H',
                2,
                100,
                ''
            ])

        # 5. ABA CARACTERISTICAS
        sheet_char_headers = [
            'MWERT_02 Valor Caract', 'VORNR Nº operação', 'VERWMERKM Carac.mestre contr.',
            'QPMK_WERKS Centro Caract.', 'KURZTEXT Texto breve característica',
            'PMETHODE Método', 'QPMK_WERKS Centro Caract.',
            'STICHPRVER Processo amostra na característica controle',
            'STELLEN Casas decimais', 'MASSEINHSW Unidade',
            'SOLLWERT Valor teórico para uma característica quantitativa',
            'TOLERANZUN Valor limite inferior', 'TOLERANZOB Valor limite superior',
            'AUSWMENGE1 Grupo codes para avaliação RESULTADOS', 'AUSWMGWRK1 Centro Catálogo'
        ]
        char_rows = [sheet_char_headers]
        for ch in chars:
            nponto = nponto_map.get(ch.get('item_id'), '')
            char_rows.append([
                nponto,
                '0010',
                ch.get('characteristic_type', ''),
                'US01',
                ch.get('description', ''),
                ch.get('method_code', ''),
                'US01',
                'AMRT0001',
                ch.get('decimals', 0),
                ch.get('unit_code', ''),
                ch.get('reference_value', 0),
                ch.get('lower_limit', 0),
                ch.get('upper_limit', 0),
                'PMAVALIA',
                'US01'
            ])

        sheets = [
            {'name': 'PLANO', 'rows': plano_rows},
            {'name': 'ITEM', 'rows': item_rows},
            {'name': 'CABEÇALHO', 'rows': cab_rows},
            {'name': 'OPERAÇÃO', 'rows': oper_rows},
            {'name': 'CARACTERISTICAS', 'rows': char_rows}
        ]

        return build_xlsx(sheets)
    finally:
        c.close()
