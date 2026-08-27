import datetime, statistics, time
from .database import get_conn


def _interval_days(unit,cycle):
    cycle=max(1,int(float(cycle or 1)))
    return cycle if str(unit or '').upper()=='DIA' else cycle*7

def _date(s):return datetime.date.fromisoformat(s) if s else datetime.date.today()
def _route_key(route):
    s=str(route or '').strip()
    try:return (0,int(s))
    except:return (1,s)

def _filters_sql(filters=None):
    f=filters or {};where=[];args=[]
    mp={'plan_id':'i.plan_id','gpm':'i.gpm','work_center':'i.work_center','condition':'i.condition_code','priority':'i.priority','status':'i.status'}
    for k,col in mp.items():
        v=f.get(k)
        if v not in (None,'','ALL','TODOS'):
            where.append(col+'=?');args.append(int(v) if k in ('plan_id','priority') and str(v).isdigit() else v)
    if f.get('route'):
        where.append('i.route LIKE ?');args.append('%'+str(f['route'])+'%')
    return where,args

def load_items(project_id,filters=None):
    c=get_conn()
    try:
        wh,args=_filters_sql(filters);where=["i.project_id=?","i.status='ACTIVE'","p.status='ACTIVE'"]+wh
        q=f'''SELECT i.id,i.legacy_identifier,i.equipment_code,i.gpm,i.work_center,i.condition_code,i.priority,i.route,i.description,i.inspection_minutes,i.balance_offset_days,
        p.id plan_id,p.code plan_code,p.cycle_code,p.cycle_value,p.unit,p.text_cycle
        FROM inspection_items i JOIN inspection_plans p ON p.id=i.plan_id WHERE {' AND '.join(where)} ORDER BY i.legacy_identifier'''
        return [dict(r) for r in c.execute(q,[project_id]+args).fetchall()]
    finally:c.close()

def filter_options(project_id):
    c=get_conn()
    try:
        return {'plans':[dict(r) for r in c.execute('SELECT id,code,description FROM inspection_plans WHERE project_id=? AND status=\'ACTIVE\' ORDER BY code',(project_id,)).fetchall()],
                'gpms':[r[0] for r in c.execute("SELECT DISTINCT gpm FROM inspection_items WHERE project_id=? AND TRIM(gpm)<>'' ORDER BY gpm",(project_id,)).fetchall()],
                'work_centers':[r[0] for r in c.execute("SELECT DISTINCT work_center FROM inspection_items WHERE project_id=? AND TRIM(work_center)<>'' ORDER BY work_center",(project_id,)).fetchall()],
                'routes':[r[0] for r in c.execute("SELECT DISTINCT route FROM inspection_items WHERE project_id=? AND TRIM(route)<>'' ORDER BY route",(project_id,)).fetchall()]}
    finally:c.close()

def project_schedule(project_id,start_date=None,days=30,offset_override=None,filters=None):
    start=_date(start_date);days=max(1,min(int(days),730));items=load_items(project_id,filters);over={int(k):int(v) for k,v in (offset_override or {}).items()}
    loads=[0.0]*days;counts=[0]*days;occ=[[] for _ in range(days)]
    for it in items:
        interval=_interval_days(it['unit'],it['cycle_value']);off=int(over.get(it['id'],it['balance_offset_days'] or 0));off=0 if interval<=1 else off%interval
        idx=off
        while idx<days:
            mins=float(it['inspection_minutes'] or 0);loads[idx]+=mins;counts[idx]+=1
            occ[idx].append({'item_id':it['id'],'identifier':it['legacy_identifier'],'route':it['route'],'equipment':it['equipment_code'],'description':it['description'],'minutes':mins,'plan_code':it['plan_code'],'cycle_code':it['cycle_code'],'gpm':it['gpm'],'work_center':it['work_center']})
            idx+=interval
    rows=[]
    for i in range(days):
        occ[i].sort(key=lambda x:_route_key(x['route']))
        rows.append({'date':(start+datetime.timedelta(days=i)).isoformat(),'minutes':round(loads[i],2),'hours':round(loads[i]/60,2),'count':counts[i],'items':occ[i]})
    return rows

def metrics(schedule,target_minutes=0):
    loads=[float(r['minutes'] or 0) for r in schedule];counts=[int(r['count'] or 0) for r in schedule]
    if not loads:return {'avg_minutes':0,'avg_hours':0,'max_minutes':0,'max_hours':0,'min_minutes':0,'min_hours':0,'avg_items':0,'max_items':0,'linearity':100,'stdev_minutes':0,'target_minutes':float(target_minutes or 0),'days_over_target':0,'target_utilization':0}
    avg=sum(loads)/len(loads);sd=statistics.pstdev(loads) if len(loads)>1 else 0;cv=(sd/avg) if avg>0 else 0;linearity=max(0.0,100*(1-min(cv,1.0)));target=float(target_minutes or 0);over=sum(1 for x in loads if target>0 and x>target)
    return {'avg_minutes':round(avg,2),'avg_hours':round(avg/60,2),'max_minutes':round(max(loads),2),'max_hours':round(max(loads)/60,2),'min_minutes':round(min(loads),2),'min_hours':round(min(loads)/60,2),'avg_items':round(sum(counts)/len(counts),2),'max_items':max(counts) if counts else 0,'linearity':round(linearity,1),'stdev_minutes':round(sd,2),'target_minutes':target,'days_over_target':over,'target_utilization':round((avg/target*100),1) if target>0 else 0}

def _score(loads,target=0):
    if not loads:return 0
    avg=sum(loads)/len(loads);variance=sum((x-avg)**2 for x in loads)/len(loads);peak=max(loads);penalty=sum((max(0,x-target))**2 for x in loads) if target>0 else 0
    return variance+(peak*peak)*0.015+penalty*2.5

def auto_balance_preview(project_id,start_date=None,days=90,target_minutes=0,filters=None):
    t0=time.perf_counter();items=load_items(project_id,filters);days=max(7,min(int(days),730));target=float(target_minutes or 0)
    base=project_schedule(project_id,start_date,days,filters=filters);base_metrics=metrics(base,target)
    flexible=[];fixed=[]
    for it in items:
        interval=_interval_days(it['unit'],it['cycle_value']);(fixed if interval<=1 else flexible).append((it,interval))
    loads=[0.0]*days
    for it,interval in fixed:
        mins=float(it['inspection_minutes'] or 0)
        for d in range(days):loads[d]+=mins
    offsets={};flexible.sort(key=lambda x:(-float(x[0]['inspection_minutes'] or 0),-x[1],_route_key(x[0]['route'])))
    for it,interval in flexible:
        mins=float(it['inspection_minutes'] or 0);max_offset=min(interval,days);best_off=0;best_score=None
        for off in range(max_offset):
            changed=[];d=off
            while d<days:loads[d]+=mins;changed.append(d);d+=interval
            sc=_score(loads,target)
            for d in changed:loads[d]-=mins
            try:route_n=int(str(it['route'] or '0'))
            except:route_n=0
            sc+=abs((route_n%max(1,interval))-off)*0.0001
            if best_score is None or sc<best_score:best_score=sc;best_off=off
        offsets[it['id']]=best_off;d=best_off
        while d<days:loads[d]+=mins;d+=interval
    proposed=project_schedule(project_id,start_date,days,offsets,filters);prop_metrics=metrics(proposed,target);changed=sum(1 for it,_ in flexible if int(it.get('balance_offset_days') or 0)!=int(offsets.get(it['id'],0)))
    return {'start_date':_date(start_date).isoformat(),'days':days,'before':base,'after':proposed,'before_metrics':base_metrics,'after_metrics':prop_metrics,'offsets':offsets,'changed_items':changed,'elapsed_seconds':round(time.perf_counter()-t0,3),'algorithm':'PM11 V3 — periodicidade + rota + meta diária'}

def apply_offsets(project_id,offsets):
    c=get_conn()
    try:
        c.execute('BEGIN')
        for item_id,off in offsets.items():c.execute('UPDATE inspection_items SET balance_offset_days=?,updated_at=CURRENT_TIMESTAMP WHERE project_id=? AND id=?',(int(off),project_id,int(item_id)))
        c.commit();return {'updated':len(offsets)}
    except Exception:c.rollback();raise
    finally:c.close()

def book_items(project_id,filters=None):
    out=[]
    for it in load_items(project_id,filters):
        interval=_interval_days(it['unit'],it['cycle_value'])
        if interval<=1:continue
        out.append({'item_id':it['id'],'identifier':it['legacy_identifier'],'equipment':it['equipment_code'],'description':it['description'],'route':it['route'],'minutes':float(it['inspection_minutes'] or 0),'plan_code':it['plan_code'],'cycle_code':it['cycle_code'],'interval_days':interval,'current_offset':int(it['balance_offset_days'] or 0),'gpm':it['gpm'],'work_center':it['work_center']})
    out.sort(key=lambda x:(_route_key(x['route']),x['identifier']));return out

def manual_preview(project_id,start_date=None,days=90,offsets=None,target_minutes=0,filters=None):
    schedule=project_schedule(project_id,start_date,days,offsets or {},filters);return {'schedule':schedule,'metrics':metrics(schedule,target_minutes),'days':int(days),'start':_date(start_date).isoformat(),'manual':True}
