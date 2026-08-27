import os,sys,json,re,mimetypes,urllib.parse,traceback,tempfile,webbrowser,socket,datetime
from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler

BASE_DIR=os.path.dirname(os.path.abspath(__file__));sys.path.insert(0,BASE_DIR)
from core.migrations import run_migrations
from core import models,history,balance,import_export,backup
PORT=8766
BUILD='2026.08.20-pm11-v3-profissional'

def log(msg):print(f"[PM11 {datetime.datetime.now().strftime('%H:%M:%S')}] {msg}",flush=True)

class ExclusiveServer(ThreadingHTTPServer):
    allow_reuse_address=False
    def server_bind(self):
        if hasattr(socket,'SO_EXCLUSIVEADDRUSE'):self.socket.setsockopt(socket.SOL_SOCKET,socket.SO_EXCLUSIVEADDRUSE,1)
        super().server_bind()

class Handler(BaseHTTPRequestHandler):
    def log_message(self,fmt,*args):pass
    def send_json(self,data,status=200):
        b=json.dumps(data,ensure_ascii=False,default=str).encode('utf-8');self.send_response(status);self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Content-Length',str(len(b)));self.send_header('Cache-Control','no-store');self.send_header('X-PM11-Build',BUILD);self.end_headers();self.wfile.write(b)
    def err(self,msg,status=400):self.send_json({'error':str(msg)},status)
    def body(self):
        n=int(self.headers.get('Content-Length',0) or 0)
        if not n:return {}
        return json.loads(self.rfile.read(n).decode('utf-8'))
    def query(self):return {k:v[-1] for k,v in urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query).items()}
    def path_only(self):return urllib.parse.urlsplit(self.path).path
    def project_id(self,data=None):
        q=self.query();v=(data or {}).get('project_id') if isinstance(data,dict) else None;v=v or q.get('project_id') or self.headers.get('X-PM11-Project-ID');return int(v) if v and str(v).isdigit() else None
    def send_bytes(self,b,ctype='application/octet-stream',filename=None):
        self.send_response(200);self.send_header('Content-Type',ctype);self.send_header('Content-Length',str(len(b)));self.send_header('Cache-Control','no-store');
        if filename:self.send_header('Content-Disposition',f'attachment; filename="{filename}"')
        self.end_headers();self.wfile.write(b)
    def parse_upload(self):
        ctype=self.headers.get('Content-Type','');m=re.search(r'boundary=([^;]+)',ctype)
        if not m:raise ValueError('Upload multipart inválido.')
        boundary=m.group(1).strip().strip('"').encode();n=int(self.headers.get('Content-Length',0) or 0)
        if n>100*1024*1024:raise ValueError('Arquivo excede 100 MB.')
        raw=self.rfile.read(n);parts=raw.split(b'--'+boundary);fields={};file_info=None
        for part in parts:
            if b'\r\n\r\n' not in part:continue
            head,content=part.split(b'\r\n\r\n',1);content=content.rstrip(b'\r\n-');hm=re.search(br'name="([^"]+)"',head)
            if not hm:continue
            name=hm.group(1).decode();fm=re.search(br'filename="([^"]*)"',head)
            if fm:
                filename=os.path.basename(fm.group(1).decode(errors='ignore') or 'import.xlsx');fd,path=tempfile.mkstemp(prefix='pm11_import_',suffix='.xlsx');os.close(fd)
                with open(path,'wb') as f:f.write(content)
                file_info={'name':filename,'path':path,'size':len(content)}
            else:fields[name]=content.decode('utf-8',errors='ignore')
        if not file_info:raise ValueError('Nenhum arquivo recebido.')
        return fields,file_info
    def json_field(self,fields,key,default=None):
        try:return json.loads(fields.get(key,'')) if fields.get(key) else default
        except:return default
    def mutate(self,pid,label,fn):
        if pid and models.project_is_locked(pid):raise ValueError('Projeto trancado. Destranque o projeto para alterar seus dados.')
        before=history.capture(pid);result=fn();after=history.capture(pid);history.record(pid,label,before,after);return result
    def balance_filters(self,src):
        return {k:src.get(k) for k in ('plan_id','route','gpm','work_center','condition','priority','status') if src.get(k) not in (None,'','ALL','TODOS')}

    def do_GET(self):
        p=self.path_only();q=self.query()
        try:
            if p=='/api/health':return self.send_json({'ok':True,'build':BUILD,'port':PORT})
            if p=='/api/projects':return self.send_json(models.get_projects())
            if p.startswith('/api/projects/'):return self.send_json(models.get_project(int(p.rsplit('/',1)[1])) or {})
            if p=='/api/dashboard':return self.send_json(models.dashboard(self.project_id()))
            if p=='/api/catalogs':return self.send_json({'cycles':models.get_cycles(),**models.get_code_catalogs()})
            if p=='/api/methods':return self.send_json(models.search_methods(q.get('q',''),q.get('hint',''),int(q.get('limit',30))))
            if p=='/api/units':return self.send_json(models.search_units(q.get('q',''),q.get('hint',''),int(q.get('limit',30))))
            if p=='/api/plans':return self.send_json(models.list_plans(self.project_id(),q.get('search',''),q.get('status',''),q.get('cycle_code',''),q.get('row_color','')))
            if p.startswith('/api/plans/'):return self.send_json(models.get_plan(int(p.rsplit('/',1)[1])) or {})
            if p=='/api/items/filter-options':return self.send_json(models.list_filter_options(self.project_id()))
            if p=='/api/items':
                plan_id=int(q['plan_id']) if q.get('plan_id','').isdigit() else None
                return self.send_json(models.list_items(self.project_id(),q.get('search',''),plan_id,q.get('status',''),q.get('equipment',''),q.get('route',''),q.get('gpm',''),q.get('work_center',''),q.get('condition',''),q.get('priority',''),q.get('row_color','')))
            if p.startswith('/api/items/'):return self.send_json(models.get_item(int(p.rsplit('/',1)[1])) or {})
            if p=='/api/characteristics':
                item_id=int(q['item_id']) if q.get('item_id','').isdigit() else None
                return self.send_json(models.list_characteristics(self.project_id(),q.get('search',''),item_id,q.get('type',''),q.get('method',''),q.get('status',''),q.get('row_color','')))
            if p.startswith('/api/characteristics/'):return self.send_json(models.get_characteristic(int(p.rsplit('/',1)[1])) or {})
            if p=='/api/templates/characteristics':return self.send_json(models.list_char_templates(self.project_id()))
            if p.startswith('/api/templates/characteristics/'):return self.send_json(models.get_char_template(int(p.rsplit('/',1)[1])) or {})
            if p=='/api/templates/items':return self.send_json(models.list_item_templates(self.project_id()))
            if p.startswith('/api/templates/items/'):return self.send_json(models.get_item_template(int(p.rsplit('/',1)[1])) or {})
            if p=='/api/templates/equipment':return self.send_json(models.list_equipment_templates(self.project_id()))
            if p.startswith('/api/templates/equipment/'):return self.send_json(models.get_equipment_template(int(p.rsplit('/',1)[1])) or {})
            if p=='/api/balance/options':return self.send_json(balance.filter_options(self.project_id()))
            if p=='/api/balance':
                pid=self.project_id();days=int(q.get('days',30));start=q.get('start') or None;target=float(q.get('target_minutes') or 0);s=balance.project_schedule(pid,start,days,filters=self.balance_filters(q));return self.send_json({'schedule':s,'metrics':balance.metrics(s,target),'days':days,'start':start})
            if p=='/api/balance/book':return self.send_json(balance.book_items(self.project_id(),self.balance_filters(q)))
            if p=='/api/history/status':return self.send_json(history.status(self.project_id()))
            if p=='/api/export/model':return self.send_bytes(import_export.export_model(),'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet','MODELO_PM11.xlsx')
            if p=='/api/export/project':
                pid=self.project_id();days=int(q.get('days',90));start=q.get('start') or None;s=balance.project_schedule(pid,start,days,filters=self.balance_filters(q));b=import_export.export_project(pid,s);proj=models.get_project(pid) or {'name':'PM11'};fn='PM11_'+re.sub(r'[^A-Za-z0-9_-]+','_',proj['name'])+'_'+datetime.datetime.now().strftime('%Y%m%d_%H%M%S')+'.xlsx';return self.send_bytes(b,'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',fn)
            if p=='/api/backup':
                path=backup.create_backup('manual');return self.send_bytes(open(path,'rb').read(),'application/zip',os.path.basename(path))
            if p.startswith('/api/'):return self.err('Rota GET não encontrada.',404)
            return self.serve_static(p)
        except ValueError as e:log(f'GET {p} REGRA | {e}');return self.err(e,400)
        except Exception as e:log(f'GET {p} ERRO | {type(e).__name__}: {e}');traceback.print_exc();return self.err(e,500)

    def do_POST(self):
        p=self.path_only()
        try:
            if p=='/api/logs':
                d=self.body();log(f"FRONTEND [{d.get('context','APP')}] {d.get('message','')}");return self.send_json({'ok':True})
            if p=='/api/shutdown':
                self.send_json({'ok':True});log('Encerramento solicitado pela interface.');import threading;threading.Thread(target=self.server.shutdown,daemon=True).start();return
            if p=='/api/projects':return self.send_json(models.create_project(self.body()),201)
            if p=='/api/projects/duplicate':
                d=self.body();return self.send_json(models.duplicate_project(int(d['project_id']),d.get('name')),201)
            if p=='/api/projects/lock':
                d=self.body();return self.send_json(models.set_project_lock(int(d['project_id']),bool(d.get('locked',True))))
            if p=='/api/plans':
                d=self.body();pid=self.project_id(d);return self.send_json(self.mutate(pid,'Criar plano',lambda:models.create_plan(pid,d)),201)
            if p=='/api/plans/clone':
                d=self.body();pid=self.project_id(d);return self.send_json(self.mutate(pid,'Duplicar plano',lambda:models.clone_plan(pid,int(d['plan_id']),bool(d.get('include_children',False)),d.get('new_code'),d.get('new_description'))),201)
            if p=='/api/plans/save-package-template':
                d=self.body();pid=self.project_id(d);return self.send_json(self.mutate(pid,'Salvar plano como modelo',lambda:models.save_plan_as_package_template(pid,int(d['plan_id']),d['name'],d.get('category',''),d.get('description',''),d.get('scope','PROJECT'))),201)
            if p=='/api/plans/bulk-update':
                d=self.body();pid=self.project_id(d);return self.send_json(self.mutate(pid,'Editar planos em massa',lambda:models.bulk_update_plans(d.get('ids',[]),d.get('updates',{}))))
            if p=='/api/plans/bulk-delete':
                d=self.body();pid=self.project_id(d);return self.send_json(self.mutate(pid,'Excluir planos',lambda:(models.delete_plans(d.get('ids',[])) or {'ok':True})))
            if p=='/api/items':
                d=self.body();pid=self.project_id(d);return self.send_json(self.mutate(pid,'Criar item',lambda:models.create_item(pid,d)),201)
            if p=='/api/items/clone':
                d=self.body();pid=self.project_id(d);return self.send_json(self.mutate(pid,'Clonar item PM11',lambda:models.clone_item(pid,int(d['item_id']),bool(d.get('include_characteristics',True)))))
            if p=='/api/items/bulk-update':
                d=self.body();pid=self.project_id(d);return self.send_json(self.mutate(pid,'Editar itens em massa',lambda:models.bulk_update_items(d.get('ids',[]),d.get('updates',{}))))
            if p=='/api/items/bulk-delete':
                d=self.body();pid=self.project_id(d);return self.send_json(self.mutate(pid,'Excluir itens',lambda:(models.delete_items(d.get('ids',[])) or {'ok':True})))
            if p=='/api/items/save-template':
                d=self.body();pid=self.project_id(d);return self.send_json(self.mutate(pid,'Salvar item como modelo',lambda:models.save_item_template_from_item(pid,int(d['item_id']),d['name'],d.get('category',''),d.get('description',''),d.get('scope','PROJECT'))),201)
            if p=='/api/templates/items/apply':
                d=self.body();pid=self.project_id(d);return self.send_json(self.mutate(pid,'Aplicar modelo de item',lambda:models.apply_item_template(pid,int(d['template_id']),int(d['plan_id']),d.get('equipment_code',''),d.get('route',''),d.get('gpm',''),d.get('work_center',''))))
            if p=='/api/templates/items/delete':
                d=self.body();pid=self.project_id(d);return self.send_json(self.mutate(pid,'Excluir modelo de item',lambda:(models.delete_item_template(int(d['template_id'])) or {'ok':True})))
            if p=='/api/characteristics':
                d=self.body();pid=self.project_id(d);return self.send_json(self.mutate(pid,'Criar característica',lambda:models.create_characteristic(pid,d)),201)
            if p=='/api/characteristics/bulk-update':
                d=self.body();pid=self.project_id(d);return self.send_json(self.mutate(pid,'Editar características em massa',lambda:models.bulk_update_characteristics(d.get('ids',[]),d.get('updates',{}))))
            if p=='/api/characteristics/bulk-delete':
                d=self.body();pid=self.project_id(d);return self.send_json(self.mutate(pid,'Excluir características',lambda:(models.delete_characteristics(d.get('ids',[])) or {'ok':True})))
            if p=='/api/catalogs/upsert':
                d=self.body();return self.send_json(models.upsert_catalog(d['kind'],d['code'],d.get('description','')))
            if p=='/api/templates/meta':
                d=self.body();pid=self.project_id(d);return self.send_json(self.mutate(pid,'Editar modelo',lambda:models.update_template_meta(d['kind'],int(d['template_id']),d.get('updates',{}))))
            if p=='/api/templates/duplicate':
                d=self.body();pid=self.project_id(d);return self.send_json(self.mutate(pid,'Duplicar modelo',lambda:models.duplicate_template(d['kind'],int(d['template_id']),d.get('name'))),201)
            if p=='/api/templates/characteristics/save-from-item':
                d=self.body();pid=self.project_id(d);return self.send_json(self.mutate(pid,'Salvar padrão de características',lambda:models.save_char_template_from_item(pid,int(d['item_id']),d['name'],d.get('category',''),d.get('description',''),d.get('scope','PROJECT'))),201)
            if p=='/api/templates/characteristics/apply':
                d=self.body();pid=self.project_id(d);return self.send_json(self.mutate(pid,'Aplicar padrão de características',lambda:models.apply_char_template(pid,int(d['template_id']),[int(x) for x in d.get('item_ids',[])],d.get('policy','IGNORE'))))
            if p=='/api/templates/equipment/save':
                d=self.body();pid=self.project_id(d);return self.send_json(self.mutate(pid,'Salvar padrão de equipamento',lambda:models.save_equipment_template(pid,d['equipment_code'],d['name'],d.get('category',''),d.get('description',''),d.get('scope','PROJECT'))),201)
            if p=='/api/templates/characteristics/delete':
                d=self.body();pid=self.project_id(d);return self.send_json(self.mutate(pid,'Excluir padrão de características',lambda:(models.delete_char_template(int(d['template_id'])) or {'ok':True})))
            if p=='/api/templates/equipment/delete':
                d=self.body();pid=self.project_id(d);return self.send_json(self.mutate(pid,'Excluir padrão de equipamento',lambda:(models.delete_equipment_template(int(d['template_id'])) or {'ok':True})))
            if p=='/api/templates/equipment/apply':
                d=self.body();pid=self.project_id(d);return self.send_json(self.mutate(pid,'Aplicar padrão de equipamento',lambda:models.apply_equipment_template(pid,int(d['template_id']),d.get('equipment_code',''),d.get('route_start'),d.get('gpm'),d.get('work_center'),d.get('plan_id_override'))))
            if p=='/api/balance/auto-preview':
                d=self.body();pid=self.project_id(d);filters=self.balance_filters(d);target=float(d.get('target_minutes') or 0);log(f"BALANCE AUTO PREVIEW INÍCIO projeto={pid} dias={d.get('days',90)} meta={target}");r=balance.auto_balance_preview(pid,d.get('start'),d.get('days',90),target,filters);log(f"BALANCE AUTO PREVIEW OK projeto={pid} alterados={r['changed_items']} tempo={r['elapsed_seconds']}s");return self.send_json(r)
            if p=='/api/balance/manual-preview':
                d=self.body();pid=self.project_id(d);filters=self.balance_filters(d);return self.send_json(balance.manual_preview(pid,d.get('start'),d.get('days',90),d.get('offsets',{}),float(d.get('target_minutes') or 0),filters))
            if p=='/api/balance/apply':
                d=self.body();pid=self.project_id(d);backup.create_backup(f'auto_before_balance_{pid}');return self.send_json(self.mutate(pid,'Aplicar balanceamento PM11',lambda:balance.apply_offsets(pid,d.get('offsets',{}))))
            if p=='/api/history/undo':return self.send_json(history.undo(self.project_id(self.body())))
            if p=='/api/history/redo':return self.send_json(history.redo(self.project_id(self.body())))
            if p=='/api/backup/restore':
                fields,f=self.parse_upload();log(f"BACKUP RESTORE INÍCIO arquivo={f['name']}")
                try:backup.restore_backup(f['path']);log('BACKUP RESTORE OK');return self.send_json({'ok':True})
                finally:
                    try:os.remove(f['path'])
                    except:pass
            if p=='/api/import/preview':
                fields,f=self.parse_upload();mapping=self.json_field(fields,'mapping',None);log(f"IMPORT PREVIEW INÍCIO arquivo={f['name']} tamanho={f['size']/1024/1024:.2f}MB")
                try:
                    r=import_export.preview_import(f['path'],mapping);log(f"IMPORT PREVIEW OK planos={r['counts']['plans']} itens={r['counts']['items']} caracteristicas={r['counts']['characteristics']}")
                    # Preview does not send the whole parsed workbook back to the browser. Confirm re-parses transactionally.
                    r=dict(r);r.pop('data',None);return self.send_json(r)
                finally:
                    try:os.remove(f['path'])
                    except:pass
            if p=='/api/import/confirm':
                fields,f=self.parse_upload();pid=int(fields.get('project_id') or 0);mode=fields.get('mode','MERGE').upper();mapping=self.json_field(fields,'mapping',None);before=history.capture(pid);backup.create_backup(f'auto_before_import_{pid}');log(f"IMPORT CONFIRM INÍCIO projeto={pid} modo={mode} arquivo={f['name']}")
                try:r=import_export.confirm_import(pid,f['path'],mode,mapping);after=history.capture(pid);history.record(pid,'Importar planilha PM11',before,after);log(f"IMPORT CONFIRM OK {r['stats']}");return self.send_json(r)
                finally:
                    try:os.remove(f['path'])
                    except:pass
            return self.err('Rota POST não encontrada.',404)
        except ValueError as e:log(f'POST {p} REGRA | {e}');return self.err(e,400)
        except Exception as e:log(f'POST {p} ERRO | {type(e).__name__}: {e}');traceback.print_exc();return self.err(e,500)

    def do_PUT(self):
        p=self.path_only()
        try:
            d=self.body()
            if p.startswith('/api/projects/'):
                pid=int(p.rsplit('/',1)[1])
                if models.project_is_locked(pid):raise ValueError('Projeto trancado. Destranque o projeto para editar seus dados.')
                return self.send_json(models.update_project(pid,d))
            if p.startswith('/api/plans/'):
                plan_id=int(p.rsplit('/',1)[1]);old=models.get_plan(plan_id);pid=old['project_id'];return self.send_json(self.mutate(pid,'Editar plano',lambda:models.update_plan(plan_id,d)))
            if p.startswith('/api/items/'):
                iid=int(p.rsplit('/',1)[1]);old=models.get_item(iid);pid=old['project_id'];return self.send_json(self.mutate(pid,'Editar item',lambda:models.update_item(iid,d)))
            if p.startswith('/api/characteristics/'):
                cid=int(p.rsplit('/',1)[1]);old=models.get_characteristic(cid);pid=old['project_id'];return self.send_json(self.mutate(pid,'Editar característica',lambda:models.update_characteristic(cid,d)))
            return self.err('Rota PUT não encontrada.',404)
        except ValueError as e:return self.err(e,400)
        except Exception as e:log(f'PUT {p} ERRO {e}');traceback.print_exc();return self.err(e,500)

    def do_DELETE(self):
        p=self.path_only();q=self.query()
        try:
            if p.startswith('/api/projects/'):
                pid=int(p.rsplit('/',1)[1])
                if models.project_is_locked(pid):raise ValueError('Projeto trancado. Destranque o projeto antes de excluir.')
                models.delete_project(pid);return self.send_json({'ok':True})
            if p=='/api/catalogs':models.delete_catalog(q['kind'],q['code']);return self.send_json({'ok':True})
            return self.err('Rota DELETE não encontrada.',404)
        except ValueError as e:return self.err(e,400)
        except Exception as e:log(f'DELETE {p} ERRO {e}');traceback.print_exc();return self.err(e,500)

    def serve_static(self,p):
        if p in ('','/'):p='/index.html'
        rel=os.path.normpath(p.lstrip('/'))
        if rel.startswith('..'):return self.err('Acesso inválido',403)
        path=os.path.join(BASE_DIR,'static',rel)
        if not os.path.isfile(path):path=os.path.join(BASE_DIR,'static','index.html')
        ctype=mimetypes.guess_type(path)[0] or 'application/octet-stream';b=open(path,'rb').read();self.send_response(200);self.send_header('Content-Type',ctype);self.send_header('Content-Length',str(len(b)));self.send_header('Cache-Control','no-cache');self.end_headers();self.wfile.write(b)

if __name__=='__main__':
    run_migrations();log(f'PM11 build {BUILD}');log(f'Banco: {os.path.join(BASE_DIR,"data","pm11.db")}');server=ExclusiveServer(('127.0.0.1',PORT),Handler);url=f'http://127.0.0.1:{PORT}';log(f'Servidor iniciado em {url}')
    try:webbrowser.open(url)
    except:pass
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:server.server_close();log('Servidor encerrado.')
