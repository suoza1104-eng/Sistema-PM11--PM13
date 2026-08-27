import unittest
import os
import io
import sqlite3
import json
import socket
import threading
import time
import urllib.request
import urllib.error
import zipfile
import shutil
import http.server

# Import system modules
from core import database, migrations, validators, calculations, backup_service, export_service, models, auto_balance_service
import app

class TestDatabaseAndMigrations(unittest.TestCase):
    def setUp(self):
        self.db_path = os.path.abspath("test_pm13.db")
        if os.path.exists(self.db_path):
            try:
                os.remove(self.db_path)
            except Exception:
                pass
        database.DB_PATH = self.db_path

    def tearDown(self):
        if os.path.exists(self.db_path):
            try:
                os.remove(self.db_path)
            except Exception:
                pass

    def test_database_initialization(self):
        conn = database.get_db_connection()
        self.assertIsNotNone(conn)
        conn.close()

    def test_migrations(self):
        conn = database.get_db_connection()
        migrations.run_migrations(conn)
        
        # Verify tables exist
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = [row[0] for row in cursor.fetchall()]
        
        self.assertIn("projects", tables)
        self.assertIn("plans", tables)
        self.assertIn("maintenance_items", tables)
        self.assertIn("shifts", tables)
        self.assertIn("cycle_catalog", tables)
        self.assertIn("audit_log", tables)
        self.assertIn("project_settings", tables)

        for table in ("plans", "maintenance_items", "item_operations", "operation_long_texts"):
            columns = [row[1] for row in cursor.execute(f"PRAGMA table_info({table})").fetchall()]
            self.assertIn("validation_status", columns)
            self.assertIn("validation_issues_json", columns)
        
        conn.close()

    def test_stop_workforce_uses_daily_team_hours(self):
        conn = database.get_db_connection(); migrations.run_migrations(conn); conn.close()
        project_id = models.create_project('Workforce Project', '', '', '', 1, 1, 1.0)
        plan_id = models.create_plan(project_id, '1P1', 'Daily workforce', 1, 'PRD', '1P', 18.0, 1)
        team = models.create_team(project_id, {
            'name': 'ELE 9H', 'work_center': 'ELE01', 'num_shifts': 1,
            'shift_hours': 9.0, 'headcount_per_shift': 20,
            'tool_time_percent': 100.0, 'stop_days': 2
        })
        models.create_item(
            project_id, '1', plan_id, 'EQUIPAMENTO', 'MOTOR', 'ELE', 'ELE01',
            'P', 1, None, '322 HH electric work', 322.0, 1, team_id=team['id'],
            ele_headcount=1, ele_hours=322.0
        )
        result = calculations.project_balance(project_id, grouping='specialty')
        stop = result['stops'][0]
        self.assertEqual(stop['ele_hh'], 322.0)
        self.assertEqual(stop['ele_headcount_needed'], 36)
        self.assertEqual(stop['ele_headcount_per_day'], 18)
        self.assertEqual(result['capacity_stop_days']['ele'], 2)
        self.assertEqual(result['capacity_hours_per_person']['ele'], 9.0)

    def test_migration_removes_only_obsolete_numeric_identifier_warning(self):
        conn = database.get_db_connection()
        migrations.run_migrations(conn)
        cursor = conn.cursor()
        cursor.execute("INSERT INTO projects (name) VALUES ('Projeto identificador textual')")
        project_id = cursor.lastrowid
        issues = [
            {'code': 'Identificador', 'severity': 'WARNING',
             'message': 'Identificador legado não é estritamente numérico.', 'value': '1F57'},
            {'field': 'GPM', 'severity': 'WARNING', 'message': 'GPM pendente.', 'value': ''},
        ]
        cursor.execute("""INSERT INTO maintenance_items
            (project_id,legacy_identifier,object_code,gpm,work_center,condition_code,
             priority,description,character_count,duration_hours,hh,
             validation_status,validation_issues_json)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (project_id, '1F57', 'EQ-01', '000', 'MEC01', 'Q', 3, 'Item', 4, 1.0, 1.0,
             'WARNING', json.dumps(issues, ensure_ascii=False)))
        item_id = cursor.lastrowid
        conn.commit()

        migrations.run_migrations(conn)
        row = conn.execute("""SELECT validation_status,validation_issues_json
                              FROM maintenance_items WHERE id=?""", (item_id,)).fetchone()
        remaining = json.loads(row['validation_issues_json'])
        self.assertEqual(row['validation_status'], 'WARNING')
        self.assertEqual([issue['field'] for issue in remaining], ['GPM'])
        conn.close()

class TestCalculations(unittest.TestCase):
    def test_next_occurrence(self):
        # S_next = R + k * C
        # Case 1: reference counter S = 100, cycle C = 3, current counter = 106
        # (106 - 100) % 3 == 6 % 3 == 0 -> next occurrence is 106 (today)
        self.assertEqual(calculations.calculate_next_occurrence(100, 3, 106), 106)
        
        # Case 2: S = 100, C = 3, current counter = 107
        # (107 - 100) % 3 == 7 % 3 == 1 -> next occurrence is 107 + (3 - 1) = 109
        self.assertEqual(calculations.calculate_next_occurrence(100, 3, 107), 109)
        
        # Case 3: S = 110, C = 3, current counter = 106
        # S >= current -> next occurrence is S = 110
        self.assertEqual(calculations.calculate_next_occurrence(110, 3, 106), 110)

    def test_plan_occurrences(self):
        # S = 100, C = 3, current = 106, horizon = 12
        # Start_stop = 107, End_stop = 118
        # occurrences in range: 109, 112, 115, 118
        occs = calculations.get_plan_occurrences(100, 3, 106, 12)
        self.assertEqual(occs, [109, 112, 115, 118])

class TestValidators(unittest.TestCase):
    def test_zero_headcount_is_valid(self):
        issues = validators.validate_item_row(
            2, 'EQ-01', '042', 'MEC01', 'Q', 3, 'PLAN-A',
            'ITEM-0', 1, 'Item sem efetivo', 2.0, 0,
        )
        self.assertFalse(any(row.get('field') == 'Efetivo' for row in issues))

    def test_item_identifier_is_an_opaque_text_key(self):
        issues = validators.validate_item_row(
            2, 'EQ-01', '042', 'MEC01', 'Q', 3, 'PLAN-A',
            '1F57-A/SETOR#2', 1, 'Item textual', 2.0, 1,
        )
        identifier_issues = [row for row in issues if row.get('field') == 'Identificador']
        self.assertEqual(identifier_issues, [])

    def test_operation_structure_and_long_text_rules(self):
        required = {'0010', '0011', '0012', '0013', '0014'}
        header_ok = validators.validate_operation_structure('0010', '', 'TÍTULO', 0, required)
        self.assertEqual(header_ok, [])

        header_with_text = validators.validate_operation_structure('0010', '', 'TÍTULO', 1, required)
        self.assertIn('header_has_long_text', [x['code'] for x in header_with_text])

        missing_text = validators.validate_operation_structure('0020', '', 'ATIVIDADE', 0)
        self.assertIn('missing_long_text', [x['code'] for x in missing_text])

        wrong_sequence = validators.validate_operation_structure('0021', '', 'ATIVIDADE', 1)
        self.assertIn('invalid_operation_sequence', [x['code'] for x in wrong_sequence])

        wrong_standard_title = validators.validate_operation_structure('0010', '0010', 'MECÂNICOS', 1)
        self.assertIn('invalid_standard_title', [x['code'] for x in wrong_standard_title])

    def test_description_length_warning(self):
        # Less than or equal to 35: no warning
        issues_short = validators.validate_plan_row(1, "CODE1", "REP PREVENTIV MANUT", 3, "PRD", "3 P", 35.0, 106)
        warnings_short = [x for x in issues_short if x['severity'] == 'WARNING']
        self.assertEqual(len(warnings_short), 0)
        
        # Greater than 35: warning
        issues_long = validators.validate_plan_row(1, "CODE1", "REP PREVENTIV MANUT SIST-P 1P1 ELETROMAISLONGOQUE35CARAC", 3, "PRD", "3 P", 35.0, 106)
        warnings_long = [x for x in issues_long if x['severity'] == 'WARNING' and 'limite é 35' in x['message']]
        self.assertEqual(len(warnings_long), 1)

    def test_copy_paste_code_description_mismatch(self):
        # If code contains 'STP' (SIST-P) but description contains 'SIST-E' (SIST-E)
        code = "URRST3STP010"
        desc_mismatch = "REP PREVENTIVA MANUT SIST-E 1P1"
        desc_match = "REP PREVENTIVA MANUT SIST-P 1P1"
        
        cp_err_mismatch = validators.check_copy_paste_error(code, desc_mismatch)
        self.assertIsNotNone(cp_err_mismatch)
        self.assertIn("Divergência", cp_err_mismatch)
        
        cp_err_match = validators.check_copy_paste_error(code, desc_match)
        self.assertIsNone(cp_err_match)

class TestExcelExports(unittest.TestCase):
    def test_orders_xlsx_is_valid_styled_workbook(self):
        orders = [{
            'stop_num': 2, 'legacy_identifier': '001', 'object_code': 'EQ-01',
            'object_type': 'EQUIPAMENTO', 'description': 'Manutenção preventiva',
            'plan_code': 'PLAN-2P', 'plan_description': 'Plano preventivo',
            'cycle': 2, 'unit': 'PRD', 'gpm': '041', 'work_center': 'CT-01',
            'condition_code': 'A', 'priority': 1, 'duration_hours': 4.0,
            'headcount': 2
        }]
        content = export_service.export_orders_xlsx(
            orders, 108, {'name': 'Projeto Verde'}, {'stop_num': 2})
        self.assertTrue(content.startswith(b'PK'))
        with zipfile.ZipFile(io.BytesIO(content)) as workbook:
            names = workbook.namelist()
            self.assertIn('xl/worksheets/sheet1.xml', names)
            self.assertIn('xl/styles.xml', names)
            sheet = workbook.read('xl/worksheets/sheet1.xml').decode('utf-8')
            styles = workbook.read('xl/styles.xml').decode('utf-8')
            self.assertIn('LISTA DE ORDENS DE MANUTENÇÃO PROGRAMADA', sheet)
            self.assertIn('autoFilter', sheet)
            self.assertIn('FF365E00', styles)

class TestModelsAndBackups(unittest.TestCase):
    def setUp(self):
        self.db_path = os.path.abspath("test_pm13_models.db")
        if os.path.exists(self.db_path):
            try:
                os.remove(self.db_path)
            except Exception:
                pass
        database.DB_PATH = self.db_path
        backup_service.DB_PATH = self.db_path
        
        conn = database.get_db_connection()
        migrations.run_migrations(conn)
        conn.close()
        
        # Setup backups directory mock
        self.backup_dir = os.path.abspath("test_backups")
        if not os.path.exists(self.backup_dir):
            os.makedirs(self.backup_dir)
        backup_service.BACKUP_DIR = self.backup_dir

    def tearDown(self):
        if os.path.exists(self.db_path):
            try:
                os.remove(self.db_path)
            except Exception:
                pass
        if os.path.exists(self.backup_dir):
            shutil.rmtree(self.backup_dir)

    def test_crud_project_and_plans(self):
        # Create Project
        proj_id = models.create_project("Projeto Alfa", "Área MS3", "Teste de CRUD", 106, 12, 1.0)
        self.assertGreater(proj_id, 0)
        
        # Read Project
        proj = models.get_project(proj_id)
        self.assertEqual(proj['name'], "Projeto Alfa")
        
        # Create Plan
        plan_id = models.create_plan(
            project_id=proj_id,
            legacy_code="URRST3STP001",
            description="REP PREV MANUT SIST-P",
            cycle=3,
            unit="PRD",
            cycle_text="3 PARADAS",
            opening_horizon=35.0,
            reference_counter=106
        )
        self.assertGreater(plan_id, 0)
        
        # Verify plan list
        plans = models.list_plans(proj_id)
        self.assertEqual(len(plans), 1)
        self.assertEqual(plans[0]['legacy_code'], "URRST3STP001")

    def test_plan_search_is_contains_case_and_accent_insensitive(self):
        project_id = models.create_project(
            "Projeto Filtros", "Área MS2", "Teste dos filtros de planos", 106, 12, 1.0)
        models.create_plan(
            project_id, "URRSTISTC001", "MANUTENÇÃO PREVENTIVA ELÉTRICA",
            1, "PRD", "1P", 35.0, 106)
        models.create_plan(
            project_id, "URRSTISTC002", "INSPEÇÃO MECÂNICA",
            2, "PRD", "2P", 35.0, 106)
        models.create_plan(
            project_id, "OUTROPLANO003", "LUBRIFICAÇÃO GERAL",
            3, "PRD", "3P", 35.0, 106)

        by_code = models.list_plans(project_id, {'search': 'tistc00'}, limit=100)
        self.assertEqual(
            [plan['legacy_code'] for plan in by_code],
            ['URRSTISTC001', 'URRSTISTC002'])

        by_description = models.list_plans(
            project_id, {'search': 'manutencao preventiva eletrica'}, limit=100)
        self.assertEqual(
            [plan['legacy_code'] for plan in by_description],
            ['URRSTISTC001'])
        self.assertEqual(
            models.count_plans(project_id, {'search': 'INSPECAO mecanica'}), 1)

    def test_item_list_exposes_plan_cycle_and_start_code(self):
        project_id = models.create_project(
            "Projeto Ciclo Item", "Área MS2", "Ciclo e início na tabela", 106, 12, 1.0)
        plan_id = models.create_plan(
            project_id, "URRST2STC008", "REP PREVENTIVA SIST-C 6P2",
            6, "PRD", "6P2", 36.0, 2, start_stop=2)
        models.create_item(
            project_id, "ITEM-CICLO", plan_id, "EQUIPAMENTO", "EQ-01",
            "G1", "CT1", "A", 1, None, "Item com ciclo", 2.0, 1)

        items = models.list_items(project_id, limit=100)
        self.assertEqual(items[0]['plan_cycle'], 6)
        self.assertEqual(items[0]['plan_phase'], 2)
        self.assertEqual(items[0]['plan_cycle_phase'], '6P2')

    def test_duplicate_project(self):
        # Create source project
        src_id = models.create_project("Projeto Original", "Área 1", "Original", 106, 12, 1.0)
        plan_id = models.create_plan(src_id, "CODE1", "Plan 1", 3, "PRD", "3 P", 35.0, 106)
        team = models.create_team(src_id, {
            'name': 'Equipe completa', 'work_center': 'ELE01', 'num_shifts': 1,
            'shift_hours': 9, 'headcount_per_shift': 20, 'tool_time_percent': 100,
            'stop_days': 2
        })
        item_id = models.create_item(
            src_id, 'ITEM1', plan_id, 'EQUIPAMENTO', 'MOTOR1', 'ELE', 'ELE01',
            'P', 1, None, 'Item completo', 4, 3, team_id=team['id'],
            ele_headcount=3, ele_hours=4
        )
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute("""INSERT INTO item_operations
            (project_id,item_id,operation_code,suboperation_code,work_center,short_text,unit,headcount,hours)
            VALUES (?,?,?,?,?,?,?,?,?)""", (src_id,item_id,'0020','','ELE01','Executar teste','H',3,4))
        operation_id = cur.lastrowid
        cur.execute("""INSERT INTO operation_long_texts
            (project_id,operation_id,line_sequence,text) VALUES (?,?,?,?)""",
            (src_id,operation_id,1,'Procedimento completo'))
        conn.commit()
        deleted_item_id = models.create_item(
            src_id, 'ITEM-APAGADO', plan_id, 'EQUIPAMENTO', 'OLD', 'ELE', 'ELE01',
            'P', 1, None, 'Item apagado', 1, 1)
        cur.execute("""INSERT INTO item_operations
            (project_id,item_id,operation_code,work_center,short_text,unit,headcount,hours)
            VALUES (?,?,?,?,?,?,?,?)""",
            (src_id,deleted_item_id,'0099','ELE01','Operacao orfa','H',1,1))
        cur.execute("UPDATE maintenance_items SET deleted_at=CURRENT_TIMESTAMP WHERE id=?", (deleted_item_id,))
        cur.execute("UPDATE projects SET ele_capacity=20,mec_capacity=10,sol_capacity=5 WHERE id=?", (src_id,))
        conn.commit(); conn.close()
        
        # Duplicate
        dup_id = models.duplicate_project(src_id, "Projeto Duplicado")
        self.assertGreater(dup_id, 0)
        
        # Verify duplicate contains same plans
        dup_plans = models.list_plans(dup_id)
        self.assertEqual(len(dup_plans), 1)
        self.assertEqual(dup_plans[0]['legacy_code'], "CODE1")
        dup_items = models.list_items(dup_id, limit=100)
        self.assertEqual(len(dup_items), 1)
        self.assertEqual(dup_items[0]['ele_headcount'], 3)
        self.assertEqual(dup_items[0]['ele_hours'], 4)
        self.assertEqual(dup_items[0]['hh'], 12)
        self.assertEqual(dup_items[0]['team_name'], 'Equipe completa')
        conn = database.get_db_connection()
        self.assertEqual(conn.execute('SELECT COUNT(*) FROM item_operations WHERE project_id=?',(dup_id,)).fetchone()[0], 1)
        self.assertEqual(conn.execute('SELECT COUNT(*) FROM operation_long_texts WHERE project_id=?',(dup_id,)).fetchone()[0], 1)
        copied_text = conn.execute('SELECT text FROM operation_long_texts WHERE project_id=?',(dup_id,)).fetchone()[0]
        copied_project = conn.execute('SELECT ele_capacity,mec_capacity,sol_capacity FROM projects WHERE id=?',(dup_id,)).fetchone()
        conn.close()
        self.assertEqual(copied_text, 'Procedimento completo')
        self.assertEqual(tuple(copied_project), (20, 10, 5))

        # Reusing a name must never expose a database UNIQUE error. This also
        # covers names held by soft-deleted projects because the DB constraint
        # remains global.
        second_dup_id = models.duplicate_project(src_id, "Projeto Duplicado")
        conn = database.get_db_connection()
        second_name = conn.execute('SELECT name FROM projects WHERE id=?', (second_dup_id,)).fetchone()[0]
        conn.close()
        self.assertEqual(second_name, "Projeto Duplicado (Cópia)")

    def test_delete_item_can_preserve_or_cascade_operations_and_texts(self):
        project_id = models.create_project("Projeto Exclusao", "Teste", "MS3", 0, 12, 1.0)
        plan_id = models.create_plan(project_id, "PLANO-DEL", "Plano", 1, "PRD", "1P", 1, 1)

        def chain(identifier):
            item_id = models.create_item(project_id, identifier, plan_id, "EQUIPAMENTO", identifier,
                                         "ELE", "CT", "P", 1, None, identifier, 1, 1)
            conn = database.get_db_connection()
            cur = conn.cursor()
            cur.execute("""INSERT INTO item_operations
                (project_id,item_id,operation_code,work_center,short_text,unit,headcount,hours)
                VALUES (?,?,?,?,?,?,?,?)""", (project_id,item_id,'0010','CT','Operacao','H',1,1))
            op_id = cur.lastrowid
            cur.execute("""INSERT INTO operation_long_texts
                (project_id,operation_id,line_sequence,text) VALUES (?,?,?,?)""",
                (project_id,op_id,1,'Texto'))
            text_id = cur.lastrowid
            conn.commit(); conn.close()
            return item_id, op_id, text_id

        item_id, op_id, text_id = chain('MANTER-ORFAOS')
        models.delete_item(item_id, cascade_related=False)
        conn = database.get_db_connection()
        self.assertEqual(conn.execute('SELECT validation_status FROM item_operations WHERE id=?', (op_id,)).fetchone()[0], 'ERROR')
        self.assertEqual(conn.execute('SELECT validation_status FROM operation_long_texts WHERE id=?', (text_id,)).fetchone()[0], 'ERROR')
        conn.close()

        item_id, op_id, text_id = chain('APAGAR-PACOTE')
        models.delete_item(item_id, cascade_related=True)
        conn = database.get_db_connection()
        self.assertIsNone(conn.execute('SELECT id FROM item_operations WHERE id=?', (op_id,)).fetchone())
        self.assertIsNone(conn.execute('SELECT id FROM operation_long_texts WHERE id=?', (text_id,)).fetchone())
        conn.close()

    def test_automatic_balance_rules_and_cycles(self):
        project_id = models.create_project(
            "Projeto Auto Balance", "Cenário de teste", "Área 1",
            current_counter=100, default_horizon=6, utilization_factor=1.0)

        def add_plan_with_item(code, desc, cycle, reference, hh):
            plan_id = models.create_plan(
                project_id, code, desc, cycle, "PRD", f"{cycle}P", 36.0, reference)
            item_id = models.create_item(
                project_id, f"ITEM_{code}", plan_id, "EQUIPAMENTO", code,
                "G1", "CT1", "A", 1, None, code, hh, 1)
            return plan_id, item_id

        fixed_plan, _ = add_plan_with_item("FIXO1P00001", "REP PREVENTIVA 1P", 1, 101, 100)
        sib_a1, item_a1 = add_plan_with_item("SIBLING01_1", "REP PREVENTIVA 2P1", 2, 101, 60)
        sib_a2, item_a2 = add_plan_with_item("SIBLING01_2", "REP PREVENTIVA 2P2", 2, 102, 10)
        sib_b1, item_b1 = add_plan_with_item("SIBLING02_1", "REP PREVENTIVA 2P1", 2, 101, 40)
        sib_b2, item_b2 = add_plan_with_item("SIBLING02_2", "REP PREVENTIVA 2P2", 2, 102, 10)

        rules = [
            {'name': 'Executar juntos', 'type': 'together', 'item_ids': [item_a1, item_b1]}
        ]
        result = auto_balance_service.optimize(project_id, rules, 6, max_passes=20)

        self.assertEqual(len(result['stops_after']), 6)
        self.assertGreaterEqual(result['plans_analyzed'], 5)
        self.assertIn('before', result)
        self.assertIn('after', result)

    def test_backup_and_restore(self):
        # Insert test data
        proj_id = models.create_project("Projeto Backup", "Área 1", "Backup", 106, 12, 1.0)
        models.create_plan(proj_id, "CODE_BACKUP", "Plan Backup", 3, "PRD", "3 P", 35.0, 106)
        
        # Execute Backup
        backup_res = backup_service.create_backup("test")
        backup_file = backup_res['path']
        self.assertTrue(os.path.exists(backup_file))
        
        # Delete original project to test restore
        models.delete_project(proj_id)
        self.assertIsNone(models.get_project(proj_id))
        
        # Restore Backup
        backup_service.restore_backup(backup_res['filename'])
        
        # Verify data restored
        proj = models.list_projects()
        self.assertEqual(len(proj), 1)
        self.assertEqual(proj[0]['name'], "Projeto Backup")

    def test_restore_legacy_backup_reapplies_current_schema(self):
        project_id = models.create_project(
            "Projeto Backup Legado", "Área 1", "Migração após restauração", 106, 12, 1.0)
        conn = database.get_db_connection()
        try:
            conn.execute('DROP TABLE manual_balance_assignments')
            conn.execute('DROP TABLE manual_balance_sessions')
            conn.execute('DROP TABLE auto_balance_rules')
            conn.execute("""CREATE TABLE auto_balance_rules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                name TEXT NOT NULL,
                rule_type TEXT NOT NULL CHECK(rule_type IN ('together','sequence')),
                item_ids_json TEXT NOT NULL,
                active INTEGER NOT NULL DEFAULT 1,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )""")
            conn.commit()
        finally:
            conn.close()

        legacy = backup_service.create_backup('legacy_schema')
        backup_service.restore_backup(legacy['filename'])

        conn = database.get_db_connection()
        try:
            tables = {row[0] for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
            rule_columns = {row[1] for row in conn.execute(
                'PRAGMA table_info(auto_balance_rules)').fetchall()}
        finally:
            conn.close()
        self.assertIn('manual_balance_sessions', tables)
        self.assertIn('manual_balance_assignments', tables)
        self.assertIn('enforcement', rule_columns)
        self.assertIn('config_json', rule_columns)
        self.assertIsNotNone(models.get_project(project_id))

class TestHttpApiIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Setup temporary DB for server
        cls.db_path = os.path.abspath("test_pm13_server.db")
        if os.path.exists(cls.db_path):
            try:
                os.remove(cls.db_path)
            except Exception:
                pass
        database.DB_PATH = cls.db_path
        backup_service.DB_PATH = cls.db_path
        
        conn = database.get_db_connection()
        migrations.run_migrations(conn)
        conn.close()
        
        # Populate one dummy project
        cls.proj_id = models.create_project("Servidor Integrado", "Siderurgia", "Integração", 106, 12, 1.0)
        
        # Find free port dynamically
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.bind(('127.0.0.1', 0))
        cls.port = s.getsockname()[1]
        s.close()
        
        # Spin up HTTP server on cls.port
        cls.server = http.server.ThreadingHTTPServer(('127.0.0.1', cls.port), app.PM13RequestHandler)
        cls.server_thread = threading.Thread(target=cls.server.serve_forever)
        cls.server_thread.daemon = True
        cls.server_thread.start()
        
        # Wait for server to bind
        time.sleep(0.3)

    @classmethod
    def tearDownClass(cls):
        # Shutdown server socket safely
        cls.server.shutdown()
        cls.server.server_close()
        cls.server_thread.join(timeout=1.0)
        
        # Clean file
        if os.path.exists(cls.db_path):
            try:
                os.remove(cls.db_path)
            except Exception:
                pass

    def test_get_projects_api(self):
        url = f"http://127.0.0.1:{self.port}/api/projects"
        response = urllib.request.urlopen(url)
        self.assertEqual(response.status, 200)
        
        data = json.loads(response.read().decode('utf-8'))
        self.assertGreater(len(data), 0)
        self.assertEqual(data[0]['name'], "Servidor Integrado")

    def test_project_lock_blocks_mutations_and_import_but_allows_reads(self):
        base = f"http://127.0.0.1:{self.port}"
        def post(path, payload, headers=None):
            body = json.dumps(payload).encode('utf-8')
            req_headers = {'Content-Type': 'application/json', **(headers or {})}
            return urllib.request.urlopen(urllib.request.Request(base + path, data=body, headers=req_headers, method='POST'))

        post(f"/api/projects/{self.proj_id}/lock", {'locked': True})
        try:
            project = json.loads(urllib.request.urlopen(base + f"/api/projects/{self.proj_id}").read())
            self.assertEqual(project['is_locked'], 1)

            with self.assertRaises(urllib.error.HTTPError) as blocked:
                post('/api/plans', {
                    'project_id': self.proj_id, 'legacy_code': 'LOCKED_PLAN',
                    'description': 'Must not be created', 'cycle': 1, 'unit': 'PRD'
                })
            self.assertEqual(blocked.exception.code, 423)

            req = urllib.request.Request(
                base + '/api/import/preview', data=b'', method='POST',
                headers={'X-PM13-Project-ID': str(self.proj_id)}
            )
            with self.assertRaises(urllib.error.HTTPError) as import_blocked:
                urllib.request.urlopen(req)
            self.assertEqual(import_blocked.exception.code, 423)

            balance = urllib.request.urlopen(base + f"/api/balance?project_id={self.proj_id}")
            self.assertEqual(balance.status, 200)
        finally:
            post(f"/api/projects/{self.proj_id}/lock", {'locked': False})

        created = post('/api/plans', {
            'project_id': self.proj_id, 'legacy_code': 'UNLOCKED_PLAN',
            'description': 'Allowed after unlock', 'cycle': 1, 'unit': 'PRD',
            'cycle_text': '1P', 'opening_horizon': 12
        })
        self.assertIn(created.status, (200, 201))

    def test_get_sap_maintenance_order_preview(self):
        conn = database.get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""INSERT INTO maintenance_items
            (project_id,legacy_identifier,object_type,object_code,gpm,work_center,condition_code,
             priority,description,character_count,duration_hours,headcount,hh,status)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,'ACTIVE')""",
            (self.proj_id,'SAP-1','EQUIPAMENTO','EQ-SAP','042','R55E-042','P',1,
             'ORDEM PARA PRÉ-VISUALIZAÇÃO',28,2.0,2,4.0))
        item_id = cursor.lastrowid
        cursor.execute("""INSERT INTO item_operations
            (project_id,item_id,operation_code,suboperation_code,work_center,short_text,unit,headcount,hours)
            VALUES(?,?,?,?,?,?,?,?,?)""",
            (self.proj_id,item_id,'0020','','R55E-042','INSPECIONAR EQUIPAMENTO','H',2,2.0))
        operation_id = cursor.lastrowid
        cursor.execute("""INSERT INTO operation_long_texts
            (project_id,operation_id,line_sequence,text) VALUES(?,?,1,?)""",
            (self.proj_id,operation_id,'EXECUTAR INSPEÇÃO CONFORME PROCEDIMENTO.'))
        conn.commit(); conn.close()

        response = urllib.request.urlopen(
            f"http://127.0.0.1:{self.port}/api/items/{item_id}/sap-order")
        data = json.loads(response.read().decode('utf-8'))
        self.assertEqual(data['item']['description'], 'ORDEM PARA PRÉ-VISUALIZAÇÃO')
        self.assertEqual(data['operations'][0]['operation_code'], '0020')
        self.assertEqual(data['operations'][0]['long_texts'][0]['operation_id'], operation_id)

        long_text_id = data['operations'][0]['long_texts'][0]['id']
        updated_text = 'TEXTO LONGO ATUALIZADO\nCOM VÁRIAS LINHAS PARA A PRÉ-VISUALIZAÇÃO.'
        payload = json.dumps({'text': updated_text, 'group_code': '1707', 'group_counter': 'N4'}).encode('utf-8')
        request = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/api/long-texts/{long_text_id}",
            data=payload, headers={'Content-Type': 'application/json'}, method='PUT')
        update_response = urllib.request.urlopen(request)
        self.assertEqual(update_response.status, 200)

        response = urllib.request.urlopen(
            f"http://127.0.0.1:{self.port}/api/items/{item_id}/sap-order")
        updated = json.loads(response.read().decode('utf-8'))
        self.assertEqual(updated['operations'][0]['long_texts'][0]['text'], updated_text)

    def test_post_project_validation_failure(self):
        url = f"http://127.0.0.1:{self.port}/api/projects"
        # Missing required parameter: name
        invalid_data = json.dumps({
            "description": "Fails because name is missing",
            "current_counter": 106
        }).encode('utf-8')
        
        req = urllib.request.Request(
            url,
            data=invalid_data,
            headers={'Content-Type': 'application/json'},
            method='POST'
        )
        
        with self.assertRaises(urllib.error.HTTPError) as cm:
            urllib.request.urlopen(req)
        
        self.assertEqual(cm.exception.code, 400)
        err_msg = json.loads(cm.exception.read().decode('utf-8'))
        self.assertIn("error", err_msg)

    def test_auto_balance_preview_api(self):
        plan_id = models.create_plan(
            self.proj_id, "AUTO_API_2P", "Plano automático API", 2,
            "PRD", "2P", 36.0, 13)
        models.create_item(
            self.proj_id, "AUTO_API_ITEM", plan_id, "EQUIPAMENTO",
            "EQ_AUTO", "G1", "CT1", "A", 1, None,
            "Item automático API", 8.0, 2)

        url = f"http://127.0.0.1:{self.port}/api/auto-balance/preview"
        payload = json.dumps({
            'project_id': self.proj_id, 'horizon': 6, 'rules': []
        }).encode('utf-8')
        req = urllib.request.Request(
            url, data=payload, headers={'Content-Type': 'application/json'}, method='POST')
        response = urllib.request.urlopen(req)
        self.assertEqual(response.status, 200)
        data = json.loads(response.read().decode('utf-8'))
        self.assertEqual(data['horizon'], 6)
        self.assertIn('before', data)
        self.assertIn('after', data)
        self.assertGreaterEqual(data['plans_analyzed'], 1)

    def test_orders_xlsx_download_api(self):
        plan_id = models.create_plan(
            self.proj_id, "XLSX_API_1P", "Plano Excel API", 1,
            "PRD", "1P", 36.0, 13)
        models.create_item(
            self.proj_id, "XLSX_API_ITEM", plan_id, "EQUIPAMENTO",
            "EQ_XLSX", "G1", "CT1", "A", 1, None,
            "Item exportado para Excel", 3.0, 2)
        url = (f"http://127.0.0.1:{self.port}/api/export?type=orders&format=xlsx"
               f"&project_id={self.proj_id}&stop_counter=13")
        response = urllib.request.urlopen(url)
        self.assertEqual(response.status, 200)
        self.assertEqual(
            response.headers.get_content_type(),
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        self.assertTrue(response.read().startswith(b'PK'))

    def test_teams_crud_api(self):
        # 1. Create Team
        url = f"http://127.0.0.1:{self.port}/api/teams"
        team_data = json.dumps({
            "project_id": self.proj_id,
            "name": "Equipe Teste Integracao",
            "work_center": "MEC01",
            "num_shifts": 2,
            "shift_hours": 9.0,
            "headcount_per_shift": 5,
            "tool_time_percent": 90.0,
            "stop_days": 2,
            "notes": "Teste de integracao API"
        }).encode('utf-8')
        
        req = urllib.request.Request(url, data=team_data, headers={'Content-Type': 'application/json'}, method='POST')
        res = urllib.request.urlopen(req)
        self.assertEqual(res.status, 200)
        body = json.loads(res.read().decode('utf-8'))
        team_id = body['team']['id']

        # 2. List Teams
        res_list = urllib.request.urlopen(f"{url}?project_id={self.proj_id}")
        self.assertEqual(res_list.status, 200)
        teams = json.loads(res_list.read().decode('utf-8'))
        self.assertTrue(any(t['id'] == team_id for t in teams))

        # 3. Delete Team
        req_del = urllib.request.Request(f"{url}/{team_id}", method='DELETE')
        res_del = urllib.request.urlopen(req_del)
        self.assertEqual(res_del.status, 200)

    def test_rebalancing_endpoints(self):
        # 1. Test plans-for-stop
        url_plans = f"http://127.0.0.1:{self.port}/api/balance/plans-for-stop?project_id={self.proj_id}&stop_counter=106"
        res = urllib.request.urlopen(url_plans)
        self.assertEqual(res.status, 200)
        body = json.loads(res.read().decode('utf-8'))
        self.assertIn('plans', body)

        # 2. Test reassign-item
        # Create a new plan first
        url_plans_post = f"http://127.0.0.1:{self.port}/api/plans"
        plan_data = json.dumps({
            "project_id": self.proj_id,
            "legacy_code": "PLAN_REASSIGN_TEST",
            "description": "Test Reassign Plan",
            "cycle": 3,
            "unit": "PRD",
            "cycle_text": "3 P",
            "reference_counter": 106,
            "opening_horizon": 36.0
        }).encode('utf-8')
        req = urllib.request.Request(url_plans_post, data=plan_data, headers={'Content-Type': 'application/json'}, method='POST')
        res_plan = urllib.request.urlopen(req)
        new_plan_id = json.loads(res_plan.read().decode('utf-8'))['id']
        # Create an item
        url_items_post = f"http://127.0.0.1:{self.port}/api/items"
        item_data = json.dumps({
            "project_id": self.proj_id,
            "plan_id": None,
            "legacy_identifier": "ITEM_REASSIGN_TEST",
            "object_code": "OBJ1",
            "gpm": "GPM1",
            "work_center": "MEC01",
            "condition_code": "P",
            "priority": 1,
            "description": "Item Reassign Test",
            "duration_hours": 10.0,
            "headcount": 2
        }).encode('utf-8')
        req_item = urllib.request.Request(url_items_post, data=item_data, headers={'Content-Type': 'application/json'}, method='POST')
        res_item = urllib.request.urlopen(req_item)
        new_item_id = json.loads(res_item.read().decode('utf-8'))['id']
        # Reassign item to new plan
        url_reassign = f"http://127.0.0.1:{self.port}/api/balance/reassign-item"
        reassign_data = json.dumps({
            "item_id": new_item_id,
            "plan_id": new_plan_id
        }).encode('utf-8')
        req_reassign = urllib.request.Request(url_reassign, data=reassign_data, headers={'Content-Type': 'application/json'}, method='POST')
        res_reassign = urllib.request.urlopen(req_reassign)
        self.assertEqual(res_reassign.status, 200)

        # 3. Test create-independent-plan
        url_create_ind = f"http://127.0.0.1:{self.port}/api/balance/create-independent-plan"
        create_ind_data = json.dumps({
            "item_id": new_item_id,
            "target_stop": 108
        }).encode('utf-8')
        req_create_ind = urllib.request.Request(url_create_ind, data=create_ind_data, headers={'Content-Type': 'application/json'}, method='POST')
        res_create_ind = urllib.request.urlopen(req_create_ind)
        self.assertEqual(res_create_ind.status, 200)
        body_create_ind = json.loads(res_create_ind.read().decode('utf-8'))
        self.assertIn('new_plan_id', body_create_ind)

if __name__ == "__main__":
    unittest.main()
