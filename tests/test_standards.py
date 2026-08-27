import unittest
import os
import sys
import time
import sqlite3

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

import core.database as database
from core.migrations import run_migrations
import core.models as models

class TestStandardsAndCapacities(unittest.TestCase):
    def setUp(self):
        self.db_path = os.path.abspath("test_pm13_standards.db")
        if os.path.exists(self.db_path):
            try:
                os.remove(self.db_path)
            except Exception:
                pass
        database.DB_PATH = self.db_path
        conn = database.get_db_connection()
        run_migrations(conn)
        conn.close()

    def tearDown(self):
        if os.path.exists(self.db_path):
            try:
                os.remove(self.db_path)
            except Exception:
                pass

    def test_project_capacities_persistence(self):
        proj_name = f"Test Capacity Project {time.time()}"
        proj_id = models.create_project(proj_name, "Desc", "Area", "SYS", 106, 12, 1.0)
        
        # Initially capacities are None
        caps = models.get_project_capacities(proj_id)
        self.assertIsNone(caps['ele'])
        self.assertIsNone(caps['mec'])
        self.assertIsNone(caps['sol'])

        # Update capacities
        updated = models.update_project_capacities(proj_id, 3.5, 5.0, 2.0)
        self.assertEqual(updated['ele'], 3.5)
        self.assertEqual(updated['mec'], 5.0)
        self.assertEqual(updated['sol'], 2.0)

        # Retrieve again to verify DB persistence
        fetched = models.get_project_capacities(proj_id)
        self.assertEqual(fetched['ele'], 3.5)
        self.assertEqual(fetched['mec'], 5.0)
        self.assertEqual(fetched['sol'], 2.0)

    def test_standard_long_texts_crud(self):
        # Create
        std_lt = models.create_standard_long_text("Procedimento Motor", "Motores", "1. Passo um.\n2. Passo dois.")
        self.assertIsNotNone(std_lt['id'])
        self.assertEqual(std_lt['title'], "Procedimento Motor")

        # List
        all_lts = models.get_standard_long_texts()
        self.assertTrue(any(t['id'] == std_lt['id'] for t in all_lts))

        # Update
        updated = models.update_standard_long_text(std_lt['id'], "Procedimento Motor V2", "Motores", "1. Novo passo.")
        self.assertEqual(updated['title'], "Procedimento Motor V2")

        # Delete
        deleted = models.delete_standard_long_text(std_lt['id'])
        self.assertTrue(deleted)

    def test_standard_item_instantiation(self):
        proj_name = f"Test Instantiation Project {time.time()}"
        proj_id = models.create_project(proj_name, "Desc", "Area", "SYS", 106, 12, 1.0)
        plan_id = models.create_plan(proj_id, f"PL-{time.time()}", "Plano Teste", 12, "MES", "12 MESES", 12.0, 106)

        # Create a standard item model
        std_data = {
            'title': 'Bomba Centrifuga Padrão',
            'category': 'Bombas',
            'description': 'MANUTENÇÃO EM BOMBA CENTRIFUGA',
            'work_center': 'MEC01',
            'gpm': 'MEC',
            'priority': 2,
            'duration_hours': 6.0,
            'headcount': 2,
            'operations': [
                {
                    'operation_code': '0010',
                    'short_text': 'ISOLAMENTO E DESMONTAGEM DA BOMBA',
                    'work_center': 'MEC01',
                    'hours': 2.0,
                    'headcount': 2,
                    'long_texts': [{'text': 'Desconectar tubulação e remover parafusos.'}]
                },
                {
                    'operation_code': '0020',
                    'short_text': 'TROCA DE ROTOR E RETENTORES',
                    'work_center': 'MEC01',
                    'hours': 4.0,
                    'headcount': 2,
                    'long_texts': [{'text': 'Substituir retentores e alinhar conjunto.'}]
                }
            ]
        }

        std_item = models.create_standard_item(std_data)
        self.assertIsNotNone(std_item['id'])
        self.assertEqual(len(std_item['operations']), 2)

        # Instantiate into project
        new_item_id = models.instantiate_standard_item(proj_id, std_item['id'], {'plan_id': plan_id})
        self.assertIsNotNone(new_item_id)

        # Verify created item in DB
        created_item = models.get_item(new_item_id)
        self.assertEqual(created_item['description'], 'MANUTENÇÃO EM BOMBA CENTRIFUGA')
        self.assertEqual(created_item['plan_id'], plan_id)

        # Verify copied operations and long texts via DB query
        conn = database.get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM item_operations WHERE item_id = ? ORDER BY operation_code;", (new_item_id,))
        ops = [dict(r) for r in cursor.fetchall()]
        self.assertEqual(len(ops), 2)
        op_codes = [op['operation_code'] for op in ops]
        self.assertIn('0010', op_codes)
        self.assertIn('0020', op_codes)

        # Check long text of operation 0010
        op10 = next(op for op in ops if op['operation_code'] == '0010')
        cursor.execute("SELECT * FROM operation_long_texts WHERE operation_id = ?;", (op10['id'],))
        lts = [dict(r) for r in cursor.fetchall()]
        conn.close()
        self.assertEqual(len(lts), 1)
        self.assertIn('Desconectar tubulação', lts[0]['text'])


    def test_save_standard_preserves_nullable_operation_workload(self):
        project_id = models.create_project(
            f"Nullable Standard Project {time.time()}", "Desc", "Area", "SYS", 106, 12, 1.0
        )
        plan_id = models.create_plan(
            project_id, f"NULL-PLAN-{time.time()}", "Plano Teste", 12, "MES", "12 MESES", 12.0, 106
        )
        item_id = models.create_item(
            project_id, "1", plan_id, "EQUIPAMENTO", "EQ-NULL", "ELE", "R55E-041",
            "P", 0, 1, "ITEM COM CABECALHO SAP", 4.0, 1
        )
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute("""INSERT INTO item_operations
            (project_id,item_id,operation_code,suboperation_code,work_center,short_text,unit,headcount,hours,status)
            VALUES (?,?,?,?,?,?,?,?,?,'ACTIVE')""",
            (project_id,item_id,'0010','0011', 'R55E-041','CABECALHO DA ORDEM','H',None,None))
        operation_id = cur.lastrowid
        cur.execute("""INSERT INTO operation_long_texts
            (project_id,operation_id,group_code,group_counter,line_sequence,text)
            VALUES (?,?,?,?,?,?)""",
            (project_id, operation_id, 'TXT', '1', 1, 'TEXTO LONGO PRESERVADO'))
        conn.commit()
        conn.close()

        standard = models.save_item_as_standard(item_id, 'Modelo com campos vazios', 'Teste')
        self.assertEqual(len(standard['operations']), 1)
        self.assertIsNone(standard['operations'][0]['headcount'])
        self.assertIsNone(standard['operations'][0]['hours'])
        self.assertEqual(standard['operations'][0]['suboperation_code'], '0011')
        self.assertEqual(standard['operations'][0]['long_texts'][0]['text'], 'TEXTO LONGO PRESERVADO')

        cloned_from_standard_id = models.instantiate_standard_item(project_id, standard['id'], {'plan_id': plan_id})
        conn = database.get_db_connection()
        cloned_op = conn.execute(
            'SELECT * FROM item_operations WHERE item_id=? LIMIT 1', (cloned_from_standard_id,)
        ).fetchone()
        cloned_text = conn.execute(
            'SELECT * FROM operation_long_texts WHERE operation_id=? LIMIT 1', (cloned_op['id'],)
        ).fetchone()
        conn.close()
        self.assertIsNone(cloned_op['headcount'])
        self.assertIsNone(cloned_op['hours'])
        self.assertEqual(cloned_op['suboperation_code'], '0011')
        self.assertEqual(cloned_text['text'], 'TEXTO LONGO PRESERVADO')

    def test_complete_item_model_and_automatic_identifier(self):
        project_id = models.create_project(
            f"Complete Model Project {time.time()}", "Desc", "Area", "SYS", 106, 12, 1.0
        )
        plan_id = models.create_plan(
            project_id, f"PLAN-{time.time()}", "Test Plan", 12, "MES", "12 MESES", 12.0, 106
        )
        standard = models.create_standard_item({
            'title': 'Complete motor model',
            'category': 'Motors',
            'object_type': 'EQUIPAMENTO',
            'object_code': 'MOTOR-001',
            'description': 'COMPLETE MOTOR MAINTENANCE',
            'work_center': 'R55E-041',
            'gpm': 'ELE',
            'condition_code': 'P',
            'priority': 2,
            'ele_headcount': 2,
            'ele_hours': 4.0,
            'notes': 'Model notes',
            'operations': [{
                'operation_code': '0010',
                'short_text': 'Inspect motor',
                'work_center': 'R55E-041',
                'hours': 4.0,
                'headcount': 2,
                'long_texts': [{'text': 'Inspect bearings and insulation.'}]
            }]
        })

        first_id = models.instantiate_standard_item(project_id, standard['id'], {'plan_id': plan_id})
        first = models.get_item(first_id)
        self.assertEqual(str(first['legacy_identifier']), '1')
        self.assertEqual(first['object_code'], 'MOTOR-001')
        self.assertEqual(first['ele_headcount'], 2)
        self.assertEqual(first['ele_hours'], 4.0)
        self.assertEqual(first['hh'], 8.0)

        generated = models.save_item_as_standard(first_id, 'Generated complete model', 'Motors')
        self.assertEqual(generated['ele_headcount'], 2)
        self.assertEqual(len(generated['operations']), 1)
        self.assertEqual(len(generated['operations'][0]['long_texts']), 1)

        second_id = models.instantiate_standard_item(project_id, generated['id'], {'plan_id': plan_id})
        second = models.get_item(second_id)
        self.assertEqual(str(second['legacy_identifier']), '2')
        self.assertEqual(second['hh'], 8.0)

        with self.assertRaisesRegex(ValueError, 'CONFIRM_REPLACE'):
            models.apply_standard_item_to_existing(first_id, generated['id'])

        replacement = models.apply_standard_item_to_existing(
            first_id, generated['id'], {'description': 'EDITABLE REPLACEMENT'}, True
        )
        replaced = models.get_item(first_id)
        self.assertEqual(replaced['description'], 'EDITABLE REPLACEMENT')
        self.assertEqual(replacement['operations_created'], 1)
        self.assertEqual(replacement['long_texts_created'], 1)
        conn = database.get_db_connection()
        operation_count = conn.execute(
            'SELECT COUNT(*) FROM item_operations WHERE item_id=?', (first_id,)
        ).fetchone()[0]
        text_count = conn.execute(
            '''SELECT COUNT(*) FROM operation_long_texts t
               JOIN item_operations o ON o.id=t.operation_id WHERE o.item_id=?''', (first_id,)
        ).fetchone()[0]
        conn.close()
        self.assertEqual(operation_count, 1)
        self.assertEqual(text_count, 1)

        conn = database.get_db_connection()
        source_operation_id = conn.execute(
            'SELECT id FROM item_operations WHERE item_id=? LIMIT 1', (first_id,)
        ).fetchone()[0]
        source_text_id = conn.execute(
            'SELECT id FROM operation_long_texts WHERE operation_id=? LIMIT 1', (source_operation_id,)
        ).fetchone()[0]
        conn.close()
        pending_op = models.clone_operation_pending(source_operation_id)
        pending_text = models.clone_long_text_pending(source_text_id)
        conn = database.get_db_connection()
        op_copy = conn.execute('SELECT * FROM item_operations WHERE id=?', (pending_op['id'],)).fetchone()
        text_copy = conn.execute('SELECT * FROM operation_long_texts WHERE id=?', (pending_text['id'],)).fetchone()
        conn.close()
        self.assertEqual(op_copy['pending_item_identifier'], '[COPIA] 1111')
        self.assertEqual(op_copy['validation_status'], 'ERROR')
        self.assertEqual(text_copy['pending_item_identifier'], '[COPIA] 1111')
        self.assertEqual(text_copy['validation_status'], 'ERROR')

        clone = models.clone_item_shallow(first_id)
        self.assertEqual(str(clone['legacy_identifier']), '3')
        cloned_item = models.get_item(clone['id'])
        self.assertEqual(cloned_item['description'], '[copia] EDITABLE REPLACEMENT')
        conn = database.get_db_connection()
        clone_operation_count = conn.execute(
            'SELECT COUNT(*) FROM item_operations WHERE item_id=?', (clone['id'],)
        ).fetchone()[0]
        conn.close()
        self.assertEqual(clone_operation_count, 0)

        full_clone = models.clone_item(first_id, include_structure=True)
        self.assertEqual(str(full_clone['legacy_identifier']), '4')
        self.assertEqual(full_clone['operations_created'], 2)
        self.assertEqual(full_clone['long_texts_created'], 2)
        conn = database.get_db_connection()
        full_op = conn.execute(
            '''SELECT o.*, i.legacy_identifier FROM item_operations o
               JOIN maintenance_items i ON i.id=o.item_id WHERE o.item_id=? LIMIT 1''',
            (full_clone['id'],)
        ).fetchone()
        full_text = conn.execute(
            'SELECT * FROM operation_long_texts WHERE operation_id=? LIMIT 1', (full_op['id'],)
        ).fetchone()
        conn.close()
        self.assertEqual(str(full_op['legacy_identifier']), '4')
        self.assertEqual(full_text['text'], 'Inspect bearings and insulation.')

        models.set_item_row_color(clone['id'], 'purple')
        self.assertEqual(models.get_item(clone['id'])['row_color'], 'purple')
        purple_items = models.list_items(project_id, {'row_color': 'purple'}, limit=100)
        self.assertEqual([row['id'] for row in purple_items], [clone['id']])
        models.set_item_row_color(clone['id'], '')
        self.assertIsNone(models.get_item(clone['id'])['row_color'])
        displayed = models.list_items(project_id, limit=100)
        displayed_ids = [row['id'] for row in displayed]
        self.assertEqual(displayed_ids.index(full_clone['id']), displayed_ids.index(first_id) + 1)
        self.assertEqual(displayed_ids.index(clone['id']), displayed_ids.index(full_clone['id']) + 1)

        sorted_by_identifier = models.list_items(
            project_id, limit=100, order_by='legacy_identifier', order_dir='ASC'
        )
        self.assertEqual(
            [str(row['legacy_identifier']) for row in sorted_by_identifier], ['1', '2', '3', '4']
        )

    def test_bulk_apply_standard_structure_preserves_items_and_handles_conflicts(self):
        project_id = models.create_project(
            f"Bulk Standard Project {time.time()}", "Desc", "Area", "SYS", 106, 12, 1.0
        )
        plan_id = models.create_plan(
            project_id, f"BULK-PLAN-{time.time()}", "Plano Bulk", 12, "MES", "12 MESES", 12.0, 106
        )
        standard = models.create_standard_item({
            'title': 'Modelo elétrico para aplicação em massa',
            'category': 'Teste',
            'description': 'DESCRIÇÃO DO MODELO QUE NÃO DEVE SUBSTITUIR O ITEM',
            'work_center': 'R55E-041',
            'gpm': '041',
            'priority': 0,
            'operations': [
                {
                    'operation_code': '0010', 'short_text': 'BLOQUEAR EQUIPAMENTO',
                    'work_center': 'R55E-041', 'headcount': 2, 'hours': 0.5,
                    'long_texts': [{'group_code': 'TXT', 'group_counter': '1', 'text': 'Executar bloqueio LOTO.'}]
                },
                {
                    'operation_code': '0020', 'short_text': 'EXECUTAR MANUTENÇÃO',
                    'work_center': '', 'headcount': None, 'hours': None,
                    'long_texts': [{'group_code': 'TXT', 'group_counter': '2', 'text': 'Executar manutenção preventiva.'}]
                }
            ]
        })

        item_ids = []
        originals = {}
        for legacy, code, desc in [
            ('154', 'EQ-C201', 'C201 MANUT PREVENTIVA ELÉTRICA'),
            ('156', 'EQ-C202', 'C202 MANUT PREVENTIVA ELÉTRICA'),
            ('158', 'EQ-C203', 'C203 MANUT PREVENTIVA ELÉTRICA'),
        ]:
            item_id = models.create_item(
                project_id, legacy, plan_id, 'EQUIPAMENTO', code, '041', 'ITEM-WC',
                'P', 0, 1, desc, 2.0, 2
            )
            item_ids.append(item_id)
            originals[item_id] = models.get_item(item_id)

        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute("""INSERT INTO item_operations
            (project_id,item_id,operation_code,suboperation_code,work_center,short_text,unit,headcount,hours,status)
            VALUES (?,?,?,?,?,?,?,?,?,'ACTIVE')""",
            (project_id, item_ids[1], '0099', '', 'OLD-WC', 'OPERAÇÃO ANTIGA', 'H', 1, 1.0))
        old_op_id = cur.lastrowid
        cur.execute("""INSERT INTO operation_long_texts
            (project_id,operation_id,group_code,group_counter,line_sequence,text)
            VALUES (?,?,?,?,?,?)""",
            (project_id, old_op_id, 'OLD', '1', 1, 'TEXTO ANTIGO'))
        conn.commit()
        conn.close()

        preview = models.preview_bulk_standard_structure(project_id, item_ids, standard['id'])
        self.assertEqual(preview['summary']['selected_items'], 3)
        self.assertEqual(preview['summary']['conflicting_items'], 1)
        self.assertEqual(preview['summary']['operations_per_item'], 2)
        self.assertEqual(preview['summary']['long_texts_per_item'], 2)
        self.assertEqual(preview['conflicts'][0]['id'], item_ids[1])

        skipped = models.bulk_apply_standard_structure(
            project_id, item_ids, standard['id'], conflict_policy='skip'
        )
        self.assertEqual(skipped['applied_items'], 2)
        self.assertEqual(skipped['skipped_items'], 1)
        self.assertEqual(skipped['operations_created'], 4)
        self.assertEqual(skipped['long_texts_created'], 4)

        for item_id in item_ids:
            current = models.get_item(item_id)
            self.assertEqual(current['legacy_identifier'], originals[item_id]['legacy_identifier'])
            self.assertEqual(current['object_code'], originals[item_id]['object_code'])
            self.assertEqual(current['description'], originals[item_id]['description'])
            self.assertEqual(current['plan_id'], originals[item_id]['plan_id'])

        conn = database.get_db_connection()
        old_op = conn.execute('SELECT * FROM item_operations WHERE item_id=?', (item_ids[1],)).fetchall()
        self.assertEqual(len(old_op), 1)
        self.assertEqual(old_op[0]['operation_code'], '0099')
        clean_ops = conn.execute('SELECT * FROM item_operations WHERE item_id=? ORDER BY operation_code', (item_ids[0],)).fetchall()
        self.assertEqual([row['operation_code'] for row in clean_ops], ['0010', '0020'])
        self.assertEqual(clean_ops[1]['work_center'], 'ITEM-WC')
        conn.close()

        edited_ops = [{
            'operation_code': '0030',
            'suboperation_code': '',
            'work_center': 'R55E-041',
            'short_text': 'OPERAÇÃO AJUSTADA NA PRÉVIA',
            'unit': 'H',
            'headcount': 3,
            'hours': 1.25,
            'long_texts': [{
                'group_code': 'EDIT', 'group_counter': '7',
                'text': 'TEXTO AJUSTADO ANTES DA APLICAÇÃO EM MASSA'
            }]
        }]
        replaced = models.bulk_apply_standard_structure(
            project_id, item_ids, standard['id'], operations=edited_ops, conflict_policy='replace'
        )
        self.assertEqual(replaced['applied_items'], 3)
        self.assertEqual(replaced['replaced_items'], 3)
        self.assertEqual(replaced['operations_created'], 3)
        self.assertEqual(replaced['long_texts_created'], 3)

        conn = database.get_db_connection()
        for item_id in item_ids:
            op = conn.execute('SELECT * FROM item_operations WHERE item_id=?', (item_id,)).fetchone()
            self.assertEqual(op['operation_code'], '0030')
            self.assertEqual(op['short_text'], 'OPERAÇÃO AJUSTADA NA PRÉVIA')
            text = conn.execute('SELECT * FROM operation_long_texts WHERE operation_id=?', (op['id'],)).fetchone()
            self.assertEqual(text['text'], 'TEXTO AJUSTADO ANTES DA APLICAÇÃO EM MASSA')
            joined = conn.execute(
                'SELECT i.legacy_identifier FROM item_operations o JOIN maintenance_items i ON i.id=o.item_id WHERE o.id=?',
                (op['id'],)
            ).fetchone()
            self.assertEqual(str(joined['legacy_identifier']), str(originals[item_id]['legacy_identifier']))
        conn.close()


    def test_mass_application_restores_blank_lines_compacted_by_preview(self):
        standard_operations = [{
            'operation_code': '0020', 'suboperation_code': '',
            'long_texts': [{
                'text': 'LINE A\n\nLINE B\n\nLINE C',
                'structure_mode': 'MIXED',
                'structure_json': '[{"type":"free","level":0,"text":"LINE A"}]',
                'source_text_original': 'LINE A\n\nLINE B\n\nLINE C',
            }],
        }]
        preview_operations = [{
            'operation_code': '0020', 'suboperation_code': '',
            'long_texts': [{'text': 'LINE A\nLINE B\nLINE C'}],
        }]
        restored = models._restore_standard_blank_lines(preview_operations, standard_operations)
        self.assertEqual(restored[0]['long_texts'][0]['text'], 'LINE A\n\nLINE B\n\nLINE C')
        self.assertEqual(restored[0]['long_texts'][0]['structure_mode'], 'MIXED')


if __name__ == '__main__':
    unittest.main()
