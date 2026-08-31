import datetime, statistics, time, random
from .database import get_conn

def _interval_days(unit, cycle):
    u = str(unit or '').upper()
    if u in ('PRD', 'PARADA'): return 99999
    c = max(1, int(float(cycle or 1)))
    if u == 'DIA': return c
    if u in ('SMS', 'SEM', 'SEMANA', 'W'): return c * 5
    if u in ('MES', 'M'): return c * 20
    return c * 5
def _date(value):return datetime.date.fromisoformat(value) if value else datetime.date.today()
def _route_key(value):
    try:return (0,int(str(value or '').strip()))
    except:return (1,str(value or '').strip())
def _filters_sql(filters=None):
    f=filters or {};where=[];args=[]
    for key,col in {'plan_id':'i.plan_id','item_id':'i.id','gpm':'i.gpm','work_center':'i.work_center','condition':'i.condition_code','priority':'i.priority','status':'i.status'}.items():
        value=f.get(key)
        if value not in (None,'','ALL','TODOS'):where.append(col+'=?');args.append(int(value) if key in ('plan_id','item_id','priority') and str(value).isdigit() else value)
    if f.get('route'):where.append('i.route LIKE ?');args.append('%'+str(f['route'])+'%')
    return where,args
def load_items(project_id,filters=None,only_in_book=None):
    c=get_conn()
    try:
        wh,args=_filters_sql(filters);where=["i.project_id=?","i.status='ACTIVE'","p.status='ACTIVE'"]+wh
        if only_in_book is True:
            where.append("COALESCE(i.in_book,0)=1")
        elif only_in_book is False:
            where.append("COALESCE(i.in_book,0)=0")
        query=f'''SELECT i.id,i.legacy_identifier,i.equipment_code,i.gpm,i.work_center,i.condition_code,i.priority,i.route,i.description,i.inspection_minutes,i.balance_offset_days,COALESCE(i.locked,0) locked,p.id plan_id,p.code plan_code,p.description plan_description,p.cycle_code,p.cycle_value,p.unit,p.text_cycle,p.offset_days plan_offset_days FROM inspection_items i JOIN inspection_plans p ON p.id=i.plan_id WHERE {' AND '.join(where)} ORDER BY i.legacy_identifier'''
        return [dict(r) for r in c.execute(query,[project_id]+args).fetchall()]
    finally:c.close()
def filter_options(project_id):
    c=get_conn()
    try:return {'plans':[dict(r) for r in c.execute("SELECT id,code,description FROM inspection_plans WHERE project_id=? AND status='ACTIVE' ORDER BY code",(project_id,)).fetchall()],'items':[dict(r) for r in c.execute("SELECT id,legacy_identifier,description,equipment_code FROM inspection_items WHERE project_id=? AND status='ACTIVE' ORDER BY legacy_identifier",(project_id,)).fetchall()],'gpms':[r[0] for r in c.execute("SELECT DISTINCT gpm FROM inspection_items WHERE project_id=? AND TRIM(gpm)<>'' ORDER BY gpm",(project_id,)).fetchall()],'work_centers':[r[0] for r in c.execute("SELECT DISTINCT work_center FROM inspection_items WHERE project_id=? AND TRIM(work_center)<>'' ORDER BY work_center",(project_id,)).fetchall()],'routes':[r[0] for r in c.execute("SELECT DISTINCT route FROM inspection_items WHERE project_id=? AND TRIM(route)<>'' ORDER BY route",(project_id,)).fetchall()]}
    finally:c.close()
def _anchor(project_id,supplied=None):
    if supplied:return _date(supplied)
    c=get_conn()
    try:r=c.execute('SELECT balance_anchor_date FROM projects WHERE id=?',(project_id,)).fetchone()
    finally:c.close()
    return _date(r[0] if r and r[0] else None)
def _working_dates(start,count,include_saturday=False):
    out=[]
    while len(out)<count:
        if start.weekday() < (6 if include_saturday else 5):out.append(start)
        start+=datetime.timedelta(days=1)
    return out
def _occurrence_indices(dates,anchor,offset_days,unit,cycle):
    u = str(unit or '').upper()
    if u in ('PRD', 'PARADA'): return []
    interval = _interval_days(unit, cycle)
    offset = max(1, int(offset_days or 1))
    # nSd describes the logical PM11 week (2=Monday ... 6=Friday).  The
    # projection's first date is always SEG1, even when that date is not a
    # civil Monday.  Therefore this conversion must not use anchor.weekday().
    calendar_delta = offset - 1
    start_idx = ((calendar_delta // 7) * 5 + min(calendar_delta % 7, 5)) % interval
    return list(range(start_idx, len(dates), interval))
def project_schedule(project_id,start_date=None,days=30,offset_override=None,filters=None,assignment_override=None,include_book=False):
    days=max(1,min(int(days),730));anchor=_anchor(project_id,start_date);dates=_working_dates(anchor,days);items=load_items(project_id,filters,only_in_book=None if (assignment_override or include_book) else False);offsets={int(k):int(v) for k,v in (offset_override or {}).items()};assignments={int(k):int(v) for k,v in (assignment_override or {}).items()}
    if assignments:
        c=get_conn()
        try:plans={r['id']:dict(r) for r in c.execute('SELECT * FROM inspection_plans WHERE project_id=?',(project_id,)).fetchall()}
        finally:c.close()
        for it in items:
            p=plans.get(assignments.get(it['id']))
            if p:it.update(plan_id=p['id'],plan_code=p['code'],cycle_code=p['cycle_code'],cycle_value=p['cycle_value'],unit=p['unit'],text_cycle=p['text_cycle'],plan_offset_days=p['offset_days'])
    loads=[0.0]*days;counts=[0]*days;occ=[[] for _ in range(days)]
    for it in items:
        interval=_interval_days(it['unit'],it['cycle_value']);plan_offset=max(1,int(it.get('plan_offset_days') or 1))
        indices=list(range(offsets[it['id']]%interval,days,interval)) if it['id'] in offsets else _occurrence_indices(dates,anchor,plan_offset,it['unit'],it['cycle_value'])
        for idx in indices:
            mins=float(it['inspection_minutes'] or 0);loads[idx]+=mins;counts[idx]+=1;occ[idx].append({'item_id':it['id'],'identifier':it['legacy_identifier'],'route':it['route'],'equipment':it['equipment_code'],'description':it['description'],'minutes':mins,'plan_code':it['plan_code'],'plan_description':it.get('plan_description',''),'text_cycle':it.get('text_cycle',''),'cycle_code':it['cycle_code'],'cycle_value':it['cycle_value'],'unit':it['unit'],'interval_days':interval,'current_offset':plan_offset-1,'locked':int(it.get('locked') or 0),'gpm':it['gpm'],'work_center':it['work_center'],'condition_code':it['condition_code']})
    return [{'day_index':i,'date':dates[i].isoformat(),'minutes':round(loads[i],2),'hours':round(loads[i]/60,2),'count':counts[i],'items':sorted(occ[i],key=lambda x:_route_key(x['route']))} for i in range(days)]
def metrics(schedule,target_minutes=0):
    loads=[float(r['minutes'] or 0) for r in schedule];counts=[int(r['count'] or 0) for r in schedule];target=float(target_minutes or 0)
    if not loads:return {'avg_minutes':0,'avg_hours':0,'max_minutes':0,'max_hours':0,'min_minutes':0,'min_hours':0,'avg_items':0,'max_items':0,'linearity':100,'stdev_minutes':0,'target_minutes':target,'days_over_target':0,'target_utilization':0}
    avg=sum(loads)/len(loads);sd=statistics.pstdev(loads) if len(loads)>1 else 0
    return {'avg_minutes':round(avg,2),'avg_hours':round(avg/60,2),'max_minutes':round(max(loads),2),'max_hours':round(max(loads)/60,2),'min_minutes':round(min(loads),2),'min_hours':round(min(loads)/60,2),'avg_items':round(sum(counts)/len(counts),2),'max_items':max(counts) if counts else 0,'linearity':round(max(0,100*(1-min(sd/avg if avg else 0,1))),1),'stdev_minutes':round(sd,2),'target_minutes':target,'days_over_target':sum(1 for x in loads if target>0 and x>target),'target_utilization':round(avg/target*100,1) if target else 0}
def _score(loads,target=0):
    if not loads:return 0
    avg=sum(loads)/len(loads);variance=sum((x-avg)**2 for x in loads)/len(loads);peak=max(loads);penalty=sum(max(0,x-target)**2 for x in loads) if target>0 else 0
    return variance+peak*peak*.015+penalty*2.5
def _objective(loads,target=0):
    if not loads:return (0,0,0,0)
    avg=sum(loads)/len(loads);variance=sum((x-avg)**2 for x in loads)/len(loads)
    overload=sum(max(0,x-target)**2 for x in loads) if target>0 else 0
    return (round(overload,6),round(max(loads)-min(loads),6),round(variance,6),round(max(loads),6))
def auto_balance_preview(project_id,start_date=None,days=90,target_minutes=0,filters=None,attempts=50,balance_by='none'):
    t0=time.perf_counter();items=load_items(project_id,filters);base=project_schedule(project_id,start_date,days,filters=filters);c=get_conn()
    try:plans=[dict(r) for r in c.execute("SELECT * FROM inspection_plans WHERE project_id=? AND status='ACTIVE' AND offset_days IS NOT NULL",(project_id,)).fetchall()]
    finally:c.close()
    families={}
    for p in plans:families.setdefault((p['cycle_value'],str(p['unit'] or '').upper(),str(p['text_cycle'] or '').strip(),str(p['code'] or '')[:9].upper()),[]).append(p)
    attempts=max(1,min(int(attempts or 50),1000));balance_by=str(balance_by or 'none').lower()
    dimension_field={'gpm':'gpm','work_center':'work_center'}.get(balance_by)
    fixed_assignments={};failures=[];target=float(target_minutes or 0);anchor=_anchor(project_id,start_date);dates=_working_dates(anchor,int(days));fixed_loads=[0.0]*len(dates);fixed_dimension_loads={}
    movable=[]
    for it in items:
        if not int(it.get('locked') or 0):movable.append(it);continue
        current=next((p for p in plans if p['id']==it['plan_id']),None)
        if not current:failures.append({'item_id':it['id'],'identifier':it['legacy_identifier'],'reason':'Item trancado sem plano de origem com offset.'});continue
        fixed_assignments[it['id']]=current['id']
        dimension=str(it.get(dimension_field) or 'Sem cadastro') if dimension_field else '__all__'
        dim_loads=fixed_dimension_loads.setdefault(dimension,[0.0]*len(dates))
        for idx in _occurrence_indices(dates,anchor,current['offset_days'],current['unit'],current['cycle_value']):
            fixed_loads[idx]+=float(it.get('inspection_minutes') or 0);dim_loads[idx]+=float(it.get('inspection_minutes') or 0)
    route_groups={}
    for it in movable:
        family=(it['cycle_value'],str(it['unit'] or '').upper(),str(it['text_cycle'] or '').strip(),str(it['plan_code'] or '')[:9].upper())
        dimension=str(it.get(dimension_field) or 'Sem cadastro') if dimension_field else '__all__'
        route_groups.setdefault((family,str(it.get('route') or '').strip(),dimension),[]).append(it)
    ordered_groups=sorted(route_groups.items(),key=lambda entry:(_route_key(entry[0][1]),entry[0][0]))
    valid_groups=[]
    for (family,route,dimension),group_items in ordered_groups:
        eligible=families.get(family,[])
        if not eligible:
            for it in group_items:failures.append({'item_id':it['id'],'identifier':it['legacy_identifier'],'route':route,'reason':'Nenhum plano com offset, mesmo ciclo, texto ciclo e prefixo de 9 caracteres.'})
            continue
        options=[];mins=sum(float(it.get('inspection_minutes') or 0) for it in group_items)
        for candidate in eligible:options.append((candidate,_occurrence_indices(dates,anchor,candidate['offset_days'],candidate['unit'],candidate['cycle_value'])))
        valid_groups.append({'items':group_items,'minutes':mins,'options':options,'route':route,'dimension':dimension})
    rng=random.Random(project_id*1000003+int(days));orders=[list(valid_groups)]
    if attempts>1:orders.append(list(reversed(valid_groups)))
    for _ in range(max(0,attempts-len(orders))):
        order=list(valid_groups);rng.shuffle(order);orders.append(order)
    best_global=None
    for order in orders:
        loads=list(fixed_loads);dimension_loads={k:list(v) for k,v in fixed_dimension_loads.items()};trial=dict(fixed_assignments);chosen_by_group={}
        for group in order:
            dim_loads=dimension_loads.setdefault(group['dimension'],[0.0]*len(dates))
            choice=None
            for candidate,indices in group['options']:
                for idx in indices:loads[idx]+=group['minutes'];dim_loads[idx]+=group['minutes']
                rank=((_score(dim_loads,0),_score(loads,target)) if dimension_field else (_score(loads,target),),candidate['offset_days'],candidate['id'])
                for idx in indices:loads[idx]-=group['minutes'];dim_loads[idx]-=group['minutes']
                if choice is None or rank<choice[0]:choice=(rank,candidate,indices)
            for it in group['items']:trial[it['id']]=choice[1]['id']
            for idx in choice[2]:loads[idx]+=group['minutes'];dim_loads[idx]+=group['minutes']
            chosen_by_group[id(group)]=(choice[1],choice[2])
        dimension_rank=tuple(sum(x) for x in zip(*(_objective(v,0) for v in dimension_loads.values()))) if dimension_field and dimension_loads else ()
        rank=(dimension_rank,_objective(loads,target)) if dimension_field else _objective(loads,target)
        if best_global is None or rank<best_global[0]:best_global=(rank,trial,loads,chosen_by_group,dimension_loads)
    # Coordinate-descent refinement: retest every route against the complete load.
    rank,assignments,loads,chosen_by_group,dimension_loads=best_global
    refinement_rounds=0
    for _ in range(8):
        improved=False;refinement_rounds+=1
        for group in valid_groups:
            dim_loads=dimension_loads.setdefault(group['dimension'],[0.0]*len(dates))
            old_candidate,old_indices=chosen_by_group[id(group)]
            for idx in old_indices:loads[idx]-=group['minutes'];dim_loads[idx]-=group['minutes']
            choice=None
            for candidate,indices in group['options']:
                for idx in indices:loads[idx]+=group['minutes'];dim_loads[idx]+=group['minutes']
                candidate_rank=((_objective(dim_loads,0),_objective(loads,target)) if dimension_field else _objective(loads,target))
                for idx in indices:loads[idx]-=group['minutes'];dim_loads[idx]-=group['minutes']
                if choice is None or candidate_rank<choice[0]:choice=(candidate_rank,candidate,indices)
            for idx in choice[2]:loads[idx]+=group['minutes'];dim_loads[idx]+=group['minutes']
            chosen_by_group[id(group)]=(choice[1],choice[2])
            for it in group['items']:assignments[it['id']]=choice[1]['id']
            if choice[1]['id']!=old_candidate['id']:improved=True
        dimension_rank=tuple(sum(x) for x in zip(*(_objective(v,0) for v in dimension_loads.values()))) if dimension_field and dimension_loads else ()
        new_rank=(dimension_rank,_objective(loads,target)) if dimension_field else _objective(loads,target)
        if not improved or new_rank>=rank:break
        rank=new_rank
    proposed=project_schedule(project_id,start_date,days,filters=filters,assignment_override=assignments);changes=[{'item_id':it['id'],'identifier':it['legacy_identifier'],'from_plan_id':it['plan_id'],'from_plan_code':it['plan_code'],'to_plan_id':assignments[it['id']]} for it in items if assignments.get(it['id'],it['plan_id'])!=it['plan_id']]
    constrained_families=[];weekday_names=('Segunda','Terca','Quarta','Quinta','Sexta','Sabado')
    for family,family_plans in families.items():
        if not any(key[0]==family for key in route_groups):continue
        available={(int(p['offset_days'])-1)%7 for p in family_plans};missing=[name for idx,name in enumerate(weekday_names) if idx not in available]
        if missing:constrained_families.append({'cycle_value':family[0],'unit':family[1],'text_cycle':family[2],'code_prefix':family[3],'missing_weekdays':missing})
    return {'start_date':_anchor(project_id,start_date).isoformat(),'days':int(days),'before':base,'after':proposed,'before_metrics':metrics(base,target_minutes),'after_metrics':metrics(proposed,target_minutes),'assignments':assignments,'changes':changes,'failures':failures,'changed_items':len(changes),'route_groups_tested':len(route_groups),'attempts':len(orders),'balance_by':balance_by,'refinement_rounds':refinement_rounds,'objective':rank,'constrained_families':constrained_families,'elapsed_seconds':round(time.perf_counter()-t0,3),'algorithm':'PM11 - Busca multi-rodada e refinamento por rota; menor gap global dentro das regras'}
def apply_assignments(project_id,assignments):
    c=get_conn()
    try:
        c.execute('BEGIN');updated=0;unchanged=0
        for item_id,plan_id in assignments.items():
            valid=c.execute("""SELECT 1 FROM inspection_items i JOIN inspection_plans src ON src.id=i.plan_id JOIN inspection_plans dst ON dst.id=? AND dst.project_id=i.project_id WHERE i.id=? AND i.project_id=? AND src.cycle_value IS dst.cycle_value AND UPPER(COALESCE(src.unit,''))=UPPER(COALESCE(dst.unit,'')) AND TRIM(COALESCE(src.text_cycle,''))=TRIM(COALESCE(dst.text_cycle,'')) AND UPPER(SUBSTR(COALESCE(src.code,''),1,9))=UPPER(SUBSTR(COALESCE(dst.code,''),1,9))""",(int(plan_id),int(item_id),project_id)).fetchone()
            if not valid:raise ValueError(f'Item {item_id}: destino deve ter o mesmo ciclo, texto ciclo e os 9 primeiros caracteres do código.')
            c.execute('UPDATE inspection_items SET plan_id=?,in_book=0,updated_at=CURRENT_TIMESTAMP WHERE id=? AND project_id=?',(int(plan_id),int(item_id),project_id));updated+=1
        c.commit();return {'updated':updated,'unchanged':unchanged,'requested':len(assignments)}
    except Exception:c.rollback();raise
    finally:c.close()
    c=get_conn()
    try:
        for item_id,off in offsets.items():c.execute('UPDATE inspection_items SET balance_offset_days=?,updated_at=CURRENT_TIMESTAMP WHERE project_id=? AND id=?',(int(off),project_id,int(item_id)))
        c.commit();return {'updated':len(offsets)}
    finally:c.close()
def lock_item(project_id,item_id,locked=True):
    c=get_conn()
    try:c.execute('UPDATE inspection_items SET locked=?,updated_at=CURRENT_TIMESTAMP WHERE project_id=? AND id=?',(1 if locked else 0,project_id,int(item_id)));c.commit();return {'item_id':item_id,'locked':1 if locked else 0}
    finally:c.close()
def reset_offsets(project_id, only_unlocked=False):
    c=get_conn()
    try:
        if only_unlocked:
            c.execute('UPDATE inspection_items SET in_book=1,balance_offset_days=0,updated_at=CURRENT_TIMESTAMP WHERE project_id=? AND COALESCE(locked,0)=0',(project_id,))
        else:
            c.execute('UPDATE inspection_items SET in_book=1,balance_offset_days=0,updated_at=CURRENT_TIMESTAMP WHERE project_id=?',(project_id,))
        c.commit()
        return {'reset':True}
    finally:c.close()
def book_items(project_id,filters=None):
    out=[]
    items = load_items(project_id, filters, only_in_book=True)
    for it in items:
        interval=_interval_days(it['unit'],it['cycle_value'])
        if interval>1:out.append({'item_id':it['id'],'identifier':it['legacy_identifier'],'equipment':it['equipment_code'],'description':it['description'],'route':it['route'],'minutes':float(it['inspection_minutes'] or 0),'plan_code':it['plan_code'],'plan_description':it.get('plan_description',''),'text_cycle':it.get('text_cycle',''),'cycle_code':it['cycle_code'],'cycle_value':it['cycle_value'],'interval_days':interval,'current_offset':max(0,int(it.get('plan_offset_days') or 1)-1),'locked':int(it.get('locked') or 0),'gpm':it['gpm'],'work_center':it['work_center']})
    return sorted(out,key=lambda x:(_route_key(x['route']),x['identifier']))
def manual_preview(project_id,start_date=None,days=90,offsets=None,target_minutes=0,filters=None):
    schedule=project_schedule(project_id,start_date,days,offsets or {},filters);return {'schedule':schedule,'metrics':metrics(schedule,target_minutes),'days':int(days),'start':_anchor(project_id,start_date).isoformat(),'manual':True}

def get_eligible_plans_for_drop(project_id, item_id, day_idx, start_date=None, days=30):
    items = load_items(project_id)
    item = next((x for x in items if x['id'] == int(item_id)), None)
    if not item:
        return {'error': 'Item não encontrado.'}

    anchor = _anchor(project_id, start_date)
    dates = _working_dates(anchor, int(days))
    day_idx = int(day_idx)
    target_date = dates[day_idx].isoformat() if 0 <= day_idx < len(dates) else ''

    c = get_conn()
    try:
        plans = [dict(r) for r in c.execute("SELECT id, code, description, cycle_code, cycle_value, unit, text_cycle, offset_days FROM inspection_plans WHERE project_id=? AND status='ACTIVE' ORDER BY code", (project_id,)).fetchall()]
    finally:
        c.close()

    fam_cycle = item['cycle_value']
    fam_unit = str(item['unit'] or '').upper()
    fam_text = str(item['text_cycle'] or '').strip()
    fam_prefix = str(item['plan_code'] or '')[:9].upper()

    eligible = []
    family_plans = []

    for p in plans:
        p_cycle = p['cycle_value']
        p_unit = str(p['unit'] or '').upper()
        p_text = str(p['text_cycle'] or '').strip()
        p_prefix = str(p['code'] or '')[:9].upper()

        if p_cycle == fam_cycle and p_unit == fam_unit and p_text == fam_text and p_prefix == fam_prefix:
            family_plans.append(p)
            occ = _occurrence_indices(dates, anchor, p['offset_days'], p['unit'], p['cycle_value'])
            if day_idx in occ:
                eligible.append(p)

    return {
        'item': {
            'id': item['id'],
            'legacy_identifier': item['legacy_identifier'],
            'description': item['description'],
            'equipment_code': item['equipment_code'],
            'plan_id': item['plan_id'],
            'plan_code': item['plan_code'],
            'cycle_value': item['cycle_value'],
            'unit': item['unit'],
            'text_cycle': item.get('text_cycle', ''),
            'route': item.get('route', '')
        },
        'day_idx': day_idx,
        'target_date': target_date,
        'family_prefix': fam_prefix,
        'eligible_plans': eligible,
        'family_plans': family_plans
    }
