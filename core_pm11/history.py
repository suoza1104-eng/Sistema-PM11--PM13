import json
from .database import get_conn

PROJECT_TABLES=['inspection_plans','inspection_items','control_characteristics']

def _rows(conn,sql,args=()):return [dict(r) for r in conn.execute(sql,args).fetchall()]

def capture(project_id):
    c=get_conn()
    try:
        data={}
        for t in PROJECT_TABLES:data[t]=_rows(c,f'SELECT * FROM {t} WHERE project_id=?',(project_id,))
        local_ct=_rows(c,'SELECT * FROM characteristic_templates WHERE project_id=?',(project_id,));data['characteristic_templates']=local_ct
        tids=[r['id'] for r in local_ct]
        data['characteristic_template_rows']=[]
        if tids:
            qs=','.join('?'*len(tids));data['characteristic_template_rows']=_rows(c,f'SELECT * FROM characteristic_template_rows WHERE template_id IN ({qs})',tids)
        local_et=_rows(c,'SELECT * FROM equipment_templates WHERE project_id=?',(project_id,));data['equipment_templates']=local_et
        etids=[r['id'] for r in local_et];data['equipment_template_items']=[];data['equipment_template_characteristics']=[]
        if etids:
            qs=','.join('?'*len(etids));its=_rows(c,f'SELECT * FROM equipment_template_items WHERE template_id IN ({qs})',etids);data['equipment_template_items']=its
            iids=[r['id'] for r in its]
            if iids:
                qs=','.join('?'*len(iids));data['equipment_template_characteristics']=_rows(c,f'SELECT * FROM equipment_template_characteristics WHERE template_item_id IN ({qs})',iids)
        return data
    finally:c.close()

def _insert_rows(c,table,rows):
    if not rows:return
    cols=list(rows[0].keys());sql=f"INSERT INTO {table} ({','.join(cols)}) VALUES ({','.join('?'*len(cols))})"
    c.executemany(sql,[[r.get(k) for k in cols] for r in rows])

def restore(project_id,data):
    c=get_conn()
    try:
        c.execute('BEGIN')
        c.execute('DELETE FROM control_characteristics WHERE project_id=?',(project_id,))
        c.execute('DELETE FROM inspection_items WHERE project_id=?',(project_id,))
        c.execute('DELETE FROM inspection_plans WHERE project_id=?',(project_id,))
        tids=[r['id'] for r in c.execute('SELECT id FROM characteristic_templates WHERE project_id=?',(project_id,)).fetchall()]
        for tid in tids:c.execute('DELETE FROM characteristic_template_rows WHERE template_id=?',(tid,))
        c.execute('DELETE FROM characteristic_templates WHERE project_id=?',(project_id,))
        etids=[r['id'] for r in c.execute('SELECT id FROM equipment_templates WHERE project_id=?',(project_id,)).fetchall()]
        for tid in etids:
            iids=[r['id'] for r in c.execute('SELECT id FROM equipment_template_items WHERE template_id=?',(tid,)).fetchall()]
            for iid in iids:c.execute('DELETE FROM equipment_template_characteristics WHERE template_item_id=?',(iid,))
            c.execute('DELETE FROM equipment_template_items WHERE template_id=?',(tid,))
        c.execute('DELETE FROM equipment_templates WHERE project_id=?',(project_id,))
        _insert_rows(c,'inspection_plans',data.get('inspection_plans',[]))
        _insert_rows(c,'inspection_items',data.get('inspection_items',[]))
        _insert_rows(c,'control_characteristics',data.get('control_characteristics',[]))
        _insert_rows(c,'characteristic_templates',data.get('characteristic_templates',[]))
        _insert_rows(c,'characteristic_template_rows',data.get('characteristic_template_rows',[]))
        _insert_rows(c,'equipment_templates',data.get('equipment_templates',[]))
        _insert_rows(c,'equipment_template_items',data.get('equipment_template_items',[]))
        _insert_rows(c,'equipment_template_characteristics',data.get('equipment_template_characteristics',[]))
        c.commit()
    except Exception:c.rollback();raise
    finally:c.close()

def record(project_id,label,before,after):
    c=get_conn()
    try:
        c.execute('DELETE FROM project_history WHERE project_id=? AND undone=1',(project_id,))
        c.execute('INSERT INTO project_history(project_id,action_label,before_json,after_json,undone) VALUES(?,?,?,?,0)',(project_id,label,json.dumps(before,ensure_ascii=False),json.dumps(after,ensure_ascii=False)))
        c.execute('''DELETE FROM project_history WHERE project_id=? AND id NOT IN (SELECT id FROM project_history WHERE project_id=? ORDER BY id DESC LIMIT 30)''',(project_id,project_id));c.commit()
    finally:c.close()

def undo(project_id):
    c=get_conn();r=None
    try:r=c.execute('SELECT * FROM project_history WHERE project_id=? AND undone=0 ORDER BY id DESC LIMIT 1',(project_id,)).fetchone()
    finally:c.close()
    if not r:return {'ok':False,'message':'Nada para desfazer.'}
    restore(project_id,json.loads(r['before_json']))
    c=get_conn();c.execute('UPDATE project_history SET undone=1 WHERE id=?',(r['id'],));c.commit();c.close()
    return {'ok':True,'action':r['action_label']}

def redo(project_id):
    c=get_conn();r=None
    try:r=c.execute('SELECT * FROM project_history WHERE project_id=? AND undone=1 ORDER BY id ASC LIMIT 1',(project_id,)).fetchone()
    finally:c.close()
    if not r:return {'ok':False,'message':'Nada para refazer.'}
    restore(project_id,json.loads(r['after_json']))
    c=get_conn();c.execute('UPDATE project_history SET undone=0 WHERE id=?',(r['id'],));c.commit();c.close()
    return {'ok':True,'action':r['action_label']}

def status(project_id):
    c=get_conn()
    try:
        u=c.execute('SELECT action_label FROM project_history WHERE project_id=? AND undone=0 ORDER BY id DESC LIMIT 1',(project_id,)).fetchone()
        r=c.execute('SELECT action_label FROM project_history WHERE project_id=? AND undone=1 ORDER BY id ASC LIMIT 1',(project_id,)).fetchone()
        return {'undo':u['action_label'] if u else None,'redo':r['action_label'] if r else None}
    finally:c.close()
