import json, math, re, datetime
from .database import get_conn, normalize_search
from .plans_util import parse_offset_from_text, get_plan_dates_and_labels


def rows(rows): return [dict(r) for r in rows]
def row(r): return dict(r) if r else None

def _now(): return datetime.datetime.now().isoformat(timespec='seconds')

def _revalidate(pid):
    if not pid: return
    try:
        from .validation_engine import validate_pm11_project
        validate_pm11_project(int(pid))
    except Exception as e:
        print(f"[PM11 Revalidation Warning] {e}")

def get_projects():
    c=get_conn()
    try:
        q='''SELECT p.*, (SELECT COUNT(*) FROM inspection_plans x WHERE x.project_id=p.id) plans_count,
             (SELECT COUNT(*) FROM inspection_items x WHERE x.project_id=p.id) items_count,
             (SELECT COUNT(*) FROM control_characteristics x WHERE x.project_id=p.id) characteristics_count
             FROM projects p ORDER BY p.id DESC'''
        return rows(c.execute(q).fetchall())
    finally:c.close()

def get_project(pid):
    c=get_conn();
    try:return row(c.execute('SELECT * FROM projects WHERE id=?',(pid,)).fetchone())
    finally:c.close()

def create_project(data):
    c=get_conn()
    try:
        cur=c.execute('''INSERT INTO projects(name,area,system_name,description,default_center_code,default_process_code,default_type_code)
                         VALUES(?,?,?,?,?,?,?)''',(data.get('name') or 'Novo Projeto',data.get('area',''),data.get('system_name',''),data.get('description',''),data.get('default_center_code','U'),data.get('default_process_code','R'),data.get('default_type_code','I')))
        c.commit();return get_project(cur.lastrowid)
    finally:c.close()

def update_project(pid,data):
    allowed=['name','area','system_name','description','status','default_center_code','default_process_code','default_type_code','balance_anchor_date']
    if data.get('balance_anchor_date'):
        try: anchor = datetime.date.fromisoformat(str(data['balance_anchor_date']))
        except ValueError: raise ValueError('Data de Início da Programação inválida.')
        if anchor.weekday() != 0:
            raise ValueError('A Data de Início da Programação deve ser uma segunda-feira.')
    sets=[];vals=[]
    for k in allowed:
        if k in data: sets.append(f'{k}=?'); vals.append(data[k])
    if sets:
        vals += [_now(),pid]
        c=get_conn();
        try:c.execute(f"UPDATE projects SET {','.join(sets)},updated_at=? WHERE id=?",vals);c.commit()
        finally:c.close()
    return get_project(pid)

def delete_project(pid):
    c=get_conn();
    try:c.execute('DELETE FROM projects WHERE id=?',(pid,));c.commit()
    finally:c.close()


def get_cycles():
    c=get_conn();
    try:return rows(c.execute('SELECT * FROM cycle_catalog ORDER BY sort_order,cycle_value').fetchall())
    finally:c.close()

def get_code_catalogs():
    c=get_conn();
    try:
        return {'centers':rows(c.execute('SELECT * FROM production_centers ORDER BY code').fetchall()),
                'processes':rows(c.execute('SELECT * FROM process_catalog ORDER BY code').fetchall()),
                'types':rows(c.execute('SELECT * FROM plan_type_catalog ORDER BY code').fetchall()),
                'lines':rows(c.execute('SELECT * FROM production_lines ORDER BY code').fetchall()),
                'subareas':rows(c.execute('SELECT * FROM subareas ORDER BY code').fetchall())}
    finally:c.close()

def upsert_catalog(kind,code,description):
    table={'lines':'production_lines','subareas':'subareas'}[kind]
    code=(code or '').strip().upper()
    if len(code)!=3: raise ValueError('O código deve possuir exatamente 3 caracteres.')
    c=get_conn();
    try:c.execute(f'INSERT OR REPLACE INTO {table}(code,description) VALUES(?,?)',(code,description or ''));c.commit()
    finally:c.close()
    return get_code_catalogs()

def delete_catalog(kind,code):
    table={'lines':'production_lines','subareas':'subareas'}[kind]
    c=get_conn();
    try:c.execute(f'DELETE FROM {table} WHERE code=?',(code,));c.commit()
    finally:c.close()


def _build_plan_code(data):
    parts=[str(data.get('center_code','U')).upper(),str(data.get('process_code','R')).upper(),str(data.get('type_code','I')).upper(),str(data.get('line_code','')).upper(),str(data.get('subarea_code','')).upper(),str(data.get('suffix','')).upper()]
    if len(parts[0])!=1 or len(parts[1])!=1 or len(parts[2])!=1 or len(parts[3])!=3 or len(parts[4])!=3 or len(parts[5])!=3:
        return ''.join(parts)
    return ''.join(parts)

def _plan_payload(data):
    d=dict(data)
    d['description']=(d.get('description') or '').strip()
    d['char_count']=len(d['description'])
    d['center_code']=(d.get('center_code') or 'U').strip().upper()[:1]
    d['process_code']=(d.get('process_code') or 'R').strip().upper()[:1]
    d['type_code']=(d.get('type_code') or 'I').strip().upper()[:1]
    d['line_code']=(d.get('line_code') or '').strip().upper()[:3]
    d['subarea_code']=(d.get('subarea_code') or '').strip().upper()[:3]
    d['suffix']=(d.get('suffix') or '').strip().upper()[:3]
    d['code']=(d.get('code') or _build_plan_code(d)).strip().upper()
    if 'offset_days' in d and d.get('offset_days') not in (None, ''):
        d['offset_days'] = int(d['offset_days'])
        if d['offset_days'] < 1: raise ValueError('O Offset deve ser maior ou igual a 1.')
    elif 'offset_days' not in d or d.get('offset_days') in (None, ''):
        d['offset_days'] = parse_offset_from_text(d['description'], d['code'])
    if d.get('cycle_code'):
        c=get_conn()
        try:cy=c.execute('SELECT * FROM cycle_catalog WHERE code=?',(d['cycle_code'],)).fetchone()
        finally:c.close()
        if cy:
            d['cycle_value']=cy['cycle_value'];d['unit']=cy['unit'];d['text_cycle']=cy['text_cycle'];d['horizon']=cy['horizon']
    return d

def _decorate_plans(pid, values):
    project = get_project(pid) or {}
    anchor = project.get('balance_anchor_date') or ''
    for value in values:
        value.update(get_plan_dates_and_labels(anchor, value.get('offset_days'), value.get('description',''), value.get('code','')))
    return values

def list_plans(pid,search='',status='',cycle_code='',row_color=''):
    c=get_conn()
    try:
        where=['project_id=?'];args=[pid]
        if search: where.append('(SEARCH_NORMALIZE(code) LIKE ? OR SEARCH_NORMALIZE(description) LIKE ?)'); s='%'+normalize_search(search)+'%';args += [s,s]
        if status: where.append('status=?');args.append(status)
        if cycle_code:where.append('cycle_code=?');args.append(cycle_code)
        if row_color:where.append('row_color=?');args.append(row_color)
        return _decorate_plans(pid, rows(c.execute(f"SELECT * FROM inspection_plans WHERE {' AND '.join(where)} ORDER BY code",args).fetchall()))
    finally:c.close()

def get_plan(plan_id):
    c=get_conn();
    try:
        value=row(c.execute('SELECT * FROM inspection_plans WHERE id=?',(plan_id,)).fetchone())
        return _decorate_plans(value['project_id'], [value])[0] if value else None
    finally:c.close()

def create_plan(pid,data):
    d=_plan_payload(data)
    if len(d['code'])!=12: raise ValueError('O código do plano deve possuir 12 caracteres no padrão X X X XXX XXX XXX.')
    c=get_conn()
    try:
        cur=c.execute('''INSERT INTO inspection_plans(project_id,code,description,char_count,center_code,process_code,type_code,line_code,subarea_code,suffix,cycle_code,cycle_value,unit,text_cycle,horizon,offset_days,status)
                         VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',(pid,d['code'],d['description'],d['char_count'],d['center_code'],d['process_code'],d['type_code'],d['line_code'],d['subarea_code'],d['suffix'],d.get('cycle_code'),d.get('cycle_value'),d.get('unit'),d.get('text_cycle'),d.get('horizon'),d.get('offset_days'),d.get('status','ACTIVE')))
        c.commit();return get_plan(cur.lastrowid)
    except Exception:
        c.rollback();raise
    finally:c.close()

def update_plan(plan_id,data):
    d=_plan_payload({**(get_plan(plan_id) or {}),**data})
    c=get_conn()
    try:
        c.execute('''UPDATE inspection_plans SET code=?,description=?,char_count=?,center_code=?,process_code=?,type_code=?,line_code=?,subarea_code=?,suffix=?,cycle_code=?,cycle_value=?,unit=?,text_cycle=?,horizon=?,offset_days=?,status=?,updated_at=? WHERE id=?''',
        (d['code'],d['description'],d['char_count'],d['center_code'],d['process_code'],d['type_code'],d['line_code'],d['subarea_code'],d['suffix'],d.get('cycle_code'),d.get('cycle_value'),d.get('unit'),d.get('text_cycle'),d.get('horizon'),d.get('offset_days'),d.get('status','ACTIVE'),_now(),plan_id));c.commit();return get_plan(plan_id)
    except Exception:c.rollback();raise
    finally:c.close()

def delete_plans(ids):
    if not ids:return
    c=get_conn();
    try:c.executemany('DELETE FROM inspection_plans WHERE id=?',[(int(x),) for x in ids]);c.commit()
    finally:c.close()

def bulk_update_plans(ids,updates):
    allowed={'cycle_code','status','offset_days','row_color'}; upd={k:v for k,v in updates.items() if k in allowed}
    if not upd:return
    if 'cycle_code' in upd:
        c=get_conn();cy=c.execute('SELECT * FROM cycle_catalog WHERE code=?',(upd['cycle_code'],)).fetchone();c.close()
        if cy:upd.update({'cycle_value':cy['cycle_value'],'unit':cy['unit'],'text_cycle':cy['text_cycle'],'horizon':cy['horizon']})
    sets=','.join(f'{k}=?' for k in upd);vals=list(upd.values())
    c=get_conn();
    try:
        for i in ids:c.execute(f'UPDATE inspection_plans SET {sets},updated_at=? WHERE id=?',vals+[_now(),int(i)])
        c.commit()
    finally:c.close()


def next_identifier(pid):
    c=get_conn();
    try:return int(c.execute('SELECT COALESCE(MAX(legacy_identifier),0)+1 FROM inspection_items WHERE project_id=?',(pid,)).fetchone()[0])
    finally:c.close()

def _item_payload(data):
    d=dict(data);d['description']=(d.get('description') or '').strip();d['char_count']=len(d['description'])
    d['route']=str(d.get('route') or '').strip().zfill(4) if str(d.get('route') or '').strip() else ''
    d['condition_code']=(d.get('condition_code') or 'Q').upper()
    d['priority']=int(d.get('priority') or 0);d['inspection_minutes']=float(d.get('inspection_minutes') or 0)
    d['status']=d.get('status') or 'ACTIVE'
    return d

def list_items(pid,search='',plan_id=None,status='',equipment='',route=''):
    c=get_conn()
    try:
        where=['i.project_id=?'];args=[pid]
        if search:
            s='%'+normalize_search(search)+'%';where.append('(SEARCH_NORMALIZE(i.description) LIKE ? OR SEARCH_NORMALIZE(i.equipment_code) LIKE ? OR CAST(i.legacy_identifier AS TEXT) LIKE ?)');args += [s,s,'%'+str(search)+'%']
        if plan_id:where.append('i.plan_id=?');args.append(plan_id)
        if status:where.append('i.status=?');args.append(status)
        if equipment:where.append('SEARCH_NORMALIZE(i.equipment_code) LIKE ?');args.append('%'+normalize_search(equipment)+'%')
        if route:where.append('i.route LIKE ?');args.append('%'+route+'%')
        q=f'''SELECT i.*,p.code plan_code,p.description plan_description,p.cycle_code,p.cycle_value,p.unit,p.text_cycle,p.horizon,
              (SELECT COUNT(*) FROM control_characteristics c2 WHERE c2.item_id=i.id) characteristic_count
              FROM inspection_items i LEFT JOIN inspection_plans p ON p.id=i.plan_id WHERE {' AND '.join(where)}
              ORDER BY i.legacy_identifier'''
        return rows(c.execute(q,args).fetchall())
    finally:c.close()

def get_item(item_id):
    c=get_conn();
    try:return row(c.execute('''SELECT i.*,p.code plan_code,p.description plan_description,p.cycle_code,p.cycle_value,p.unit,p.text_cycle,p.horizon FROM inspection_items i LEFT JOIN inspection_plans p ON p.id=i.plan_id WHERE i.id=?''',(item_id,)).fetchone())
    finally:c.close()

def create_item(pid,data):
    d=_item_payload(data);ident=int(d.get('legacy_identifier') or next_identifier(pid))
    if len(d['description'])>35:raise ValueError('A descrição do Item possui mais de 35 caracteres.')
    c=get_conn()
    try:
        cur=c.execute('''INSERT INTO inspection_items(project_id,plan_id,legacy_identifier,equipment_code,gpm,work_center,condition_code,priority,route,description,char_count,inspection_minutes,criticality,status,balance_offset_days)
                         VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',(pid,d.get('plan_id'),ident,d.get('equipment_code',''),d.get('gpm',''),d.get('work_center',''),d['condition_code'],d['priority'],d['route'],d['description'],d['char_count'],d['inspection_minutes'],d.get('criticality',''),d['status'],int(d.get('balance_offset_days') or 0)))
        c.commit();return get_item(cur.lastrowid)
    except Exception:c.rollback();raise
    finally:c.close()

def update_item(item_id,data):
    old=get_item(item_id) or {};d=_item_payload({**old,**data})
    if len(d['description'])>35:raise ValueError('A descrição do Item possui mais de 35 caracteres.')
    c=get_conn();
    try:
        c.execute('''UPDATE inspection_items SET plan_id=?,equipment_code=?,gpm=?,work_center=?,condition_code=?,priority=?,route=?,description=?,char_count=?,inspection_minutes=?,criticality=?,status=?,balance_offset_days=?,updated_at=? WHERE id=?''',
                  (d.get('plan_id'),d.get('equipment_code',''),d.get('gpm',''),d.get('work_center',''),d['condition_code'],d['priority'],d['route'],d['description'],d['char_count'],d['inspection_minutes'],d.get('criticality',''),d['status'],int(d.get('balance_offset_days') or 0),_now(),item_id));c.commit();return get_item(item_id)
    finally:c.close()

def delete_items(ids):
    c=get_conn();
    try:c.executemany('DELETE FROM inspection_items WHERE id=?',[(int(x),) for x in ids]);c.commit()
    finally:c.close()

def bulk_update_items(ids,updates):
    allowed={'plan_id','gpm','work_center','condition_code','priority','route','inspection_minutes','criticality','status','equipment_code'}
    upd={k:v for k,v in updates.items() if k in allowed}
    if 'route' in upd and upd['route'] not in (None,''):upd['route']=str(upd['route']).zfill(4)
    if not upd:return
    sets=','.join(f'{k}=?' for k in upd);vals=list(upd.values())
    c=get_conn();
    try:
        for i in ids:c.execute(f'UPDATE inspection_items SET {sets},updated_at=? WHERE id=?',vals+[_now(),int(i)])
        c.commit()
    finally:c.close()


def list_characteristics(pid,search='',item_id=None,type_='',method='',status=''):
    c=get_conn()
    try:
        where=['c.project_id=?'];args=[pid]
        if search:
            s='%'+normalize_search(search)+'%';where.append('(SEARCH_NORMALIZE(c.description) LIKE ? OR SEARCH_NORMALIZE(i.description) LIKE ?)');args += [s,s]
        if item_id:where.append('c.item_id=?');args.append(item_id)
        if type_:where.append('c.characteristic_type=?');args.append(type_)
        if method:where.append('c.method_code=?');args.append(method)
        if status:where.append('c.status=?');args.append(status)
        q=f'''SELECT c.*,i.legacy_identifier,i.description item_description,i.equipment_code,i.route,p.code plan_code
              FROM control_characteristics c JOIN inspection_items i ON i.id=c.item_id LEFT JOIN inspection_plans p ON p.id=i.plan_id
              WHERE {' AND '.join(where)} ORDER BY i.legacy_identifier,c.sort_order,c.id'''
        return rows(c.execute(q,args).fetchall())
    finally:c.close()

def get_characteristic(cid):
    c=get_conn();
    try:return row(c.execute('SELECT * FROM control_characteristics WHERE id=?',(cid,)).fetchone())
    finally:c.close()

def _char_payload(data):
    d=dict(data);typ=(d.get('characteristic_type') or 'QUALITAT').upper();d['characteristic_type']='QUANTITA' if typ.startswith('QUANT') else 'QUALITAT'
    d['description']=(d.get('description') or '').strip();d['method_code']=(d.get('method_code') or '').strip()
    if d['characteristic_type']=='QUALITAT':
        d['decimals']=None;d['unit_code']='';d['reference_value']=None;d['lower_limit']=None;d['upper_limit']=None
    else:
        d['decimals']=int(d.get('decimals') or 0);d['unit_code']=(d.get('unit_code') or '').strip()
        for k in ['reference_value','lower_limit','upper_limit']:
            v=d.get(k);d[k]=None if v in ('',None) else float(v)
        if d.get('lower_limit') is not None and d.get('upper_limit') is not None and d['lower_limit']>d['upper_limit']:
            raise ValueError('O limite inferior não pode ser maior que o limite superior.')
    return d

def create_characteristic(pid,data):
    d=_char_payload(data);item_id=int(d['item_id'])
    c=get_conn()
    try:
        sort=d.get('sort_order')
        if sort is None: sort=c.execute('SELECT COALESCE(MAX(sort_order),0)+1 FROM control_characteristics WHERE item_id=?',(item_id,)).fetchone()[0]
        cur=c.execute('''INSERT INTO control_characteristics(project_id,item_id,sort_order,characteristic_type,description,method_code,decimals,unit_code,reference_value,lower_limit,upper_limit,status,source_template_id)
                         VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)''',(pid,item_id,sort,d['characteristic_type'],d['description'],d['method_code'],d.get('decimals'),d.get('unit_code',''),d.get('reference_value'),d.get('lower_limit'),d.get('upper_limit'),d.get('status','ACTIVE'),d.get('source_template_id')))
        c.commit();return get_characteristic(cur.lastrowid)
    finally:c.close()

def update_characteristic(cid,data):
    old=get_characteristic(cid) or {};d=_char_payload({**old,**data})
    c=get_conn();
    try:
        c.execute('''UPDATE control_characteristics SET item_id=?,sort_order=?,characteristic_type=?,description=?,method_code=?,decimals=?,unit_code=?,reference_value=?,lower_limit=?,upper_limit=?,status=?,updated_at=? WHERE id=?''',
                  (d['item_id'],d.get('sort_order',0),d['characteristic_type'],d['description'],d['method_code'],d.get('decimals'),d.get('unit_code',''),d.get('reference_value'),d.get('lower_limit'),d.get('upper_limit'),d.get('status','ACTIVE'),_now(),cid));c.commit();return get_characteristic(cid)
    finally:c.close()

def delete_characteristics(ids):
    c=get_conn();
    try:c.executemany('DELETE FROM control_characteristics WHERE id=?',[(int(x),) for x in ids]);c.commit()
    finally:c.close()

def bulk_update_characteristics(ids,updates):
    for cid in ids:update_characteristic(int(cid),updates)


def _hint_tokens(text):
    s=normalize_search(text)
    rules=[]
    if any(x in s for x in ['vibr','oscil']): rules += ['vibr','canetvib']
    if any(x in s for x in ['temper','aquec','termic','calor']): rules += ['term','piro','termogra']
    if any(x in s for x in ['corrente','amper']): rules += ['amper']
    if any(x in s for x in ['tensao','voltag','volt']): rules += ['volt','multim']
    if any(x in s for x in ['pressao','press']): rules += ['manom']
    if any(x in s for x in ['dimens','espess','diametro','folga']): rules += ['paquim','microm','calfolga']
    if any(x in s for x in ['visual','estado','fixacao','afroux','vazamento','trinca','protecao']): rules += ['visual']
    if any(x in s for x in ['tato','toque']): rules += ['tato']
    return rules

def search_methods(q='',hint='',limit=30):
    c=get_conn();
    try:data=rows(c.execute('SELECT code,description FROM inspection_methods').fetchall())
    finally:c.close()
    nq=normalize_search(q); hints=_hint_tokens(hint)
    def score(r):
        code=normalize_search(r['code']);desc=normalize_search(r['description']);sc=0
        if nq:
            if code==nq or desc==nq:sc+=100
            elif code.startswith(nq) or desc.startswith(nq):sc+=70
            elif nq in code or nq in desc:sc+=50
            else:return -999
        if r['code'] in ('VISUAL','TATO'):sc+=8
        for h in hints:
            if h in code or h in desc:sc+=40
        return sc
    ranked=[(score(r),r) for r in data];ranked=[x for x in ranked if x[0]>-999];ranked.sort(key=lambda x:(-x[0],x[1]['description']))
    return [r for _,r in ranked[:limit]]

def search_units(q='',hint='',limit=30):
    c=get_conn();
    try:data=rows(c.execute('SELECT code,description FROM measurement_units').fetchall())
    finally:c.close()
    nq=normalize_search(q);h=normalize_search(hint)
    preferred=[]
    if any(x in h for x in ['temper','termic','calor','aquec']):preferred=['°c','celsius']
    elif any(x in h for x in ['vibr','oscil']):preferred=['mm/s','gravidade','aceler']
    elif any(x in h for x in ['corrente','amper']):preferred=['ampere','a']
    elif any(x in h for x in ['tensao','voltag','volt']):preferred=['volt','v']
    elif any(x in h for x in ['pressao','press']):preferred=['bar','pascal','kgf/cm']
    elif any(x in h for x in ['dimens','espess','diametro','folga']):preferred=['milimetro','mm']
    def score(r):
        code=normalize_search(r['code']);desc=normalize_search(r['description']);sc=0
        if nq:
            if code==nq or desc==nq:sc+=100
            elif code.startswith(nq) or desc.startswith(nq):sc+=70
            elif nq in code or nq in desc:sc+=50
            else:return -999
        for p in preferred:
            p=normalize_search(p)
            if p==code:sc+=55
            elif p in desc or p in code:sc+=35
        return sc
    ranked=[(score(r),r) for r in data];ranked=[x for x in ranked if x[0]>-999];ranked.sort(key=lambda x:(-x[0],x[1]['description']))
    return [r for _,r in ranked[:limit]]


def dashboard(pid):
    c=get_conn()
    try:
        plan_count=c.execute("SELECT COUNT(*) FROM inspection_plans WHERE project_id=? AND status='ACTIVE'",(pid,)).fetchone()[0]
        item_count=c.execute("SELECT COUNT(*) FROM inspection_items WHERE project_id=? AND status='ACTIVE'",(pid,)).fetchone()[0]
        total_items=c.execute("SELECT COUNT(*) FROM inspection_items WHERE project_id=?",(pid,)).fetchone()[0]
        char_count=c.execute("SELECT COUNT(*) FROM control_characteristics WHERE project_id=? AND status='ACTIVE'",(pid,)).fetchone()[0]
        routes=c.execute("SELECT COUNT(DISTINCT route) FROM inspection_items WHERE project_id=? AND route<>''",(pid,)).fetchone()[0]
        total_min=c.execute("SELECT COALESCE(SUM(inspection_minutes),0) FROM inspection_items WHERE project_id=? AND status='ACTIVE'",(pid,)).fetchone()[0]
        missing_time=c.execute("SELECT COUNT(*) FROM inspection_items WHERE project_id=? AND (inspection_minutes IS NULL OR inspection_minutes<=0)",(pid,)).fetchone()[0]
        missing_route=c.execute("SELECT COUNT(*) FROM inspection_items WHERE project_id=? AND TRIM(route)=''",(pid,)).fetchone()[0]
        missing_chars=c.execute("SELECT COUNT(*) FROM inspection_items i WHERE i.project_id=? AND NOT EXISTS(SELECT 1 FROM control_characteristics c2 WHERE c2.item_id=i.id)",(pid,)).fetchone()[0]
        by_cycle=rows(c.execute("SELECT COALESCE(p.cycle_code,'SEM CICLO') label,COUNT(*) value FROM inspection_items i LEFT JOIN inspection_plans p ON p.id=i.plan_id WHERE i.project_id=? GROUP BY label ORDER BY value DESC",(pid,)).fetchall())
        by_type=rows(c.execute("SELECT characteristic_type label,COUNT(*) value FROM control_characteristics WHERE project_id=? GROUP BY characteristic_type",(pid,)).fetchall())
        top_methods=rows(c.execute("SELECT COALESCE(method_code,'SEM MÉTODO') label,COUNT(*) value FROM control_characteristics WHERE project_id=? GROUP BY label ORDER BY value DESC LIMIT 8",(pid,)).fetchall())
        quality=rows(c.execute("SELECT UPPER(COALESCE(validation_status,'OK')) label,COUNT(*) value FROM inspection_items WHERE project_id=? GROUP BY label",(pid,)).fetchall())
    finally:c.close()
    from . import balance
    schedule=balance.project_schedule(pid,days=30)
    balance_metrics=balance.metrics(schedule)
    return {'plans':plan_count,'items':item_count,'total_items':total_items,'inactive_items':max(0,total_items-item_count),'characteristics':char_count,'routes':routes,'total_minutes':float(total_min or 0),'issues':{'missing_time':missing_time,'missing_route':missing_route,'missing_characteristics':missing_chars},'by_cycle':by_cycle,'by_type':by_type,'top_methods':top_methods,'quality':quality,'balance_metrics':balance_metrics,'daily_load':[{'date':x['date'],'minutes':x['minutes'],'count':x['count']} for x in schedule]}


def clone_item(pid,item_id,include_characteristics=True):
    c=get_conn()
    try:
        src=c.execute('SELECT * FROM inspection_items WHERE id=? AND project_id=?',(item_id,pid)).fetchone()
        if not src: raise ValueError('Item não encontrado.')
        ident=int(c.execute('SELECT COALESCE(MAX(legacy_identifier),0)+1 FROM inspection_items WHERE project_id=?',(pid,)).fetchone()[0])
        cur=c.execute('''INSERT INTO inspection_items(project_id,plan_id,legacy_identifier,equipment_code,gpm,work_center,condition_code,priority,route,description,char_count,inspection_minutes,criticality,status,balance_offset_days)
                         VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',(pid,src['plan_id'],ident,src['equipment_code'],src['gpm'],src['work_center'],src['condition_code'],src['priority'],src['route'],src['description'],src['char_count'],src['inspection_minutes'],src['criticality'],src['status'],src['balance_offset_days']))
        new_id=cur.lastrowid;count=0
        if include_characteristics:
            for ch in c.execute('SELECT * FROM control_characteristics WHERE item_id=? ORDER BY sort_order,id',(item_id,)).fetchall():
                c.execute('''INSERT INTO control_characteristics(project_id,item_id,sort_order,characteristic_type,description,method_code,decimals,unit_code,reference_value,lower_limit,upper_limit,status,source_template_id)
                             VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)''',(pid,new_id,ch['sort_order'],ch['characteristic_type'],ch['description'],ch['method_code'],ch['decimals'],ch['unit_code'],ch['reference_value'],ch['lower_limit'],ch['upper_limit'],ch['status'],ch['source_template_id']));count+=1
        c.commit();return {'item':get_item(new_id),'characteristics_cloned':count}
    except Exception:c.rollback();raise
    finally:c.close()

def delete_char_template(tid):
    c=get_conn()
    try:c.execute('DELETE FROM characteristic_templates WHERE id=?',(tid,));c.commit()
    finally:c.close()

def delete_equipment_template(tid):
    c=get_conn()
    try:c.execute('DELETE FROM equipment_templates WHERE id=?',(tid,));c.commit()
    finally:c.close()

def list_char_templates(pid):
    c=get_conn()
    try:return rows(c.execute('''SELECT t.*,(SELECT COUNT(*) FROM characteristic_template_rows r WHERE r.template_id=t.id) row_count
        FROM characteristic_templates t WHERE t.scope='GLOBAL' OR t.project_id=? ORDER BY t.category,t.name''',(pid,)).fetchall())
    finally:c.close()

def get_char_template(tid):
    c=get_conn()
    try:
        t=row(c.execute('SELECT * FROM characteristic_templates WHERE id=?',(tid,)).fetchone())
        if t:t['rows']=rows(c.execute('SELECT * FROM characteristic_template_rows WHERE template_id=? ORDER BY sort_order,id',(tid,)).fetchall())
        return t
    finally:c.close()

def save_char_template_from_item(pid,item_id,name,category='',description='',scope='PROJECT'):
    c=get_conn()
    try:
        src=c.execute('SELECT * FROM control_characteristics WHERE item_id=? ORDER BY sort_order,id',(item_id,)).fetchall()
        if not src:raise ValueError('O item não possui Características de Controle para salvar como padrão.')
        project_id=None if scope=='GLOBAL' else pid
        cur=c.execute('INSERT INTO characteristic_templates(project_id,name,category,description,scope) VALUES(?,?,?,?,?)',(project_id,name,category,description,scope));tid=cur.lastrowid
        for r in src:
            c.execute('''INSERT INTO characteristic_template_rows(template_id,sort_order,characteristic_type,description,method_code,decimals,unit_code,reference_value,lower_limit,upper_limit,status)
                         VALUES(?,?,?,?,?,?,?,?,?,?,?)''',(tid,r['sort_order'],r['characteristic_type'],r['description'],r['method_code'],r['decimals'],r['unit_code'],r['reference_value'],r['lower_limit'],r['upper_limit'],r['status']))
        c.commit();return get_char_template(tid)
    finally:c.close()

def apply_char_template(pid,tid,item_ids,policy='IGNORE'):
    t=get_char_template(tid)
    if not t:raise ValueError('Padrão não encontrado.')
    c=get_conn();stats={'items':0,'created':0,'skipped':0,'replaced':0}
    try:
        for item_id in item_ids:
            existing=c.execute('SELECT COUNT(*) FROM control_characteristics WHERE item_id=?',(item_id,)).fetchone()[0]
            if existing and policy=='IGNORE':stats['skipped']+=1;continue
            if existing and policy=='REPLACE':c.execute('DELETE FROM control_characteristics WHERE item_id=?',(item_id,));stats['replaced']+=1
            for r in t['rows']:
                c.execute('''INSERT INTO control_characteristics(project_id,item_id,sort_order,characteristic_type,description,method_code,decimals,unit_code,reference_value,lower_limit,upper_limit,status,source_template_id)
                             VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)''',(pid,item_id,r['sort_order'],r['characteristic_type'],r['description'],r['method_code'],r['decimals'],r['unit_code'],r['reference_value'],r['lower_limit'],r['upper_limit'],r['status'],tid));stats['created']+=1
            stats['items']+=1
        c.commit();return stats
    except Exception:c.rollback();raise
    finally:c.close()


def list_equipment_templates(pid):
    c=get_conn()
    try:return rows(c.execute('''SELECT t.*,(SELECT COUNT(*) FROM equipment_template_items x WHERE x.template_id=t.id) item_count,
        (SELECT COUNT(*) FROM equipment_template_characteristics c2 JOIN equipment_template_items ti ON ti.id=c2.template_item_id WHERE ti.template_id=t.id) characteristic_count
        FROM equipment_templates t WHERE t.scope='GLOBAL' OR t.project_id=? ORDER BY t.category,t.name''',(pid,)).fetchall())
    finally:c.close()

def get_equipment_template(tid):
    c=get_conn()
    try:
        t=row(c.execute('SELECT * FROM equipment_templates WHERE id=?',(tid,)).fetchone())
        if not t:return None
        its=rows(c.execute('SELECT * FROM equipment_template_items WHERE template_id=? ORDER BY sort_order,id',(tid,)).fetchall())
        for it in its:it['characteristics']=rows(c.execute('SELECT * FROM equipment_template_characteristics WHERE template_item_id=? ORDER BY sort_order,id',(it['id'],)).fetchall())
        t['items']=its;return t
    finally:c.close()

def save_equipment_template(pid,equipment_code,name,category='',description='',scope='PROJECT'):
    c=get_conn()
    try:
        src=c.execute('''SELECT i.*,p.code plan_code FROM inspection_items i LEFT JOIN inspection_plans p ON p.id=i.plan_id WHERE i.project_id=? AND i.equipment_code=? ORDER BY CAST(i.route AS INTEGER),i.legacy_identifier''',(pid,equipment_code)).fetchall()
        if not src:raise ValueError('Nenhum Item encontrado para esse Equipamento.')
        project_id=None if scope=='GLOBAL' else pid;total=sum(float(r['inspection_minutes'] or 0) for r in src)
        cur=c.execute('INSERT INTO equipment_templates(project_id,name,category,description,scope,total_minutes) VALUES(?,?,?,?,?,?)',(project_id,name,category,description,scope,total));tid=cur.lastrowid
        for idx,r in enumerate(src,1):
            ti=c.execute('''INSERT INTO equipment_template_items(template_id,sort_order,plan_code,gpm,work_center,condition_code,priority,route_relative,original_route,description,inspection_minutes,criticality,status)
                            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)''',(tid,idx,r['plan_code'] or '',r['gpm'],r['work_center'],r['condition_code'],r['priority'],idx,r['route'],r['description'],r['inspection_minutes'],r['criticality'],r['status'])).lastrowid
            chars=c.execute('SELECT * FROM control_characteristics WHERE item_id=? ORDER BY sort_order,id',(r['id'],)).fetchall()
            for ch in chars:
                c.execute('''INSERT INTO equipment_template_characteristics(template_item_id,sort_order,characteristic_type,description,method_code,decimals,unit_code,reference_value,lower_limit,upper_limit,status)
                             VALUES(?,?,?,?,?,?,?,?,?,?,?)''',(ti,ch['sort_order'],ch['characteristic_type'],ch['description'],ch['method_code'],ch['decimals'],ch['unit_code'],ch['reference_value'],ch['lower_limit'],ch['upper_limit'],ch['status']))
        c.commit();return get_equipment_template(tid)
    except Exception:c.rollback();raise
    finally:c.close()

def apply_equipment_template(pid,tid,equipment_code,route_start=None,gpm_override=None,work_center_override=None,plan_id_override=None):
    t=get_equipment_template(tid)
    if not t:raise ValueError('Padrão de Equipamento não encontrado.')
    c=get_conn();created=[]
    try:
        missing=[]
        if plan_id_override:
            if not c.execute('SELECT 1 FROM inspection_plans WHERE project_id=? AND id=?',(pid,int(plan_id_override))).fetchone():
                raise ValueError('Plano destino não encontrado neste projeto.')
        else:
            for ti in t['items']:
                if ti['plan_code'] and not c.execute('SELECT 1 FROM inspection_plans WHERE project_id=? AND code=?',(pid,ti['plan_code'])).fetchone():missing.append(ti['plan_code'])
            if missing:raise ValueError('Planos não encontrados no projeto destino: '+', '.join(sorted(set(missing))))
        ident=int(c.execute('SELECT COALESCE(MAX(legacy_identifier),0)+1 FROM inspection_items WHERE project_id=?',(pid,)).fetchone()[0])
        start_num=int(route_start) if route_start not in (None,'') and str(route_start).isdigit() else None
        for idx,ti in enumerate(t['items']):
            plan_id=int(plan_id_override) if plan_id_override else None
            if not plan_id and ti['plan_code']:plan_id=c.execute('SELECT id FROM inspection_plans WHERE project_id=? AND code=?',(pid,ti['plan_code'])).fetchone()[0]
            route=(str(start_num+idx).zfill(4) if start_num is not None else ti['original_route'])
            cur=c.execute('''INSERT INTO inspection_items(project_id,plan_id,legacy_identifier,equipment_code,gpm,work_center,condition_code,priority,route,description,char_count,inspection_minutes,criticality,status)
                             VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',(pid,plan_id,ident,equipment_code,gpm_override if gpm_override is not None else ti['gpm'],work_center_override if work_center_override is not None else ti['work_center'],ti['condition_code'],ti['priority'],route,ti['description'],len(ti['description']),ti['inspection_minutes'],ti['criticality'],ti['status']))
            item_id=cur.lastrowid
            for ch in ti['characteristics']:
                c.execute('''INSERT INTO control_characteristics(project_id,item_id,sort_order,characteristic_type,description,method_code,decimals,unit_code,reference_value,lower_limit,upper_limit,status)
                             VALUES(?,?,?,?,?,?,?,?,?,?,?,?)''',(pid,item_id,ch['sort_order'],ch['characteristic_type'],ch['description'],ch['method_code'],ch['decimals'],ch['unit_code'],ch['reference_value'],ch['lower_limit'],ch['upper_limit'],ch['status']))
            created.append({'item_id':item_id,'legacy_identifier':ident});ident+=1
        c.commit();return {'items_created':len(created),'characteristics_created':sum(len(x['characteristics']) for x in t['items']),'items':created}
    except Exception:c.rollback();raise
    finally:c.close()

# ========================= PM11 V3 PROFESSIONAL EXTENSIONS =========================
def project_is_locked(pid):
    c=get_conn()
    try:
        r=c.execute('SELECT COALESCE(locked,0) FROM projects WHERE id=?',(pid,)).fetchone()
        return bool(r and r[0])
    finally:c.close()

def set_project_lock(pid,locked=True):
    c=get_conn()
    try:
        c.execute('UPDATE projects SET locked=?,updated_at=? WHERE id=?',(1 if locked else 0,_now(),pid));c.commit()
    finally:c.close()
    return get_project(pid)

def update_project(pid,data):
    allowed=['name','area','system_name','description','status','default_center_code','default_process_code','default_type_code','balance_anchor_date','daily_inspection_target_minutes']
    if data.get('balance_anchor_date'):
        try: anchor = datetime.date.fromisoformat(str(data['balance_anchor_date']))
        except ValueError: raise ValueError('Data de Início da Programação inválida.')
        if anchor.weekday() != 0:
            raise ValueError('A Data de Início da Programação deve ser uma segunda-feira.')
    sets=[];vals=[]
    for k in allowed:
        if k in data:sets.append(f'{k}=?');vals.append(data[k])
    if sets:
        vals += [_now(),pid];c=get_conn()
        try:c.execute(f"UPDATE projects SET {','.join(sets)},updated_at=? WHERE id=?",vals);c.commit()
        finally:c.close()
    return get_project(pid)

def duplicate_project(pid,new_name=None):
    src=get_project(pid)
    if not src:raise ValueError('Projeto não encontrado.')
    c=get_conn()
    try:
        c.execute('BEGIN')
        cur=c.execute('''INSERT INTO projects(name,area,system_name,description,status,default_center_code,default_process_code,default_type_code,balance_anchor_date,locked,daily_inspection_target_minutes)
                         VALUES(?,?,?,?,?,?,?,?,?,?,?)''',(new_name or (src['name']+' - CÓPIA'),src.get('area',''),src.get('system_name',''),src.get('description',''),src.get('status','ACTIVE'),src.get('default_center_code','U'),src.get('default_process_code','R'),src.get('default_type_code','I'),src.get('balance_anchor_date'),0,src.get('daily_inspection_target_minutes',240)))
        npid=cur.lastrowid;plan_map={};item_map={}
        for p in c.execute('SELECT * FROM inspection_plans WHERE project_id=? ORDER BY id',(pid,)).fetchall():
            cols=['code','description','char_count','center_code','process_code','type_code','line_code','subarea_code','suffix','cycle_code','cycle_value','unit','text_cycle','horizon','offset_days','status','row_color']
            vals=[p[k] if k in p.keys() else '' for k in cols]
            nid=c.execute(f"INSERT INTO inspection_plans(project_id,{','.join(cols)}) VALUES(? ,{','.join('?' for _ in cols)})",[npid]+vals).lastrowid;plan_map[p['id']]=nid
        for i in c.execute('SELECT * FROM inspection_items WHERE project_id=? ORDER BY id',(pid,)).fetchall():
            cols=['legacy_identifier','equipment_code','gpm','work_center','condition_code','priority','route','description','char_count','inspection_minutes','criticality','status','balance_offset_days','row_color']
            vals=[i[k] if k in i.keys() else '' for k in cols]
            nid=c.execute(f"INSERT INTO inspection_items(project_id,plan_id,{','.join(cols)}) VALUES(?,?,{','.join('?' for _ in cols)})",[npid,plan_map.get(i['plan_id'])]+vals).lastrowid;item_map[i['id']]=nid
        for ch in c.execute('SELECT * FROM control_characteristics WHERE project_id=? ORDER BY id',(pid,)).fetchall():
            cols=['sort_order','characteristic_type','description','method_code','decimals','unit_code','reference_value','lower_limit','upper_limit','status','source_template_id','row_color']
            vals=[ch[k] if k in ch.keys() else '' for k in cols]
            c.execute(f"INSERT INTO control_characteristics(project_id,item_id,{','.join(cols)}) VALUES(?,?,{','.join('?' for _ in cols)})",[npid,item_map[ch['item_id']]]+vals)
        c.commit();return get_project(npid)
    except Exception:c.rollback();raise
    finally:c.close()

def list_plans(pid,search='',status='',cycle_code='',row_color=''):
    c=get_conn()
    try:
        where=['project_id=?'];args=[pid]
        if search:s='%'+normalize_search(search)+'%';where.append('(SEARCH_NORMALIZE(code) LIKE ? OR SEARCH_NORMALIZE(description) LIKE ?)');args += [s,s]
        if status:where.append('status=?');args.append(status)
        if cycle_code:where.append('cycle_code=?');args.append(cycle_code)
        if row_color:where.append("COALESCE(row_color,'')=?");args.append(row_color)
        return _decorate_plans(pid, rows(c.execute(f"SELECT * FROM inspection_plans WHERE {' AND '.join(where)} ORDER BY code",args).fetchall()))
    finally:c.close()

def clone_plan(pid,plan_id,include_children=False,new_code=None,new_description=None):
    src=get_plan(plan_id)
    if not src or src['project_id']!=pid:raise ValueError('Plano não encontrado.')
    d=dict(src);d.pop('id',None);d['code']=new_code or '';d['description']=new_description or (src['description']+' - CÓPIA')
    # generate next available suffix if code not explicit
    if not new_code:
        base=(src['code'][:9] if len(src['code'])>=9 else src['code'])
        c=get_conn()
        try:
            n=1
            while True:
                suffix=f'{n:03d}'[-3:];candidate=(base+suffix)[:12]
                if not c.execute('SELECT 1 FROM inspection_plans WHERE project_id=? AND code=?',(pid,candidate)).fetchone():break
                n+=1
        finally:c.close()
        d.update({'suffix':suffix,'code':candidate})
    p=create_plan(pid,d)
    if not include_children:return {'plan':p,'items_cloned':0,'characteristics_cloned':0}
    c=get_conn();items_n=chars_n=0
    try:
        c.execute('BEGIN')
        old_items=c.execute('SELECT * FROM inspection_items WHERE project_id=? AND plan_id=? ORDER BY legacy_identifier',(pid,plan_id)).fetchall()
        ident=int(c.execute('SELECT COALESCE(MAX(legacy_identifier),0)+1 FROM inspection_items WHERE project_id=?',(pid,)).fetchone()[0])
        for it in old_items:
            ni=c.execute('''INSERT INTO inspection_items(project_id,plan_id,legacy_identifier,equipment_code,gpm,work_center,condition_code,priority,route,description,char_count,inspection_minutes,criticality,status,balance_offset_days,row_color)
                            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',(pid,p['id'],ident,it['equipment_code'],it['gpm'],it['work_center'],it['condition_code'],it['priority'],it['route'],it['description'],it['char_count'],it['inspection_minutes'],it['criticality'],it['status'],it['balance_offset_days'],it['row_color'] if 'row_color' in it.keys() else '')).lastrowid
            for ch in c.execute('SELECT * FROM control_characteristics WHERE item_id=? ORDER BY sort_order,id',(it['id'],)).fetchall():
                c.execute('''INSERT INTO control_characteristics(project_id,item_id,sort_order,characteristic_type,description,method_code,decimals,unit_code,reference_value,lower_limit,upper_limit,status,source_template_id,row_color)
                             VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',(pid,ni,ch['sort_order'],ch['characteristic_type'],ch['description'],ch['method_code'],ch['decimals'],ch['unit_code'],ch['reference_value'],ch['lower_limit'],ch['upper_limit'],ch['status'],ch['source_template_id'],ch['row_color'] if 'row_color' in ch.keys() else ''));chars_n+=1
            ident+=1;items_n+=1
        c.commit();return {'plan':p,'items_cloned':items_n,'characteristics_cloned':chars_n}
    except Exception:c.rollback();raise
    finally:c.close()

def bulk_update_plans(ids,updates):
    allowed={'cycle_code','status','offset_days','row_color'};upd={k:v for k,v in updates.items() if k in allowed}
    if not upd:return {'updated':0}
    if 'cycle_code' in upd:
        c=get_conn();cy=c.execute('SELECT * FROM cycle_catalog WHERE code=?',(upd['cycle_code'],)).fetchone();c.close()
        if cy:upd.update({'cycle_value':cy['cycle_value'],'unit':cy['unit'],'text_cycle':cy['text_cycle'],'horizon':cy['horizon']})
    sets=','.join(f'{k}=?' for k in upd);vals=list(upd.values());c=get_conn()
    try:
        for i in ids:c.execute(f'UPDATE inspection_plans SET {sets},updated_at=? WHERE id=?',vals+[_now(),int(i)])
        c.commit();return {'updated':len(ids)}
    finally:c.close()

def list_filter_options(pid):
    c=get_conn()
    try:
        return {'gpms':[r[0] for r in c.execute("SELECT DISTINCT gpm FROM inspection_items WHERE project_id=? AND TRIM(gpm)<>'' ORDER BY gpm",(pid,)).fetchall()],
                'work_centers':[r[0] for r in c.execute("SELECT DISTINCT work_center FROM inspection_items WHERE project_id=? AND TRIM(work_center)<>'' ORDER BY work_center",(pid,)).fetchall()]}
    finally:c.close()

def list_items(pid,search='',plan_id=None,status='',equipment='',route='',gpm='',work_center='',condition='',priority='',row_color=''):
    c=get_conn()
    try:
        where=['i.project_id=?'];args=[pid]
        if search:s='%'+normalize_search(search)+'%';where.append('(SEARCH_NORMALIZE(i.description) LIKE ? OR SEARCH_NORMALIZE(i.equipment_code) LIKE ? OR CAST(i.legacy_identifier AS TEXT) LIKE ?)');args += [s,s,'%'+str(search)+'%']
        if plan_id:where.append('i.plan_id=?');args.append(plan_id)
        if status:where.append('i.status=?');args.append(status)
        if equipment:where.append('SEARCH_NORMALIZE(i.equipment_code) LIKE ?');args.append('%'+normalize_search(equipment)+'%')
        if route:where.append('i.route LIKE ?');args.append('%'+route+'%')
        if gpm:where.append('i.gpm=?');args.append(gpm)
        if work_center:where.append('i.work_center=?');args.append(work_center)
        if condition:where.append('i.condition_code=?');args.append(condition)
        if priority not in ('',None):where.append('i.priority=?');args.append(int(priority))
        if row_color:where.append("COALESCE(i.row_color,'')=?");args.append(row_color)
        q=f'''SELECT i.*,p.code plan_code,p.description plan_description,p.cycle_code,p.cycle_value,p.unit,p.text_cycle,p.horizon,
              (SELECT COUNT(*) FROM control_characteristics c2 WHERE c2.item_id=i.id) characteristic_count
              FROM inspection_items i LEFT JOIN inspection_plans p ON p.id=i.plan_id WHERE {' AND '.join(where)} ORDER BY i.legacy_identifier'''
        return rows(c.execute(q,args).fetchall())
    finally:c.close()

def bulk_update_items(ids,updates):
    allowed={'plan_id','equipment_code','gpm','work_center','condition_code','priority','route','inspection_minutes','criticality','status','row_color'}
    upd={k:v for k,v in updates.items() if k in allowed}
    for iid in ids:update_item(int(iid),upd)
    return {'updated':len(ids)}

def list_characteristics(pid,search='',item_id=None,type_='',method='',status='',row_color=''):
    c=get_conn()
    try:
        where=['ch.project_id=?'];args=[pid]
        if search:s='%'+normalize_search(search)+'%';where.append('(SEARCH_NORMALIZE(ch.description) LIKE ? OR SEARCH_NORMALIZE(i.description) LIKE ?)');args += [s,s]
        if item_id:where.append('ch.item_id=?');args.append(item_id)
        if type_:where.append('ch.characteristic_type=?');args.append(type_)
        if method:where.append('ch.method_code=?');args.append(method)
        if status:where.append('ch.status=?');args.append(status)
        if row_color:where.append("COALESCE(ch.row_color,'')=?");args.append(row_color)
        q=f'''SELECT ch.*,i.legacy_identifier,i.description item_description,i.equipment_code,i.plan_id,p.code plan_code
              FROM control_characteristics ch JOIN inspection_items i ON i.id=ch.item_id LEFT JOIN inspection_plans p ON p.id=i.plan_id
              WHERE {' AND '.join(where)} ORDER BY i.legacy_identifier,ch.sort_order,ch.id'''
        return rows(c.execute(q,args).fetchall())
    finally:c.close()

def bulk_update_characteristics(ids,updates):
    allowed={'item_id','characteristic_type','description','method_code','decimals','unit_code','reference_value','lower_limit','upper_limit','status','row_color'}
    upd={k:v for k,v in updates.items() if k in allowed}
    for cid in ids:update_characteristic(int(cid),upd)
    return {'updated':len(ids)}

# Item templates: item + all control characteristics.
def list_item_templates(pid):
    c=get_conn()
    try:return rows(c.execute('''SELECT t.*,(SELECT COUNT(*) FROM item_template_characteristics c2 WHERE c2.template_id=t.id) characteristic_count
        FROM item_templates t WHERE t.scope='GLOBAL' OR t.project_id=? ORDER BY t.category,t.name''',(pid,)).fetchall())
    finally:c.close()

def get_item_template(tid):
    c=get_conn()
    try:
        t=row(c.execute('SELECT * FROM item_templates WHERE id=?',(tid,)).fetchone())
        if t:t['characteristics']=rows(c.execute('SELECT * FROM item_template_characteristics WHERE template_id=? ORDER BY sort_order,id',(tid,)).fetchall())
        return t
    finally:c.close()

def save_item_template_from_item(pid,item_id,name,category='',description='',scope='PROJECT'):
    item=get_item(item_id)
    if not item:raise ValueError('Item não encontrado.')
    c=get_conn()
    try:
        project_id=None if scope=='GLOBAL' else pid
        tid=c.execute('''INSERT INTO item_templates(project_id,name,category,description,scope,status,condition_code,priority,route,item_description,inspection_minutes,criticality)
                         VALUES(?,?,?,?,?,?,?,?,?,?,?,?)''',(project_id,name,category,description,scope,'ACTIVE',item['condition_code'],item['priority'],item['route'],item['description'],item['inspection_minutes'],item['criticality'])).lastrowid
        for ch in c.execute('SELECT * FROM control_characteristics WHERE item_id=? ORDER BY sort_order,id',(item_id,)).fetchall():
            c.execute('''INSERT INTO item_template_characteristics(template_id,sort_order,characteristic_type,description,method_code,decimals,unit_code,reference_value,lower_limit,upper_limit,status)
                         VALUES(?,?,?,?,?,?,?,?,?,?,?)''',(tid,ch['sort_order'],ch['characteristic_type'],ch['description'],ch['method_code'],ch['decimals'],ch['unit_code'],ch['reference_value'],ch['lower_limit'],ch['upper_limit'],ch['status']))
        c.commit();return get_item_template(tid)
    except Exception:c.rollback();raise
    finally:c.close()

def apply_item_template(pid,tid,plan_id,equipment_code='',route='',gpm='',work_center=''):
    t=get_item_template(tid)
    if not t:raise ValueError('Modelo de Item não encontrado.')
    item=create_item(pid,{'plan_id':plan_id,'equipment_code':equipment_code,'gpm':gpm,'work_center':work_center,'condition_code':t['condition_code'],'priority':t['priority'],'route':route or t['route'],'description':t['item_description'],'inspection_minutes':t['inspection_minutes'],'criticality':t['criticality'],'status':t['status']})
    c=get_conn();n=0
    try:
        for ch in t['characteristics']:
            c.execute('''INSERT INTO control_characteristics(project_id,item_id,sort_order,characteristic_type,description,method_code,decimals,unit_code,reference_value,lower_limit,upper_limit,status)
                         VALUES(?,?,?,?,?,?,?,?,?,?,?,?)''',(pid,item['id'],ch['sort_order'],ch['characteristic_type'],ch['description'],ch['method_code'],ch['decimals'],ch['unit_code'],ch['reference_value'],ch['lower_limit'],ch['upper_limit'],ch['status']));n+=1
        c.commit();return {'item':item,'characteristics_created':n}
    except Exception:c.rollback();raise
    finally:c.close()

def delete_item_template(tid):
    c=get_conn()
    try:c.execute('DELETE FROM item_templates WHERE id=?',(tid,));c.commit()
    finally:c.close()

def save_plan_as_package_template(pid,plan_id,name,category='',description='',scope='PROJECT'):
    p=get_plan(plan_id)
    if not p:raise ValueError('Plano não encontrado.')
    # Reuse equipment-package engine, but capture all items of the plan regardless of equipment.
    c=get_conn()
    try:
        its=c.execute('SELECT * FROM inspection_items WHERE project_id=? AND plan_id=? ORDER BY legacy_identifier',(pid,plan_id)).fetchall()
        if not its:raise ValueError('O Plano não possui Itens para salvar como modelo.')
        project_id=None if scope=='GLOBAL' else pid;total=sum(float(i['inspection_minutes'] or 0) for i in its)
        tid=c.execute('INSERT INTO equipment_templates(project_id,name,category,description,scope,total_minutes) VALUES(?,?,?,?,?,?)',(project_id,name,category,description,scope,total)).lastrowid
        for idx,i in enumerate(its,1):
            ti=c.execute('''INSERT INTO equipment_template_items(template_id,sort_order,plan_code,gpm,work_center,condition_code,priority,route_relative,original_route,description,inspection_minutes,criticality,status)
                            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)''',(tid,idx,p['code'],i['gpm'],i['work_center'],i['condition_code'],i['priority'],idx,i['route'],i['description'],i['inspection_minutes'],i['criticality'],i['status'])).lastrowid
            for ch in c.execute('SELECT * FROM control_characteristics WHERE item_id=? ORDER BY sort_order,id',(i['id'],)).fetchall():
                c.execute('''INSERT INTO equipment_template_characteristics(template_item_id,sort_order,characteristic_type,description,method_code,decimals,unit_code,reference_value,lower_limit,upper_limit,status)
                             VALUES(?,?,?,?,?,?,?,?,?,?,?)''',(ti,ch['sort_order'],ch['characteristic_type'],ch['description'],ch['method_code'],ch['decimals'],ch['unit_code'],ch['reference_value'],ch['lower_limit'],ch['upper_limit'],ch['status']))
        c.commit();return get_equipment_template(tid)
    except Exception:c.rollback();raise
    finally:c.close()

def update_template_meta(kind,tid,updates):
    table={'characteristics':'characteristic_templates','items':'item_templates','equipment':'equipment_templates'}[kind]
    allowed={'name','category','description','status','row_color'};u={k:v for k,v in updates.items() if k in allowed}
    if not u:return {'ok':True}
    c=get_conn()
    try:c.execute(f"UPDATE {table} SET {','.join(k+'=?' for k in u)},updated_at=? WHERE id=?",list(u.values())+[_now(),tid]);c.commit()
    finally:c.close()
    return {'ok':True}

def duplicate_template(kind,tid,name=None):
    if kind=='characteristics':
        t=get_char_template(tid);c=get_conn()
        try:
            nid=c.execute('INSERT INTO characteristic_templates(project_id,name,category,description,scope,status,row_color) VALUES(?,?,?,?,?,?,?)',(t['project_id'],name or t['name']+' - CÓPIA',t['category'],t['description'],t['scope'],t['status'],t.get('row_color',''))).lastrowid
            for r in t['rows']:c.execute('''INSERT INTO characteristic_template_rows(template_id,sort_order,characteristic_type,description,method_code,decimals,unit_code,reference_value,lower_limit,upper_limit,status) VALUES(?,?,?,?,?,?,?,?,?,?,?)''',(nid,r['sort_order'],r['characteristic_type'],r['description'],r['method_code'],r['decimals'],r['unit_code'],r['reference_value'],r['lower_limit'],r['upper_limit'],r['status']))
            c.commit();return get_char_template(nid)
        finally:c.close()
    if kind=='items':
        t=get_item_template(tid);c=get_conn()
        try:
            nid=c.execute('''INSERT INTO item_templates(project_id,name,category,description,scope,status,row_color,condition_code,priority,route,item_description,inspection_minutes,criticality) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)''',(t['project_id'],name or t['name']+' - CÓPIA',t['category'],t['description'],t['scope'],t['status'],t.get('row_color',''),t['condition_code'],t['priority'],t['route'],t['item_description'],t['inspection_minutes'],t['criticality'])).lastrowid
            for r in t['characteristics']:c.execute('''INSERT INTO item_template_characteristics(template_id,sort_order,characteristic_type,description,method_code,decimals,unit_code,reference_value,lower_limit,upper_limit,status) VALUES(?,?,?,?,?,?,?,?,?,?,?)''',(nid,r['sort_order'],r['characteristic_type'],r['description'],r['method_code'],r['decimals'],r['unit_code'],r['reference_value'],r['lower_limit'],r['upper_limit'],r['status']))
            c.commit();return get_item_template(nid)
        finally:c.close()
    if kind=='equipment':
        t=get_equipment_template(tid);c=get_conn()
        try:
            nid=c.execute('INSERT INTO equipment_templates(project_id,name,category,description,scope,status,total_minutes,row_color) VALUES(?,?,?,?,?,?,?,?)',(t['project_id'],name or t['name']+' - CÓPIA',t['category'],t['description'],t['scope'],t['status'],t['total_minutes'],t.get('row_color',''))).lastrowid
            for it in t['items']:
                ni=c.execute('''INSERT INTO equipment_template_items(template_id,sort_order,plan_code,gpm,work_center,condition_code,priority,route_relative,original_route,description,inspection_minutes,criticality,status) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)''',(nid,it['sort_order'],it['plan_code'],it['gpm'],it['work_center'],it['condition_code'],it['priority'],it['route_relative'],it['original_route'],it['description'],it['inspection_minutes'],it['criticality'],it['status'])).lastrowid
                for ch in it['characteristics']:c.execute('''INSERT INTO equipment_template_characteristics(template_item_id,sort_order,characteristic_type,description,method_code,decimals,unit_code,reference_value,lower_limit,upper_limit,status) VALUES(?,?,?,?,?,?,?,?,?,?,?)''',(ni,ch['sort_order'],ch['characteristic_type'],ch['description'],ch['method_code'],ch['decimals'],ch['unit_code'],ch['reference_value'],ch['lower_limit'],ch['upper_limit'],ch['status']))
            c.commit();return get_equipment_template(nid)
        finally:c.close()
    raise ValueError('Tipo de modelo inválido.')

def _item_payload(data):
    d=dict(data);d['description']=(d.get('description') or '').strip();d['char_count']=len(d['description'])
    if len(d['description'])>35:raise ValueError('A descrição do Item não pode ultrapassar 35 caracteres.')
    d['route']=str(d.get('route') or '').strip().zfill(4) if str(d.get('route') or '').strip() else ''
    d['condition_code']=(d.get('condition_code') or 'Q').upper()
    if d['condition_code'] not in ('Q','P','M','F'):raise ValueError('Condição inválida. Use Q, P, M ou F.')
    d['priority']=int(d.get('priority') or 0);d['inspection_minutes']=float(d.get('inspection_minutes') or 0)
    d['status']=d.get('status') or 'ACTIVE';d['row_color']=d.get('row_color') or ''
    return d

def create_item(pid,data):
    d=_item_payload(data);ident=int(d.get('legacy_identifier') or next_identifier(pid));c=get_conn()
    try:
        cur=c.execute('''INSERT INTO inspection_items(project_id,plan_id,legacy_identifier,equipment_code,gpm,work_center,condition_code,priority,route,description,char_count,inspection_minutes,criticality,status,balance_offset_days,row_color)
                         VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',(pid,d.get('plan_id') or None,ident,d.get('equipment_code',''),d.get('gpm',''),d.get('work_center',''),d['condition_code'],d['priority'],d['route'],d['description'],d['char_count'],d['inspection_minutes'],d.get('criticality',''),d['status'],int(d.get('balance_offset_days') or 0),d['row_color']))
        c.commit();return get_item(cur.lastrowid)
    except Exception:c.rollback();raise
    finally:c.close()

def update_item(item_id,data):
    old=get_item(item_id) or {};d=_item_payload({**old,**data});c=get_conn()
    try:
        c.execute('''UPDATE inspection_items SET plan_id=?,equipment_code=?,gpm=?,work_center=?,condition_code=?,priority=?,route=?,description=?,char_count=?,inspection_minutes=?,criticality=?,status=?,balance_offset_days=?,row_color=?,updated_at=? WHERE id=?''',(d.get('plan_id') or None,d.get('equipment_code',''),d.get('gpm',''),d.get('work_center',''),d['condition_code'],d['priority'],d['route'],d['description'],d['char_count'],d['inspection_minutes'],d.get('criticality',''),d['status'],int(d.get('balance_offset_days') or 0),d['row_color'],_now(),item_id));c.commit();return get_item(item_id)
    except Exception:c.rollback();raise
    finally:c.close()

def _char_payload(data):
    d=dict(data);typ=(d.get('characteristic_type') or 'QUALITAT').upper();d['characteristic_type']='QUANTITA' if typ.startswith('QUANT') else 'QUALITAT'
    d['description']=(d.get('description') or '').strip();d['method_code']=(d.get('method_code') or '').strip();d['status']=d.get('status') or 'ACTIVE';d['row_color']=d.get('row_color') or ''
    if d['characteristic_type']=='QUALITAT':d['decimals']=None;d['unit_code']='';d['reference_value']=None;d['lower_limit']=None;d['upper_limit']=None
    else:
        d['decimals']=int(d.get('decimals') or 0);d['unit_code']=(d.get('unit_code') or '').strip()
        for k in ['reference_value','lower_limit','upper_limit']:
            v=d.get(k);d[k]=None if v in ('',None) else float(v)
        if d.get('lower_limit') is not None and d.get('upper_limit') is not None and d['lower_limit']>d['upper_limit']:raise ValueError('O limite inferior não pode ser maior que o limite superior.')
        if d.get('reference_value') is not None and d.get('lower_limit') is not None and d['reference_value']<d['lower_limit']:raise ValueError('O valor de referência não pode ser menor que o limite inferior.')
        if d.get('reference_value') is not None and d.get('upper_limit') is not None and d['reference_value']>d['upper_limit']:raise ValueError('O valor de referência não pode ser maior que o limite superior.')
    return d

def create_characteristic(pid,data):
    d=_char_payload(data);item_id=int(d.get('item_id') or 0)
    if not item_id:raise ValueError('Selecione o Item de Inspeção.')
    c=get_conn()
    try:
        sort=d.get('sort_order');
        if sort is None:sort=c.execute('SELECT COALESCE(MAX(sort_order),0)+1 FROM control_characteristics WHERE item_id=?',(item_id,)).fetchone()[0]
        cur=c.execute('''INSERT INTO control_characteristics(project_id,item_id,sort_order,characteristic_type,description,method_code,decimals,unit_code,reference_value,lower_limit,upper_limit,status,source_template_id,row_color)
                         VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',(pid,item_id,sort,d['characteristic_type'],d['description'],d['method_code'],d.get('decimals'),d.get('unit_code',''),d.get('reference_value'),d.get('lower_limit'),d.get('upper_limit'),d['status'],d.get('source_template_id'),d['row_color']))
        c.commit()
        _revalidate(pid)
        return get_characteristic(cur.lastrowid)
    except Exception:c.rollback();raise
    finally:c.close()

def update_characteristic(cid,data):
    old=get_characteristic(cid) or {};d=_char_payload({**old,**data});c=get_conn()
    try:
        c.execute('''UPDATE control_characteristics SET item_id=?,sort_order=?,characteristic_type=?,description=?,method_code=?,decimals=?,unit_code=?,reference_value=?,lower_limit=?,upper_limit=?,status=?,row_color=?,updated_at=? WHERE id=?''',(d['item_id'],d.get('sort_order',0),d['characteristic_type'],d['description'],d['method_code'],d.get('decimals'),d.get('unit_code',''),d.get('reference_value'),d.get('lower_limit'),d.get('upper_limit'),d['status'],d['row_color'],_now(),cid))
        c.commit()
        _revalidate(old.get('project_id') or d.get('project_id'))
        return get_characteristic(cid)
    except Exception:c.rollback();raise
    finally:c.close()

def list_char_templates(pid):
    c=get_conn()
    try:return rows(c.execute('''SELECT t.*,(SELECT COUNT(*) FROM characteristic_template_rows r WHERE r.template_id=t.id) row_count FROM characteristic_templates t WHERE t.scope='GLOBAL' OR t.project_id=? ORDER BY t.category,t.name''',(pid,)).fetchall())
    finally:c.close()

def list_equipment_templates(pid):
    c=get_conn()
    try:return rows(c.execute('''SELECT t.*,(SELECT COUNT(*) FROM equipment_template_items x WHERE x.template_id=t.id) item_count,(SELECT COUNT(*) FROM equipment_template_characteristics c2 JOIN equipment_template_items ti ON ti.id=c2.template_item_id WHERE ti.template_id=t.id) characteristic_count FROM equipment_templates t WHERE t.scope='GLOBAL' OR t.project_id=? ORDER BY t.category,t.name''',(pid,)).fetchall())
    finally:c.close()
