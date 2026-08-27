import os
import re
import json
import urllib.parse
import datetime
import traceback
import tempfile

from . import models
from . import balance
from . import import_export
from . import history
from . import backup
from . import xlsx_io

BUILD_PM11 = '2026.08.21-pm11-v3-profissional'


def _parse_body(handler):
    if hasattr(handler, '_body_json') and handler._body_json is not None:
        d = handler._body_json
        if isinstance(d, str):
            try:
                d = json.loads(d)
            except Exception:
                d = {}
        return d if isinstance(d, dict) else {}
    if hasattr(handler, 'read_json_body'):
        try:
            data = handler.read_json_body()
            if isinstance(data, str):
                try:
                    data = json.loads(data)
                except Exception:
                    data = {}
            handler._body_json = data
            return data if isinstance(data, dict) else {}
        except Exception:
            pass
    try:
        content_length = int(handler.headers.get('Content-Length', 0) or 0)
        if not content_length:
            return {}
        raw = handler.rfile.read(content_length).decode('utf-8')
        data = json.loads(raw) if raw else {}
        if isinstance(data, str):
            try:
                data = json.loads(data)
            except Exception:
                data = {}
        handler._body_json = data
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}

def _get_project_id(handler, path, q_params, body_data=None):
    if body_data and isinstance(body_data, dict) and body_data.get('project_id'):
        return int(body_data['project_id'])
    v = q_params.get('project_id') or handler.headers.get('X-PM11-Project-ID')
    return int(v) if v and str(v).isdigit() else None


def _send_bytes(handler, b_content, ctype='application/octet-stream', filename=None):
    handler.send_response(200)
    handler.send_header('Content-Type', ctype)
    handler.send_header('Content-Length', str(len(b_content)))
    handler.send_header('Cache-Control', 'no-store')
    if filename:
        handler.send_header('Content-Disposition', f'attachment; filename="{filename}"')
    handler.end_headers()
    handler.wfile.write(b_content)


def _parse_upload(handler):
    ctype = handler.headers.get('Content-Type', '')
    m = re.search(r'boundary=([^;]+)', ctype)
    if not m:
        raise ValueError('Upload multipart inválido.')
    boundary = m.group(1).strip().strip('"').encode()
    n = int(handler.headers.get('Content-Length', 0) or 0)
    if n > 100 * 1024 * 1024:
        raise ValueError('Arquivo excede 100 MB.')
    raw = handler.rfile.read(n)
    parts = raw.split(b'--' + boundary)
    fields = {}
    file_info = None
    for part in parts:
        if b'\r\n\r\n' not in part:
            continue
        head, content = part.split(b'\r\n\r\n', 1)
        content = content.rstrip(b'\r\n-')
        hm = re.search(br'name="([^"]+)"', head)
        if not hm:
            continue
        name = hm.group(1).decode()
        fm = re.search(br'filename="([^"]*)"', head)
        if fm:
            filename = os.path.basename(fm.group(1).decode(errors='ignore') or 'import.xlsx')
            fd, path = tempfile.mkstemp(prefix='pm11_import_', suffix='.xlsx')
            os.close(fd)
            with open(path, 'wb') as f:
                f.write(content)
            file_info = {'name': filename, 'path': path, 'size': len(content)}
        else:
            fields[name] = content.decode('utf-8', errors='ignore')
    if not file_info:
        raise ValueError('Nenhum arquivo recebido.')
    return fields, file_info


def _json_field(fields, key, default=None):
    try:
        return json.loads(fields.get(key, '')) if fields.get(key) else default
    except Exception:
        return default


def _mutate(pid, label, fn):
    if pid and models.project_is_locked(pid):
        raise ValueError('Projeto trancado. Destranque o projeto para alterar seus dados.')
    before = history.capture(pid)
    result = fn()
    after = history.capture(pid)
    history.record(pid, label, before, after)
    return result


def _balance_filters(src):
    return {k: src.get(k) for k in ('plan_id', 'item_id', 'route', 'gpm', 'work_center', 'condition', 'priority', 'status')
            if src.get(k) not in (None, '', 'ALL', 'TODOS')}


def handle_pm11_request(handler, method, full_path, q_params):
    # Normalize path: /api/pm11/projects -> /api/projects for routing
    if full_path.startswith('/api/pm11/'):
        subpath = '/api/' + full_path[len('/api/pm11/'):]
    elif full_path == '/api/pm11':
        subpath = '/api/'
    else:
        subpath = full_path

    try:
        if method == 'GET':
            if subpath == '/api/health':
                handler.send_json({'ok': True, 'build': BUILD_PM11})
                return True
            if subpath == '/api/projects':
                handler.send_json(models.get_projects())
                return True
            if subpath.startswith('/api/projects/'):
                pid = int(subpath.rsplit('/', 1)[1])
                handler.send_json(models.get_project(pid) or {})
                return True
            if subpath == '/api/dashboard':
                pid = _get_project_id(handler, subpath, q_params)
                handler.send_json(models.dashboard(pid))
                return True
            if subpath == '/api/catalogs':
                handler.send_json({'cycles': models.get_cycles(), **models.get_code_catalogs()})
                return True
            if subpath == '/api/methods':
                handler.send_json(models.search_methods(q_params.get('q', ''), q_params.get('hint', ''), int(q_params.get('limit', 30))))
                return True
            if subpath == '/api/units':
                handler.send_json(models.search_units(q_params.get('q', ''), q_params.get('hint', ''), int(q_params.get('limit', 30))))
                return True
            if subpath == '/api/plans':
                pid = _get_project_id(handler, subpath, q_params)
                handler.send_json(models.list_plans(pid, q_params.get('search', ''), q_params.get('status', ''), q_params.get('cycle_code', ''), q_params.get('row_color', '')))
                return True
            if subpath.startswith('/api/plans/'):
                plan_id = int(subpath.rsplit('/', 1)[1])
                handler.send_json(models.get_plan(plan_id) or {})
                return True
            if subpath == '/api/items/filter-options':
                pid = _get_project_id(handler, subpath, q_params)
                handler.send_json(models.list_filter_options(pid))
                return True
            if subpath == '/api/items':
                pid = _get_project_id(handler, subpath, q_params)
                plan_id = int(q_params['plan_id']) if q_params.get('plan_id', '').isdigit() else None
                handler.send_json(models.list_items(pid, q_params.get('search', ''), plan_id, q_params.get('status', ''), q_params.get('equipment', ''), q_params.get('route', ''), q_params.get('gpm', ''), q_params.get('work_center', ''), q_params.get('condition', ''), q_params.get('priority', ''), q_params.get('row_color', '')))
                return True
            if subpath.startswith('/api/items/'):
                iid = int(subpath.rsplit('/', 1)[1])
                handler.send_json(models.get_item(iid) or {})
                return True
            if subpath == '/api/characteristics':
                pid = _get_project_id(handler, subpath, q_params)
                item_id = int(q_params['item_id']) if q_params.get('item_id', '').isdigit() else None
                handler.send_json(models.list_characteristics(pid, q_params.get('search', ''), item_id, q_params.get('type', ''), q_params.get('method', ''), q_params.get('status', ''), q_params.get('row_color', '')))
                return True
            if subpath.startswith('/api/characteristics/'):
                cid = int(subpath.rsplit('/', 1)[1])
                handler.send_json(models.get_characteristic(cid) or {})
                return True
            if subpath == '/api/templates/characteristics':
                pid = _get_project_id(handler, subpath, q_params)
                handler.send_json(models.list_char_templates(pid))
                return True
            if subpath.startswith('/api/templates/characteristics/'):
                tid = int(subpath.rsplit('/', 1)[1])
                handler.send_json(models.get_char_template(tid) or {})
                return True
            if subpath == '/api/templates/items':
                pid = _get_project_id(handler, subpath, q_params)
                handler.send_json(models.list_item_templates(pid))
                return True
            if subpath.startswith('/api/templates/items/'):
                tid = int(subpath.rsplit('/', 1)[1])
                handler.send_json(models.get_item_template(tid) or {})
                return True
            if subpath == '/api/templates/equipment':
                pid = _get_project_id(handler, subpath, q_params)
                handler.send_json(models.list_equipment_templates(pid))
                return True
            if subpath.startswith('/api/templates/equipment/'):
                tid = int(subpath.rsplit('/', 1)[1])
                handler.send_json(models.get_equipment_template(tid) or {})
                return True
            if subpath == '/api/balance/options':
                pid = _get_project_id(handler, subpath, q_params)
                handler.send_json(balance.filter_options(pid))
                return True
            if subpath == '/api/balance':
                pid = _get_project_id(handler, subpath, q_params)
                days = int(q_params.get('days', 30))
                start = q_params.get('start') or None
                target = float(q_params.get('target_minutes') or 0)
                s = balance.project_schedule(pid, start, days, filters=_balance_filters(q_params))
                handler.send_json({'schedule': s, 'metrics': balance.metrics(s, target), 'days': days, 'start': start})
                return True
            if subpath == '/api/balance/book':
                pid = _get_project_id(handler, subpath, q_params)
                handler.send_json(balance.book_items(pid, _balance_filters(q_params)))
                return True
            if subpath == '/api/balance/eligible-plans':
                pid = _get_project_id(handler, subpath, q_params)
                item_id = int(q_params.get('item_id', 0))
                day_idx = int(q_params.get('day_idx', 0))
                start = q_params.get('start') or None
                days = int(q_params.get('days', 30))
                handler.send_json(balance.get_eligible_plans_for_drop(pid, item_id, day_idx, start, days))
                return True
            if subpath == '/api/history/status':
                pid = _get_project_id(handler, subpath, q_params)
                handler.send_json(history.status(pid))
                return True
            if subpath == '/api/export/model':
                _send_bytes(handler, import_export.export_model(), 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', 'MODELO_PM11.xlsx')
                return True
            if subpath == '/api/export/project':
                pid = _get_project_id(handler, subpath, q_params)
                days = int(q_params.get('days', 90))
                start = q_params.get('start') or None
                s = balance.project_schedule(pid, start, days, filters=_balance_filters(q_params))
                b_content = import_export.export_project(pid, s)
                proj = models.get_project(pid) or {'name': 'PM11'}
                fn = 'PM11_' + re.sub(r'[^A-Za-z0-9_-]+', '_', proj['name']) + '_' + datetime.datetime.now().strftime('%Y%m%d_%H%M%S') + '.xlsx'
                _send_bytes(handler, b_content, 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', fn)
                return True
            if subpath == '/api/export/systems':
                pid = _get_project_id(handler, subpath, q_params)
                b_content = xlsx_io.export_systems_xlsx(pid)
                proj = models.get_project(pid) or {'name': 'PM11'}
                fn = 'CARGA_SISTEMAS_PM11_' + re.sub(r'[^A-Za-z0-9_-]+', '_', proj['name']) + '_' + datetime.datetime.now().strftime('%Y%m%d_%H%M%S') + '.xlsx'
                _send_bytes(handler, b_content, 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', fn)
                return True
            if subpath == '/api/sap-cycles':
                from .sap_standards import SAP_CYCLE_TABLE
                handler.send_json(SAP_CYCLE_TABLE)
                return True
            if subpath == '/api/backup':
                path = backup.create_backup('manual')
                _send_bytes(handler, open(path, 'rb').read(), 'application/zip', os.path.basename(path))
                return True

        elif method == 'POST':
            if subpath == '/api/logs':
                d = _parse_body(handler)
                handler.send_json({'ok': True})
                return True
            if subpath in ('/api/validate', '/api/pm11/validate'):
                d = _parse_body(handler)
                pid = _get_project_id(handler, subpath, q_params, d)
                from .validation_engine import validate_pm11_project
                handler.send_json(validate_pm11_project(pid))
                return True
            if subpath == '/api/projects':
                d = _parse_body(handler)
                handler.send_json(models.create_project(d), 201)
                return True
            if subpath == '/api/projects/duplicate':
                d = _parse_body(handler)
                handler.send_json(models.duplicate_project(int(d['project_id']), d.get('name')), 201)
                return True
            if subpath == '/api/projects/lock':
                d = _parse_body(handler)
                handler.send_json(models.set_project_lock(int(d['project_id']), bool(d.get('locked', True))))
                return True
            if re.match(r'^/api/projects/\d+/anchor-date$', subpath):
                d = _parse_body(handler); pid = int(subpath.split('/')[3])
                anchor = d.get('balance_anchor_date') or d.get('anchor_date') or None
                if anchor:
                    datetime.date.fromisoformat(anchor)
                handler.send_json(models.update_project(pid, {'balance_anchor_date': anchor}))
                return True
            if subpath == '/api/plans':
                d = _parse_body(handler)
                pid = _get_project_id(handler, subpath, q_params, d)
                handler.send_json(_mutate(pid, 'Criar plano', lambda: models.create_plan(pid, d)), 201)
                return True
            if subpath == '/api/plans/clone':
                d = _parse_body(handler)
                pid = _get_project_id(handler, subpath, q_params, d)
                handler.send_json(_mutate(pid, 'Duplicar plano', lambda: models.clone_plan(pid, int(d['plan_id']), bool(d.get('include_children', False)), d.get('new_code'), d.get('new_description'))), 201)
                return True
            if subpath == '/api/plans/save-package-template':
                d = _parse_body(handler)
                pid = _get_project_id(handler, subpath, q_params, d)
                handler.send_json(_mutate(pid, 'Salvar plano como modelo', lambda: models.save_plan_as_package_template(pid, int(d['plan_id']), d['name'], d.get('category', ''), d.get('description', ''), d.get('scope', 'PROJECT'))), 201)
                return True
            if subpath == '/api/plans/bulk-update':
                d = _parse_body(handler)
                pid = _get_project_id(handler, subpath, q_params, d)
                handler.send_json(_mutate(pid, 'Editar planos em massa', lambda: models.bulk_update_plans(d.get('ids', []), d.get('updates', {}))))
                return True
            if subpath == '/api/plans/bulk-delete':
                d = _parse_body(handler)
                pid = _get_project_id(handler, subpath, q_params, d)
                handler.send_json(_mutate(pid, 'Excluir planos', lambda: (models.delete_plans(d.get('ids', [])) or {'ok': True})))
                return True
            if subpath == '/api/items':
                d = _parse_body(handler)
                pid = _get_project_id(handler, subpath, q_params, d)
                handler.send_json(_mutate(pid, 'Criar item', lambda: models.create_item(pid, d)), 201)
                return True
            if subpath == '/api/items/clone':
                d = _parse_body(handler)
                pid = _get_project_id(handler, subpath, q_params, d)
                handler.send_json(_mutate(pid, 'Clonar item PM11', lambda: models.clone_item(pid, int(d['item_id']), bool(d.get('include_characteristics', True)))))
                return True
            if subpath == '/api/items/bulk-update':
                d = _parse_body(handler)
                pid = _get_project_id(handler, subpath, q_params, d)
                handler.send_json(_mutate(pid, 'Editar itens em massa', lambda: models.bulk_update_items(d.get('ids', []), d.get('updates', {}))))
                return True
            if subpath == '/api/items/bulk-delete':
                d = _parse_body(handler)
                pid = _get_project_id(handler, subpath, q_params, d)
                handler.send_json(_mutate(pid, 'Excluir itens', lambda: (models.delete_items(d.get('ids', [])) or {'ok': True})))
                return True
            if subpath == '/api/items/save-template':
                d = _parse_body(handler)
                pid = _get_project_id(handler, subpath, q_params, d)
                handler.send_json(_mutate(pid, 'Salvar item como modelo', lambda: models.save_item_template_from_item(pid, int(d['item_id']), d['name'], d.get('category', ''), d.get('description', ''), d.get('scope', 'PROJECT'))), 201)
                return True
            if subpath == '/api/templates/items/apply':
                d = _parse_body(handler)
                pid = _get_project_id(handler, subpath, q_params, d)
                handler.send_json(_mutate(pid, 'Aplicar modelo de item', lambda: models.apply_item_template(pid, int(d['template_id']), int(d['plan_id']), d.get('equipment_code', ''), d.get('route', ''), d.get('gpm', ''), d.get('work_center', ''))))
                return True
            if subpath == '/api/templates/items/delete':
                d = _parse_body(handler)
                pid = _get_project_id(handler, subpath, q_params, d)
                handler.send_json(_mutate(pid, 'Excluir modelo de item', lambda: (models.delete_item_template(int(d['template_id'])) or {'ok': True})))
                return True
            if subpath == '/api/characteristics':
                d = _parse_body(handler)
                pid = _get_project_id(handler, subpath, q_params, d)
                handler.send_json(_mutate(pid, 'Criar característica', lambda: models.create_characteristic(pid, d)), 201)
                return True
            if subpath == '/api/characteristics/bulk-update':
                d = _parse_body(handler)
                pid = _get_project_id(handler, subpath, q_params, d)
                handler.send_json(_mutate(pid, 'Editar características em massa', lambda: models.bulk_update_characteristics(d.get('ids', []), d.get('updates', {}))))
                return True
            if subpath == '/api/characteristics/bulk-delete':
                d = _parse_body(handler)
                pid = _get_project_id(handler, subpath, q_params, d)
                handler.send_json(_mutate(pid, 'Excluir características', lambda: (models.delete_characteristics(d.get('ids', [])) or {'ok': True})))
                return True
            if subpath == '/api/catalogs/upsert':
                d = _parse_body(handler)
                handler.send_json(models.upsert_catalog(d['kind'], d['code'], d.get('description', '')))
                return True
            if subpath == '/api/templates/meta':
                d = _parse_body(handler)
                pid = _get_project_id(handler, subpath, q_params, d)
                handler.send_json(_mutate(pid, 'Editar modelo', lambda: models.update_template_meta(d['kind'], int(d['template_id']), d.get('updates', {}))))
                return True
            if subpath == '/api/templates/duplicate':
                d = _parse_body(handler)
                pid = _get_project_id(handler, subpath, q_params, d)
                handler.send_json(_mutate(pid, 'Duplicar modelo', lambda: models.duplicate_template(d['kind'], int(d['template_id']), d.get('name'))), 201)
                return True
            if subpath == '/api/templates/characteristics/save-from-item':
                d = _parse_body(handler)
                pid = _get_project_id(handler, subpath, q_params, d)
                handler.send_json(_mutate(pid, 'Salvar padrão de características', lambda: models.save_char_template_from_item(pid, int(d['item_id']), d['name'], d.get('category', ''), d.get('description', ''), d.get('scope', 'PROJECT'))), 201)
                return True
            if subpath == '/api/templates/characteristics/apply':
                d = _parse_body(handler)
                pid = _get_project_id(handler, subpath, q_params, d)
                handler.send_json(_mutate(pid, 'Aplicar padrão de características', lambda: models.apply_char_template(pid, int(d['template_id']), [int(x) for x in d.get('item_ids', [])], d.get('policy', 'IGNORE'))))
                return True
            if subpath == '/api/templates/equipment/save':
                d = _parse_body(handler)
                pid = _get_project_id(handler, subpath, q_params, d)
                handler.send_json(_mutate(pid, 'Salvar padrão de equipamento', lambda: models.save_equipment_template(pid, d['equipment_code'], d['name'], d.get('category', ''), d.get('description', ''), d.get('scope', 'PROJECT'))), 201)
                return True
            if subpath == '/api/templates/characteristics/delete':
                d = _parse_body(handler)
                pid = _get_project_id(handler, subpath, q_params, d)
                handler.send_json(_mutate(pid, 'Excluir padrão de características', lambda: (models.delete_char_template(int(d['template_id'])) or {'ok': True})))
                return True
            if subpath == '/api/templates/equipment/delete':
                d = _parse_body(handler)
                pid = _get_project_id(handler, subpath, q_params, d)
                handler.send_json(_mutate(pid, 'Excluir padrão de equipamento', lambda: (models.delete_equipment_template(int(d['template_id'])) or {'ok': True})))
                return True
            if subpath == '/api/templates/equipment/apply':
                d = _parse_body(handler)
                pid = _get_project_id(handler, subpath, q_params, d)
                handler.send_json(_mutate(pid, 'Aplicar padrão de equipamento', lambda: models.apply_equipment_template(pid, int(d['template_id']), d.get('equipment_code', ''), d.get('route_start'), d.get('gpm'), d.get('work_center'), d.get('plan_id_override'))))
                return True
            if subpath == '/api/balance/auto-preview':
                d = _parse_body(handler)
                pid = _get_project_id(handler, subpath, q_params, d)
                filters = _balance_filters(d)
                target = float(d.get('target_minutes') or 0)
                r = balance.auto_balance_preview(pid, d.get('start'), d.get('days', 90), target, filters)
                handler.send_json(r)
                return True
            if subpath == '/api/balance/manual-preview':
                d = _parse_body(handler)
                pid = _get_project_id(handler, subpath, q_params, d)
                filters = _balance_filters(d)
                handler.send_json(balance.manual_preview(pid, d.get('start'), d.get('days', 90), d.get('offsets', {}), float(d.get('target_minutes') or 0), filters))
                return True
            if subpath == '/api/balance/apply':
                d = _parse_body(handler)
                pid = _get_project_id(handler, subpath, q_params, d)
                backup.create_backup(f'auto_before_balance_{pid}')
                action = (lambda: balance.apply_assignments(pid, d.get('assignments', {}))) if 'assignments' in d else (lambda: balance.apply_offsets(pid, d.get('offsets', {})))
                handler.send_json(_mutate(pid, 'Aplicar balanceamento PM11', action))
                return True
            if subpath == '/api/balance/lock':
                d = _parse_body(handler)
                pid = _get_project_id(handler, subpath, q_params, d)
                handler.send_json(balance.lock_item(pid, int(d['item_id']), bool(d.get('locked', True))))
                return True
            if subpath in ('/api/balance/reset', '/api/balance/return-all'):
                d = _parse_body(handler)
                pid = _get_project_id(handler, subpath, q_params, d)
                only_unlocked = bool(d.get('only_unlocked', False))
                handler.send_json(_mutate(pid, 'Restaurar carga inicial PM11', lambda: balance.reset_offsets(pid, only_unlocked=only_unlocked)))
                return True
            if subpath == '/api/history/undo':
                d = _parse_body(handler)
                handler.send_json(history.undo(_get_project_id(handler, subpath, q_params, d)))
                return True
            if subpath == '/api/history/redo':
                d = _parse_body(handler)
                handler.send_json(history.redo(_get_project_id(handler, subpath, q_params, d)))
                return True
            if subpath == '/api/backup/restore':
                fields, f = _parse_upload(handler)
                try:
                    backup.restore_backup(f['path'])
                    handler.send_json({'ok': True})
                    return True
                finally:
                    try:
                        os.remove(f['path'])
                    except Exception:
                        pass
            if subpath == '/api/import/preview':
                fields, f = _parse_upload(handler)
                mapping = _json_field(fields, 'mapping', None)
                try:
                    r = import_export.preview_import(f['path'], mapping)
                    r = dict(r)
                    r.pop('data', None)
                    handler.send_json(r)
                    return True
                finally:
                    try:
                        os.remove(f['path'])
                    except Exception:
                        pass
            if subpath == '/api/import/confirm':
                fields, f = _parse_upload(handler)
                pid = int(fields.get('project_id') or 0)
                mode = fields.get('mode', 'MERGE').upper()
                mapping = _json_field(fields, 'mapping', None)
                before = history.capture(pid)
                backup.create_backup(f'auto_before_import_{pid}')
                try:
                    r = import_export.confirm_import(pid, f['path'], mode, mapping)
                    after = history.capture(pid)
                    history.record(pid, 'Importar planilha PM11', before, after)
                    handler.send_json(r)
                    return True
                finally:
                    try:
                        os.remove(f['path'])
                    except Exception:
                        pass

        elif method == 'PUT':
            d = _parse_body(handler)
            if subpath.startswith('/api/projects/'):
                pid = int(subpath.rsplit('/', 1)[1])
                if models.project_is_locked(pid):
                    raise ValueError('Projeto trancado. Destranque o projeto para editar seus dados.')
                handler.send_json(models.update_project(pid, d))
                return True
            if subpath.startswith('/api/plans/'):
                plan_id = int(subpath.rsplit('/', 1)[1])
                old = models.get_plan(plan_id)
                pid = old['project_id']
                handler.send_json(_mutate(pid, 'Editar plano', lambda: models.update_plan(plan_id, d)))
                return True
            if subpath.startswith('/api/items/'):
                iid = int(subpath.rsplit('/', 1)[1])
                old = models.get_item(iid)
                pid = old['project_id']
                handler.send_json(_mutate(pid, 'Editar item', lambda: models.update_item(iid, d)))
                return True
            if subpath.startswith('/api/characteristics/'):
                cid = int(subpath.rsplit('/', 1)[1])
                old = models.get_characteristic(cid)
                pid = old['project_id']
                handler.send_json(_mutate(pid, 'Editar característica', lambda: models.update_characteristic(cid, d)))
                return True

        elif method == 'DELETE':
            if subpath.startswith('/api/projects/'):
                pid = int(subpath.rsplit('/', 1)[1])
                if models.project_is_locked(pid):
                    raise ValueError('Projeto trancado. Destranque o projeto antes de excluir.')
                models.delete_project(pid)
                handler.send_json({'ok': True})
                return True
            if subpath == '/api/catalogs':
                models.delete_catalog(q_params['kind'], q_params['code'])
                handler.send_json({'ok': True})
                return True

        handler.send_error_json(f'Rota PM11 {method} {full_path} não encontrada.', 404)
        return True

    except ValueError as e:
        handler.send_error_json(str(e), 400)
        return True
    except Exception as e:
        traceback.print_exc()
        handler.send_error_json(f'Erro no PM11: {str(e)}', 500)
        return True
