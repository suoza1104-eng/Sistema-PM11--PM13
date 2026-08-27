import os, datetime, re
from .database import get_conn
from .xlsx_io import read_workbook, build_xlsx, norm

FIELDS={
 'plans':{
  'code':['plano','codigo do plano','cod plano'], 'description':['descricao do plano','descrição do plano'], 'char_count':['qtd caracter','qtd caracteres','quantidade caracteres'],
  'cycle_value':['ciclo'], 'unit':['unid.','unid','unidade'], 'text_cycle':['texto ciclo','texto do ciclo'], 'horizon':['horiz abertura','horizonte de abertura'], 'counter':['contador - planos de paradas','contador']},
 'items':{
  'equipment_code':['equipamento','codigo equipamento','código equipamento'], 'gpm':['gpm'], 'work_center':['centro de trabalho','centro trabalho'], 'condition_code':['condicao','condição'],
  'priority':['prioridade'], 'plan_code':['plano inspecao','plano inspeção','plano de inspecao'], 'legacy_identifier':['identificador','id item'], 'route':['rota'], 'description':['descricao item','descrição item','item descricao'],
  'char_count':['qtd caracteres','qtd caracter'], 'plan_description':['descricao do plano','descrição do plano'], 'cycle_value':['ciclo'], 'unit':['unid.','unid','unidade'], 'text_cycle':['texto ciclo'],
  'horizon':['horiz abertura','horizonte de abertura'], 'inspection_minutes':['t(min)','tempo (min)','tempo min','tempo'], 'inspection_label':['itens_inspecao','itens inspeção'], 'criticality':['criticidade'], 'status':['status (apagar)','status']},
 'characteristics':{
  'legacy_identifier':['identificador','id item'], 'characteristic_type':['caracteristica mestre cont quantita/ qualitat','característica mestre cont quantita/ qualitat','tipo','qualitat/quantita'],
  'description':['itens de inspecao','itens de inspeção','caracteristica','característica','descricao caracteristica'], 'method_code':['metodo','método'], 'decimals':['casas decimais'], 'unit_code':['unidade de medida'],
  'reference_value':['valor referencia','valor referência'], 'lower_limit':['limite inferior'], 'upper_limit':['valor superior','limite superior'], 'status':['status (apagar)','status']}
}

def _num(v,default=None):
    if v in ('',None):return default
    try:return float(str(v).strip().replace(',','.'))
    except:return default

def _int(v,default=None):
    x=_num(v,None);return int(x) if x is not None else default

def _clean(v):
    if v is None:return ''
    s=str(v).strip();return '' if s.upper() in ('#N/A','#VALUE!','#REF!','N/A') else s

def _aliases(entity):
    out={}
    for key,aliases in FIELDS[entity].items():
        for a in aliases:out[norm(a)]=key
    return out

def _header_score(entity,d):
    aliases=_aliases(entity);matched={}
    for col,val in d.items():
        n=norm(val)
        if n in aliases:matched[aliases[n]]=str(val).strip()
    weights={'legacy_identifier':3,'code':3,'description':3,'equipment_code':2,'method_code':2,'route':2,'plan_code':2,'characteristic_type':2}
    score=sum(weights.get(k,1) for k in matched)
    return score,matched

def _suggest_sheets(headers):
    out={e:{} for e in FIELDS}
    for e in FIELDS:
        for sh,rows in headers.items():
            best={'score':0,'header_index':0,'header_row':None,'fields':{},'header_values':[]}
            for idx,(rn,d) in enumerate(rows[:25]):
                sc,m=_header_score(e,d)
                if sc>best['score']:
                    best={'score':sc,'header_index':idx,'header_row':rn,'fields':m,'header_values':[v for v in d.values() if str(v or '').strip()]}
            # Name bonus
            sn=norm(sh)
            if e=='plans' and ('plano' in sn and 'cod' in sn):best['score']+=5
            if e=='items' and sn=='itens':best['score']+=8
            if e=='characteristics' and ('sintese' in sn or 'caract' in sn):best['score']+=8
            out[e][sh]=best
    return out

def _choose_detection(suggestions,mapping_override=None):
    result={}
    for e,by in suggestions.items():
        override=(mapping_override or {}).get(e,{}) if isinstance(mapping_override,dict) else {}
        sh=override.get('sheet')
        if sh and sh in by:
            pass
        else:
            sh=max(by,key=lambda x:by[x]['score']) if by else None
            if sh and by[sh].get('score',0)<3: sh=None
        if not sh:result[e]={'sheet':None,'score':0,'header_index':0,'fields':{},'available_headers':[]};continue
        x=dict(by[sh]);x['sheet']=sh
        # headers available for manual field mapping in the import wizard
        x['available_headers']=[str(v).strip() for v in (x.get('header_values') or []) if str(v).strip()]
        # fields override: system_field -> excel header
        if override.get('fields'):x['manual_fields']=override['fields']
        result[e]=x
    return result

def _map_entity(rows,entity,det):
    if not rows or not det or det.get('sheet') is None:return []
    header_idx=int(det.get('header_index',0));_,head=rows[header_idx]
    aliases=_aliases(entity);colmap={}
    # automatic
    for col,val in head.items():
        key=aliases.get(norm(val))
        if key:colmap[col]=key
    # manual override system_field->header text
    for field,hname in (det.get('manual_fields') or {}).items():
        for col,val in head.items():
            if norm(val)==norm(hname):colmap[col]=field
    out=[];blank=0
    for rn,d in rows[header_idx+1:]:
        rec={'_row':rn}
        for col,key in colmap.items():
            if col in d:rec[key]=_clean(d[col])
        meaningful=any(str(v).strip() for k,v in rec.items() if k!='_row')
        if meaningful:out.append(rec);blank=0
        else:
            blank+=1
            if blank>300:break
    return out

def _catalog_cycles():
    c=get_conn()
    try:return [dict(r) for r in c.execute('SELECT * FROM cycle_catalog ORDER BY sort_order').fetchall()]
    finally:c.close()

def _infer_plan_cycle(p,cat):
    cv=_int(p.get('cycle_value'),None);unit=(p.get('unit') or '').upper();txt=(p.get('text_cycle') or '').upper();desc=(p.get('description') or '').upper()
    if cv is not None and unit in ('DIA','SMS'):return p
    text=' '.join([txt,desc])
    # strongly ordered common corporate patterns
    code=None
    rules=[('DIÁR','01D'),('DIARI','01D'),('2 DIAS','02D'),('DOIS DIAS','02D'),('3 DIAS','03D'),('TRIMEST','03M'),('SEMEST','06M'),('ANUAL','01A'),('2 ANOS','02A'),('3 ANOS','03A'),('4 ANOS','04A'),('18 MESES','18M'),('9 MESES','09M'),('BIMEST','02M'),('QUINZEN','02S'),('MENSAL','01M'),('SEMANAL','01S')]
    for k,cod in rules:
        if k in text:code=cod;break
    if not code:
        m=re.search(r'\b(\d+)\s*SEMAN',text)
        if m:
            n=int(m.group(1));code=next((x['code'] for x in cat if x['unit']=='SMS' and x['cycle_value']==n),None)
    if code:
        cy=next((x for x in cat if x['code']==code),None)
        if cy:p.update({'cycle_code':cy['code'],'cycle_value':cy['cycle_value'],'unit':cy['unit'],'text_cycle':cy['text_cycle'],'horizon':cy['horizon']})
    return p

def preview_import(path,mapping_override=None):
    # Header-only scan prevents inflated workbooks from loading millions of rows before detection.
    header_wb=read_workbook(path,max_meaningful_rows=80,max_cells=120000,row_limit_per_sheet=40)
    suggestions=_suggest_sheets(header_wb);det=_choose_detection(suggestions,mapping_override)
    selected=[x['sheet'] for x in det.values() if x.get('sheet')]
    if not selected:raise ValueError('Nenhuma aba compatível com Planos, Itens ou Características foi reconhecida.')
    # Use structural anchor columns to stop inflated formula tails. Real records need at least
    # two meaningful anchors (e.g. Plano+Descrição, Identificador+Descrição/Equipamento).
    primary_cols={};primary_min={}
    anchors={'plans':['code','description'],'items':['legacy_identifier','equipment_code','description','plan_code'],'characteristics':['legacy_identifier','description','characteristic_type','method_code']}
    for entity,detection in det.items():
        sh=detection.get('sheet')
        if not sh:continue
        rows=header_wb.get(sh,[]);hi=int(detection.get('header_index',0))
        if hi>=len(rows):continue
        _,hdr=rows[hi]
        wanted=[]
        manual=detection.get('manual_fields') or {}
        auto=detection.get('fields') or {}
        for field in anchors[entity]:
            hname=manual.get(field) or auto.get(field)
            if not hname:continue
            for col,val in hdr.items():
                if norm(val)==norm(hname):wanted.append(col);break
        if wanted:
            primary_cols[sh]=sorted(set(primary_cols.get(sh,[])+wanted))
            primary_min[sh]=2 if len(primary_cols[sh])>=2 else 1
    # Full read only for detected sheets. Limits are intentionally defensive.
    wb=read_workbook(path,target_sheets=selected,max_meaningful_rows=200000,max_cells=500000,stop_blank_run=80,primary_cols_by_sheet=primary_cols,primary_min_nonblank_by_sheet=primary_min)
    data={e:_map_entity(wb.get(det[e]['sheet'],[]),e,det[e]) if det[e].get('sheet') else [] for e in FIELDS}
    cat=_catalog_cycles();data['plans']=[_infer_plan_cycle(p,cat) for p in data['plans']]
    # Meaningful records only.
    data['plans']=[p for p in data['plans'] if p.get('code') and p.get('description') and re.fullmatch(r'[A-Za-z0-9]{8,15}',p.get('code','')) and len(p.get('code',''))>=3 and p.get('code','')[2].upper()=='I']
    data['items']=[i for i in data['items'] if _int(i.get('legacy_identifier')) is not None and (i.get('equipment_code') or i.get('description') or i.get('plan_code'))]
    data['characteristics']=[c for c in data['characteristics'] if _int(c.get('legacy_identifier')) is not None and (c.get('description') or c.get('method_code') or c.get('characteristic_type'))]
    errors=[];warnings=[];ids=set()
    for i in data['items']:
        ident=_int(i.get('legacy_identifier'))
        if ident in ids:warnings.append(f'Aba {det["items"]["sheet"]}, linha {i.get("_row")}: Identificador repetido {ident}.')
        ids.add(ident)
        if len(i.get('description',''))>35:errors.append(f'Item {ident}: descrição excede 35 caracteres.')
        cc=(i.get('condition_code') or 'Q').upper()
        if cc not in ('Q','P','M','F'):warnings.append(f'Item {ident}: condição {cc} inválida; será convertida para Q.')
    orphans=[c for c in data['characteristics'] if _int(c.get('legacy_identifier')) not in ids]
    if orphans:warnings.append(f'{len(orphans)} Característica(s) referenciam Identificadores ausentes na aba de Itens.')
    unresolved=sum(1 for p in data['plans'] if _int(p.get('cycle_value')) is None or not p.get('unit'))
    if unresolved:warnings.append(f'{unresolved} Plano(s) continuam sem ciclo/unidade e não entrarão corretamente no Balanceamento até revisão.')
    # clean suggestions for JSON
    simple={e:{sh:{'score':v['score'],'header_index':v['header_index'],'header_row':v.get('header_row'),'fields':v.get('fields',{}),'available_headers':[str(x).strip() for x in v.get('header_values',[]) if str(x).strip()]} for sh,v in by.items()} for e,by in suggestions.items()}
    samples={e:data[e][:5] for e in data}
    return {'detection':det,'sheet_suggestions':simple,'field_catalog':FIELDS,'sheets':list(header_wb.keys()),'counts':{e:len(data[e]) for e in data},'samples':samples,'errors':errors[:100],'warnings':warnings[:100],'data':data,'file_name':os.path.basename(path)}

def confirm_import(project_id,path,mode='MERGE',mapping_override=None):
    preview=preview_import(path,mapping_override)
    if preview['errors']:raise ValueError('Importação bloqueada: '+preview['errors'][0])
    d=preview['data'];c=get_conn();stats={'plans_created':0,'plans_updated':0,'items_created':0,'characteristics_created':0,'orphan_characteristics':0};mode=(mode or 'MERGE').upper()
    try:
        c.execute('BEGIN')
        if mode=='REPLACE':
            c.execute('DELETE FROM control_characteristics WHERE project_id=?',(project_id,));c.execute('DELETE FROM inspection_items WHERE project_id=?',(project_id,));c.execute('DELETE FROM inspection_plans WHERE project_id=?',(project_id,))
        plan_map={};cat=_catalog_cycles()
        for raw in d['plans']:
            p=_infer_plan_cycle(dict(raw),cat);code=(p.get('code') or '').strip().upper();desc=(p.get('description') or '').strip();cv=_int(p.get('cycle_value'),None);unit=(p.get('unit') or '').upper();txt=p.get('text_cycle') or '';h=_num(p.get('horizon'),None);counter=p.get('counter') or ''
            ex=c.execute('SELECT id FROM inspection_plans WHERE project_id=? AND code=?',(project_id,code)).fetchone();cycle_code=p.get('cycle_code') or ''
            if ex:
                pid=ex[0];c.execute('UPDATE inspection_plans SET description=?,char_count=?,cycle_code=?,cycle_value=?,unit=?,text_cycle=?,horizon=?,counter=?,updated_at=CURRENT_TIMESTAMP WHERE id=?',(desc,len(desc),cycle_code,cv,unit,txt,h,counter,pid));stats['plans_updated']+=1
            else:
                center=code[:1] or 'U';process=code[1:2] or 'R';typ=code[2:3] or 'I';line=code[3:6] if len(code)>=6 else '';sub=code[6:9] if len(code)>=9 else '';suffix=code[-3:] if len(code)>=3 else ''
                pid=c.execute('''INSERT INTO inspection_plans(project_id,code,description,char_count,center_code,process_code,type_code,line_code,subarea_code,suffix,cycle_code,cycle_value,unit,text_cycle,horizon,counter,status) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',(project_id,code,desc,len(desc),center,process,typ,line,sub,suffix,cycle_code,cv,unit,txt,h,counter,'ACTIVE')).lastrowid;stats['plans_created']+=1
            plan_map[code]=pid
        used={int(r[0]) for r in c.execute('SELECT legacy_identifier FROM inspection_items WHERE project_id=?',(project_id,)).fetchall()};next_ident=max(used or {0})+1;id_map={}
        for it in d['items']:
            old=_int(it.get('legacy_identifier'))
            if old is None:continue
            new_ident=old
            if mode=='MERGE' and new_ident in used:
                while next_ident in used:next_ident+=1
                new_ident=next_ident;next_ident+=1
            used.add(new_ident);pc=(it.get('plan_code') or '').strip().upper();plan_id=plan_map.get(pc)
            if not plan_id and pc:
                rr=c.execute('SELECT id FROM inspection_plans WHERE project_id=? AND code=?',(project_id,pc)).fetchone();plan_id=rr[0] if rr else None
            desc=(it.get('description') or '').strip();route=(it.get('route') or '').strip();route=route.zfill(4) if route else '';cond=(it.get('condition_code') or 'Q').strip().upper();cond=cond if cond in ('Q','P','M','F') else 'Q';st='INACTIVE' if norm(it.get('status')) in ('inativo','inactive') else 'ACTIVE'
            item_id=c.execute('''INSERT INTO inspection_items(project_id,plan_id,legacy_identifier,equipment_code,gpm,work_center,condition_code,priority,route,description,char_count,inspection_minutes,criticality,status) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',(project_id,plan_id,new_ident,it.get('equipment_code',''),it.get('gpm',''),it.get('work_center',''),cond,_int(it.get('priority'),0),route,desc,len(desc),_num(it.get('inspection_minutes'),0),it.get('criticality',''),st)).lastrowid
            id_map[old]=item_id;stats['items_created']+=1
        sort_cache={}
        for ch in d['characteristics']:
            item_id=id_map.get(_int(ch.get('legacy_identifier')))
            if not item_id:stats['orphan_characteristics']+=1;continue
            sort_cache[item_id]=sort_cache.get(item_id,0)+1;t=norm(ch.get('characteristic_type'));typ='QUANTITA' if t.startswith('quant') else 'QUALITAT';dec=_int(ch.get('decimals'),None) if typ=='QUANTITA' else None;unit=ch.get('unit_code','') if typ=='QUANTITA' else '';ref=_num(ch.get('reference_value'),None) if typ=='QUANTITA' else None;lo=_num(ch.get('lower_limit'),None) if typ=='QUANTITA' else None;hi=_num(ch.get('upper_limit'),None) if typ=='QUANTITA' else None
            c.execute('''INSERT INTO control_characteristics(project_id,item_id,sort_order,characteristic_type,description,method_code,decimals,unit_code,reference_value,lower_limit,upper_limit,status) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)''',(project_id,item_id,sort_cache[item_id],typ,ch.get('description',''),ch.get('method_code',''),dec,unit,ref,lo,hi,'ACTIVE'));stats['characteristics_created']+=1
        c.commit();return {'stats':stats,'preview':{k:v for k,v in preview.items() if k!='data'}}
    except Exception:c.rollback();raise
    finally:c.close()

# Backwards-compatible alias.
import_project=confirm_import

def export_project(project_id,balance_rows=None):
    c=get_conn()
    try:
        plans=[dict(r) for r in c.execute('SELECT * FROM inspection_plans WHERE project_id=? ORDER BY code',(project_id,)).fetchall()]
        items=[dict(r) for r in c.execute('''SELECT i.*,p.code plan_code,p.description plan_description,p.cycle_value,p.unit,p.text_cycle,p.horizon FROM inspection_items i LEFT JOIN inspection_plans p ON p.id=i.plan_id WHERE i.project_id=? ORDER BY i.legacy_identifier''',(project_id,)).fetchall()]
        chars=[dict(r) for r in c.execute('''SELECT ch.*,i.legacy_identifier FROM control_characteristics ch JOIN inspection_items i ON i.id=ch.item_id WHERE ch.project_id=? ORDER BY i.legacy_identifier,ch.sort_order,ch.id''',(project_id,)).fetchall()]
    finally:c.close()
    pr=[['Plano','Descrição do Plano','Qtd caracter','Ciclo','Unid.','Texto Ciclo','Horiz Abertura','Contador']]+[[p['code'],p['description'],p['char_count'],p['cycle_value'],p['unit'],p['text_cycle'],p['horizon'],p['counter']] for p in plans]
    ir=[['Equipamento','GPM','CENTRO DE TRABALHO','CONDIÇÃO','PRIORIDADE','PLANO INSPEÇÃO','Identificador','ROTA','DESCRIÇÃO ITEM','QTD CARACTERES','Descrição do Plano','Ciclo','unid.','Texto Ciclo','Horiz Abertura','t(min)','Itens_Inspeção','Criticidade','STATUS (apagar)']]
    for i in items:ir.append([i['equipment_code'],i['gpm'],i['work_center'],i['condition_code'],i['priority'],i['plan_code'] or '',i['legacy_identifier'],str(i['route']).zfill(4) if i['route'] else '',i['description'],i['char_count'],i['plan_description'] or '',i['cycle_value'],i['unit'],i['text_cycle'],i['horizon'],i['inspection_minutes'],((str(i['route']).zfill(4)+' ') if i['route'] else '')+i['description'],i['criticality'],i['status']])
    cr=[['Identificador','Caracteristica mestre cont\nQUANTITA/ QUALITAT','ITENS DE INSPEÇÃO','MÉTODO','CASAS DECIMAIS','UNIDADE DE MEDIDA','VALOR REFERÊNCIA','LIMITE INFERIOR','VALOR SUPERIOR','STATUS (apagar)']]+[[x['legacy_identifier'],x['characteristic_type'],x['description'],x['method_code'],x['decimals'],x['unit_code'],x['reference_value'],x['lower_limit'],x['upper_limit'],x['status']] for x in chars]
    sheets=[{'name':'Cod Planos','rows':pr,'widths':[18,42,13,10,10,24,16,14]},{'name':'ITENS','rows':ir,'widths':[18,10,18,12,11,18,13,9,40,14,40,10,10,24,16,11,48,14,17],'gray_cols':{19}},{'name':'SÍNTESE DE CARACT - INSPEÇÃO','rows':cr,'widths':[13,21,48,18,14,20,17,17,17,17],'gray_cols':{10}}]
    if balance_rows:
        br=[['Data','Tempo (min)','Tempo (h)','Qtd. Ordens','Rotas / Itens']]
        for r in balance_rows:
            try:d=datetime.date.fromisoformat(r['date']).strftime('%d/%m/%Y')
            except:d=r['date']
            br.append([d,r['minutes'],r['hours'],r['count'],' | '.join(f"{x['route']} #{x['identifier']} {x['description']}" for x in r['items'])])
        sheets.append({'name':'Balanceamento','rows':br,'widths':[14,14,12,14,80]})
    return build_xlsx(sheets)

def export_model():
    pr=[['Plano','Descrição do Plano','Qtd caracter','Ciclo','Unid.','Texto Ciclo','Horiz Abertura','Contador']]
    ir=[['Equipamento','GPM','CENTRO DE TRABALHO','CONDIÇÃO','PRIORIDADE','PLANO INSPEÇÃO','Identificador','ROTA','DESCRIÇÃO ITEM','QTD CARACTERES','Descrição do Plano','Ciclo','unid.','Texto Ciclo','Horiz Abertura','t(min)','Itens_Inspeção','Criticidade','STATUS (apagar)']]
    cr=[['Identificador','Caracteristica mestre cont\nQUANTITA/ QUALITAT','ITENS DE INSPEÇÃO','MÉTODO','CASAS DECIMAIS','UNIDADE DE MEDIDA','VALOR REFERÊNCIA','LIMITE INFERIOR','VALOR SUPERIOR','STATUS (apagar)']]
    return build_xlsx([{'name':'Cod Planos','rows':pr,'widths':[18,42,13,10,10,24,16,14]},{'name':'ITENS','rows':ir,'widths':[18,10,18,12,11,18,13,9,40,14,40,10,10,24,16,11,48,14,17],'gray_cols':{19}},{'name':'SÍNTESE DE CARACT - INSPEÇÃO','rows':cr,'widths':[13,21,48,18,14,20,17,17,17,17],'gray_cols':{10}}])
