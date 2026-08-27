import copy
import os
import tempfile
import unittest

from core import database, migrations, manual_balance_service
from core.import_service import confirm_import, normalize_identifier


class TestPartialImport(unittest.TestCase):
    """Contract tests for atomic, dependency-safe scoped imports."""

    DATA_TABLES = (
        'plans',
        'maintenance_items',
        'item_operations',
        'operation_long_texts',
        'imports',
        'import_errors',
        'audit_log',
    )

    def setUp(self):
        self._old_db_path = database.DB_PATH
        self._old_migrations_run = database._migrations_run
        self._temp_dir = tempfile.TemporaryDirectory()
        database.DB_PATH = os.path.join(self._temp_dir.name, 'partial-import.db')
        database._migrations_run = False

        conn = database.get_db_connection()
        migrations.run_migrations(conn)
        # The full schema creates the operation tables; run the lightweight
        # dynamic migration once afterwards to add validation metadata.
        database._migrations_run = False
        conn.close()
        conn = database.get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """INSERT INTO projects
               (name, description, area, current_counter, default_horizon,
                utilization_factor, status)
               VALUES ('Projeto teste parcial', '', 'TESTE', 106, 12, 1.0, 'ACTIVE')"""
        )
        self.project_id = cursor.lastrowid
        conn.commit()
        conn.close()

    def tearDown(self):
        database.DB_PATH = self._old_db_path
        database._migrations_run = self._old_migrations_run
        self._temp_dir.cleanup()

    @staticmethod
    def _plan(code='PLAN-A', description='Plano A'):
        return {
            'row_number': 2,
            'legacy_code': code,
            'description': description,
            'character_count': len(description),
            'cycle': 2,
            'unit': 'PRD',
            'cycle_text': '2 P',
            'opening_horizon': 12,
            'reference_counter': 1,
            'extracted_start_stop': 1,
            'is_valid': True,
        }

    @staticmethod
    def _item(identifier='1', plan_code='PLAN-A', description='Item A', headcount=2):
        return {
            'row_number': 2,
            'legacy_identifier': identifier,
            'plano_reparo_code': plan_code,
            'object_type': 'EQUIPAMENTO',
            'object_code': 'EQ-01',
            'gpm': '042',
            'work_center': 'MEC01',
            'condition_code': 'Q',
            'priority': 3,
            'legacy_start': 1,
            'description': description,
            'character_count': len(description),
            'duration_hours': 2.0,
            'headcount': headcount,
            'validation_status': 'OK',
            'validation_issues': [],
            'is_valid': True,
        }

    @staticmethod
    def _operation(identifier='1', code='0010', sub='', short_text='Operacao A'):
        return {
            'row_number': 2,
            'legacy_identifier': identifier,
            'operation_code': code,
            'suboperation_code': sub,
            'work_center': 'MEC01',
            'short_text': short_text,
            'unit': 'H',
            'headcount': 2,
            'hours': 2.0,
            'validation_status': 'OK',
            'validation_issues': [],
        }

    @staticmethod
    def _long_text(identifier='1', code='0010', sub='', text='Texto A'):
        return {
            'row_number': 2,
            'legacy_identifier': identifier,
            'operation_code': code,
            'suboperation_code': sub,
            'group_code': None,
            'group_counter': None,
            'text': text,
            'validation_status': 'OK',
            'validation_issues': [],
        }

    def _preview(self, selected=None, *, plans=None, items=None,
                 operations=None, long_texts=None, suffix='base'):
        selected = selected or ['plans', 'items', 'operations', 'long_texts']
        return {
            'summary': {
                'filename': f'{suffix}.xlsx',
                'file_hash': f'hash-{suffix}',
                'selected_entities': list(selected),
            },
            'selected_entities': list(selected),
            'plans': list(plans or []),
            'items': list(items or []),
            'operations': list(operations or []),
            'long_texts': list(long_texts or []),
            'errors': [],
            'suggested_cycles': [],
        }

    def _full_preview(self, *, plan_code='PLAN-A', identifier='1', suffix='base'):
        return self._preview(
            plans=[self._plan(plan_code)],
            items=[self._item(identifier, plan_code)],
            operations=[
                self._operation(identifier, '0010', '', 'Cabecalho'),
                self._operation(identifier, '0020', '', 'Atividade'),
            ],
            long_texts=[
                self._long_text(identifier, '0010', '', ''),
                self._long_text(identifier, '0020', '', 'Procedimento original'),
            ],
            suffix=suffix,
        )

    def _two_graph_preview(self, suffix='two-graphs'):
        return self._preview(
            plans=[self._plan('PLAN-A'), self._plan('PLAN-B', 'Plano B')],
            items=[self._item('1', 'PLAN-A'), self._item('2', 'PLAN-B', 'Item B')],
            operations=[
                self._operation('1', '0010', '', 'Operacao do item A'),
                self._operation('2', '0020', '', 'Operacao do item B'),
            ],
            long_texts=[
                self._long_text('1', '0010', '', 'Texto do item A'),
                self._long_text('2', '0020', '', 'Texto do item B'),
            ],
            suffix=suffix,
        )

    def _rows(self, table):
        conn = database.get_db_connection()
        try:
            rows = conn.execute(f'SELECT * FROM {table} ORDER BY id').fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    def _snapshot(self):
        return {table: self._rows(table) for table in self.DATA_TABLES}

    def _seed_complete_graph(self):
        confirm_import(self.project_id, self._full_preview(), merge_mode='replace')

    def test_full_replace_removes_old_graph_and_writes_exact_new_graph(self):
        self._seed_complete_graph()
        old_ids = {
            table: [row['id'] for row in self._rows(table)]
            for table in ('plans', 'maintenance_items', 'item_operations', 'operation_long_texts')
        }

        confirm_import(
            self.project_id,
            self._full_preview(plan_code='PLAN-B', identifier='9', suffix='replacement'),
            merge_mode='replace',
        )

        self.assertEqual([row['legacy_code'] for row in self._rows('plans')], ['PLAN-B'])
        self.assertEqual([row['legacy_identifier'] for row in self._rows('maintenance_items')], ['9'])
        self.assertEqual(
            [(row['operation_code'], row['suboperation_code']) for row in self._rows('item_operations')],
            [('0010', ''), ('0020', '')],
        )
        self.assertEqual([row['text'] for row in self._rows('operation_long_texts')], ['', 'Procedimento original'])
        for table in old_ids:
            self.assertTrue(set(old_ids[table]).isdisjoint(row['id'] for row in self._rows(table)))

    def test_full_replace_discards_manual_balance_draft_from_previous_catalog(self):
        self._seed_complete_graph()
        draft = manual_balance_service.start_session(self.project_id, 'zero', 12)
        self.assertGreater(draft['total_items'], 0)

        confirm_import(
            self.project_id,
            self._full_preview(plan_code='PLAN-NOVO', identifier='99', suffix='new-catalog'),
            merge_mode='replace',
        )

        self.assertIsNone(manual_balance_service.get_active_session(self.project_id))
        sessions = self._rows('manual_balance_sessions')
        self.assertEqual(sessions[-1]['status'], 'DISCARDED')

        new_draft = manual_balance_service.start_session(self.project_id, 'zero', 12)
        self.assertEqual(new_draft['total_items'], 1)
        self.assertEqual(new_draft['counts'].get('PENDING'), 1)

    def test_text_identifier_with_letters_and_special_characters_links_all_entities(self):
        identifier = 'EQ.01-A/SETOR#2'
        self.assertEqual(normalize_identifier(identifier), identifier)
        self.assertEqual(normalize_identifier(157.0), '157')

        confirm_import(
            self.project_id,
            self._full_preview(identifier=identifier, suffix='text-identifier'),
            merge_mode='replace',
        )

        items = self._rows('maintenance_items')
        operations = self._rows('item_operations')
        texts = self._rows('operation_long_texts')
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]['legacy_identifier'], identifier)
        self.assertEqual({row['item_id'] for row in operations}, {items[0]['id']})
        self.assertEqual({row['operation_id'] for row in texts}, {row['id'] for row in operations})

    def test_identifier_link_is_exact_and_does_not_ignore_leading_zeroes(self):
        preview = self._preview(
            plans=[self._plan()],
            items=[self._item('1')],
            operations=[self._operation('001')],
            long_texts=[self._long_text('001')],
            suffix='exact-identifier',
        )
        confirm_import(self.project_id, preview, merge_mode='replace')

        items = self._rows('maintenance_items')
        self.assertEqual({row['legacy_identifier'] for row in items}, {'1', '001'})
        placeholder = next(row for row in items if row['legacy_identifier'] == '001')
        self.assertEqual(placeholder['validation_status'], 'ERROR')
        self.assertIn('operation_without_item', placeholder['validation_issues_json'])

    def test_zero_headcount_is_preserved_as_zero_hh_in_full_import(self):
        preview = self._full_preview(suffix='zero-headcount-full')
        preview['items'][0]['headcount'] = 0
        confirm_import(self.project_id, preview, merge_mode='replace')

        item = self._rows('maintenance_items')[0]
        self.assertEqual(item['headcount'], 0)
        self.assertEqual(item['hh'], 0)

    def test_zero_headcount_clears_stale_trade_load_in_scoped_item_import(self):
        self._seed_complete_graph()
        conn = database.get_db_connection()
        conn.execute("""UPDATE maintenance_items SET mec_headcount=2,mec_hours=4,
                        ele_headcount=1,ele_hours=2,sol_headcount=1,sol_hours=3
                        WHERE project_id=?""", (self.project_id,))
        conn.commit()
        conn.close()

        preview = self._preview(
            ['items'], items=[self._item(headcount=0)], suffix='zero-headcount-scoped')
        confirm_import(self.project_id, preview, merge_mode='replace')

        item = self._rows('maintenance_items')[0]
        self.assertEqual(item['headcount'], 0)
        self.assertEqual(item['hh'], 0)
        self.assertEqual(
            (item['mec_headcount'], item['mec_hours'], item['ele_headcount'],
             item['ele_hours'], item['sol_headcount'], item['sol_hours']),
            (0, 0, 0, 0, 0, 0),
        )

    def test_long_text_only_is_an_exact_scope_and_preserves_all_parents(self):
        self._seed_complete_graph()
        parent_before = {
            table: self._rows(table)
            for table in ('plans', 'maintenance_items', 'item_operations')
        }

        preview = self._preview(
            ['long_texts'],
            long_texts=[self._long_text('1', '0010', '', 'Cabecalho atualizado')],
            suffix='texts-only',
        )
        confirm_import(self.project_id, preview, merge_mode='replace')

        for table, expected in parent_before.items():
            self.assertEqual(self._rows(table), expected, table)
        texts = self._rows('operation_long_texts')
        self.assertEqual([row['text'] for row in texts], ['Cabecalho atualizado'])

    def test_long_text_only_with_empty_source_clears_all_texts(self):
        self._seed_complete_graph()
        parents_before = {
            table: self._rows(table)
            for table in ('plans', 'maintenance_items', 'item_operations')
        }

        confirm_import(
            self.project_id,
            self._preview(['long_texts'], suffix='empty-texts'),
            merge_mode='replace',
        )

        self.assertEqual(self._rows('operation_long_texts'), [])
        for table, expected in parents_before.items():
            self.assertEqual(self._rows(table), expected, table)

    def test_operations_only_rejects_stale_operation_with_unselected_text(self):
        self._seed_complete_graph()
        before = self._snapshot()

        preview = self._preview(
            ['operations'],
            operations=[self._operation('1', '0010', '', 'Cabecalho atualizado')],
            suffix='unsafe-operations-only',
        )
        with self.assertRaises(ValueError):
            confirm_import(self.project_id, preview, merge_mode='replace')

        self.assertEqual(self._snapshot(), before)

    def test_operations_only_exact_sync_preserves_matching_id_when_safe(self):
        self._seed_complete_graph()
        conn = database.get_db_connection()
        conn.execute(
            """DELETE FROM operation_long_texts
               WHERE operation_id IN (
                   SELECT id FROM item_operations
                   WHERE project_id=? AND operation_code='0020'
               )""",
            (self.project_id,),
        )
        conn.commit()
        conn.close()
        plans_before = self._rows('plans')
        items_before = self._rows('maintenance_items')
        texts_before = self._rows('operation_long_texts')
        operation_before = {
            (row['operation_code'], row['suboperation_code']): row
            for row in self._rows('item_operations')
        }

        preview = self._preview(
            ['operations'],
            operations=[
                self._operation('1', '0010', '', 'Cabecalho atualizado'),
                self._operation('1', '0030', '', 'Nova atividade'),
            ],
            suffix='operations-only',
        )
        confirm_import(self.project_id, preview, merge_mode='replace')

        operation_after = {
            (row['operation_code'], row['suboperation_code']): row
            for row in self._rows('item_operations')
        }
        self.assertEqual(self._rows('plans'), plans_before)
        self.assertEqual(self._rows('maintenance_items'), items_before)
        self.assertEqual(self._rows('operation_long_texts'), texts_before)
        self.assertEqual(operation_after[('0010', '')]['id'], operation_before[('0010', '')]['id'])
        self.assertEqual(operation_after[('0010', '')]['short_text'], 'Cabecalho atualizado')
        self.assertNotIn(('0020', ''), operation_after)
        self.assertIn(('0030', ''), operation_after)

    def test_operations_and_texts_replace_exactly_with_cascade(self):
        self._seed_complete_graph()
        operation_before = {
            (row['operation_code'], row['suboperation_code']): row
            for row in self._rows('item_operations')
        }

        confirm_import(
            self.project_id,
            self._preview(
                ['operations', 'long_texts'],
                operations=[self._operation('1', '0010', '', 'Cabecalho atualizado')],
                long_texts=[self._long_text('1', '0010', '', 'Novo texto')],
                suffix='operations-and-texts',
            ),
            merge_mode='replace',
        )

        operations = self._rows('item_operations')
        self.assertEqual(len(operations), 1)
        self.assertEqual(operations[0]['id'], operation_before[('0010', '')]['id'])
        self.assertEqual(operations[0]['operation_code'], '0010')
        self.assertEqual([row['text'] for row in self._rows('operation_long_texts')], ['Novo texto'])

    def test_plans_only_rejects_referenced_stale_plan_and_rolls_back(self):
        confirm_import(self.project_id, self._two_graph_preview(), merge_mode='replace')
        before = self._snapshot()

        with self.assertRaises(ValueError):
            confirm_import(
                self.project_id,
                self._preview(
                    ['plans'], plans=[self._plan('PLAN-A', 'Plano A atualizado')],
                    suffix='unsafe-plans-only',
                ),
                merge_mode='replace',
            )

        self.assertEqual(self._snapshot(), before)

    def test_plans_only_replace_is_exact_when_stale_plan_is_unreferenced(self):
        confirm_import(
            self.project_id,
            self._preview(
                plans=[self._plan('PLAN-A'), self._plan('PLAN-B', 'Plano B')],
                items=[self._item('1', 'PLAN-A')],
                operations=[self._operation('1', '0010')],
                long_texts=[self._long_text('1', '0010', '', 'Texto preservado')],
                suffix='unreferenced-plan',
            ),
            merge_mode='replace',
        )
        plans_before = {row['legacy_code']: row for row in self._rows('plans')}
        items_before = self._rows('maintenance_items')
        operations_before = self._rows('item_operations')
        texts_before = self._rows('operation_long_texts')

        confirm_import(
            self.project_id,
            self._preview(
                ['plans'], plans=[self._plan('PLAN-A', 'Plano A atualizado')],
                suffix='plans-only-exact',
            ),
            merge_mode='replace',
        )

        plans = self._rows('plans')
        self.assertEqual([(row['legacy_code'], row['description']) for row in plans],
                         [('PLAN-A', 'Plano A atualizado')])
        self.assertEqual(plans[0]['id'], plans_before['PLAN-A']['id'])
        self.assertEqual(self._rows('maintenance_items'), items_before)
        self.assertEqual(self._rows('item_operations'), operations_before)
        self.assertEqual(self._rows('operation_long_texts'), texts_before)

    def test_items_only_rejects_stale_item_with_operations_and_rolls_back(self):
        confirm_import(self.project_id, self._two_graph_preview(), merge_mode='replace')
        before = self._snapshot()

        with self.assertRaises(ValueError):
            confirm_import(
                self.project_id,
                self._preview(
                    ['items'], items=[self._item('1', 'PLAN-A', 'Item A atualizado')],
                    suffix='unsafe-items-only',
                ),
                merge_mode='replace',
            )

        self.assertEqual(self._snapshot(), before)

    def test_items_only_replace_is_exact_when_stale_item_has_no_children(self):
        confirm_import(self.project_id, self._two_graph_preview(), merge_mode='replace')
        conn = database.get_db_connection()
        conn.execute(
            """DELETE FROM item_operations
               WHERE item_id IN (
                   SELECT id FROM maintenance_items
                   WHERE project_id=? AND legacy_identifier='2'
               )""",
            (self.project_id,),
        )
        conn.commit()
        conn.close()
        items_before = {row['legacy_identifier']: row for row in self._rows('maintenance_items')}
        operations_before = {row['item_id']: row for row in self._rows('item_operations')}

        confirm_import(
            self.project_id,
            self._preview(
                ['items'], items=[self._item('1', 'PLAN-A', 'Item A atualizado')],
                suffix='items-only-exact',
            ),
            merge_mode='replace',
        )

        items = self._rows('maintenance_items')
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]['id'], items_before['1']['id'])
        self.assertEqual(items[0]['description'], 'Item A atualizado')
        operations = self._rows('item_operations')
        self.assertEqual(len(operations), 1)
        self.assertEqual(operations[0]['id'], operations_before[items_before['1']['id']]['id'])
        self.assertEqual([row['text'] for row in self._rows('operation_long_texts')], ['Texto do item A'])

    def test_items_only_duplicate_natural_keys_are_rejected_atomically(self):
        self._seed_complete_graph()
        before = self._snapshot()
        duplicate = self._item('1', 'PLAN-A', 'Duplicado')
        duplicate['is_duplicate'] = True
        preview = self._preview(
            ['items'],
            items=[self._item('1', 'PLAN-A'), duplicate],
            suffix='duplicate-items',
        )

        with self.assertRaises(ValueError):
            confirm_import(self.project_id, preview, merge_mode='replace')
        self.assertEqual(self._snapshot(), before)

    def test_merge_preserves_extra_rows_in_every_partial_scope(self):
        confirm_import(self.project_id, self._two_graph_preview(), merge_mode='replace')
        ids_before = {
            'plans': {row['legacy_code']: row['id'] for row in self._rows('plans')},
            'items': {row['legacy_identifier']: row['id'] for row in self._rows('maintenance_items')},
            'operations': {(row['item_id'], row['operation_code']): row['id']
                           for row in self._rows('item_operations')},
        }

        confirm_import(
            self.project_id,
            self._preview(['plans'], plans=[self._plan('PLAN-A', 'Plano merge')], suffix='merge-plan'),
            merge_mode='merge',
        )
        confirm_import(
            self.project_id,
            self._preview(['items'], items=[self._item('1', 'PLAN-A', 'Item merge')], suffix='merge-item'),
            merge_mode='merge',
        )
        confirm_import(
            self.project_id,
            self._preview(
                ['operations'], operations=[self._operation('1', '0010', '', 'Operacao merge')],
                suffix='merge-operation',
            ),
            merge_mode='merge',
        )
        confirm_import(
            self.project_id,
            self._preview(
                ['long_texts'], long_texts=[self._long_text('1', '0010', '', 'Texto merge')],
                suffix='merge-text',
            ),
            merge_mode='merge',
        )

        plans = {row['legacy_code']: row for row in self._rows('plans')}
        items = {row['legacy_identifier']: row for row in self._rows('maintenance_items')}
        operations = {(row['item_id'], row['operation_code']): row
                      for row in self._rows('item_operations')}
        self.assertEqual(set(plans), {'PLAN-A', 'PLAN-B'})
        self.assertEqual(set(items), {'1', '2'})
        self.assertEqual(len(operations), 2)
        self.assertEqual(plans['PLAN-A']['id'], ids_before['plans']['PLAN-A'])
        self.assertEqual(plans['PLAN-B']['id'], ids_before['plans']['PLAN-B'])
        self.assertEqual(items['1']['id'], ids_before['items']['1'])
        self.assertEqual(items['2']['id'], ids_before['items']['2'])
        self.assertEqual(operations[(items['1']['id'], '0010')]['id'],
                         ids_before['operations'][(items['1']['id'], '0010')])
        self.assertEqual(operations[(items['2']['id'], '0020')]['id'],
                         ids_before['operations'][(items['2']['id'], '0020')])
        self.assertEqual(sorted(row['text'] for row in self._rows('operation_long_texts')),
                         ['Texto do item B', 'Texto merge'])

    def test_unresolved_dependencies_roll_back_every_change(self):
        invalid_previews = {
            'item_without_plan': self._preview(
                ['items'], items=[self._item('2', 'PLAN-INEXISTENTE')], suffix='bad-item'
            ),
            'operation_without_item': self._preview(
                ['operations'], operations=[self._operation('999', '0010')], suffix='bad-operation'
            ),
        }
        for label, preview in invalid_previews.items():
            with self.subTest(label=label):
                # Each case gets the same independently-created baseline.
                if self._rows('plans'):
                    conn = database.get_db_connection()
                    conn.execute('DELETE FROM operation_long_texts WHERE project_id=?', (self.project_id,))
                    conn.execute('DELETE FROM item_operations WHERE project_id=?', (self.project_id,))
                    conn.execute('DELETE FROM maintenance_items WHERE project_id=?', (self.project_id,))
                    conn.execute('DELETE FROM plans WHERE project_id=?', (self.project_id,))
                    conn.execute('DELETE FROM imports WHERE project_id=?', (self.project_id,))
                    conn.execute('DELETE FROM audit_log WHERE project_id=?', (self.project_id,))
                    conn.commit()
                    conn.close()
                self._seed_complete_graph()
                before = self._snapshot()

                with self.assertRaises(ValueError):
                    confirm_import(self.project_id, copy.deepcopy(preview), merge_mode='replace')

                self.assertEqual(self._snapshot(), before)

    def test_full_import_keeps_operation_without_item_as_validation_error(self):
        preview = self._full_preview(suffix='orphan-full')
        preview['operations'].append(self._operation('SEM-ITEM', '0030', '', 'Operacao orfa'))

        confirm_import(self.project_id, preview, merge_mode='replace')

        items = {row['legacy_identifier']: row for row in self._rows('maintenance_items')}
        self.assertIn('SEM-ITEM', items)
        self.assertEqual(items['SEM-ITEM']['validation_status'], 'ERROR')
        operations = self._rows('item_operations')
        orphan = next(row for row in operations if row['operation_code'] == '0030')
        self.assertEqual(orphan['item_id'], items['SEM-ITEM']['id'])
        self.assertEqual(orphan['validation_status'], 'ERROR')
        self.assertIn('operation_without_item', orphan['validation_issues_json'])
        self.assertEqual(len(self._rows('import_errors')), 1)

    def test_partial_merge_keeps_operation_without_item_as_validation_error(self):
        self._seed_complete_graph()
        preview = self._preview(
            ['operations'], operations=[self._operation('SEM-ITEM', '0030')], suffix='orphan-merge'
        )

        confirm_import(self.project_id, preview, merge_mode='merge')

        placeholder = next(row for row in self._rows('maintenance_items')
                           if row['legacy_identifier'] == 'SEM-ITEM')
        orphan = next(row for row in self._rows('item_operations')
                      if row['operation_code'] == '0030')
        self.assertEqual(orphan['item_id'], placeholder['id'])
        self.assertEqual(orphan['validation_status'], 'ERROR')

    def test_full_import_keeps_long_text_without_operation_as_validation_error(self):
        preview = self._full_preview(suffix='orphan-text-full')
        preview['long_texts'].extend([
            self._long_text('1', '0090', '', 'Primeira linha preservada'),
            self._long_text('1', '0090', '', 'Segunda linha preservada'),
        ])

        confirm_import(self.project_id, preview, merge_mode='replace')

        operations = self._rows('item_operations')
        placeholder = next(row for row in operations if row['operation_code'] == '0090')
        self.assertEqual(placeholder['validation_status'], 'ERROR')
        self.assertIn('long_text_without_operation', placeholder['validation_issues_json'])
        texts = [row for row in self._rows('operation_long_texts')
                 if row['operation_id'] == placeholder['id']]
        self.assertEqual([row['text'] for row in texts],
                         ['Primeira linha preservada', 'Segunda linha preservada'])
        self.assertTrue(all(row['validation_status'] == 'ERROR' for row in texts))
        self.assertTrue(all('long_text_without_operation' in row['validation_issues_json']
                            for row in texts))
        self.assertTrue(any(row['field_name'] == 'Vínculo da operação'
                            for row in self._rows('import_errors')))

    def test_long_text_only_creates_error_placeholders_for_missing_operation_and_item(self):
        self._seed_complete_graph()
        preview = self._preview(
            ['long_texts'],
            long_texts=[self._long_text('SEM-ITEM-TEXTO', '0020', '', 'Procedimento órfão')],
            suffix='orphan-text-partial',
        )

        confirm_import(self.project_id, preview, merge_mode='replace')

        item = next(row for row in self._rows('maintenance_items')
                    if row['legacy_identifier'] == 'SEM-ITEM-TEXTO')
        self.assertEqual(item['validation_status'], 'ERROR')
        operation = next(row for row in self._rows('item_operations')
                         if row['item_id'] == item['id'] and row['operation_code'] == '0020')
        self.assertEqual(operation['validation_status'], 'ERROR')
        text = self._rows('operation_long_texts')[0]
        self.assertEqual(text['operation_id'], operation['id'])
        self.assertEqual(text['text'], 'Procedimento órfão')
        self.assertEqual(text['validation_status'], 'ERROR')

    def test_invalid_selected_entities_are_rejected_without_writes(self):
        self._seed_complete_graph()
        for invalid in ([], ['plans', 'desconhecido'], 'plans'):
            with self.subTest(selected_entities=invalid):
                preview = self._full_preview(suffix='bad-selection')
                preview['selected_entities'] = invalid
                preview['summary']['selected_entities'] = invalid
                before = self._snapshot()

                with self.assertRaises(ValueError):
                    confirm_import(self.project_id, preview, merge_mode='replace')

                self.assertEqual(self._snapshot(), before)


if __name__ == '__main__':
    unittest.main()
