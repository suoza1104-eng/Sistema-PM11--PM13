import os
import re
import sys
import json
import socket
import sqlite3
import urllib.parse
import webbrowser
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
import datetime
import time
import traceback

# Add root folder to sys.path to resolve imports correctly
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

from core.database import get_db_connection, DB_PATH
from core.migrations import run_migrations
import core.models as models
import core.calculations as calculations
import core.import_service as import_service
import core.export_service as export_service
import core.backup_service as backup_service
import core.auto_balance_service as auto_balance_service
import core.manual_balance_service as manual_balance_service
import core.history_service as history_service
from core.validators import validate_operation_structure
from core.long_text_structure import detect_structure, prepare_for_save, materialize_record
import core_pm11.handler as pm11_handler
import core_pm11.migrations as pm11_migrations

APP_BUILD = '2026.08.19-v6-priorimetro-compacto-multicola'


def _server_trace(event, **fields):
    """Compact operational trace shown in the black PM13 server window."""
    stamp = datetime.datetime.now().strftime('%H:%M:%S')
    detail = ' | '.join(f'{key}={value}' for key, value in fields.items() if value is not None)
    print(f'[PM13 {stamp}] {event}' + (f' | {detail}' if detail else ''), flush=True)


def _server_trace_exception(event, exc, **fields):
    _server_trace(event, error_type=type(exc).__name__, error=str(exc), **fields)
    traceback.print_exc()


def _parse_bool(value, default=False):
    """Parse booleans safely even if a frontend sends strings."""
    if value is None:
        return bool(default)
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    text = str(value).strip().lower()
    if text in ('1', 'true', 'sim', 'yes', 'on'):
        return True
    if text in ('0', 'false', 'nao', 'não', 'no', 'off', ''):
        return False
    return bool(default)



# Single-file compatibility helpers for the mass standard-model workflow.
# They are used only if core/models.py is still from the immediately previous
# PM13 version. This makes app.py sufficient to restore the missing POST routes.
def _bulk_standard_unique_ids(values):
    result = []
    for value in values or []:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            continue
        if parsed > 0 and parsed not in result:
            result.append(parsed)
    return result


def _bulk_standard_tree_compat(cursor, standard_id):
    std = cursor.execute('SELECT * FROM standard_items WHERE id=?', (int(standard_id),)).fetchone()
    if not std:
        raise ValueError(f'Modelo de item padrão id {standard_id} não encontrado.')
    operations = []
    std_ops = cursor.execute(
        'SELECT * FROM standard_item_operations WHERE standard_item_id=? ORDER BY operation_code, id',
        (int(standard_id),),
    ).fetchall()
    for op in std_ops:
        texts = cursor.execute(
            'SELECT * FROM standard_operation_long_texts WHERE standard_operation_id=? ORDER BY id',
            (int(op['id']),),
        ).fetchall()
        operations.append({
            'operation_code': str(op['operation_code'] or '').strip(),
            'suboperation_code': str(op['suboperation_code'] or '').strip(),
            'work_center': op['work_center'],
            'short_text': str(op['short_text'] or '').strip(),
            'unit': str(op['unit'] or 'H').strip() or 'H',
            'headcount': op['headcount'],
            'hours': op['hours'],
            'long_texts': [
                {'group_code': lt['group_code'], 'group_counter': lt['group_counter'], 'text': str(lt['text'] or '')}
                for lt in texts
            ],
        })
    return dict(std), operations


def _bulk_standard_normalize_compat(raw_operations):
    if not isinstance(raw_operations, list) or not raw_operations:
        raise ValueError('O modelo precisa possuir pelo menos uma operação para ser aplicado.')
    normalized, seen = [], set()
    for index, raw in enumerate(raw_operations, 1):
        if not isinstance(raw, dict):
            raise ValueError(f'Operação {index} inválida.')
        code = str(raw.get('operation_code') or '').strip()
        subcode = str(raw.get('suboperation_code') or '').strip()
        short_text = str(raw.get('short_text') or '').strip()
        if not code:
            raise ValueError(f'Informe o código da operação {index}.')
        if not short_text:
            raise ValueError(f'Informe o texto breve da operação {code}.')
        key = (code, subcode)
        if key in seen:
            raise ValueError(f'Operação duplicada na prévia: {code}/{subcode}.')
        seen.add(key)

        def n_int(value):
            if value is None or str(value).strip() == '': return None
            parsed = int(float(str(value).replace(',', '.')))
            if parsed < 0: raise ValueError(f'Efetivo não pode ser negativo na operação {code}.')
            return parsed
        def n_float(value):
            if value is None or str(value).strip() == '': return None
            parsed = float(str(value).replace(',', '.'))
            if parsed < 0: raise ValueError(f'Horas não podem ser negativas na operação {code}.')
            return parsed

        long_texts = []
        for row in raw.get('long_texts') or []:
            if not isinstance(row, dict):
                continue
            value = str(row.get('text') or '').strip()
            if value:
                long_texts.append({
                    'group_code': str(row.get('group_code') or '').strip() or None,
                    'group_counter': str(row.get('group_counter') or '').strip() or None,
                    'text': value,
                })
        normalized.append({
            'operation_code': code,
            'suboperation_code': subcode,
            'work_center': str(raw.get('work_center') or '').strip() or None,
            'short_text': short_text[:40],
            'unit': (str(raw.get('unit') or 'H').strip().upper() or 'H')[:10],
            'headcount': n_int(raw.get('headcount')),
            'hours': n_float(raw.get('hours')),
            'long_texts': long_texts,
        })
    return normalized


def _preview_bulk_standard_structure_compat(project_id, item_ids, standard_id):
    ids = _bulk_standard_unique_ids(item_ids)
    if not ids:
        raise ValueError('Selecione pelo menos um item.')
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        std, operations = _bulk_standard_tree_compat(cur, standard_id)
        if not operations:
            raise ValueError('O modelo selecionado não possui operações para aplicar.')
        marks = ','.join('?' for _ in ids)
        rows = cur.execute(f'''SELECT i.id,i.project_id,i.legacy_identifier,i.object_type,i.object_code,
            i.description,i.gpm,i.work_center,i.condition_code,i.priority,i.plan_id,i.order_type,
            p.legacy_code AS plan_code,p.description AS plan_description
            FROM maintenance_items i LEFT JOIN plans p ON p.id=i.plan_id
            WHERE i.project_id=? AND i.deleted_at IS NULL AND i.id IN ({marks})
            ORDER BY i.display_order,CAST(i.legacy_identifier AS INTEGER),i.legacy_identifier''',
            (int(project_id), *ids)).fetchall()
        if len(rows) != len(ids):
            found = {int(r['id']) for r in rows}
            raise ValueError('Há itens inválidos ou pertencentes a outro projeto: ' + ', '.join(str(i) for i in ids if i not in found))
        counts = cur.execute(f'''SELECT o.item_id,COUNT(DISTINCT o.id) operations_count,COUNT(t.id) long_texts_count
            FROM item_operations o LEFT JOIN operation_long_texts t ON t.operation_id=o.id
            WHERE o.project_id=? AND o.item_id IN ({marks}) GROUP BY o.item_id''',
            (int(project_id), *ids)).fetchall()
        cmap = {int(r['item_id']): (int(r['operations_count'] or 0), int(r['long_texts_count'] or 0)) for r in counts}
        items, conflicts = [], []
        for row in rows:
            item = dict(row)
            oc, tc = cmap.get(int(row['id']), (0, 0))
            item.update({'operations_count': oc, 'long_texts_count': tc, 'has_existing_structure': bool(oc or tc)})
            items.append(item)
            if item['has_existing_structure']: conflicts.append(item)
        lt_count = sum(len(op.get('long_texts') or []) for op in operations)
        return {'standard': {'id': int(std['id']), 'title': std['title'], 'category': std['category'],
                'description': std['description'], 'operations': operations}, 'items': items, 'conflicts': conflicts,
                'summary': {'selected_items': len(items), 'clean_items': len(items)-len(conflicts),
                'conflicting_items': len(conflicts), 'operations_per_item': len(operations),
                'long_texts_per_item': lt_count, 'projected_operations': len(items)*len(operations),
                'projected_long_texts': len(items)*lt_count}}
    finally:
        conn.close()


def _bulk_apply_standard_structure_compat(project_id, item_ids, standard_id, operations=None, conflict_policy='skip'):
    ids = _bulk_standard_unique_ids(item_ids)
    if not ids: raise ValueError('Selecione pelo menos um item.')
    policy = str(conflict_policy or 'skip').strip().lower()
    if policy not in {'skip', 'replace'}: raise ValueError("Política de conflito inválida. Use 'skip' ou 'replace'.")
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        std, db_ops = _bulk_standard_tree_compat(cur, standard_id)
        template = _bulk_standard_normalize_compat(operations if operations is not None else db_ops)
        marks = ','.join('?' for _ in ids)
        items = cur.execute(f'''SELECT id,project_id,legacy_identifier,object_code,description,work_center
            FROM maintenance_items WHERE project_id=? AND deleted_at IS NULL AND id IN ({marks}) ORDER BY display_order,id''',
            (int(project_id), *ids)).fetchall()
        if len(items) != len(ids):
            found = {int(r['id']) for r in items}
            raise ValueError('Há itens inválidos ou pertencentes a outro projeto: ' + ', '.join(str(i) for i in ids if i not in found))
        counts = cur.execute(f'''SELECT o.item_id,COUNT(DISTINCT o.id) operations_count,COUNT(t.id) long_texts_count
            FROM item_operations o LEFT JOIN operation_long_texts t ON t.operation_id=o.id
            WHERE o.project_id=? AND o.item_id IN ({marks}) GROUP BY o.item_id''',
            (int(project_id), *ids)).fetchall()
        cmap = {int(r['item_id']): (int(r['operations_count'] or 0), int(r['long_texts_count'] or 0)) for r in counts}
        result_items=[]; applied=skipped=replaced=op_total=text_total=0
        for item in items:
            iid=int(item['id']); oc,tc=cmap.get(iid,(0,0)); has=bool(oc or tc)
            if has and policy=='skip':
                skipped+=1; result_items.append({'id':iid,'legacy_identifier':item['legacy_identifier'],'status':'skipped','existing_operations':oc,'existing_long_texts':tc}); continue
            if has:
                old_ids=[r[0] for r in cur.execute('SELECT id FROM item_operations WHERE project_id=? AND item_id=?',(int(project_id),iid)).fetchall()]
                if old_ids:
                    old_marks=','.join('?' for _ in old_ids)
                    cur.execute(f'DELETE FROM operation_long_texts WHERE operation_id IN ({old_marks})', tuple(old_ids))
                cur.execute('DELETE FROM item_operations WHERE project_id=? AND item_id=?',(int(project_id),iid)); replaced+=1
            item_ops=item_texts=0
            for op in template:
                cur.execute('''INSERT INTO item_operations(project_id,item_id,operation_code,suboperation_code,work_center,short_text,unit,headcount,hours,status)
                    VALUES(?,?,?,?,?,?,?,?,?,'ACTIVE')''',(int(project_id),iid,op['operation_code'],op['suboperation_code'],op['work_center'] or item['work_center'],op['short_text'],op['unit'],op['headcount'],op['hours']))
                new_op=cur.lastrowid; item_ops+=1
                for seq,lt in enumerate(op.get('long_texts') or [],1):
                    cur.execute('''INSERT INTO operation_long_texts(project_id,operation_id,group_code,group_counter,line_sequence,text)
                        VALUES(?,?,?,?,?,?)''',(int(project_id),new_op,lt.get('group_code'),lt.get('group_counter'),seq,lt['text'])); item_texts+=1
            applied+=1; op_total+=item_ops; text_total+=item_texts
            result_items.append({'id':iid,'legacy_identifier':item['legacy_identifier'],'status':'replaced' if has else 'created','operations_created':item_ops,'long_texts_created':item_texts})
        conn.commit()
        return {'standard_id':int(std['id']),'standard_title':std['title'],'selected_items':len(items),'applied_items':applied,
                'skipped_items':skipped,'replaced_items':replaced,'operations_created':op_total,'long_texts_created':text_total,'items':result_items}
    except Exception:
        conn.rollback(); raise
    finally:
        conn.close()


class ExclusiveThreadingHTTPServer(ThreadingHTTPServer):
    """Prevent two PM13 processes from sharing the same TCP port on Windows."""
    allow_reuse_address = False

    def server_bind(self):
        if hasattr(socket, 'SO_EXCLUSIVEADDRUSE'):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


class PM13RequestHandler(BaseHTTPRequestHandler):
    
    def log_message(self, format, *args):
        # Silence console access logging to keep startup console readable
        pass

    def send_json(self, data, status=200):
        self._response_status = int(status)
        try:
            self.send_response(status)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
            self.send_header('X-PM13-Build', APP_BUILD)
            self.end_headers()
            self.wfile.write(json.dumps(data, ensure_ascii=False).encode('utf-8'))
        except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError):
            # Browsers legitimately cancel stale requests during fast inline
            # edits/navigation. The committed operation must not be reported
            # as a second server failure.
            return

    def send_error_json(self, message, status=400):
        self.send_json({'error': message}, status)

    def send_plan_code_conflict(self, error):
        conflict = dict(getattr(error, 'conflict', {}) or {})
        self.send_json({
            'error_code': 'PLAN_CODE_CONFLICT',
            'error': str(error),
            'conflict': {
                'plan_id': conflict.get('id'),
                'legacy_code': conflict.get('legacy_code'),
                'description': conflict.get('description'),
            },
        }, 409)

    def read_json_body(self):
        if hasattr(self, '_json_body_error'):
            raise self._json_body_error
        if hasattr(self, '_json_body_cache'):
            return self._json_body_cache
        try:
            content_length = int(self.headers.get('Content-Length', 0))
            if content_length == 0:
                self._json_body_cache = {}
                return self._json_body_cache
            body = self.rfile.read(content_length)
            self._json_body_cache = json.loads(body.decode('utf-8'))
            return self._json_body_cache
        except Exception as e:
            self._json_body_error = ValueError(f"Corpo da requisição JSON inválido: {e}")
            raise self._json_body_error

    @staticmethod
    def _history_action_label(method, path):
        """Return the short label displayed beside Undo/Redo."""
        exact = {
            ('POST', '/api/import/confirm'): 'Importar planilha',
            ('POST', '/api/auto-balance/apply'): 'Aplicar balanceamento automático',
            ('POST', '/api/balance/move'): 'Mover plano no balanceamento',
            ('POST', '/api/balance/reassign-item'): 'Reassociar item',
            ('POST', '/api/balance/create-independent-plan'): 'Criar plano independente',
            ('POST', '/api/items/reorder-identifiers'): 'Reordenar identificadores',
            ('POST', '/api/plans/autofill-start-stops'): 'Preencher paradas iniciais',
            ('POST', '/api/plans/bulk-update'): 'Atualizar planos em massa',
            ('POST', '/api/items/bulk-update'): 'Atualizar itens em massa',
            ('POST', '/api/items/bulk-assign-plan'): 'Atribuir plano aos itens',
            ('POST', '/api/items/bulk-apply-standard'): 'Aplicar modelo técnico aos itens',
            ('POST', '/api/operations/bulk-update'): 'Atualizar operações em massa',
            ('POST', '/api/long-texts/bulk-update'): 'Atualizar textos longos em massa',
            ('POST', '/api/priorimeter/bulk-update'): 'Atualizar priorímetro em massa',
            ('POST', '/api/priorimeter/copy'): 'Colar linha do priorímetro',
            ('PUT', '/api/shifts'): 'Atualizar turnos (legado)',
            ('PUT', '/api/cycles'): 'Atualizar catálogo de ciclos',
        }
        if (method, path) in exact:
            return exact[(method, path)]

        match = re.match(
            r'^/api/(projects|teams|plans|items|operations|long-texts|priorimeter)(?:/\d+)?$',
            path,
        )
        if match:
            singular = {
                'projects': 'projeto', 'teams': 'equipe', 'plans': 'plano',
                'items': 'item', 'operations': 'operação',
                'long-texts': 'texto longo', 'priorimeter': 'linha do priorímetro',
            }[match.group(1)]
            verb = {'POST': 'Criar', 'PUT': 'Editar', 'DELETE': 'Excluir'}.get(method, 'Alterar')
            return f'{verb} {singular}'
        if path.startswith('/api/items/from-standard/'):
            return 'Criar item a partir do padrão'
        if path.endswith('/capacities'):
            return 'Atualizar capacidades'
        return 'Atualizar dados do projeto'

    @staticmethod
    def _project_id_for_entity(path):
        """Resolve project ownership from an entity id embedded in the URL."""
        table_by_route = {
            'teams': 'work_teams',
            'plans': 'plans',
            'items': 'maintenance_items',
            'operations': 'item_operations',
            'long-texts': 'operation_long_texts',
            'priorimeter': 'maintenance_items',
        }
        match = re.match(r'^/api/(teams|plans|items|operations|long-texts|priorimeter)/(\d+)(?:/|$)', path)
        if not match:
            return None
        table = table_by_route[match.group(1)]
        conn = get_db_connection()
        try:
            row = conn.execute(
                f'SELECT project_id FROM "{table}" WHERE id = ?',
                (int(match.group(2)),),
            ).fetchone()
            return int(row['project_id']) if row else None
        finally:
            conn.close()

    def _resolve_history_project_id(self, method, path):
        """Find the affected project before a mutation consumes or deletes data."""
        excluded_exact = {
            '/api/projects',
            '/api/auto-balance/preview',
            '/api/items/bulk-standard-preview',
            '/api/long-texts/normalize',
            '/api/long-text-blocks',
            '/api/backups',
            '/api/logs', '/api/shutdown',
        }
        if path in excluded_exact:
            return None
        if path.startswith('/api/standards/') or path.startswith('/api/long-text-blocks/'):
            return None
        if re.match(r'^/api/projects/\d+/duplicate$', path):
            return None
        archive_match = re.match(r'^/api/projects/(\d+)/archive$', path)
        if archive_match:
            return int(archive_match.group(1))
        if re.match(r'^/api/projects/\d+/lock$', path):
            return None

        # Existing project edits and capacities belong to the active project.
        match = re.match(r'^/api/projects/(\d+)(?:/(?:capacities|work-capacity))?$', path)
        if match:
            route_project_id = int(match.group(1))
            return route_project_id

        entity_project_id = self._project_id_for_entity(path)
        if entity_project_id:
            return entity_project_id

        data = {}
        if 'application/json' in self.headers.get('Content-Type', ''):
            try:
                data = self.read_json_body()
            except ValueError:
                return None

        raw_project_id = data.get('project_id') if isinstance(data, dict) else None
        if raw_project_id:
            try:
                return int(raw_project_id)
            except (TypeError, ValueError):
                return None

        # These balance calls carry an entity id rather than project_id.
        lookup = None
        if path == '/api/balance/move' and data.get('plan_id'):
            lookup = ('plans', data.get('plan_id'))
        elif path in ('/api/balance/reassign-item', '/api/balance/create-independent-plan') and data.get('item_id'):
            lookup = ('maintenance_items', data.get('item_id'))
        if lookup:
            conn = get_db_connection()
            try:
                row = conn.execute(
                    f'SELECT project_id FROM "{lookup[0]}" WHERE id = ?',
                    (int(lookup[1]),),
                ).fetchone()
                if row:
                    return int(row['project_id'])
            finally:
                conn.close()

        header_project_id = self.headers.get('X-PM13-Project-ID')
        try:
            return int(header_project_id) if header_project_id else None
        except (TypeError, ValueError):
            return None

    def _handle_project_mutation(self, implementation, method):
        path = urllib.parse.urlparse(self.path).path
        if path.startswith('/api/pm11'):
            implementation()
            return
        self._response_status = 500
        token = None
        try:
            project_id = self._resolve_history_project_id(method, path)
            if project_id and models.is_project_locked(project_id):
                self.send_error_json(
                    'Projeto trancado. Destranque-o na tela Projetos para permitir alterações ou importações.',
                    423,
                )
                return
            if project_id:
                try:
                    token = history_service.begin_external_change(project_id)
                except history_service.HistoryProjectNotFound:
                    # Preserve the route's own not-found/validation response.
                    token = None
            implementation()
        finally:
            if token is not None:
                try:
                    history_service.finalize_external_change(
                        token,
                        self._history_action_label(method, path),
                        metadata={
                            'method': method,
                            'path': path,
                            'response_status': self._response_status,
                        },
                    )
                except Exception:
                    # The business response may already be on the wire.
                    import traceback
                    traceback.print_exc()

    def parse_multipart_body(self):
        """Parses multipart/form-data from request body."""
        content_type = self.headers.get('Content-Type', '')
        boundary_match = re.search(r'boundary=([^;]+)', content_type)
        if not boundary_match:
            raise ValueError("Boundary não encontrado em multipart/form-data.")
            
        boundary = boundary_match.group(1).strip().strip('"\'').encode('utf-8')
        content_length = int(self.headers.get('Content-Length', 0))
        body_bytes = self.rfile.read(content_length)
        
        # Split body by boundary
        parts = body_bytes.split(b'--' + boundary)
        form_fields = {}
        uploaded_files = {}
        
        for part in parts:
            if not part or part == b'\r\n' or part == b'--\r\n' or part == b'--':
                continue
            if b'\r\n\r\n' in part:
                header_part, content_part = part.split(b'\r\n\r\n', 1)
                
                # Strip trailing \r\n from content part
                if content_part.endswith(b'\r\n'):
                    content_part = content_part[:-2]
                    
                header_str = header_part.decode('utf-8', errors='ignore')
                name_match = re.search(r'name="([^"]+)"', header_str)
                filename_match = re.search(r'filename="([^"]+)"', header_str)
                
                if name_match:
                    name = name_match.group(1)
                    if filename_match:
                        filename = filename_match.group(1)
                        if filename: # only if file name is not empty
                            uploaded_files[name] = {
                                'filename': filename,
                                'content': content_part
                            }
                    else:
                        form_fields[name] = content_part.decode('utf-8', errors='ignore').strip()
                        
        return form_fields, uploaded_files

    def serve_static_file(self, relative_path):
        """Serves a static file from static/ directory.
        Redirects non-existent pages to index.html for SPA support.
        """
        # Clean query parameters
        clean_path = relative_path.split('?')[0].split('#')[0]
        
        # Default to index.html
        if clean_path in ['', '/', '/index.html']:
            file_path = os.path.join(BASE_DIR, 'static', 'index.html')
        else:
            # Strip leading slash
            rel = clean_path.lstrip('/')
            file_path = os.path.join(BASE_DIR, 'static', rel)

        # Security check: prevent escaping static/ directory
        static_dir = os.path.join(BASE_DIR, 'static')
        abs_file_path = os.path.abspath(file_path)
        if not abs_file_path.startswith(os.path.abspath(static_dir)):
            self.send_response(403)
            self.end_headers()
            return

        # If file does not exist, serve index.html (SPA fallback for routing)
        if not os.path.exists(abs_file_path) or os.path.isdir(abs_file_path):
            abs_file_path = os.path.join(static_dir, 'index.html')

        # Determine Mime Type
        mime_types = {
            '.html': 'text/html; charset=utf-8',
            '.css': 'text/css; charset=utf-8',
            '.js': 'application/javascript; charset=utf-8',
            '.json': 'application/json; charset=utf-8',
            '.png': 'image/png',
            '.jpg': 'image/jpeg',
            '.gif': 'image/gif',
            '.svg': 'image/svg+xml',
            '.ico': 'image/x-icon'
        }
        ext = os.path.splitext(abs_file_path)[1].lower()
        mime = mime_types.get(ext, 'application/octet-stream')

        try:
            with open(abs_file_path, 'rb') as f:
                content = f.read()
            self.send_response(200)
            self.send_header('Content-Type', mime)
            self.send_header('Content-Length', len(content))
            self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate, max-age=0')
            self.send_header('Pragma', 'no-cache')
            self.send_header('Expires', '0')
            self.send_header('X-PM13-Build', APP_BUILD)
            self.end_headers()
            self.wfile.write(content)
        except Exception as e:
            self.send_response(500)
            self.end_headers()

    def get_cookie(self, name):
        cookie_header = self.headers.get('Cookie')
        if not cookie_header:
            return None
        import http.cookies
        cookies = http.cookies.SimpleCookie()
        try:
            cookies.load(cookie_header)
            if name in cookies:
                return cookies[name].value
        except Exception:
            pass
        return None

    def get_authenticated_user(self):
        token = self.get_cookie('pm13_session') or self.headers.get('X-Session-Token')
        if not token:
            return None
        return models.get_user_by_session(token)

    def do_GET(self):
        url_parsed = urllib.parse.urlparse(self.path)
        path = url_parsed.path
        query = urllib.parse.parse_qs(url_parsed.query)
        
        # Flatten query parameters from lists to single values
        q_params = {k: v[0] for k, v in query.items() if v}

        try:
            # --- API ROUTES ---

            if path == '/api/auth/me':
                user = self.get_authenticated_user()
                if user:
                    self.send_json({'user': user})
                else:
                    self.send_error_json('Não autenticado.', 401)
                return

            if path.startswith('/api/pm11'):
                if pm11_handler.handle_pm11_request(self, 'GET', path, q_params):
                    return

            if path == '/api/health':
                self.send_json({'status': 'ok', 'build': APP_BUILD, 'pid': os.getpid()})
                return

            # GET /api/history/status?project_id=N
            if path == '/api/history/status':
                try:
                    project_id = int(q_params.get('project_id', 0))
                except (TypeError, ValueError):
                    project_id = 0
                if not project_id:
                    self.send_error_json('ID do projeto é obrigatório.')
                    return
                conn = get_db_connection()
                try:
                    project_exists = conn.execute(
                        'SELECT 1 FROM projects WHERE id = ?', (project_id,)
                    ).fetchone() is not None
                finally:
                    conn.close()
                if not project_exists:
                    self.send_error_json('Projeto não encontrado.', 404)
                    return
                state = history_service.get_history_state(project_id)
                self.send_json(state)
                return
            
            # GET /api/projects
            if path == '/api/projects':
                projects = models.list_projects()
                conn = get_db_connection()
                cursor = conn.cursor()
                enhanced_projects = []
                for p in projects:
                    p_dict = dict(p)
                    cursor.execute("SELECT COUNT(*) FROM plans WHERE project_id = ? AND deleted_at IS NULL;", (p['id'],))
                    p_dict['plans_count'] = cursor.fetchone()[0]
                    cursor.execute("SELECT COUNT(*) FROM maintenance_items WHERE project_id = ? AND deleted_at IS NULL;", (p['id'],))
                    p_dict['items_count'] = cursor.fetchone()[0]
                    enhanced_projects.append(p_dict)
                conn.close()
                self.send_json(enhanced_projects)
                return
                
            # GET /api/projects/{id}/work-capacity
            match = re.match(r'^/api/projects/(\d+)/work-capacity$', path)
            if match:
                p_id = int(match.group(1))
                self.send_json(models.get_project_work_capacity_settings(p_id))
                return

            # GET /api/projects/{id}/capacities
            match = re.match(r'^/api/projects/(\d+)/capacities$', path)
            if match:
                p_id = int(match.group(1))
                self.send_json(models.get_project_capacities(p_id))
                return

            # GET /api/projects/{id}
            match = re.match(r'^/api/projects/(\d+)$', path)
            if match:
                p_id = int(match.group(1))
                proj = models.get_project(p_id)
                if proj:
                    self.send_json(proj)
                else:
                    self.send_error_json("Projeto não encontrado.", 404)
                return

            # GET /api/standards/long-texts
            if path == '/api/standards/long-texts':
                self.send_json(models.get_standard_long_texts())
                return

            # GET /api/long-text-blocks
            if path == '/api/long-text-blocks':
                self.send_json(models.get_standard_long_text_blocks())
                return

            # GET /api/standards/items/{id}
            match = re.match(r'^/api/standards/items/(\d+)$', path)
            if match:
                std_id = int(match.group(1))
                detail = models.get_standard_item_detail(std_id)
                if detail:
                    self.send_json(detail)
                else:
                    self.send_error_json("Modelo de item padrão não encontrado.", 404)
                return

            # GET /api/standards/items
            if path == '/api/standards/items':
                self.send_json(models.get_standard_items())
                return

            # GET /api/priorimeter
            if path == '/api/priorimeter':
                proj_id = int(q_params.get('project_id', 0))
                if not proj_id:
                    self.send_error_json('ID do projeto é obrigatório.')
                    return
                rows = models.list_priorimeter(
                    proj_id, search=q_params.get('search'), status=q_params.get('status', 'ACTIVE')
                )
                total = len(rows)
                completed = sum(1 for row in rows if row.get('complete'))
                self.send_json({'rows': rows, 'total': total, 'completed': completed, 'fields': models.PRIORIMETER_FIELDS})
                return

            # GET /api/priorimeter/export
            if path == '/api/priorimeter/export':
                proj_id = int(q_params.get('project_id', 0))
                if not proj_id:
                    self.send_error_json('ID do projeto é obrigatório.')
                    return
                rows = models.list_priorimeter(
                    proj_id, search=q_params.get('search'), status=q_params.get('status', 'ACTIVE')
                )
                content = export_service.export_priorimeter_xlsx(rows)
                stamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
                filename = f'priorimetro_SAP_{stamp}.xlsx'
                self.send_response(200)
                self.send_header('Content-Type', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
                self.send_header('Content-Disposition', f'attachment; filename="{filename}"')
                self.send_header('Content-Length', len(content))
                self.end_headers()
                self.wfile.write(content)
                return

            # GET /api/plans
            if path == '/api/plans':
                proj_id = int(q_params.get('project_id', 0))
                limit = int(q_params.get('limit', 25))
                offset = int(q_params.get('offset', 0))
                order_by = q_params.get('order_by', 'legacy_code')
                order_dir = q_params.get('order_dir', 'ASC')
                
                plans = models.list_plans(proj_id, q_params, limit, offset, order_by, order_dir)
                total = models.count_plans(proj_id, q_params)
                self.send_json({'plans': plans, 'total': total})
                return
                
            # GET /api/plans/{id}
            match = re.match(r'^/api/plans/(\d+)$', path)
            if match:
                plan_id = int(match.group(1))
                plan = models.get_plan(plan_id)
                if plan:
                    self.send_json(plan)
                else:
                    self.send_error_json("Plano não encontrado.", 404)
                return

            # GET /api/items
            if path == '/api/items':
                proj_id = int(q_params.get('project_id', 0))
                limit = int(q_params.get('limit', 25))
                offset = int(q_params.get('offset', 0))
                order_by = q_params.get('order_by', 'display_order')
                order_dir = q_params.get('order_dir', 'ASC')
                
                items = models.list_items(proj_id, q_params, limit, offset, order_by, order_dir)
                total = models.count_items(proj_id, q_params)
                self.send_json({'items': items, 'total': total})
                return

            if path == '/api/operations':
                proj_id = int(q_params.get('project_id', 0))
                search = q_params.get('search', '').strip()
                work_center = q_params.get('work_center', '').strip()
                item_id = q_params.get('item_id')
                limit_param = q_params.get('limit')
                limit = 100000 if not limit_param or str(limit_param).lower() == 'all' else int(limit_param)
                offset = int(q_params.get('offset', 0))
                
                order_by = q_params.get('order_by', 'legacy_identifier').strip().lower()
                order_dir = q_params.get('order_dir', 'asc').strip().lower()
                if order_dir not in ('asc', 'desc'):
                    order_dir = 'asc'

                conn = get_db_connection(); cursor = conn.cursor()
                where = ["o.project_id = ?"]
                params = [proj_id]
                if item_id:
                    where.append("o.item_id = ?")
                    params.append(int(item_id))
                if work_center:
                    where.append("o.work_center = ?")
                    params.append(work_center)
                if search:
                    where.append("(i.legacy_identifier LIKE ? OR o.operation_code LIKE ? OR o.suboperation_code LIKE ? OR o.work_center LIKE ? OR o.short_text LIKE ? OR i.object_code LIKE ?)")
                    s_term = f"%{search}%"
                    params.extend([s_term, s_term, s_term, s_term, s_term, s_term])
                where_str = " AND ".join(where)

                cursor.execute(f"SELECT COUNT(*) FROM item_operations o LEFT JOIN maintenance_items i ON i.id=o.item_id AND i.deleted_at IS NULL WHERE {where_str}", params)
                total = cursor.fetchone()[0]

                if order_by in ('legacy_identifier', 'item_id', 'id', 'item'):
                    order_clause = f"""
                        CAST(i.legacy_identifier AS INTEGER) {order_dir.upper()}, 
                        i.legacy_identifier {order_dir.upper()}, 
                        COALESCE(o.operation_code, '') ASC,
                        CASE WHEN o.suboperation_code IS NULL OR o.suboperation_code = '' OR o.suboperation_code = '-' THEN 0 ELSE 1 END ASC,
                        COALESCE(o.suboperation_code, '') ASC,
                        o.id ASC
                    """
                elif order_by in ('operation_code', 'oper'):
                    order_clause = f"""
                        COALESCE(o.operation_code, '') {order_dir.upper()},
                        CASE WHEN o.suboperation_code IS NULL OR o.suboperation_code = '' OR o.suboperation_code = '-' THEN 0 ELSE 1 END ASC,
                        COALESCE(o.suboperation_code, '') ASC,
                        CAST(i.legacy_identifier AS INTEGER) ASC,
                        o.id ASC
                    """
                elif order_by in ('suboperation_code', 'subop'):
                    order_clause = f"""
                        CASE WHEN o.suboperation_code IS NULL OR o.suboperation_code = '' OR o.suboperation_code = '-' THEN 0 ELSE 1 END {order_dir.upper()},
                        COALESCE(o.suboperation_code, '') {order_dir.upper()},
                        CAST(i.legacy_identifier AS INTEGER) ASC,
                        COALESCE(o.operation_code, '') ASC,
                        o.id ASC
                    """
                elif order_by in ('work_center', 'ct'):
                    order_clause = f"""
                        COALESCE(o.work_center, '') {order_dir.upper()},
                        CAST(i.legacy_identifier AS INTEGER) ASC,
                        COALESCE(o.operation_code, '') ASC,
                        o.id ASC
                    """
                elif order_by in ('short_text', 'item_description'):
                    order_clause = f"""
                        COALESCE(o.short_text, '') {order_dir.upper()},
                        CAST(i.legacy_identifier AS INTEGER) ASC,
                        o.id ASC
                    """
                elif order_by == 'headcount':
                    order_clause = f"""
                        COALESCE(o.headcount, 0) {order_dir.upper()},
                        CAST(i.legacy_identifier AS INTEGER) ASC,
                        o.id ASC
                    """
                elif order_by == 'hours':
                    order_clause = f"""
                        COALESCE(o.hours, 0) {order_dir.upper()},
                        CAST(i.legacy_identifier AS INTEGER) ASC,
                        o.id ASC
                    """
                else:
                    order_clause = f"""
                        CAST(i.legacy_identifier AS INTEGER) ASC, 
                        i.legacy_identifier ASC, 
                        COALESCE(o.operation_code, '') ASC,
                        CASE WHEN o.suboperation_code IS NULL OR o.suboperation_code = '' OR o.suboperation_code = '-' THEN 0 ELSE 1 END ASC,
                        COALESCE(o.suboperation_code, '') ASC,
                        o.id ASC
                    """

                cursor.execute(f"""SELECT o.*, i.legacy_identifier, i.object_code, i.description as item_description,
                                         (SELECT COUNT(*) FROM operation_long_texts t
                                          WHERE t.operation_id=o.id AND TRIM(COALESCE(t.text, ''))<>'') AS long_text_count
                                  FROM item_operations o LEFT JOIN maintenance_items i ON i.id=o.item_id AND i.deleted_at IS NULL
                                  WHERE {where_str}
                                  ORDER BY {order_clause}
                                  LIMIT ? OFFSET ?""", params + [limit, offset])
                rows = [models.to_dict(x) for x in cursor.fetchall()]
                cursor.execute("""SELECT item_id, suboperation_code FROM item_operations
                                  WHERE project_id=? AND operation_code='0010' AND suboperation_code<>''""", (proj_id,))
                item_suboperations = {}
                for sub_row in cursor.fetchall():
                    item_suboperations.setdefault(sub_row['item_id'], set()).add(sub_row['suboperation_code'])
                for row in rows:
                    try:
                        imported_issues = json.loads(row.get('validation_issues_json') or '[]')
                    except (TypeError, ValueError):
                        imported_issues = []
                    structural_issues = validate_operation_structure(
                        row['operation_code'], row['suboperation_code'], row['short_text'],
                        row['long_text_count'], item_suboperations.get(row['item_id']))
                    if not row.get('legacy_identifier'):
                        structural_issues.append({'code': 'operation_without_item', 'severity': 'ERROR',
                                                  'message': 'Operação sem item existente atrelado.'})
                    row['validation_issues'] = imported_issues + structural_issues
                    row['validation_status'] = 'ERROR' if row['validation_issues'] else 'OK'
                conn.close()
                self.send_json({'operations': rows, 'total': total})
                return

            if path == '/api/long-texts':
                proj_id = int(q_params.get('project_id', 0))
                search = q_params.get('search', '').strip()
                operation_id = q_params.get('operation_id')
                limit_param = q_params.get('limit')
                limit = 100000 if not limit_param or str(limit_param).lower() == 'all' else int(limit_param)
                offset = int(q_params.get('offset', 0))

                conn = get_db_connection(); cursor = conn.cursor()
                where = ["t.project_id = ?"]
                params = [proj_id]
                if operation_id:
                    where.append("t.operation_id = ?")
                    params.append(int(operation_id))
                if search:
                    where.append("(i.legacy_identifier LIKE ? OR o.operation_code LIKE ? OR o.short_text LIKE ? OR t.text LIKE ?)")
                    s_term = f"%{search}%"
                    params.extend([s_term, s_term, s_term, s_term])
                where_str = " AND ".join(where)

                cursor.execute(f"""SELECT COUNT(*) FROM operation_long_texts t
                                  LEFT JOIN item_operations o ON o.id=t.operation_id
                                  LEFT JOIN maintenance_items i ON i.id=o.item_id AND i.deleted_at IS NULL
                                  WHERE {where_str}""", params)
                total = cursor.fetchone()[0]

                cursor.execute(f"""SELECT t.*, o.item_id, o.operation_code, o.suboperation_code, o.short_text as op_short_text, o.work_center,
                                         i.legacy_identifier, i.object_code, i.description AS item_description
                                  FROM operation_long_texts t
                                  LEFT JOIN item_operations o ON o.id=t.operation_id
                                  LEFT JOIN maintenance_items i ON i.id=o.item_id AND i.deleted_at IS NULL
                                  WHERE {where_str}
                                  ORDER BY COALESCE(t.display_order,t.id), t.id
                                  LIMIT ? OFFSET ?""", params + [limit, offset])
                rows = [models.to_dict(x) for x in cursor.fetchall()]
                for row in rows:
                    row['text'] = materialize_record(row)
                    try:
                        row['validation_issues'] = json.loads(row.get('validation_issues_json') or '[]')
                    except (TypeError, ValueError):
                        row['validation_issues'] = []
                    if not row.get('operation_code'):
                        row['validation_issues'].append({'code': 'long_text_without_operation', 'severity': 'ERROR',
                                                        'message': 'Texto longo sem operação existente atrelada.'})
                    elif not row.get('legacy_identifier'):
                        row['validation_issues'].append({'code': 'long_text_without_item', 'severity': 'ERROR',
                                                        'message': 'Texto longo sem ID de item existente.'})
                    row['validation_status'] = ('ERROR' if row['validation_issues'] else 'OK')
                conn.close()
                self.send_json({'long_texts': rows, 'total': total})
                return

            match = re.match(r'^/api/items/(\d+)/sap-order$', path)
            if match:
                item_id = int(match.group(1))
                conn = get_db_connection(); cursor = conn.cursor()
                cursor.execute("""SELECT i.*, p.legacy_code AS plan_code, p.description AS plan_description,
                                         p.cycle, p.unit AS plan_unit, pr.name AS project_name,
                                         pr.current_counter
                                  FROM maintenance_items i
                                  LEFT JOIN plans p ON p.id=i.plan_id
                                  JOIN projects pr ON pr.id=i.project_id
                                  WHERE i.id=? AND i.deleted_at IS NULL""", (item_id,))
                item_row = cursor.fetchone()
                if not item_row:
                    conn.close(); self.send_error_json('Item não encontrado.', 404); return
                item = models.to_dict(item_row)
                cursor.execute("""SELECT o.* FROM item_operations o WHERE o.item_id=?
                                  ORDER BY CAST(o.operation_code AS INTEGER), o.suboperation_code""", (item_id,))
                operations = [models.to_dict(row) for row in cursor.fetchall()]
                operation_ids = [row['id'] for row in operations]
                texts_by_operation = {}
                if operation_ids:
                    placeholders = ','.join('?' for _ in operation_ids)
                    cursor.execute(f"""SELECT * FROM operation_long_texts WHERE operation_id IN ({placeholders})
                                      ORDER BY operation_id, line_sequence""", operation_ids)
                    for text_row in cursor.fetchall():
                        text_data = models.to_dict(text_row)
                        text_data['text'] = materialize_record(text_data)
                        texts_by_operation.setdefault(text_data['operation_id'], []).append(text_data)
                for operation in operations:
                    operation['long_texts'] = texts_by_operation.get(operation['id'], [])
                conn.close()
                self.send_json({'item': item, 'operations': operations})
                return
                
            # GET /api/items/{id}
            match = re.match(r'^/api/items/(\d+)$', path)
            if match:
                item_id = int(match.group(1))
                item = models.get_item(item_id)
                if item:
                    self.send_json(item)
                else:
                    self.send_error_json("Item não encontrado.", 404)
                return

            # GET /api/dashboard
            if path == '/api/dashboard':
                proj_id = int(q_params.get('project_id', 0))
                if not proj_id:
                    self.send_error_json("ID do projeto é obrigatório.")
                    return
                    
                conn = get_db_connection()
                cursor = conn.cursor()
                
                # Fetch simple counts
                cursor.execute("SELECT COUNT(*) FROM plans WHERE project_id = ? AND deleted_at IS NULL;", (proj_id,))
                total_plans = cursor.fetchone()[0]
                
                cursor.execute("SELECT COUNT(*) FROM plans WHERE project_id = ? AND status = 'ACTIVE' AND deleted_at IS NULL;", (proj_id,))
                active_plans = cursor.fetchone()[0]
                
                cursor.execute("""
                SELECT COUNT(*) FROM plans p 
                LEFT JOIN maintenance_items i ON p.id = i.plan_id AND i.deleted_at IS NULL AND i.status = 'ACTIVE'
                WHERE p.project_id = ? AND p.deleted_at IS NULL AND i.id IS NULL;
                """, (proj_id,))
                plans_without_items = cursor.fetchone()[0]
                
                cursor.execute("SELECT COUNT(*) FROM plans WHERE project_id = ? AND phase <= 0 AND deleted_at IS NULL;", (proj_id,))
                plans_without_counter = cursor.fetchone()[0]
                
                cursor.execute("SELECT COUNT(*) FROM maintenance_items WHERE project_id = ? AND deleted_at IS NULL;", (proj_id,))
                total_items = cursor.fetchone()[0]
                
                cursor.execute("SELECT COUNT(*) FROM maintenance_items WHERE project_id = ? AND status = 'ACTIVE' AND deleted_at IS NULL;", (proj_id,))
                active_items = cursor.fetchone()[0]

                cursor.execute("""SELECT UPPER(COALESCE(validation_status,'OK')) status, COUNT(*) total
                    FROM maintenance_items WHERE project_id=? AND deleted_at IS NULL
                    GROUP BY UPPER(COALESCE(validation_status,'OK'))""", (proj_id,))
                quality_distribution = {str(row[0] or 'OK'): int(row[1] or 0) for row in cursor.fetchall()}

                cursor.execute("""SELECT COALESCE(NULLIF(TRIM(condition_code),''),'NAO DEFINIDO') method, COUNT(*) total
                    FROM maintenance_items WHERE project_id=? AND deleted_at IS NULL
                    GROUP BY COALESCE(NULLIF(TRIM(condition_code),''),'NAO DEFINIDO')
                    ORDER BY total DESC, method""", (proj_id,))
                method_distribution = [{'label': str(row[0]), 'value': int(row[1] or 0)} for row in cursor.fetchall()]
                
                cursor.execute("SELECT COUNT(*) FROM maintenance_items WHERE project_id = ? AND plan_id IS NULL AND deleted_at IS NULL;", (proj_id,))
                items_without_plan = cursor.fetchone()[0]
                
                cursor.execute("SELECT COUNT(*) FROM maintenance_items WHERE project_id = ? AND headcount IS NULL AND deleted_at IS NULL;", (proj_id,))
                items_without_headcount = cursor.fetchone()[0]
                
                cursor.execute("SELECT COUNT(*) FROM maintenance_items WHERE project_id = ? AND duration_hours = 0 AND deleted_at IS NULL;", (proj_id,))
                items_duration_zero = cursor.fetchone()[0]
                
                cursor.execute("SELECT COUNT(*) FROM maintenance_items WHERE project_id = ? AND character_count > 35 AND deleted_at IS NULL;", (proj_id,))
                items_long_desc = cursor.fetchone()[0]

                cursor.execute("""SELECT COUNT(*) FROM item_operations o
                    LEFT JOIN maintenance_items i ON i.id=o.item_id AND i.deleted_at IS NULL
                    WHERE o.project_id=? AND i.id IS NULL""", (proj_id,))
                operations_without_item = cursor.fetchone()[0]
                cursor.execute("""SELECT COUNT(*) FROM operation_long_texts t
                    LEFT JOIN item_operations o ON o.id=t.operation_id
                    LEFT JOIN maintenance_items i ON i.id=o.item_id AND i.deleted_at IS NULL
                    WHERE t.project_id=? AND (o.id IS NULL OR i.id IS NULL)""", (proj_id,))
                long_texts_without_chain = cursor.fetchone()[0]
                
                conn.close()
                
                # Fetch balance metrics (total HH, peaks, average)
                balance = calculations.project_balance(proj_id)
                kpis = balance['kpis']
                
                # Count total inconsistencies
                inconsistencies = (
                    plans_without_counter + 
                    items_without_plan + 
                    items_without_headcount + 
                    items_duration_zero + 
                    items_long_desc + 
                    operations_without_item +
                    long_texts_without_chain +
                    kpis['items_skipped_count']
                )
                
                dashboard_data = {
                    'total_plans': total_plans,
                    'active_plans': active_plans,
                    'plans_without_items': plans_without_items,
                    'plans_without_counter': plans_without_counter,
                    'total_items': total_items,
                    'active_items': active_items,
                    'inactive_items': max(0, total_items - active_items),
                    'quality_distribution': quality_distribution,
                    'method_distribution': method_distribution,
                    'items_without_plan': items_without_plan,
                    'items_without_headcount': items_without_headcount,
                    'items_duration_zero': items_duration_zero,
                    'items_long_desc': items_long_desc,
                    'operations_without_item': operations_without_item,
                    'long_texts_without_chain': long_texts_without_chain,
                    'total_hh': kpis['total_hh'],
                    'avg_hh': kpis['avg_hh'],
                    'max_hh': kpis['max_hh'],
                    'busy_stop': kpis['busy_stop'],
                    'max_headcount': kpis['max_headcount'],
                    'total_orders': sum(s['total_orders'] for s in balance['stops']),
                    'inconsistencies_count': inconsistencies
                }
                
                self.send_json(dashboard_data)
                return

            # GET /api/balance
            if path == '/api/balance':
                proj_id = int(q_params.get('project_id', 0))
                grouping = q_params.get('grouping', 'none')
                
                # Construct filters for calculations
                filters = {}
                for key in ['gpm', 'work_center', 'condition_code', 'priority', 'cycle', 'plan_id', 'plan_ids', 'item_ids', 'search', 'horizon', 'team_id', 'item_identifiers', 'manual_session_id']:
                    val = q_params.get(key)
                    if val and str(val).strip() not in ['undefined', 'null', 'None', 'all', '']:
                        filters[key] = str(val).strip()
                        
                balance = calculations.project_balance(proj_id, filters, grouping)
                self.send_json(balance)
                return

            # GET /api/auto-balance/rules
            if path == '/api/auto-balance/rules':
                proj_id = int(q_params.get('project_id', 0))
                if not proj_id:
                    self.send_error_json("project_id é obrigatório.")
                    return
                self.send_json({
                    'rules': auto_balance_service.list_rules(proj_id),
                    'preferences': auto_balance_service.get_preferences(proj_id),
                })
                return

            # GET /api/manual-balance/session and Book endpoints
            if path == '/api/manual-balance/session':
                proj_id = int(q_params.get('project_id', 0))
                self.send_json({'session': manual_balance_service.get_active_session(proj_id)})
                return

            if path == '/api/manual-balance/book':
                proj_id = int(q_params.get('project_id', 0))
                session_id = int(q_params.get('session_id', 0))
                cycles = [x for x in str(q_params.get('cycles') or '').split(',') if x.strip()]
                states = [x for x in str(q_params.get('states') or '').split(',') if x.strip()]
                result = manual_balance_service.list_book(
                    proj_id, session_id, q_params.get('search', ''), cycles, states,
                    q_params.get('plan_query', ''),
                    str(q_params.get('only_pending', '')).lower() in ('1', 'true', 'yes'))
                self.send_json(result)
                return

            if path == '/api/manual-balance/candidates':
                proj_id = int(q_params.get('project_id', 0))
                session_id = int(q_params.get('session_id', 0))
                target_stop = int(q_params.get('target_stop', 0))
                item_ids = [int(x) for x in str(q_params.get('item_ids') or '').split(',') if x.strip().isdigit()]
                self.send_json({'candidates': manual_balance_service.candidate_plans(
                    proj_id, session_id, item_ids, target_stop)})
                return

            # GET /api/balance/plans-for-stop
            if path == '/api/balance/plans-for-stop':
                proj_id = int(q_params.get('project_id', 0))
                stop_counter = int(q_params.get('stop_counter', 0))
                
                if not proj_id or not stop_counter:
                    self.send_error_json("project_id e stop_counter são obrigatórios.")
                    return
                
                # Fetch project current_counter
                conn = get_db_connection()
                try:
                    cursor = conn.cursor()
                    cursor.execute("SELECT current_counter FROM projects WHERE id = ?;", (proj_id,))
                    row = cursor.fetchone()
                    if not row:
                        self.send_error_json("Projeto não encontrado.")
                        return
                    current_counter = row['current_counter']
                    
                    # Fetch all active plans in this project
                    cursor.execute("""
                        SELECT id, legacy_code, description, cycle, unit, reference_counter
                        FROM plans
                        WHERE project_id = ? AND deleted_at IS NULL AND status = 'ACTIVE'
                    """, (proj_id,))
                    all_plans = cursor.fetchall()
                    
                    # Filter plans that occur in this stop_counter
                    matching_plans = []
                    for plan in all_plans:
                        ref_cnt = plan['reference_counter']
                        cycle = plan['cycle']
                        
                        if calculations.plan_occurs_on_stop(ref_cnt, cycle, stop_counter):
                            matching_plans.append({
                                    'id': plan['id'],
                                    'legacy_code': plan['legacy_code'],
                                    'description': plan['description'],
                                    'cycle': plan['cycle'],
                                    'unit': plan['unit'],
                                    'reference_counter': plan['reference_counter']
                                })
                                
                    self.send_json({'plans': matching_plans})
                except Exception as ex:
                    self.send_error_json(f"Erro ao listar planos da parada: {ex}", 500)
                finally:
                    conn.close()
                return

            # GET /api/balance/stop/{counter}
            match = re.match(r'^/api/balance/stop/(\d+)$', path)
            if match:
                stop_counter = int(match.group(1))
                proj_id = int(q_params.get('project_id', 0))
                manual_session_id = int(q_params.get('manual_session_id', 0) or 0)
                if manual_session_id:
                    self.send_json(manual_balance_service.stop_details(
                        proj_id, manual_session_id, stop_counter,
                        int(q_params.get('horizon', 12) or 12)))
                    return
                
                # Apply current filters
                filters = {}
                for key in ['gpm', 'work_center', 'condition_code', 'priority', 'cycle', 'plan_id', 'plan_ids', 'item_ids', 'search', 'team_id', 'item_identifiers', 'horizon']:
                    if key in q_params:
                        filters[key] = q_params[key]
                        
                # Fetch all active items, compute their occurrences, and filter for this stop
                balance_details = calculations.project_balance(proj_id, filters, 'none')
                
                # Get the detailed stop info matching stop_counter
                target_stop = None
                for st in balance_details['stops']:
                    if st['counter'] == stop_counter:
                        target_stop = st
                        break
                        
                if not target_stop:
                    self.send_json({'orders': [], 'stop_info': {'counter': stop_counter, 'total_orders': 0}})
                    return
                    
                # To get detailed item rows, we query DB again for items that occur on this stop
                conn = get_db_connection()
                cursor = conn.cursor()
                query = """
                SELECT 
                    i.*, p.legacy_code as plan_code, p.description as plan_description, 
                    p.cycle, p.unit, p.reference_counter
                FROM maintenance_items i
                LEFT JOIN plans p ON i.plan_id = p.id
                WHERE i.project_id = ? AND i.deleted_at IS NULL AND i.status = 'ACTIVE'
                  AND p.deleted_at IS NULL AND p.status = 'ACTIVE' AND p.reference_counter IS NOT NULL
                """
                params = [proj_id]
                item_ids = [int(x) for x in str(filters.get('item_ids') or '').split(',') if x.strip().isdigit()]
                if item_ids:
                    query += " AND i.id IN (" + ",".join("?" for _ in item_ids) + ")"; params.extend(item_ids)
                plan_ids = [int(x) for x in str(filters.get('plan_ids') or '').split(',') if x.strip().isdigit()]
                if plan_ids:
                    query += " AND p.id IN (" + ",".join("?" for _ in plan_ids) + ")"; params.extend(plan_ids)
                identifiers = [x.strip() for x in str(filters.get('item_identifiers') or '').split(',') if x.strip()]
                if identifiers:
                    query += " AND i.legacy_identifier IN (" + ",".join("?" for _ in identifiers) + ")"
                    params.extend(identifiers)
                
                # Apply query filters
                if filters.get('work_center'):
                    query += " AND i.work_center = ?"
                    params.append(filters['work_center'])
                if filters.get('gpm'):
                    query += " AND i.gpm = ?"
                    params.append(filters['gpm'])
                if filters.get('condition_code'):
                    query += " AND i.condition_code = ?"
                    params.append(filters['condition_code'])
                if filters.get('priority') is not None and filters.get('priority') != '':
                    query += " AND i.priority = ?"
                    params.append(int(filters['priority']))
                if filters.get('cycle'):
                    query += " AND p.cycle = ?"
                    params.append(int(filters['cycle']))
                if filters.get('plan_id'):
                    query += " AND i.plan_id = ?"
                    params.append(int(filters['plan_id']))
                if filters.get('search'):
                    term = f"%{filters['search']}%"
                    query += " AND (i.description LIKE ? OR i.legacy_identifier LIKE ? OR i.object_code LIKE ?)"
                    params.extend([term, term, term])
                    
                cursor.execute(query, params)
                all_items = cursor.fetchall()
                conn.close()
                
                matching_orders = []
                for item in all_items:
                    # PLAN = CLOCK: the order follows the plan phase/cycle.
                    # legacy_start (PRD INÍCIO) is kept only as legacy metadata.
                    if calculations.plan_occurs_on_stop(
                        item['reference_counter'], item['cycle'], stop_counter
                    ):
                        matching_orders.append(models.to_dict(item))
                        
                # Add stop number
                target_stop_data = {
                    'stop_num': target_stop['stop_num'],
                    'counter': stop_counter,
                    'total_hh': target_stop['total_hh'],
                    'total_duration': target_stop['total_duration'],
                    'total_orders': len(matching_orders),
                    'headcount_needed': target_stop['headcount_needed'],
                    'mec_hh': target_stop.get('mec_hh', 0.0),
                    'mec_headcount_needed': target_stop.get('mec_headcount_needed', 0),
                    'ele_hh': target_stop.get('ele_hh', 0.0),
                    'ele_headcount_needed': target_stop.get('ele_headcount_needed', 0),
                    'sol_hh': target_stop.get('sol_hh', 0.0),
                    'sol_headcount_needed': target_stop.get('sol_headcount_needed', 0),
                    'grouped_hh': target_stop['grouped_hh']
                }
                
                self.send_json({
                    'orders': matching_orders,
                    'stop_info': target_stop_data
                })
                return

            # GET /api/shifts
            if path == '/api/shifts':
                proj_id = int(q_params.get('project_id', 0))
                self.send_json(models.list_shifts(proj_id))
                return

            # GET /api/teams
            if path == '/api/teams':
                proj_id = int(q_params.get('project_id', 0))
                self.send_json(models.list_teams(proj_id))
                return

            # GET /api/teams/{id}
            match = re.match(r'^/api/teams/(\d+)$', path)
            if match:
                team_id = int(match.group(1))
                team = models.get_team(team_id)
                if team:
                    self.send_json(team)
                else:
                    self.send_error_json("Equipe não encontrada.", 404)
                return

            # GET /api/cycles
            if path == '/api/cycles':
                proj_id = int(q_params.get('project_id', 0))
                self.send_json(models.list_cycle_catalog(proj_id))
                return

            # GET /api/audit
            if path == '/api/audit':
                proj_id = int(q_params.get('project_id', 0))
                limit = int(q_params.get('limit', 100))
                offset = int(q_params.get('offset', 0))
                self.send_json(models.get_audit_log(proj_id, limit, offset))
                return

            # GET /api/imports/history
            if path == '/api/imports/history':
                proj_id = int(q_params.get('project_id', 0))
                self.send_json(models.get_imports_history(proj_id))
                return
                
            # GET /api/imports/{id}/errors
            match = re.match(r'^/api/imports/(\d+)/errors$', path)
            if match:
                imp_id = int(match.group(1))
                self.send_json(models.get_import_errors(imp_id))
                return

            # GET /api/backups
            if path == '/api/backups':
                self.send_json(backup_service.list_backups())
                return

            # GET /api/export (Handles downloads)
            if path == '/api/export':
                export_started = time.perf_counter()
                export_type = q_params.get('type')
                export_format = q_params.get('format', 'csv').lower()
                proj_id = int(q_params.get('project_id', 0))
                _server_trace('EXPORT INICIO', projeto=proj_id, tipo=export_type, formato=export_format, escopo=q_params.get('scope'))
                
                if not proj_id:
                    self.send_error_json("ID do projeto é obrigatório.")
                    return
                    
                # Setup filters
                filters = {}
                for key in ['gpm', 'work_center', 'condition_code', 'priority', 'cycle', 'plan_id', 'plan_ids', 'item_ids', 'search', 'team_id', 'item_identifiers', 'without_plan', 'without_headcount', 'duration_zero', 'long_desc', 'horizon', 'manual_session_id']:
                    if key in q_params:
                        filters[key] = q_params[key]
                        
                filename = f"export_{export_type}_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
                content = b""

                if export_type in ('full', 'template'):
                    scope = q_params.get('scope', 'full')
                    plans = models.list_plans(proj_id, {}, limit=None, offset=0)
                    items = models.list_items(proj_id, {}, limit=None, offset=0)
                    conn = get_db_connection()
                    cursor = conn.cursor()
                    cursor.execute("""SELECT o.*, i.legacy_identifier, i.object_type, i.object_code
                                      FROM item_operations o JOIN maintenance_items i ON i.id=o.item_id
                                      WHERE o.project_id=? AND o.status='ACTIVE' AND i.deleted_at IS NULL
                                      ORDER BY CAST(i.legacy_identifier AS INTEGER), o.operation_code, o.suboperation_code""", (proj_id,))
                    operations = [models.to_dict(x) for x in cursor.fetchall()]
                    cursor.execute("""SELECT t.*, o.operation_code, o.suboperation_code,
                                             i.legacy_identifier, i.object_type, i.object_code
                                      FROM operation_long_texts t JOIN item_operations o ON o.id=t.operation_id
                                      JOIN maintenance_items i ON i.id=o.item_id
                                      WHERE t.project_id=? ORDER BY CAST(i.legacy_identifier AS INTEGER),
                                      o.operation_code, o.suboperation_code, t.line_sequence""", (proj_id,))
                    long_texts = [models.to_dict(x) for x in cursor.fetchall()]
                    conn.close()
                    balance = calculations.project_balance(proj_id, {}) if scope == 'full' else {'stops': []}
                    # The available-HH line is the project's current managerial target.
                    target_hh = balance.get('kpis', {}).get('avg_hh', 0)
                    for stop in balance.get('stops', []):
                        stop['available_hh'] = target_hh
                    priorimeter_rows = models.list_priorimeter(proj_id, status='') if scope == 'full' else []
                    content = export_service.export_sap_workbook(
                        plans, items, operations, long_texts, balance,
                        models.get_project(proj_id), scope=scope,
                        template=(export_type == 'template'), priorimeter_rows=priorimeter_rows)
                    stamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
                    filename = (f"modelo_{scope}_SAP.xlsx" if export_type == 'template'
                                else f"projeto_completo_SAP_{stamp}.xlsx" if scope == 'full'
                                else f"export_{scope}_SAP_{stamp}.xlsx")
                
                elif export_type == 'plans':
                    plans = models.list_plans(proj_id, filters, limit=None, offset=0)
                    content = export_service.export_plans_csv(plans)
                    
                elif export_type == 'items':
                    items = models.list_items(proj_id, filters, limit=None, offset=0)
                    content = export_service.export_items_csv(items)
                    
                elif export_type == 'balance':
                    balance = calculations.project_balance(proj_id, filters)
                    content = export_service.export_balance_csv(balance)

                elif export_type == 'balance-report':
                    grouping = q_params.get('grouping', 'none')
                    balance = calculations.project_balance(proj_id, filters, grouping)
                    capacities = {}
                    for trade in ('ele', 'mec', 'sol'):
                        raw = q_params.get(f'cap_{trade}', '')
                        try: capacities[trade] = float(raw) if raw != '' else None
                        except (TypeError, ValueError): capacities[trade] = None

                    mode = q_params.get('headcount_status', '')
                    def exceeded(stop, trade):
                        cap = capacities.get(trade)
                        return cap is not None and float(stop.get(f'{trade}_headcount_needed') or 0) > cap
                    def stop_visible(stop):
                        flags = {t: exceeded(stop, t) for t in ('ele', 'mec', 'sol')}
                        if mode == 'any_exceeded': return any(flags.values())
                        if mode in ('ele_exceeded', 'mec_exceeded', 'sol_exceeded'):
                            return flags[mode[:3]]
                        if mode == 'within': return not any(flags.values())
                        return True
                    balance['stops'] = [s for s in balance.get('stops', []) if stop_visible(s)]
                    if mode:
                        visible = balance['stops']
                        hh_values = [float(s.get('total_hh') or 0) for s in visible]
                        hc_values = [float(s.get('headcount_needed') or 0) for s in visible]
                        order_values = [int(s.get('total_orders') or 0) for s in visible]
                        count = len(visible)
                        balance['kpis'].update({
                            'total_hh': round(sum(hh_values), 1),
                            'avg_hh': round(sum(hh_values) / count, 1) if count else 0,
                            'max_hh': round(max(hh_values), 1) if count else 0,
                            'min_hh': round(min(hh_values), 1) if count else 0,
                            'diff_hh': round(max(hh_values) - min(hh_values), 1) if count else 0,
                            'avg_headcount': round(sum(hc_values) / count, 1) if count else 0,
                            'max_headcount': max(hc_values) if count else 0,
                            'max_orders': max(order_values) if count else 0
                        })

                    manual_id = int(q_params.get('manual_session_id', 0) or 0)
                    if manual_id:
                        raw_by_id = {}
                        for visible_stop in balance['stops']:
                            detail = manual_balance_service.stop_details(
                                proj_id, manual_id, visible_stop['counter'],
                                int(filters.get('horizon', 12) or 12))
                            for order in detail.get('orders', []): raw_by_id[int(order['id'])] = order
                        raw_orders = list(raw_by_id.values())
                    else:
                        item_filters = dict(filters); item_filters['status'] = 'ACTIVE'
                        raw_orders = models.list_items(proj_id, item_filters, limit=None, offset=0,
                                                      order_by='legacy_identifier')

                    wanted_items = {int(x) for x in str(filters.get('item_ids') or '').split(',') if x.strip().isdigit()}
                    wanted_plans = {int(x) for x in str(filters.get('plan_ids') or '').split(',') if x.strip().isdigit()}
                    wanted_ids = {x.strip() for x in str(filters.get('item_identifiers') or '').split(',') if x.strip()}
                    def order_visible(order):
                        if wanted_items and int(order.get('id') or 0) not in wanted_items: return False
                        if wanted_plans and int(order.get('plan_id') or 0) not in wanted_plans: return False
                        if wanted_ids and str(order.get('legacy_identifier') or '') not in wanted_ids: return False
                        if filters.get('team_id') and str(order.get('team_id') or '') != str(filters['team_id']): return False
                        if filters.get('work_center') and order.get('work_center') != filters['work_center']: return False
                        if filters.get('gpm') and order.get('gpm') != filters['gpm']: return False
                        if filters.get('condition_code') and order.get('condition_code') != filters['condition_code']: return False
                        return True
                    raw_orders = [o for o in raw_orders if order_visible(o)]
                    orders_by_stop = {}
                    for stop in balance['stops']:
                        counter = int(stop['counter'])
                        rows = []
                        for order in raw_orders:
                            reference = order.get('reference_counter')
                            if reference is None: reference = order.get('plan_reference_counter')
                            cycle = order.get('cycle')
                            if cycle is None: cycle = order.get('plan_cycle')
                            if calculations.plan_occurs_on_stop(reference, cycle, counter): rows.append(order)
                        orders_by_stop[counter] = rows

                    content = export_service.export_balance_managerial_xlsx(
                        balance, orders_by_stop, models.get_project(proj_id), filters,
                        capacities, headcount_status=mode)
                    filename = f"relatorio_balanceamento_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
                    
                elif export_type == 'orders':
                    stop_counter = int(q_params.get('stop_counter', 0))
                    if not stop_counter:
                        self.send_error_json("Contador da parada é obrigatório para exportar ordens.")
                        return
                        
                    # Fetch orders on that stop
                    balance_details = calculations.project_balance(proj_id, filters, 'none')
                    target_stop = next((s for s in balance_details['stops'] if s['counter'] == stop_counter), None)
                    
                    conn = get_db_connection()
                    cursor = conn.cursor()
                    orders_query = """
                    SELECT 
                        i.*, p.legacy_code as plan_code, p.description as plan_description, 
                        p.cycle, p.unit, p.reference_counter
                    FROM maintenance_items i
                    LEFT JOIN plans p ON i.plan_id = p.id
                    WHERE i.project_id = ? AND i.deleted_at IS NULL AND i.status = 'ACTIVE'
                      AND p.deleted_at IS NULL AND p.status = 'ACTIVE' AND p.reference_counter IS NOT NULL
                    """
                    orders_params = [proj_id]
                    item_ids = [int(x) for x in str(filters.get('item_ids') or '').split(',') if x.strip().isdigit()]
                    if item_ids:
                        orders_query += " AND i.id IN (" + ",".join("?" for _ in item_ids) + ")"; orders_params.extend(item_ids)
                    plan_ids = [int(x) for x in str(filters.get('plan_ids') or '').split(',') if x.strip().isdigit()]
                    if plan_ids:
                        orders_query += " AND p.id IN (" + ",".join("?" for _ in plan_ids) + ")"; orders_params.extend(plan_ids)
                    identifiers = [x.strip() for x in str(filters.get('item_identifiers') or '').split(',') if x.strip()]
                    if identifiers:
                        orders_query += " AND i.legacy_identifier IN (" + ",".join("?" for _ in identifiers) + ")"
                        orders_params.extend(identifiers)
                    if filters.get('work_center'):
                        orders_query += " AND i.work_center = ?"
                        orders_params.append(filters['work_center'])
                    if filters.get('gpm'):
                        orders_query += " AND i.gpm = ?"
                        orders_params.append(filters['gpm'])
                    if filters.get('condition_code'):
                        orders_query += " AND i.condition_code = ?"
                        orders_params.append(filters['condition_code'])
                    orders_query += " ORDER BY CAST(i.legacy_identifier AS INTEGER), i.legacy_identifier"
                    cursor.execute(orders_query, orders_params)
                    all_items = cursor.fetchall()
                    conn.close()
                    
                    matching_orders = []
                    for item in all_items:
                        # Use exactly the same plan-driven occurrence rule as the graph.
                        if calculations.plan_occurs_on_stop(
                            item['reference_counter'], item['cycle'], stop_counter
                        ):
                            # Add stop number
                            dict_item = models.to_dict(item)
                            dict_item['stop_num'] = target_stop['stop_num'] if target_stop else ''
                            matching_orders.append(dict_item)
                            
                    timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
                    if export_format == 'xlsx':
                        content = export_service.export_orders_xlsx(
                            matching_orders, stop_counter,
                            project=models.get_project(proj_id), stop_info=target_stop)
                        filename = f"ordens_parada_{stop_counter}_{timestamp}.xlsx"
                    else:
                        content = export_service.export_orders_csv(matching_orders, stop_counter)
                        filename = f"export_ordens_parada_{stop_counter}_{timestamp}.csv"
                else:
                    self.send_error_json("Tipo de exportação desconhecido.")
                    return
                    
                self.send_response(200)
                content_type = ('application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
                                if filename.lower().endswith('.xlsx') else 'text/csv; charset=utf-8-sig')
                self.send_header('Content-Type', content_type)
                self.send_header('Content-Disposition', f'attachment; filename="{filename}"')
                self.send_header('Content-Length', len(content))
                self.end_headers()
                self.wfile.write(content)
                _server_trace('EXPORT OK', projeto=proj_id, tipo=export_type, arquivo=filename,
                              tamanho_kb=round(len(content)/1024, 1),
                              segundos=round(time.perf_counter()-export_started, 2))
                return

            # --- STATIC FILES ---
            self.serve_static_file(path)
            
        except Exception as e:
            _server_trace_exception('HTTP GET FALHA', e, rota=path)
            self.send_error_json(f"Erro interno no servidor: {e}", 500)

    def do_POST(self):
        self._handle_project_mutation(self._do_POST_impl, 'POST')

    def _do_POST_impl(self):
        url_parsed = urllib.parse.urlparse(self.path)
        path = url_parsed.path
        query = urllib.parse.parse_qs(url_parsed.query)
        q_params = {k: v[0] for k, v in query.items() if v}
        
        try:
            # --- API POST ROUTES ---

            if path == '/api/auth/login':
                data = self.read_json_body()
                login = str(data.get('login') or '').strip()
                password = str(data.get('password') or '')
                remember = bool(data.get('remember', False))
                user = models.authenticate_user(login, password)
                if not user:
                    self.send_error_json('Usuário ou senha inválidos.', 401)
                    return
                days = 30 if remember else 7
                token = models.create_user_session(user['id'], days=days)
                self.send_response(200)
                self.send_header('Content-Type', 'application/json; charset=utf-8')
                max_age = days * 24 * 60 * 60
                cookie_val = f"pm13_session={token}; Path=/; HttpOnly; SameSite=Lax; Max-Age={max_age}"
                self.send_header('Set-Cookie', cookie_val)
                self.end_headers()
                self.wfile.write(json.dumps({'user': user, 'token': token}).encode('utf-8'))
                return

            if path == '/api/auth/logout':
                token = self.get_cookie('pm13_session') or self.headers.get('X-Session-Token')
                if token:
                    models.revoke_user_session(token)
                self.send_response(200)
                self.send_header('Content-Type', 'application/json; charset=utf-8')
                cookie_val = "pm13_session=; Path=/; Expires=Thu, 01 Jan 1970 00:00:00 GMT; HttpOnly; SameSite=Lax"
                self.send_header('Set-Cookie', cookie_val)
                self.end_headers()
                self.wfile.write(json.dumps({'ok': True}).encode('utf-8'))
                return

            if path.startswith('/api/pm11'):
                if pm11_handler.handle_pm11_request(self, 'POST', path, q_params):
                    return

            # POST /api/history/undo and /api/history/redo
            match = re.match(r'^/api/history/(undo|redo)$', path)
            if match:
                data = self.read_json_body()
                try:
                    project_id = int(data.get('project_id', 0))
                except (TypeError, ValueError):
                    project_id = 0
                if not project_id:
                    self.send_error_json('ID do projeto é obrigatório.')
                    return
                conn = get_db_connection()
                try:
                    project_exists = conn.execute(
                        'SELECT 1 FROM projects WHERE id = ?', (project_id,)
                    ).fetchone() is not None
                finally:
                    conn.close()
                if not project_exists:
                    self.send_error_json('Projeto não encontrado.', 404)
                    return
                direction = match.group(1)
                try:
                    entry = (history_service.undo(project_id)
                             if direction == 'undo'
                             else history_service.redo(project_id))
                    status = history_service.get_history_state(project_id)
                    verb = 'desfeita' if direction == 'undo' else 'refeita'
                    self.send_json({
                        'message': f"Alteração {verb}: {entry['action']}.",
                        'action': entry,
                        'status': status,
                    })
                except (history_service.NothingToUndo, history_service.NothingToRedo) as exc:
                    self.send_error_json(str(exc), 409)
                except history_service.HistoryProjectNotFound as exc:
                    self.send_error_json(str(exc), 404)
                return
            
            # POST /api/priorimeter/bulk-update
            if path == '/api/priorimeter/bulk-update':
                data = self.read_json_body()
                proj_id = int(data.get('project_id', 0))
                if not proj_id:
                    self.send_error_json('ID do projeto é obrigatório.')
                    return
                result = models.bulk_update_priorimeter(proj_id, data.get('item_ids') or [], data.get('updates') or {})
                self.send_json({'message': f"{result['updated']} linha(s) do priorímetro atualizadas.", **result})
                return

            # POST /api/priorimeter/copy
            if path == '/api/priorimeter/copy':
                data = self.read_json_body()
                proj_id = int(data.get('project_id', 0))
                source_item_id = int(data.get('source_item_id', 0))
                target_item_ids = data.get('target_item_ids') or []
                if not proj_id or not source_item_id or not target_item_ids:
                    self.send_error_json('Origem, destino e projeto são obrigatórios.')
                    return
                result = models.copy_priorimeter_row(proj_id, source_item_id, target_item_ids)
                self.send_json({'message': f"Linha copiada para {result['updated']} item(ns).", **result})
                return

            # POST /api/projects
            if path == '/api/projects':
                data = self.read_json_body()
                name = str(data.get('name') or '').strip()
                desc = data.get('description')
                area = data.get('area')
                system_name = data.get('system_name')
                counter = int(data.get('current_counter', 0))
                horizon = int(data.get('default_horizon', 12))
                util = float(data.get('utilization_factor', 1.0))
                
                if not name:
                    self.send_error_json("Nome do projeto é obrigatório.")
                    return
                    
                try:
                    p_id = models.create_project(name, desc, area, system_name, counter, horizon, util)
                    self.send_json({'id': p_id, 'message': 'Projeto criado com sucesso!'})
                except sqlite3.IntegrityError:
                    self.send_error_json(f"Já existe um projeto cadastrado com o nome '{name}'. Por favor, escolha um nome diferente.", 400)
                return

            # POST /api/standards/long-texts
            if path == '/api/standards/long-texts':
                data = self.read_json_body()
                title = str(data.get('title') or '').strip()
                category = str(data.get('category') or 'GERAL').strip()
                text = str(data.get('text') or '').strip()
                if not title or not text:
                    self.send_error_json("Título e texto são obrigatórios.")
                    return
                new_std = models.create_standard_long_text(
                    title, category, text, data.get('structure_mode'), data.get('structure_json')
                )
                self.send_json(new_std, 201)
                return

            # Same parser is reused by UI, spreadsheet import and server saves.
            if path == '/api/long-texts/normalize':
                data = self.read_json_body()
                self.send_json(detect_structure(data.get('text') or ''))
                return

            # Reusable hierarchical blocks inside a long text.
            if path == '/api/long-text-blocks':
                data = self.read_json_body()
                result = models.create_standard_long_text_block(
                    data.get('title'), data.get('category'), data.get('structure_json'), data.get('tags')
                )
                self.send_json(result, 201)
                return

            # POST /api/standards/items/from-item/{item_id}
            match = re.match(r'^/api/standards/items/from-item/(\d+)$', path)
            if match:
                item_id = int(match.group(1))
                data = self.read_json_body()
                title = str(data.get('title') or '').strip()
                category = str(data.get('category') or 'GERAL').strip()
                res = models.save_item_as_standard(item_id, title, category)
                self.send_json(res, 201)
                return

            # POST /api/standards/items
            if path == '/api/standards/items':
                data = self.read_json_body()
                title = str(data.get('title') or '').strip()
                if not title or not data.get('description'):
                    self.send_error_json("Título e descrição do item são obrigatórios.")
                    return
                res = models.create_standard_item(data)
                self.send_json(res, 201)
                return

            # POST /api/items/from-standard/{standard_id}
            match = re.match(r'^/api/items/from-standard/(\d+)$', path)
            if match:
                std_id = int(match.group(1))
                data = self.read_json_body()
                project_id = int(data.get('project_id', 0))
                if not project_id:
                    self.send_error_json("ID do projeto é obrigatório.")
                    return
                new_item_id = models.instantiate_standard_item(project_id, std_id, data)
                self.send_json({'id': new_item_id, 'message': 'Item criado a partir do modelo padrão!'}, 201)
                return

            # POST /api/standards/items/{id}/duplicate
            match = re.match(r'^/api/standards/items/(\d+)/duplicate$', path)
            if match:
                std_id = int(match.group(1))
                data = self.read_json_body()
                res = models.duplicate_standard_item(std_id, data.get('title'))
                self.send_json(res, 201)
                return

            # POST /api/items/{item_id}/apply-standard/{standard_id}
            match = re.match(r'^/api/items/(\d+)/apply-standard/(\d+)$', path)
            if match:
                item_id, std_id = int(match.group(1)), int(match.group(2))
                data = self.read_json_body()
                result = models.apply_standard_item_to_existing(
                    item_id, std_id, data, bool(data.get('replace_existing'))
                )
                self.send_json({**result, 'message': 'Modelo aplicado ao item com sucesso.'})
                return

            # POST /api/items/{item_id}/clone
            # Body: { include_structure: true|false }
            match = re.match(r'^/api/items/(\d+)/clone$', path)
            if match:
                data = self.read_json_body()
                include_structure = bool(data.get('include_structure'))
                result = models.clone_item(int(match.group(1)), include_structure=include_structure)
                message = ('Item, operacoes e textos longos clonados com sucesso.'
                           if include_structure else 'Item clonado sem operacoes ou textos longos.')
                self.send_json({**result, 'message': message}, 201)
                return

            match = re.match(r'^/api/items/(\d+)/row-color$', path)
            if match:
                data = self.read_json_body()
                self.send_json(models.set_item_row_color(int(match.group(1)), data.get('row_color')))
                return

            match = re.match(r'^/api/(plans|operations|long-texts)/(\d+)/row-color$', path)
            if match:
                data = self.read_json_body()
                self.send_json(models.set_entity_row_color(match.group(1), int(match.group(2)), data.get('row_color')))
                return

            match = re.match(r'^/api/(operations|long-texts)/(\d+)/clone$', path)
            if match:
                result = (models.clone_operation_pending(int(match.group(2))) if match.group(1) == 'operations'
                          else models.clone_long_text_pending(int(match.group(2))))
                self.send_json(result, 201)
                return
                
            # POST /api/projects/{id}/duplicate
            match = re.match(r'^/api/projects/(\d+)/duplicate$', path)
            if match:
                src_id = int(match.group(1))
                data = self.read_json_body()
                new_name = data.get('new_name')
                if not new_name:
                    self.send_error_json("Nome da cópia é obrigatório.")
                    return
                    
                new_id = models.duplicate_project(src_id, new_name)
                self.send_json({'id': new_id, 'message': 'Projeto duplicado com sucesso!'})
                return

            # POST /api/projects/{id}/lock -- deliberately bypasses project lock guard
            match = re.match(r'^/api/projects/(\d+)/lock$', path)
            if match:
                data = self.read_json_body()
                project = models.set_project_locked(int(match.group(1)), bool(data.get('locked')))
                self.send_json(project)
                return
                
            # POST /api/projects/{id}/archive
            match = re.match(r'^/api/projects/(\d+)/archive$', path)
            if match:
                p_id = int(match.group(1))
                models.archive_project(p_id)
                self.send_json({'message': 'Projeto arquivado com sucesso!'})
                return

            # POST /api/teams
            if path == '/api/teams':
                data = self.read_json_body()
                proj_id = int(data.get('project_id', 0))
                name = data.get('name')
                if not proj_id or not name:
                    self.send_error_json("Campos obrigatórios ausentes (project_id, name).")
                    return
                team = models.create_team(proj_id, data)
                self.send_json({'team': team, 'message': 'Equipe criada com sucesso!'})
                return

            # POST /api/plans
            if path == '/api/plans':
                data = self.read_json_body()
                proj_id = int(data.get('project_id', 0))
                code = data.get('legacy_code')
                desc = data.get('description')
                cycle = data.get('cycle')
                unit = data.get('unit')
                text = data.get('cycle_text')
                horiz = data.get('opening_horizon')
                start_stop = data.get('start_stop')
                ref_cnt = data.get('reference_counter')
                notes = data.get('notes')
                
                if not code or not desc or cycle is None or not unit:
                    self.send_error_json("Campos obrigatórios ausentes.")
                    return
                    
                # Parse counter
                if start_stop is not None and start_stop != '':
                    start_stop = max(1, int(start_stop))
                    project = models.get_project(proj_id)
                    cnt_val = int(project['current_counter']) + start_stop
                else:
                    start_stop = None
                    cnt_val = int(ref_cnt) if ref_cnt is not None and ref_cnt != '' else None
                
                try:
                    plan_id = models.create_plan(
                        proj_id, code, desc, cycle, unit, text, horiz,
                        cnt_val, notes, start_stop)
                except models.PlanCodeConflict as conflict:
                    self.send_plan_code_conflict(conflict)
                    return
                self.send_json({'id': plan_id, 'message': 'Plano criado com sucesso!'})
                return

            # POST /api/items
            if path == '/api/items/reorder-identifiers':
                data = self.read_json_body()
                proj_id = int(data.get('project_id', 0))
                if not proj_id:
                    self.send_error_json('ID do projeto é obrigatório.')
                    return
                backup_service.create_backup(f'auto_before_reorder_ids_proj_{proj_id}')
                mapping = models.reorder_item_identifiers(proj_id)
                self.send_json({'message': f'{len(mapping)} identificadores reordenados com sucesso.',
                                'count': len(mapping), 'mapping': mapping})
                return

            if path == '/api/items':
                data = self.read_json_body()
                proj_id = int(data.get('project_id', 0))
                identifier = data.get('legacy_identifier')
                plan_id = data.get('plan_id')
                team_id = data.get('team_id')
                obj_type = data.get('object_type', 'EQUIPAMENTO')
                obj_code = data.get('object_code')
                gpm = data.get('gpm')
                wc = data.get('work_center')
                cond = data.get('condition_code')
                priority = data.get('priority')
                start = data.get('legacy_start')
                desc = data.get('description')
                dur = data.get('duration_hours')
                headcount = data.get('headcount')
                notes = data.get('notes')
                
                if not identifier and proj_id:
                    identifier = models.next_item_identifier(proj_id)
                if not identifier or not obj_code or not gpm or not wc or not cond or priority is None or not desc or dur is None:
                    self.send_error_json("Campos obrigatórios ausentes.")
                    return
                    
                p_id = int(plan_id) if plan_id else None
                t_id = int(team_id) if team_id else None
                cnt_start = int(start) if start is not None and start != '' else None
                mec_hc = data.get('mec_headcount', 0)
                mec_h = data.get('mec_hours', 0.0)
                ele_hc = data.get('ele_headcount', 0)
                ele_h = data.get('ele_hours', 0.0)
                sol_hc = data.get('sol_headcount', 0)
                sol_h = data.get('sol_hours', 0.0)
                
                item_id = models.create_item(
                    proj_id, identifier, p_id, obj_type, obj_code, gpm, wc, cond, priority, cnt_start, desc, dur, headcount, notes, t_id,
                    mec_headcount=mec_hc, mec_hours=mec_h, ele_headcount=ele_hc, ele_hours=ele_h, sol_headcount=sol_hc, sol_hours=sol_h
                )
                self.send_json({'id': item_id, 'message': 'Item criado com sucesso!'})
                return

            if path == '/api/operations':
                data=self.read_json_body(); proj_id=int(data.get('project_id',0)); item_id=int(data.get('item_id',0))
                if not proj_id or not item_id or not data.get('operation_code') or not data.get('short_text'):
                    self.send_error_json('Projeto, item, operação e texto breve são obrigatórios.'); return
                conn=get_db_connection(); cur=conn.cursor()
                cur.execute("""INSERT INTO item_operations(project_id,item_id,operation_code,suboperation_code,work_center,short_text,unit,headcount,hours)
                               VALUES(?,?,?,?,?,?,?,?,?)""",(proj_id,item_id,str(data['operation_code']),str(data.get('suboperation_code') or ''),
                               data.get('work_center'),data['short_text'],data.get('unit') or 'H',data.get('headcount'),data.get('hours')))
                oid=cur.lastrowid; conn.commit(); conn.close(); self.send_json({'id':oid,'message':'Operação criada com sucesso!'}); return

            if path == '/api/long-texts':
                data = self.read_json_body()
                proj_id = int(data.get('project_id', 0))
                operation_id = int(data.get('operation_id', 0))
                prepared = prepare_for_save(
                    data.get('text') or '', data.get('structure_mode'),
                    data.get('structure_json'), data.get('source_text_original')
                )
                if not proj_id or not operation_id or not prepared['text'].strip():
                    self.send_error_json('Projeto, operação e texto são obrigatórios.')
                    return
                conn = get_db_connection(); cur = conn.cursor()
                cur.execute('SELECT COALESCE(MAX(line_sequence),0)+1 FROM operation_long_texts WHERE operation_id=?', (operation_id,))
                seq = cur.fetchone()[0]
                cur.execute("""INSERT INTO operation_long_texts(
                    project_id,operation_id,group_code,group_counter,line_sequence,text,
                    structure_mode,structure_json,source_text_original
                ) VALUES(?,?,?,?,?,?,?,?,?)""", (
                    proj_id, operation_id, data.get('group_code'), data.get('group_counter'), seq,
                    prepared['text'], prepared['structure_mode'], prepared['structure_json'], prepared['source_text_original']
                ))
                tid = cur.lastrowid
                conn.commit(); conn.close()
                self.send_json({'id': tid, 'message': 'Texto longo criado com sucesso!',
                                'structure_mode': prepared['structure_mode'], 'text': prepared['text']})
                return

            # POST /api/operations/bulk-update and /api/long-texts/bulk-update
            if path in ('/api/operations/bulk-update', '/api/long-texts/bulk-update'):
                data = self.read_json_body()
                proj_id = int(data.get('project_id', 0))
                record_ids = data.get('ids', [])
                updates = data.get('updates', {})
                if not proj_id or not record_ids or not updates:
                    self.send_error_json('Parâmetros inválidos para atualização em massa.')
                    return
                if path == '/api/long-texts/bulk-update' and 'text' in updates and not str(updates['text']).strip():
                    self.send_error_json('O texto longo não pode ficar vazio.')
                    return
                if path == '/api/operations/bulk-update' and 'short_text' in updates and not str(updates['short_text']).strip():
                    self.send_error_json('O texto breve não pode ficar vazio.')
                    return
                if path == '/api/operations/bulk-update':
                    count = models.bulk_update_operations(proj_id, record_ids, updates)
                else:
                    count = models.bulk_update_long_texts(proj_id, record_ids, updates)
                self.send_json({'message': f'{count} registros atualizados com sucesso!', 'count': count})
                return

            # POST /api/plans/bulk-update
            if path == '/api/plans/bulk-update':
                data = self.read_json_body()
                proj_id = int(data.get('project_id', 0))
                plan_ids = data.get('plan_ids', [])
                updates = data.get('updates', {})
                
                if not plan_ids or not updates:
                    self.send_error_json("Parâmetros inválidos para atualização em massa de planos.")
                    return
                    
                count = models.bulk_update_plans(proj_id, plan_ids, updates)
                self.send_json({'message': f'{count} planos atualizados com sucesso!', 'count': count})
                return

            # POST /api/plans/autofill-start-stops
            if path == '/api/plans/autofill-start-stops':
                data = self.read_json_body()
                proj_id = int(data.get('project_id', 0))
                count = models.autofill_plans_start_stops(proj_id)
                self.send_json({'message': f'{count} paradas de início preenchidas automaticamente a partir da descrição dos planos!', 'count': count})
                return

            # POST /api/items/bulk-update
            if path == '/api/items/bulk-update':
                data = self.read_json_body()
                proj_id = int(data.get('project_id', 0))
                item_ids = data.get('item_ids', [])
                updates = data.get('updates', {})
                
                if not item_ids or not updates:
                    self.send_error_json("Parâmetros inválidos para atualização em massa.")
                    return
                    
                count = models.bulk_update_items(proj_id, item_ids, updates)
                self.send_json({'message': f'{count} itens atualizados com sucesso!', 'count': count})
                return

            # POST /api/items/bulk-standard-preview (read-only impact preview)
            if path == '/api/items/bulk-standard-preview':
                data = self.read_json_body()
                proj_id = int(data.get('project_id', 0))
                item_ids = data.get('item_ids', [])
                standard_id = int(data.get('standard_id', 0))
                if not proj_id or not item_ids or not standard_id:
                    self.send_error_json("Projeto, itens e modelo são obrigatórios.")
                    return
                preview_func = getattr(models, 'preview_bulk_standard_structure', None)
                preview = (preview_func(proj_id, item_ids, standard_id)
                           if callable(preview_func)
                           else _preview_bulk_standard_structure_compat(proj_id, item_ids, standard_id))
                self.send_json(preview)
                return

            # POST /api/items/bulk-apply-standard
            if path == '/api/items/bulk-apply-standard':
                data = self.read_json_body()
                proj_id = int(data.get('project_id', 0))
                item_ids = data.get('item_ids', [])
                standard_id = int(data.get('standard_id', 0))
                operations = data.get('operations')
                conflict_policy = str(data.get('conflict_policy') or 'skip')
                if not proj_id or not item_ids or not standard_id:
                    self.send_error_json("Projeto, itens e modelo são obrigatórios.")
                    return
                apply_func = getattr(models, 'bulk_apply_standard_structure', None)
                result = (apply_func(proj_id, item_ids, standard_id, operations, conflict_policy)
                          if callable(apply_func)
                          else _bulk_apply_standard_structure_compat(
                              proj_id, item_ids, standard_id, operations, conflict_policy
                          ))
                self.send_json({
                    **result,
                    'message': (
                        f"Modelo aplicado em {result['applied_items']} item(ns): "
                        f"{result['operations_created']} operações e "
                        f"{result['long_texts_created']} textos longos criados."
                    )
                })
                return

            # POST /api/items/bulk-assign-plan
            if path == '/api/items/bulk-assign-plan':
                data = self.read_json_body()
                proj_id = int(data.get('project_id', 0))
                item_ids = data.get('item_ids', [])
                plan_id = data.get('plan_id') # Can be None to unassign
                
                if not item_ids:
                    self.send_error_json("Selecione pelo menos um item.")
                    return
                    
                p_id = int(plan_id) if plan_id else None
                count = models.bulk_assign_plan(proj_id, item_ids, p_id)
                self.send_json({'message': f'Plano atribuído a {count} itens com sucesso!', 'count': count})
                return

            # POST /api/import/headers (File inspect headers)
            if path == '/api/import/headers':
                started = time.perf_counter()
                form, files = self.parse_multipart_body()
                if 'file' not in files:
                    self.send_error_json("Nenhum arquivo enviado.")
                    return
                file_info = files['file']
                file_size_mb = round(len(file_info.get('content') or b'') / (1024 * 1024), 2)
                _server_trace('IMPORT HEADERS INICIO', arquivo=file_info.get('filename'), tamanho_mb=file_size_mb)
                os.makedirs(os.path.join(BASE_DIR, 'imports'), exist_ok=True)
                temp_path = os.path.join(BASE_DIR, 'imports', f"temp_hdr_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.xlsx")
                with open(temp_path, 'wb') as f:
                    f.write(file_info['content'])
                try:
                    headers_info = import_service.get_file_headers(temp_path)
                    elapsed = round(time.perf_counter() - started, 2)
                    _server_trace('IMPORT HEADERS OK', segundos=elapsed,
                                  abas=len(headers_info.get('sheet_names') or []),
                                  padrao=headers_info.get('standard_match'))
                    self.send_json(headers_info)
                except MemoryError as ex:
                    elapsed = round(time.perf_counter() - started, 2)
                    _server_trace_exception('IMPORT HEADERS MEMORIA', ex, segundos=elapsed)
                    self.send_error_json(
                        'A planilha exigiu memória excessiva durante a leitura. Verifique se existem '
                        'centenas de milhares de linhas/células residuais e salve uma cópia limpa.', 400)
                except Exception as ex:
                    elapsed = round(time.perf_counter() - started, 2)
                    _server_trace_exception('IMPORT HEADERS FALHA', ex, segundos=elapsed)
                    self.send_error_json(str(ex), 400)
                finally:
                    if os.path.exists(temp_path):
                        os.remove(temp_path)
                return

            # POST /api/import/preview (File upload)
            if path == '/api/import/preview':
                started = time.perf_counter()
                form, files = self.parse_multipart_body()
                if 'file' not in files:
                    self.send_error_json("Nenhum arquivo enviado.")
                    return

                file_info = files['file']
                file_size_mb = round(len(file_info.get('content') or b'') / (1024 * 1024), 2)
                try:
                    default_hc = int(form.get('default_headcount', 1))
                except (TypeError, ValueError):
                    default_hc = 1
                col_map_str = form.get('column_mapping')
                col_map = json.loads(col_map_str) if col_map_str else None
                selected = (col_map or {}).get('selected_entities') or ['plans', 'items', 'operations', 'long_texts']
                _server_trace('IMPORT PREVIA INICIO', arquivo=file_info.get('filename'), tamanho_mb=file_size_mb,
                              entidades=','.join(selected))

                os.makedirs(os.path.join(BASE_DIR, 'imports'), exist_ok=True)
                temp_path = os.path.join(BASE_DIR, 'imports', f"temp_import_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.xlsx")
                with open(temp_path, 'wb') as f:
                    f.write(file_info['content'])

                try:
                    preview_data = import_service.preview_import(temp_path, default_headcount=default_hc, column_mapping=col_map)
                    preview_data['summary']['filename'] = file_info['filename']
                    summary = preview_data.get('summary', {})
                    elapsed = round(time.perf_counter() - started, 2)
                    _server_trace('IMPORT PREVIA OK', segundos=elapsed, planos=summary.get('total_plans'),
                                  itens=summary.get('total_items'), operacoes=summary.get('total_operations'),
                                  textos=summary.get('total_long_texts'), erros=summary.get('error_count'),
                                  avisos=summary.get('warning_count'),
                                  helper_especialidade_linhas=summary.get('specialty_helper_rows', 0),
                                  helper_especialidade_nao_zero=summary.get('specialty_helper_nonzero_rows', 0),
                                  helper_especialidade_colunas='|'.join(summary.get('specialty_helper_headers') or []))
                    self.send_json(preview_data)
                except MemoryError as ex:
                    elapsed = round(time.perf_counter() - started, 2)
                    _server_trace_exception('IMPORT PREVIA MEMORIA', ex, segundos=elapsed)
                    self.send_error_json(
                        'A importação foi interrompida porque a planilha exigiu memória excessiva. '
                        'Verifique linhas/células residuais muito abaixo da área real dos dados.', 400)
                except Exception as ex:
                    elapsed = round(time.perf_counter() - started, 2)
                    _server_trace_exception('IMPORT PREVIA FALHA', ex, segundos=elapsed)
                    self.send_error_json(str(ex), 400)
                finally:
                    if os.path.exists(temp_path):
                        os.remove(temp_path)
                return

            # POST /api/import/confirm
            if path == '/api/import/confirm':
                started = time.perf_counter()
                try:
                    data = self.read_json_body()
                    proj_id = int(data.get('project_id', 0))
                    preview_data = data.get('preview_data')
                    merge_mode = data.get('merge_mode', 'replace')
                    selected_entities = data.get('selected_entities')

                    if not proj_id or not preview_data:
                        self.send_error_json("Parâmetros ausentes.")
                        return

                    summary = preview_data.get('summary', {})
                    _server_trace('IMPORT GRAVACAO INICIO', projeto=proj_id, modo=merge_mode,
                                  entidades=','.join(selected_entities or summary.get('selected_entities') or []),
                                  planos=summary.get('valid_plans'), itens=summary.get('valid_items'),
                                  operacoes=summary.get('total_operations'), textos=summary.get('total_long_texts'),
                                  helper_especialidade_linhas=summary.get('specialty_helper_rows', 0),
                                  helper_especialidade_nao_zero=summary.get('specialty_helper_nonzero_rows', 0))

                    if merge_mode == 'replace':
                        backup_info = backup_service.create_backup(f"auto_before_replace_import_proj_{proj_id}")
                    else:
                        backup_info = backup_service.create_backup(f"auto_before_merge_import_proj_{proj_id}")
                    _server_trace('IMPORT BACKUP OK', arquivo=(backup_info or {}).get('filename') if isinstance(backup_info, dict) else backup_info)

                    import_id = import_service.confirm_import(
                        proj_id, preview_data, merge_mode=merge_mode,
                        selected_entities=selected_entities)
                    confirmed_selection = import_service.normalize_selected_entities(
                        selected_entities if selected_entities is not None
                        else preview_data.get('selected_entities',
                                              preview_data.get('summary', {}).get('selected_entities')))
                    elapsed = round(time.perf_counter() - started, 2)
                    _server_trace('IMPORT GRAVACAO OK', projeto=proj_id, import_id=import_id, segundos=elapsed)
                    self.send_json({'import_id': import_id, 'message': 'Planilha importada com sucesso!',
                                    'selected_entities': confirmed_selection})
                except sqlite3.IntegrityError as ex:
                    elapsed = round(time.perf_counter() - started, 2)
                    _server_trace_exception('IMPORT GRAVACAO INTEGRIDADE', ex, segundos=elapsed)
                    self.send_error_json(
                        'A importação foi cancelada por conflito de integridade no banco: ' + str(ex) +
                        '. Nenhum dado parcial desta transação foi mantido.', 409)
                except Exception as ex:
                    elapsed = round(time.perf_counter() - started, 2)
                    _server_trace_exception('IMPORT GRAVACAO FALHA', ex, segundos=elapsed)
                    self.send_error_json(str(ex), 400)
                return

            # POST /api/backups
            if path == '/api/backups':
                data = self.read_json_body()
                suffix = data.get('suffix')
                backup_info = backup_service.create_backup(suffix)
                self.send_json({'message': 'Backup criado com sucesso!', 'backup': backup_info})
                return

            # POST /api/backups/restore
            if path == '/api/backups/restore':
                data = self.read_json_body()
                filename = data.get('filename')
                if not filename:
                    self.send_error_json("Nome do arquivo de backup é obrigatório.")
                    return
                    
                # Safety backup of active database before overwrite
                backup_service.create_backup("auto_safety_before_restore")
                
                backup_service.restore_backup(filename)
                self.send_json({'message': 'Backup restaurado com sucesso! O sistema recarregará.'})
                return

            # POST /api/balance/move (Shifts plan reference counter)
            if path == '/api/auto-balance/preview':
                data = self.read_json_body()
                proj_id = int(data.get('project_id', 0))
                if not proj_id:
                    self.send_error_json("project_id é obrigatório.")
                    return
                try:
                    sim_enabled = _parse_bool(data.get('similarity_enabled'), True)
                    max_passes = int(data.get('max_passes', 50))
                    timeout_sec = float(data.get('timeout_seconds') or 30.0)
                    _server_trace('BALANCE PREVIA INICIO', projeto=proj_id, similaridade=sim_enabled,
                                  varreduras=max_passes, estrategia=data.get('distribution_strategy', 'horizontal'),
                                  geografia=data.get('geography_mode', 'off'), capacidades=data.get('capacities') or {})
                    started = time.perf_counter()
                    result = auto_balance_service.optimize(
                        proj_id, data.get('rules') or [], data.get('horizon'),
                        max_passes=max_passes, timeout_seconds=timeout_sec, similarity_enabled=sim_enabled,
                        distribution_strategy=data.get('distribution_strategy', 'horizontal'),
                        geography_mode=data.get('geography_mode', 'off'),
                        vertical_tolerance=data.get('vertical_tolerance', 10),
                        capacities=data.get('capacities') or {},
                        manual_session_id=data.get('manual_session_id'),
                        preserve_manual=_parse_bool(data.get('preserve_manual'), True))
                    _server_trace('BALANCE PREVIA OK', projeto=proj_id, segundos=round(time.perf_counter()-started, 2))
                    self.send_json(result)
                except ValueError as ex:
                    _server_trace_exception('BALANCE PREVIA VALIDACAO', ex, projeto=proj_id)
                    self.send_error_json(str(ex), 400)
                except TimeoutError as ex:
                    _server_trace_exception('BALANCE PREVIA TIMEOUT', ex, projeto=proj_id)
                    self.send_error_json(str(ex), 408)
                except Exception as ex:
                    _server_trace_exception('BALANCE PREVIA FALHA', ex, projeto=proj_id)
                    self.send_error_json(str(ex), 500)
                return

            if path == '/api/auto-balance/apply':
                data = self.read_json_body()
                proj_id = int(data.get('project_id', 0))
                if not proj_id:
                    self.send_error_json("project_id é obrigatório.")
                    return
                try:
                    sim_enabled = _parse_bool(data.get('similarity_enabled'), True)
                    max_passes = int(data.get('max_passes', 50))
                    timeout_sec = float(data.get('timeout_seconds') or 30.0)
                    _server_trace('BALANCE APLICAR INICIO', projeto=proj_id, similaridade=sim_enabled,
                                  varreduras=max_passes, estrategia=data.get('distribution_strategy', 'horizontal'),
                                  geografia=data.get('geography_mode', 'off'), capacidades=data.get('capacities') or {})
                    started = time.perf_counter()
                    backup_service.create_backup(f"auto_before_balance_proj_{proj_id}")
                    result = auto_balance_service.apply(
                        proj_id, data.get('rules') or [], data.get('horizon'),
                        max_passes=max_passes, timeout_seconds=timeout_sec, similarity_enabled=sim_enabled,
                        distribution_strategy=data.get('distribution_strategy', 'horizontal'),
                        geography_mode=data.get('geography_mode', 'off'),
                        vertical_tolerance=data.get('vertical_tolerance', 10),
                        capacities=data.get('capacities') or {},
                        manual_session_id=data.get('manual_session_id'),
                        preserve_manual=_parse_bool(data.get('preserve_manual'), True))
                    _server_trace('BALANCE APLICAR OK', projeto=proj_id, segundos=round(time.perf_counter()-started, 2))
                    self.send_json({
                        'message': 'Balanceamento automático aplicado com sucesso!',
                        'result': result
                    })
                except ValueError as ex:
                    _server_trace_exception('BALANCE APLICAR VALIDACAO', ex, projeto=proj_id)
                    self.send_error_json(str(ex), 400)
                except TimeoutError as ex:
                    _server_trace_exception('BALANCE APLICAR TIMEOUT', ex, projeto=proj_id)
                    self.send_error_json(str(ex), 408)
                except Exception as ex:
                    _server_trace_exception('BALANCE APLICAR FALHA', ex, projeto=proj_id)
                    self.send_error_json(str(ex), 500)
                return

            if path == '/api/manual-balance/start':
                try:
                    data = self.read_json_body(); proj_id = int(data.get('project_id', 0))
                    if bool(data.get('restart', False)):
                        backup_service.create_backup(f'auto_before_manual_restart_proj_{proj_id}')
                    result = manual_balance_service.start_session(
                        proj_id, data.get('base_mode', 'zero'), data.get('horizon', 12),
                        bool(data.get('restart', False)))
                    self.send_json({'session': result})
                except ValueError as ex:
                    self.send_error_json(str(ex), 400)
                return

            if path == '/api/manual-balance/move':
                try:
                    data = self.read_json_body(); proj_id = int(data.get('project_id', 0))
                    result = manual_balance_service.move_items(
                        proj_id, int(data.get('session_id', 0)), data.get('item_ids') or [],
                        int(data.get('target_stop', 0)), data.get('target_plan_ids') or {}, 'manual',
                        bool(data.get('allow_family_mismatch', False)))
                    self.send_json(result)
                except ValueError as ex:
                    self.send_error_json(str(ex), 400)
                return

            if path == '/api/manual-balance/return':
                try:
                    data = self.read_json_body(); proj_id = int(data.get('project_id', 0))
                    self.send_json(manual_balance_service.return_to_book(
                        proj_id, int(data.get('session_id', 0)), data.get('item_ids') or []))
                except ValueError as ex:
                    self.send_error_json(str(ex), 400)
                return

            if path == '/api/manual-balance/return-all':
                try:
                    data = self.read_json_body(); proj_id = int(data.get('project_id', 0))
                    sess_id = int(data.get('session_id', 0)) or (manual_balance_service.get_active_session(proj_id) or {}).get('id')
                    only_unlocked = bool(data.get('only_unlocked', False))
                    self.send_json(manual_balance_service.return_all_to_book(
                        proj_id, sess_id, only_unlocked=only_unlocked))
                except ValueError as ex:
                    self.send_error_json(str(ex), 400)
                return

            if path == '/api/manual-balance/lock':
                try:
                    data = self.read_json_body(); proj_id = int(data.get('project_id', 0))
                    self.send_json(manual_balance_service.set_item_lock(
                        proj_id, int(data.get('session_id', 0)), int(data.get('item_id', 0)),
                        bool(data.get('locked', True)), data.get('target_stop')))
                except ValueError as ex:
                    self.send_error_json(str(ex), 400)
                return

            if path == '/api/manual-balance/complete':
                try:
                    data = self.read_json_body(); proj_id = int(data.get('project_id', 0))
                    backup_service.create_backup(f'auto_before_manual_complete_proj_{proj_id}')
                    self.send_json(manual_balance_service.complete_session(
                        proj_id, int(data.get('session_id', 0)), bool(data.get('allow_pending', False))))
                except ValueError as ex:
                    self.send_error_json(str(ex), 400)
                return

            if path == '/api/manual-balance/discard':
                try:
                    data = self.read_json_body(); proj_id = int(data.get('project_id', 0))
                    self.send_json(manual_balance_service.discard_session(
                        proj_id, int(data.get('session_id', 0))))
                except ValueError as ex:
                    self.send_error_json(str(ex), 400)
                return

            if path == '/api/auto-balance/restore-pre-balance':
                data = self.read_json_body()
                proj_id = int(data.get('project_id', 0))
                if not proj_id:
                    self.send_error_json("project_id é obrigatório.")
                    return
                backup_file = backup_service.get_latest_pre_balance_backup(proj_id)
                if not backup_file:
                    self.send_error_json("Nenhum backup automático pré-balanceamento foi encontrado para este projeto.")
                    return
                backup_service.restore_backup(backup_file)
                discarded = manual_balance_service.discard_active_sessions(proj_id)
                self.send_json({
                    'message': 'Cenário inicial restaurado. O rascunho manual anterior foi encerrado.',
                    'manual_drafts_discarded': discarded,
                })
                return

            # POST /api/balance/move (Shifts plan reference counter)
            if path == '/api/balance/move':
                data = self.read_json_body()
                plan_id = data.get('plan_id')
                target_stop = data.get('target_stop')
                
                if not plan_id or target_stop is None:
                    self.send_error_json("Campos plan_id e target_stop são obrigatórios.")
                    return
                
                try:
                    models.update_plan_reference_counter(int(plan_id), int(target_stop))
                    self.send_json({'message': 'Balanceamento atualizado com sucesso!'})
                except Exception as ex:
                    self.send_error_json(f"Erro ao atualizar balanceamento: {ex}", 500)
                return

            # POST /api/balance/reassign-item (Reassigns an item to a different plan)
            if path == '/api/balance/reassign-item':
                data = self.read_json_body()
                item_id = data.get('item_id')
                plan_id = data.get('plan_id')
                
                if not item_id or plan_id is None:
                    self.send_error_json("Campos item_id e plan_id são obrigatórios.")
                    return
                
                conn = get_db_connection()
                try:
                    cursor = conn.cursor()
                    cursor.execute("""
                        SELECT i.project_id, i.plan_id,
                               op.legacy_code AS old_plan_code, op.cycle AS old_cycle,
                               p.project_id AS target_project_id, p.legacy_code AS target_plan_code,
                               p.cycle AS target_cycle, p.reference_counter, pr.current_counter
                        FROM maintenance_items i
                        LEFT JOIN plans op ON op.id = i.plan_id
                        LEFT JOIN plans p ON p.id = ?
                        LEFT JOIN projects pr ON pr.id = i.project_id
                        WHERE i.id = ?
                    """, (int(plan_id) if plan_id else None, int(item_id)))
                    row = cursor.fetchone()
                    if not row:
                        self.send_error_json("Item não encontrado.")
                        return
                    project_id = row['project_id']
                    old_plan_id = row['plan_id']
                    if row['target_project_id'] is None or int(row['target_project_id']) != int(project_id):
                        self.send_error_json("Plano de destino inválido para este projeto.", 400)
                        return
                    if row['old_cycle'] is not None and int(row['old_cycle']) != int(row['target_cycle']):
                        self.send_error_json(
                            f"A troca manual deve manter o ciclo: origem {row['old_cycle']}P, "
                            f"destino {row['target_cycle']}P.", 400)
                        return
                    old_family = auto_balance_service.get_plan_prefix9(row['old_plan_code'])
                    target_family = auto_balance_service.get_plan_prefix9(row['target_plan_code'])
                    family_mismatch = bool(old_family and target_family and old_family != target_family)
                    if family_mismatch and not bool(data.get('allow_family_mismatch', False)):
                        self.send_error_json(
                            "FAMILY_MISMATCH_CONFIRMATION_REQUIRED: "
                            f"o item pertence à família {old_family}, mas o plano escolhido pertence "
                            f"à família {target_family}. Confirme a exceção manual para continuar.", 409)
                        return

                    # PLAN = CLOCK. Reassignment changes only the linked plan.
                    # legacy_start is historical/import metadata and is not used
                    # to determine future occurrences.
                    cursor.execute("""
                        UPDATE maintenance_items
                        SET plan_id = ?, updated_at = CURRENT_TIMESTAMP
                        WHERE id = ?
                    """, (int(plan_id) if plan_id else None, int(item_id)))
                    conn.commit()
                    
                    models.log_action(project_id, 'ITEM', int(item_id), 'REASSIGN_PLAN', 
                                      {'plan_id': old_plan_id}, {'plan_id': plan_id})
                    
                    response = {'message': 'Item reassociado com sucesso!',
                                'family_warning': family_mismatch,
                                'source_family': old_family, 'target_family': target_family}
                    if family_mismatch:
                        response['warning'] = (
                            f'Exceção manual registrada: família {old_family} → {target_family}. '
                            'O balanceamento automático não repetirá esta troca.')
                    self.send_json(response)
                except Exception as ex:
                    conn.rollback()
                    self.send_error_json(f"Erro ao reassociar item: {ex}", 500)
                finally:
                    conn.close()
                return

            # POST /api/balance/create-independent-plan (Creates an independent plan and reassociates item)
            if path == '/api/balance/create-independent-plan':
                data = self.read_json_body()
                item_id = data.get('item_id')
                target_stop = data.get('target_stop')
                
                if not item_id or target_stop is None:
                    self.send_error_json("Campos item_id e target_stop são obrigatórios.")
                    return
                
                conn = get_db_connection()
                try:
                    cursor = conn.cursor()
                    # 1. Fetch item and original plan details
                    cursor.execute("""
                        SELECT i.project_id, i.plan_id, p.legacy_code, p.description, p.cycle, p.unit, p.cycle_text, p.opening_horizon
                        FROM maintenance_items i
                        LEFT JOIN plans p ON i.plan_id = p.id
                        WHERE i.id = ?
                    """, (int(item_id),))
                    row = cursor.fetchone()
                    if not row:
                        self.send_error_json("Item ou plano associado não encontrado.")
                        return
                    
                    project_id = row['project_id']
                    orig_plan_id = row['plan_id']
                    orig_code = row['legacy_code'] or 'PLANO_IND'
                    orig_desc = row['description'] or 'Plano Individual'
                    cycle = row['cycle'] or 1
                    unit = row['unit'] or 'PRD'
                    cycle_text = row['cycle_text'] or ''
                    opening_horizon = row['opening_horizon'] or 36.0
                    
                    # 2. Generate a new plan code that is unique
                    new_code = f"{orig_code}_M{target_stop}"
                    new_desc = f"{orig_desc} (Ind. P{target_stop})"
                    
                    # Check if plan with new_code already exists in this project
                    cursor.execute("SELECT id FROM plans WHERE project_id = ? AND legacy_code = ? AND deleted_at IS NULL", (project_id, new_code))
                    existing = cursor.fetchone()
                    created_new_plan = not bool(existing)
                    if existing:
                        new_plan_id = existing['id']
                    else:
                        # Insert new plan
                        cursor.execute("""
                            INSERT INTO plans (project_id, legacy_code, description, character_count, cycle, unit, cycle_text, opening_horizon, reference_counter, status, created_at, updated_at)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'ACTIVE', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                        """, (project_id, new_code, new_desc, len(new_desc), cycle, unit, cycle_text, opening_horizon, int(target_stop)))
                        new_plan_id = cursor.lastrowid
                    
                    # 3. Associate item with the new plan
                    cursor.execute("""
                        UPDATE maintenance_items
                        SET plan_id = ?, updated_at = CURRENT_TIMESTAMP
                        WHERE id = ?
                    """, (new_plan_id, int(item_id)))
                    conn.commit()

                    # Audit uses its own connection; run it only after the data
                    # transaction releases SQLite's write lock.
                    if created_new_plan:
                        models.log_action(project_id, 'PLAN', new_plan_id, 'CREATE', None, {
                            'legacy_code': new_code, 'description': new_desc,
                            'reference_counter': target_stop
                        })
                    
                    models.log_action(project_id, 'ITEM', int(item_id), 'REASSIGN_PLAN', 
                                      {'plan_id': orig_plan_id}, {'plan_id': new_plan_id})
                    
                    self.send_json({'message': 'Plano independente criado e item reassociado!', 'new_plan_id': new_plan_id})
                except Exception as ex:
                    conn.rollback()
                    self.send_error_json(f"Erro ao criar plano independente: {ex}", 500)
                finally:
                    conn.close()
                return
            # POST /api/logs (Receives logs from the frontend for debugging)
            if path == '/api/logs':
                data = self.read_json_body()
                msg = data.get('message', '')
                ctx = data.get('context', '')
                log_line = f"[{datetime.datetime.now().isoformat()}] MSG: {msg} | CTX: {ctx}\n"
                
                os.makedirs('data', exist_ok=True)
                with open('data/frontend.log', 'a', encoding='utf-8') as f_log:
                    f_log.write(log_line)
                
                print(f"[FRONTEND LOG] {msg} | Context: {ctx}")
                self.send_json({'status': 'ok'})
                return

            # POST /api/shutdown (Gracefully shuts down the server process)
            if path == '/api/shutdown':
                self.send_json({'message': 'Servidor finalizado com sucesso. Você pode fechar esta aba.'})
                
                # Inline class to close server from outside Request Handler after sending response
                def shutdown_server():
                    import time
                    time.sleep(1.0)
                    print("Shutdown requested. Exiting application...")
                    os._exit(0)
                    
                import threading
                threading.Thread(target=shutdown_server).start()
                return

            self.send_error_json("Rota POST não encontrada.", 404)
            
        except Exception as e:
            self.send_error_json(f"Erro interno no servidor: {e}", 500)
            import traceback
            traceback.print_exc()

    def do_PUT(self):
        self._handle_project_mutation(self._do_PUT_impl, 'PUT')

    def _do_PUT_impl(self):
        url_parsed = urllib.parse.urlparse(self.path)
        path = url_parsed.path
        query = urllib.parse.parse_qs(url_parsed.query)
        q_params = {k: v[0] for k, v in query.items() if v}
        
        try:
            if path.startswith('/api/pm11'):
                if pm11_handler.handle_pm11_request(self, 'PUT', path, q_params):
                    return

            # PUT /api/priorimeter/{item_id}
            match = re.match(r'^/api/priorimeter/(\d+)$', path)
            if match:
                item_id = int(match.group(1))
                data = self.read_json_body()
                proj_id = int(data.get('project_id', 0))
                if not proj_id:
                    self.send_error_json('ID do projeto é obrigatório.')
                    return
                row = models.update_priorimeter_item(proj_id, item_id, data.get('updates') or {})
                self.send_json({'row': row, 'message': 'Priorímetro atualizado.'})
                return

            # PUT /api/teams/{id}
            match = re.match(r'^/api/teams/(\d+)$', path)
            if match:
                team_id = int(match.group(1))
                data = self.read_json_body()
                team = models.update_team(team_id, data)
                self.send_json({'team': team, 'message': 'Equipe atualizada com sucesso!'})
                return

            # PUT /api/projects/{id}/work-capacity
            match = re.match(r'^/api/projects/(\d+)/work-capacity$', path)
            if match:
                p_id = int(match.group(1))
                data = self.read_json_body()
                res = models.update_project_work_capacity_settings(
                    p_id, data.get('hours_per_person', 9.1), data.get('tool_time_percent', 100.0)
                )
                print(
                    f"[PM13 CAPACIDADE] projeto={p_id} | horas_pessoa={res['hours_per_person']} | "
                    f"tool_time={res['tool_time_percent']}% | hh_pessoa={res['productive_hours_per_person']:.3f}"
                )
                self.send_json(res)
                return

            # PUT /api/projects/{id}/capacities
            match = re.match(r'^/api/projects/(\d+)/capacities$', path)
            if match:
                p_id = int(match.group(1))
                data = self.read_json_body()
                res = models.update_project_capacities(p_id, data.get('ele'), data.get('mec'), data.get('sol'))
                self.send_json(res)
                return

            # PUT /api/standards/long-texts/{id}
            match = re.match(r'^/api/standards/long-texts/(\d+)$', path)
            if match:
                std_id = int(match.group(1))
                data = self.read_json_body()
                title = str(data.get('title') or '').strip()
                category = str(data.get('category') or 'GERAL').strip()
                text = str(data.get('text') or '').strip()
                res = models.update_standard_long_text(
                    std_id, title, category, text, data.get('structure_mode'), data.get('structure_json')
                )
                self.send_json(res)
                return

            # PUT /api/standards/items/{id}
            match = re.match(r'^/api/standards/items/(\d+)$', path)
            if match:
                std_id = int(match.group(1))
                data = self.read_json_body()
                res = models.update_standard_item(std_id, data)
                self.send_json(res)
                return

            # PUT /api/long-text-blocks/{id}
            match = re.match(r'^/api/long-text-blocks/(\d+)$', path)
            if match:
                data = self.read_json_body()
                result = models.update_standard_long_text_block(
                    int(match.group(1)), data.get('title'), data.get('category'),
                    data.get('structure_json'), data.get('tags')
                )
                self.send_json(result)
                return

            # PUT /api/projects/{id}
            match = re.match(r'^/api/projects/(\d+)$', path)
            if match:
                p_id = int(match.group(1))
                data = self.read_json_body()
                name = data.get('name')
                desc = data.get('description')
                area = data.get('area')
                system_name = data.get('system_name')
                counter = int(data.get('current_counter', 0))
                horizon = int(data.get('default_horizon', 12))
                util = float(data.get('utilization_factor', 1.0))
                status = data.get('status', 'ACTIVE')
                
                if not name:
                    self.send_error_json("Nome do projeto é obrigatório.")
                    return
                    
                models.update_project(p_id, name, desc, area, system_name, counter, horizon, util, status)
                self.send_json({'message': 'Projeto atualizado com sucesso!'})
                return

            # PUT /api/plans/{id}
            match = re.match(r'^/api/plans/(\d+)$', path)
            if match:
                plan_id = int(match.group(1))
                data = self.read_json_body()
                old_plan = models.get_plan(plan_id)
                if not old_plan:
                    self.send_error_json("Plano não encontrado.", 404)
                    return
                code = data.get('legacy_code', old_plan['legacy_code'])
                desc = data.get('description', old_plan['description'])
                cycle = data.get('cycle', old_plan['cycle'])
                unit = data.get('unit', old_plan['unit'])
                text = data.get('cycle_text', old_plan.get('cycle_text') or '')
                horiz = data.get('opening_horizon', old_plan.get('opening_horizon') or 0.0)
                start_stop = data.get('start_stop', old_plan.get('phase'))
                ref_cnt = data.get('reference_counter', old_plan.get('reference_counter'))
                status = data.get('status', old_plan.get('status') or 'ACTIVE')
                notes = data.get('notes', old_plan.get('notes'))
                
                if start_stop is not None and start_stop != '':
                    start_stop = max(1, int(start_stop))
                    project = models.get_project(int(data.get('project_id') or old_plan['project_id']))
                    cnt_val = int(project['current_counter']) + start_stop
                else:
                    start_stop = None
                    cnt_val = int(ref_cnt) if ref_cnt is not None and ref_cnt != '' else None
                
                try:
                    models.update_plan(
                        plan_id, code, desc, cycle, unit, text, horiz,
                        cnt_val, status, notes, start_stop)
                except models.PlanCodeConflict as conflict:
                    self.send_plan_code_conflict(conflict)
                    return
                self.send_json({'message': 'Plano atualizado com sucesso!'})
                return

            # PUT /api/items/{id}
            match = re.match(r'^/api/items/(\d+)$', path)
            if match:
                item_id = int(match.group(1))
                data = self.read_json_body()
                old_item = models.get_item(item_id)
                if not old_item:
                    self.send_error_json("Item não encontrado.", 404)
                    return
                identifier = data.get('legacy_identifier', old_item['legacy_identifier'])
                plan_id = data.get('plan_id', old_item['plan_id'])
                team_id = data.get('team_id', old_item.get('team_id'))
                obj_type = data.get('object_type', old_item.get('object_type') or 'EQUIPAMENTO')
                obj_code = data.get('object_code', old_item.get('object_code'))
                gpm = data.get('gpm', old_item.get('gpm'))
                wc = data.get('work_center', old_item.get('work_center'))
                cond = data.get('condition_code', old_item.get('condition_code'))
                priority = data.get('priority', old_item.get('priority'))
                start = data.get('legacy_start', old_item.get('legacy_start'))
                desc = data.get('description', old_item.get('description'))
                dur = data.get('duration_hours', old_item.get('duration_hours'))
                headcount = data.get('headcount', old_item.get('headcount'))
                status = data.get('status', old_item.get('status') or 'ACTIVE')
                notes = data.get('notes', old_item.get('notes'))
                mec_hc = data.get('mec_headcount', old_item.get('mec_headcount', 0))
                mec_h = data.get('mec_hours', old_item.get('mec_hours', 0.0))
                ele_hc = data.get('ele_headcount', old_item.get('ele_headcount', 0))
                ele_h = data.get('ele_hours', old_item.get('ele_hours', 0.0))
                sol_hc = data.get('sol_headcount', old_item.get('sol_headcount', 0))
                sol_h = data.get('sol_hours', old_item.get('sol_hours', 0.0))
                
                p_id = int(plan_id) if plan_id else None
                t_id = int(team_id) if team_id else None
                cnt_start = int(start) if start is not None and start != '' else None

                models.update_item(
                    item_id, identifier, p_id, obj_type, obj_code, gpm, wc, cond, priority, cnt_start, desc, dur, headcount, status, notes, t_id,
                    mec_headcount=mec_hc, mec_hours=mec_h, ele_headcount=ele_hc, ele_hours=ele_h, sol_headcount=sol_hc, sol_hours=sol_h
                )
                self.send_json({'message': 'Item atualizado com sucesso!'})
                return

            # PUT /api/shifts
            if path == '/api/shifts':
                data = self.read_json_body()
                proj_id = int(data.get('project_id', 0))
                shifts_list = data.get('shifts', [])
                
                models.update_shifts(proj_id, shifts_list)
                self.send_json({'message': 'Turnos atualizados com sucesso!'})
                return

            # PUT /api/cycles
            if path == '/api/cycles':
                data = self.read_json_body()
                proj_id = int(data.get('project_id', 0))
                cycles_list = data.get('cycles', [])
                
                models.update_cycle_catalog(proj_id, cycles_list)
                self.send_json({'message': 'Catálogo de ciclos atualizado com sucesso!'})
                return

            match = re.match(r'^/api/operations/(\d+)$', path)
            if match:
                op_id = int(match.group(1)); data = self.read_json_body()
                conn = get_db_connection(); cur = conn.cursor()
                cur.execute("SELECT * FROM item_operations WHERE id=?", (op_id,))
                existing = cur.fetchone()
                if not existing:
                    conn.close()
                    self.send_error_json('Operação não encontrada.', 404)
                    return
                existing_dict = models.to_dict(existing)

                new_op_code = str(data.get('operation_code', existing_dict['operation_code']) or '0010').strip()
                new_sub_code = str(data.get('suboperation_code', existing_dict['suboperation_code']) or '').strip()
                new_wc = data.get('work_center', existing_dict['work_center'])
                new_short = data.get('short_text', existing_dict['short_text'])
                new_unit = data.get('unit', existing_dict['unit'])
                new_hc = data.get('headcount', existing_dict['headcount'])
                new_hours = data.get('hours', existing_dict['hours'])
                new_item_id = int(data.get('item_id') or existing_dict['item_id'])

                validation_status = existing_dict.get('validation_status') or 'OK'
                validation_issues_json = existing_dict.get('validation_issues_json')
                pending_identifier = existing_dict.get('pending_item_identifier')
                if pending_identifier and data.get('item_id') and not new_op_code.upper().startswith('COPIA'):
                    try:
                        issues = json.loads(validation_issues_json or '[]')
                    except (TypeError, ValueError):
                        issues = []
                    issues = [issue for issue in issues if issue.get('code') != 'copy_requires_item_review']
                    validation_status = ('ERROR' if any(i.get('severity') == 'ERROR' for i in issues) else 'WARNING' if issues else 'OK')
                    validation_issues_json = json.dumps(issues, ensure_ascii=False)
                    pending_identifier = None
                if data.get('resolve_import_placeholder'):
                    try:
                        issues = json.loads(validation_issues_json or '[]')
                    except (TypeError, ValueError):
                        issues = []
                    issues = [issue for issue in issues
                              if issue.get('code') != 'long_text_without_operation']
                    validation_status = ('ERROR' if any(issue.get('severity') == 'ERROR' for issue in issues)
                                         else 'WARNING' if issues else 'OK')
                    validation_issues_json = json.dumps(issues, ensure_ascii=False)

                cur.execute("""UPDATE item_operations SET item_id=?, operation_code=?, suboperation_code=?, work_center=?,
                            short_text=?, unit=?, headcount=?, hours=?,validation_status=?,validation_issues_json=?,
                            pending_item_identifier=?, updated_at=CURRENT_TIMESTAMP WHERE id=?""",
                            (new_item_id, new_op_code, new_sub_code, new_wc, new_short, new_unit, new_hc, new_hours,
                             validation_status, validation_issues_json, pending_identifier, op_id))
                if data.get('resolve_import_placeholder'):
                    text_rows = cur.execute("""SELECT id,validation_issues_json
                        FROM operation_long_texts WHERE operation_id=?""", (op_id,)).fetchall()
                    for text_row in text_rows:
                        try:
                            text_issues = json.loads(text_row['validation_issues_json'] or '[]')
                        except (TypeError, ValueError):
                            text_issues = []
                        text_issues = [issue for issue in text_issues
                                       if issue.get('code') != 'long_text_without_operation']
                        text_status = ('ERROR' if any(issue.get('severity') == 'ERROR' for issue in text_issues)
                                       else 'WARNING' if text_issues else 'OK')
                        cur.execute("""UPDATE operation_long_texts SET validation_status=?,
                            validation_issues_json=?,updated_at=CURRENT_TIMESTAMP WHERE id=?""",
                            (text_status, json.dumps(text_issues, ensure_ascii=False), text_row['id']))
                conn.commit(); conn.close()
                self.send_json({'message': 'Operação atualizada com sucesso!'})
                return

            match = re.match(r'^/api/long-texts/(\d+)$', path)
            if match:
                text_id = int(match.group(1)); data = self.read_json_body()
                prepared = prepare_for_save(
                    data.get('text') or '', data.get('structure_mode'),
                    data.get('structure_json'), data.get('source_text_original')
                )
                if not prepared['text'].strip():
                    self.send_error_json('O texto longo não pode ficar vazio.')
                    return
                conn = get_db_connection(); cur = conn.cursor()
                existing = cur.execute("SELECT * FROM operation_long_texts WHERE id=?", (text_id,)).fetchone()
                if not existing:
                    conn.close(); self.send_error_json('Texto longo não encontrado.', 404); return
                operation_id = int(data.get('operation_id') or existing['operation_id'])
                pending = existing['pending_item_identifier']
                issues_json = existing['validation_issues_json']
                status = existing['validation_status']
                if pending and data.get('operation_id'):
                    try: issues = json.loads(issues_json or '[]')
                    except (TypeError, ValueError): issues = []
                    issues = [i for i in issues if i.get('code') != 'copy_requires_item_review']
                    status = 'ERROR' if any(i.get('severity') == 'ERROR' for i in issues) else 'WARNING' if issues else 'OK'
                    issues_json = json.dumps(issues, ensure_ascii=False); pending = None
                cur.execute("""UPDATE operation_long_texts SET operation_id=?, group_code=?, group_counter=?, text=?,
                            structure_mode=?,structure_json=?,source_text_original=?,
                            validation_status=?,validation_issues_json=?,pending_item_identifier=?,updated_at=CURRENT_TIMESTAMP WHERE id=?""",
                            (operation_id, data.get('group_code'), data.get('group_counter'), prepared['text'],
                             prepared['structure_mode'], prepared['structure_json'], prepared['source_text_original'],
                             status, issues_json, pending, text_id))
                conn.commit(); conn.close()
                self.send_json({'message': 'Texto longo atualizado com sucesso!', 'text': prepared['text'],
                                'structure_mode': prepared['structure_mode']})
                return

            self.send_error_json("Rota PUT não encontrada.", 404)
            
        except Exception as e:
            self.send_error_json(f"Erro interno no servidor: {e}", 500)
            import traceback
            traceback.print_exc()

    def do_DELETE(self):
        self._handle_project_mutation(self._do_DELETE_impl, 'DELETE')

    def _do_DELETE_impl(self):
        url_parsed = urllib.parse.urlparse(self.path)
        path = url_parsed.path
        query = urllib.parse.parse_qs(url_parsed.query)
        q_params = {k: v[0] for k, v in query.items() if v}
        
        try:
            if path.startswith('/api/pm11'):
                if pm11_handler.handle_pm11_request(self, 'DELETE', path, q_params):
                    return

            # DELETE /api/standards/long-texts/{id}
            match = re.match(r'^/api/standards/long-texts/(\d+)$', path)
            if match:
                std_id = int(match.group(1))
                models.delete_standard_long_text(std_id)
                self.send_json({'message': 'Modelo de texto longo excluído com sucesso!'})
                return

            match = re.match(r'^/api/long-text-blocks/(\d+)$', path)
            if match:
                models.delete_standard_long_text_block(int(match.group(1)))
                self.send_json({'message': 'Bloco padrão excluído com sucesso!'})
                return

            # DELETE /api/standards/items/{id}
            match = re.match(r'^/api/standards/items/(\d+)$', path)
            if match:
                std_id = int(match.group(1))
                models.delete_standard_item(std_id)
                self.send_json({'message': 'Modelo de item padrão excluído com sucesso!'})
                return

            # DELETE /api/teams/{id}
            match = re.match(r'^/api/teams/(\d+)$', path)
            if match:
                team_id = int(match.group(1))
                models.delete_team(team_id)
                self.send_json({'message': 'Equipe excluída com sucesso!'})
                return

            # DELETE /api/projects/{id}
            match = re.match(r'^/api/projects/(\d+)$', path)
            if match:
                p_id = int(match.group(1))
                models.delete_project(p_id)
                self.send_json({'message': 'Projeto excluído com sucesso!'})
                return

            # DELETE /api/plans/{id}
            match = re.match(r'^/api/plans/(\d+)$', path)
            if match:
                plan_id = int(match.group(1))
                item_action = q_params.get('item_action', 'unbind')
                target_plan_id = q_params.get('target_plan_id')
                if target_plan_id:
                    target_plan_id = int(target_plan_id)
                    
                models.delete_plan(plan_id, item_action, target_plan_id)
                self.send_json({'message': 'Plano excluído com sucesso!'})
                return

            # DELETE /api/items/{id}
            match = re.match(r'^/api/items/(\d+)$', path)
            if match:
                item_id = int(match.group(1))
                cascade_related = str(q_params.get('cascade_related', 'false')).lower() == 'true'
                models.delete_item(item_id, cascade_related=cascade_related)
                self.send_json({'message': 'Item excluído com sucesso!'})
                return

            # DELETE /api/operations/{id}
            match = re.match(r'^/api/operations/(\d+)$', path)
            if match:
                op_id = int(match.group(1))
                conn = get_db_connection(); cur = conn.cursor()
                cur.execute("DELETE FROM operation_long_texts WHERE operation_id = ?", (op_id,))
                cur.execute("DELETE FROM item_operations WHERE id = ?", (op_id,))
                conn.commit(); conn.close()
                self.send_json({'message': 'Operação excluída com sucesso!'})
                return

            # DELETE /api/long-texts/{id}
            match = re.match(r'^/api/long-texts/(\d+)$', path)
            if match:
                text_id = int(match.group(1))
                conn = get_db_connection(); cur = conn.cursor()
                cur.execute("DELETE FROM operation_long_texts WHERE id = ?", (text_id,))
                conn.commit(); conn.close()
                self.send_json({'message': 'Texto longo excluído com sucesso!'})
                return

            # DELETE /api/backups
            if path == '/api/backups':
                filename = q_params.get('filename')
                if not filename:
                    self.send_error_json("Nome do backup não fornecido.")
                    return
                backup_service.delete_backup(filename)
                self.send_json({'message': 'Backup excluído com sucesso!'})
                return

            self.send_error_json("Rota DELETE não encontrada.", 404)
            
        except Exception as e:
            self.send_error_json(f"Erro interno no servidor: {e}", 500)
            import traceback
            traceback.print_exc()

def run_server():
    # 1. Run migrations first
    print("Iniciando banco de dados PM13...")
    conn = get_db_connection()
    run_migrations(conn)
    conn.close()
    
    print("Iniciando banco de dados PM11...")
    pm11_migrations.run_migrations()
    # alternate between old and new code on Windows, producing inconsistent
    # import previews. Refuse startup until the previous instance is closed.
    port = 8765
    try:
        # Listen on every local interface so authorized computers on the same
        # LAN can access the application. The browser on this machine still
        # uses loopback below.
        httpd = ExclusiveThreadingHTTPServer(('0.0.0.0', port), PM13RequestHandler)
        httpd.daemon_threads = True
        print(f"Servidor iniciado com sucesso: http://127.0.0.1:{port}")
        try:
            probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            probe.connect(('8.8.8.8', 80))
            local_ip = probe.getsockname()[0]
            probe.close()
            print(f"Acesso pela rede local: http://{local_ip}:{port}")
        except OSError:
            print(f"Acesso pela rede local: use o IP deste computador na porta {port}")
        print(f"Versão em execução: {APP_BUILD}")
    except socket.error as e:
        if e.errno in (10013, 10048, 98):
            print("ERRO: já existe uma instância do PM13 usando a porta 8765.")
            print("Feche todas as janelas antigas do servidor e execute INICIAR_PM13.bat novamente.")
        else:
            print(f"Falha crítica de socket: {e}")
        sys.exit(1)
        
    # Open the default browser during normal interactive startup.  Automated
    # restarts can suppress the extra window without changing user defaults.
    if os.environ.get('PM13_NO_BROWSER') != '1':
        try:
            webbrowser.open(f"http://127.0.0.1:{port}")
        except Exception as e:
            print(f"Erro ao abrir navegador automaticamente: {e}")
        
    # Keep server running
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nServidor interrompido pelo usuário. Finalizando...")
        sys.exit(0)

if __name__ == '__main__':
    run_server()
