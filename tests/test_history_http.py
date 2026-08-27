import http.server
import json
import os
import socket
import tempfile
import threading
import unittest
import urllib.error
import urllib.request

import app
from core import database, history_service, migrations, models


class TestHistoryHttpIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._old_db_path = database.DB_PATH
        cls._temp_dir = tempfile.TemporaryDirectory(prefix='pm13_history_http_')
        database.DB_PATH = os.path.join(cls._temp_dir.name, 'history-http.db')

        conn = database.get_db_connection()
        migrations.run_migrations(conn)
        conn.close()
        cls.project_id = models.create_project(
            'Histórico HTTP', 'Projeto isolado para testes', 'TESTE',
            system_name='HTTP', current_counter=100,
        )

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.bind(('127.0.0.1', 0))
        cls.port = sock.getsockname()[1]
        sock.close()
        cls.server = http.server.ThreadingHTTPServer(
            ('127.0.0.1', cls.port), app.PM13RequestHandler
        )
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)
        database.DB_PATH = cls._old_db_path
        cls._temp_dir.cleanup()

    def request(self, method, path, body=None, expected=200):
        data = json.dumps(body).encode('utf-8') if body is not None else None
        headers = {'Content-Type': 'application/json'} if body is not None else {}
        request = urllib.request.Request(
            f'http://127.0.0.1:{self.port}{path}',
            data=data,
            headers=headers,
            method=method,
        )
        try:
            response = urllib.request.urlopen(request, timeout=10)
            payload = json.loads(response.read().decode('utf-8'))
            self.assertEqual(response.status, expected)
            return response.status, payload
        except urllib.error.HTTPError as exc:
            payload = json.loads(exc.read().decode('utf-8'))
            self.assertEqual(exc.code, expected)
            return exc.code, payload

    def plan_payload(self, code, description):
        return {
            'project_id': self.project_id,
            'legacy_code': code,
            'description': description,
            'cycle': 2,
            'unit': 'PRD',
            'cycle_text': '2P',
            'reference_counter': 102,
            'opening_horizon': 36,
        }

    def test_mutation_undo_redo_and_redo_branch(self):
        _, created = self.request(
            'POST', '/api/plans', self.plan_payload('HIST_HTTP_1', 'Plano original')
        )
        plan_id = created['id']

        _, status = self.request(
            'GET', f'/api/history/status?project_id={self.project_id}'
        )
        self.assertTrue(status['can_undo'])
        self.assertEqual(status['undo_label'], 'Criar plano')
        self.assertFalse(status['can_redo'])

        _, undone = self.request(
            'POST', '/api/history/undo', {'project_id': self.project_id}
        )
        self.assertEqual(undone['action']['action'], 'Criar plano')
        self.assertIsNone(models.get_plan(plan_id))
        self.assertTrue(undone['status']['can_redo'])

        _, redone = self.request(
            'POST', '/api/history/redo', {'project_id': self.project_id}
        )
        self.assertEqual(models.get_plan(plan_id)['description'], 'Plano original')
        self.assertTrue(redone['status']['can_undo'])

        self.request('PUT', f'/api/plans/{plan_id}', {'description': 'Plano editado'})
        self.assertEqual(models.get_plan(plan_id)['description'], 'Plano editado')
        self.request('POST', '/api/history/undo', {'project_id': self.project_id})
        self.assertEqual(models.get_plan(plan_id)['description'], 'Plano original')

        # A rejected/no-op request must not erase the available redo step.
        self.request('POST', '/api/items', {'project_id': self.project_id}, expected=400)
        _, status = self.request(
            'GET', f'/api/history/status?project_id={self.project_id}'
        )
        self.assertTrue(status['can_redo'])

        # A real new action after undo creates a new branch and invalidates redo.
        self.request(
            'POST', '/api/plans', self.plan_payload('HIST_HTTP_2', 'Novo ramo')
        )
        _, status = self.request(
            'GET', f'/api/history/status?project_id={self.project_id}'
        )
        self.assertFalse(status['can_redo'])
        self.request(
            'POST', '/api/history/redo', {'project_id': self.project_id}, expected=409
        )

        entries = history_service.list_history(self.project_id)
        self.assertEqual(entries[0]['action'], 'Criar plano')

    def test_missing_project_status_is_404(self):
        self.request('GET', '/api/history/status?project_id=99999999', expected=404)


if __name__ == '__main__':
    unittest.main()
