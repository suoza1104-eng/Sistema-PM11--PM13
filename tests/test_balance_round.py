import os
import unittest

from core import database, migrations, models
from core import auto_balance_service, manual_balance_service
from core.balance_rules import evaluate_rule, find_feasible_assignment
from core.calculations import project_balance


class TestBalanceRound(unittest.TestCase):
    def setUp(self):
        self.db_path = os.path.abspath('test_balance_round.db')
        if os.path.exists(self.db_path):
            os.remove(self.db_path)
        database.DB_PATH = self.db_path
        conn = database.get_db_connection()
        migrations.run_migrations(conn)
        conn.close()
        self.project_id = models.create_project(
            'Rodada Balanceamento', 'MS2', 'Testes da rodada',
            current_counter=100, default_horizon=12, utilization_factor=1.0)

    def tearDown(self):
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def add_family(self, prefix9, cycle, item_specs):
        plans = []
        for phase in range(1, cycle + 1):
            plans.append(models.create_plan(
                self.project_id, f'{prefix9}{phase:02d}',
                f'PREVENTIVA {prefix9} {cycle}P{phase}', cycle, 'PRD',
                f'{cycle}P', 35.0, 100 + phase))
        item_ids = []
        for identifier, hh, phase in item_specs:
            item_ids.append(models.create_item(
                self.project_id, str(identifier), plans[phase - 1], 'EQUIPAMENTO',
                f'EQ-{identifier}', 'G1', 'CT1', 'A', 1, None,
                f'{prefix9} EQUIPAMENTO {identifier}', hh, 1))
        return plans, item_ids

    def test_cross_cycle_together_and_separate_rules(self):
        plans_3p, items_3p = self.add_family('URRST2STA', 3, [(10, 4, 2)])
        plans_6p, items_6p = self.add_family('URRST2STB', 6, [(20, 4, 5)])
        plans_2p, items_2p = self.add_family('URRST2STC', 2, [(30, 4, 1)])
        plans_4p, items_4p = self.add_family('URRST2STD', 4, [(40, 4, 1)])

        rules = [
            {'name': 'Encontro 3P com 6P', 'type': 'together', 'enforcement': 'mandatory',
             'item_ids': [items_3p[0], items_6p[0]]},
            {'name': 'Separar 2P de 4P', 'type': 'separate', 'enforcement': 'mandatory',
             'item_ids': [items_2p[0], items_4p[0]]},
        ]
        result = auto_balance_service.optimize(
            self.project_id, rules, 12, max_passes=8, similarity_enabled=False)
        diagnostics = {row['name']: row for row in result['rule_diagnostics']}
        self.assertTrue(diagnostics['Encontro 3P com 6P']['satisfied'])
        self.assertEqual(diagnostics['Encontro 3P com 6P']['required_common_occurrences'], 2)
        self.assertTrue(diagnostics['Separar 2P de 4P']['satisfied'])
        self.assertEqual(diagnostics['Separar 2P de 4P']['conflict_stops'], [])

        plan_by_id = {}
        conn = database.get_db_connection()
        try:
            plan_by_id = {row['id']: dict(row) for row in conn.execute(
                'SELECT * FROM plans WHERE project_id=?', (self.project_id,))}
        finally:
            conn.close()
        impossible = evaluate_rule(
            {'name': '1P separado', 'type': 'separate', 'enforcement': 'mandatory',
             'item_ids': [1, 2]},
            {1: plans_2p[0], 2: plans_4p[0]}, plan_by_id, 100, 12)
        self.assertFalse(impossible['satisfied'])

    def test_large_together_rule_collapses_equivalent_phase_choices(self):
        plans_3p, items_3p = self.add_family(
            'URRST2GE3', 3, [(index, 1, 1) for index in range(1, 27)])
        plans_6p, items_6p = self.add_family(
            'URRST2GE6', 6, [(index, 1, 1) for index in range(101, 117)])
        conn = database.get_db_connection()
        try:
            plan_by_id = {row['id']: dict(row) for row in conn.execute(
                'SELECT * FROM plans WHERE project_id=?', (self.project_id,))}
        finally:
            conn.close()
        candidates = {item_id: plans_3p for item_id in items_3p}
        candidates.update({item_id: plans_6p for item_id in items_6p})
        checks = {'count': 0}

        def check_deadline():
            checks['count'] += 1
            if checks['count'] > 30:
                raise AssertionError('A busca não deveria enumerar combinações por item.')

        solved = find_feasible_assignment({
            'name': 'Geografia obrigatória', 'type': 'together',
            'enforcement': 'mandatory', 'item_ids': items_3p + items_6p,
        }, candidates, plan_by_id, 100, 12,
            deadline_callback=check_deadline)
        self.assertIsNotNone(solved)
        self.assertLessEqual(checks['count'], 18)
        self.assertEqual(len({solved[item_id] for item_id in items_3p}), 1)
        self.assertEqual(len({solved[item_id] for item_id in items_6p}), 1)

    def test_manual_book_move_return_and_publish(self):
        _, fixed_items = self.add_family('URRST2FIX', 1, [(1, 2, 1)])
        plans_2p, items_2p = self.add_family('URRST2MAN', 2, [(2, 5, 2), (3, 3, 1)])
        original_plan = models.get_item(items_2p[0])['plan_id']

        session = manual_balance_service.start_session(self.project_id, 'zero', 12)
        self.assertEqual(session['counts']['FIXED'], 1)
        self.assertEqual(session['counts']['PENDING'], 2)
        draft = project_balance(self.project_id, {
            'manual_session_id': session['id'], 'horizon': 12}, 'none')
        self.assertTrue(all(stop['total_orders'] == 1 for stop in draft['stops']))

        with self.assertRaisesRegex(ValueError, '1P'):
            manual_balance_service.move_items(
                self.project_id, session['id'], fixed_items, 101)

        moved = manual_balance_service.move_items(
            self.project_id, session['id'], [items_2p[0]], 101)
        self.assertEqual(moved['session']['counts']['MANUAL'], 1)
        book = manual_balance_service.list_book(
            self.project_id, session['id'], only_pending=True)
        self.assertEqual([row['id'] for row in book['items']], [items_2p[1]])
        details = manual_balance_service.stop_details(
            self.project_id, session['id'], 101, 12)
        self.assertIn(items_2p[0], [row['id'] for row in details['orders']])

        returned = manual_balance_service.return_to_book(
            self.project_id, session['id'], [items_2p[0]])
        self.assertEqual(returned['session']['counts']['PENDING'], 2)
        manual_balance_service.move_items(
            self.project_id, session['id'], [items_2p[0]], 101)
        manual_balance_service.complete_session(
            self.project_id, session['id'], allow_pending=True)
        self.assertIsNone(manual_balance_service.get_active_session(self.project_id))
        self.assertNotEqual(models.get_item(items_2p[0])['plan_id'], original_plan)

    def test_restart_manual_session_returns_balanceable_items_to_book(self):
        self.add_family('URRST2FIX', 1, [(1, 2, 1)])
        _, item_ids = self.add_family('URRST2RST', 3, [(10, 4, 1), (20, 4, 2)])
        first = manual_balance_service.start_session(self.project_id, 'current', 12)
        self.assertEqual(first['progress_percent'], 100.0)
        official_plans_before = {
            item_id: models.get_item(item_id)['plan_id'] for item_id in item_ids
        }

        restarted = manual_balance_service.start_session(
            self.project_id, 'zero', 12, restart=True)
        self.assertNotEqual(restarted['id'], first['id'])
        self.assertEqual(restarted['counts']['PENDING'], 2)
        self.assertEqual(restarted['counts']['FIXED'], 1)
        self.assertLess(restarted['progress_percent'], 100.0)
        book = manual_balance_service.list_book(
            self.project_id, restarted['id'], only_pending=True)
        self.assertEqual({row['id'] for row in book['items']}, set(item_ids))
        self.assertEqual(
            {item_id: models.get_item(item_id)['plan_id'] for item_id in item_ids},
            official_plans_before)

    def test_discard_active_session_after_official_restore(self):
        self.add_family('URRST2DSC', 2, [(10, 2, 1)])
        session = manual_balance_service.start_session(self.project_id, 'current', 12)
        self.assertIsNotNone(session)
        self.assertEqual(manual_balance_service.discard_active_sessions(self.project_id), 1)
        self.assertIsNone(manual_balance_service.get_active_session(self.project_id))

    def test_item_inactivation_preserves_draft_and_reactivation_position(self):
        _, item_ids = self.add_family(
            'URRST2STA', 3, [(10, 4, 1), (20, 5, 2)])
        session = manual_balance_service.start_session(self.project_id, 'current', 12)
        manual_balance_service.move_items(
            self.project_id, session['id'], [item_ids[0]], 102)
        conn = database.get_db_connection()
        try:
            position_before = dict(conn.execute("""SELECT target_plan_id,target_stop,balance_state
                FROM manual_balance_assignments WHERE session_id=? AND item_id=?""",
                (session['id'], item_ids[0])).fetchone())
            conn.execute("UPDATE maintenance_items SET status='INACTIVE' WHERE id=?", (item_ids[0],))
            conn.commit()
        finally:
            conn.close()

        active = manual_balance_service.get_active_session(self.project_id)
        self.assertIsNotNone(active)
        self.assertEqual(active['id'], session['id'])
        self.assertEqual(active['total_items'], 1)
        self.assertNotIn(item_ids[0], [row['id'] for row in manual_balance_service.list_book(
            self.project_id, session['id'])['items']])
        inactive_balance = project_balance(self.project_id, {
            'manual_session_id': session['id'], 'horizon': 12}, 'none')
        self.assertEqual(sum(stop['total_orders'] for stop in inactive_balance['stops']), 4)

        conn = database.get_db_connection()
        try:
            conn.execute("UPDATE maintenance_items SET status='ACTIVE' WHERE id=?", (item_ids[0],))
            conn.commit()
            position_after = dict(conn.execute("""SELECT target_plan_id,target_stop,balance_state
                FROM manual_balance_assignments WHERE session_id=? AND item_id=?""",
                (session['id'], item_ids[0])).fetchone())
        finally:
            conn.close()
        self.assertEqual(position_after, position_before)
        reactivated = manual_balance_service.get_active_session(self.project_id)
        self.assertEqual(reactivated['id'], session['id'])
        self.assertEqual(reactivated['total_items'], 2)

    def test_automatic_ignores_inactive_fixed_draft_items(self):
        _, fixed_items = self.add_family('URRST2LCK', 1, [(1, 6, 1)])
        _, movable_items = self.add_family(
            'URRST2MOV', 3, [(10, 4, 1), (20, 5, 2)])
        session = manual_balance_service.start_session(self.project_id, 'current', 12)
        conn = database.get_db_connection()
        try:
            conn.execute("UPDATE maintenance_items SET status='INACTIVE' WHERE id=?",
                         (fixed_items[0],))
            conn.commit()
        finally:
            conn.close()

        result = auto_balance_service.optimize(
            self.project_id, [], 12, manual_session_id=session['id'])
        result_ids = {row['item_id'] for row in result['assignment_results']}
        self.assertNotIn(fixed_items[0], result_ids)
        self.assertEqual(result_ids, set(movable_items))
        active = manual_balance_service.get_active_session(self.project_id)
        self.assertEqual(active['id'], session['id'])
        self.assertEqual(active['total_items'], len(movable_items))

    def test_automatic_continues_draft_and_preserves_manual_items(self):
        self.add_family('URRST2FIX', 1, [(1, 1, 1)])
        _, item_ids = self.add_family(
            'URRST2AUT', 4, [(10, 4, 1), (20, 4, 1), (30, 4, 1), (40, 4, 1)])
        session = manual_balance_service.start_session(self.project_id, 'zero', 12)
        manual_balance_service.move_items(
            self.project_id, session['id'], [item_ids[0]], 102)
        conn = database.get_db_connection()
        try:
            manual_plan = conn.execute("""SELECT target_plan_id FROM manual_balance_assignments
                WHERE session_id=? AND item_id=?""", (session['id'], item_ids[0])).fetchone()[0]
        finally:
            conn.close()

        auto_balance_service.apply(
            self.project_id, [], 12, max_passes=10, similarity_enabled=False,
            distribution_strategy='horizontal', geography_mode='preferred',
            vertical_tolerance=15, manual_session_id=session['id'], preserve_manual=True)
        conn = database.get_db_connection()
        try:
            rows = {row['item_id']: dict(row) for row in conn.execute(
                'SELECT * FROM manual_balance_assignments WHERE session_id=?', (session['id'],))}
        finally:
            conn.close()
        self.assertEqual(rows[item_ids[0]]['target_plan_id'], manual_plan)
        self.assertEqual(rows[item_ids[0]]['balance_state'], 'MANUAL')
        self.assertTrue(all(rows[item_id]['balance_state'] == 'AUTOMATIC' for item_id in item_ids[1:]))
        preferences = auto_balance_service.get_preferences(self.project_id)
        self.assertEqual(preferences['geography_mode'], 'preferred')
        self.assertEqual(preferences['vertical_tolerance'], 15.0)
        self.assertFalse(preferences['similarity_enabled'])

    def test_user_lock_blocks_manual_and_automatic_movement(self):
        plans, item_ids = self.add_family(
            'URRST2LCK', 4, [(10, 4, 1), (20, 2, 1)])
        session = manual_balance_service.start_session(self.project_id, 'current', 12)
        item_id = item_ids[0]

        locked = manual_balance_service.set_item_lock(
            self.project_id, session['id'], item_id, True, 101)
        self.assertTrue(locked['locked'])
        with self.assertRaisesRegex(ValueError, 'trancados'):
            manual_balance_service.move_items(
                self.project_id, session['id'], [item_id], 102,
                {item_id: plans[1]})

        automatic = auto_balance_service.optimize(
            self.project_id, [], 12, max_passes=10, similarity_enabled=False,
            manual_session_id=session['id'], preserve_manual=True)
        automatic_ids = {row['item_id'] for row in automatic['assignment_results']}
        self.assertNotIn(item_id, automatic_ids)

        rebalance_all = auto_balance_service.optimize(
            self.project_id, [], 12, max_passes=10, similarity_enabled=False,
            manual_session_id=session['id'], preserve_manual=False)
        self.assertNotIn(item_id, {row['item_id'] for row in rebalance_all['assignment_results']})

        unlocked = manual_balance_service.set_item_lock(
            self.project_id, session['id'], item_id, False, 101)
        self.assertFalse(unlocked['locked'])
        moved = manual_balance_service.move_items(
            self.project_id, session['id'], [item_id], 102,
            {item_id: plans[1]})
        self.assertEqual(moved['moved'], 1)

    def test_previous_automatic_items_are_reoptimized_on_next_run(self):
        self.add_family('URRST2FIX', 1, [(1, 2, 1)])
        plans, item_ids = self.add_family(
            'URRST2RUN', 4,
            [(10, 8, 1), (20, 8, 1), (30, 8, 1), (40, 8, 1)])
        session = manual_balance_service.start_session(self.project_id, 'zero', 12)
        conn = database.get_db_connection()
        try:
            conn.execute("""UPDATE manual_balance_assignments
                SET target_plan_id=?,balance_state='AUTOMATIC',source='automatic'
                WHERE session_id=? AND balance_state='PENDING'""", (plans[0], session['id']))
            conn.commit()
        finally:
            conn.close()

        result = auto_balance_service.optimize(
            self.project_id, [], 12, max_passes=20, similarity_enabled=False,
            distribution_strategy='horizontal', geography_mode='off',
            manual_session_id=session['id'], preserve_manual=True)
        self.assertEqual(
            {row['item_id'] for row in result['assignment_results']}, set(item_ids))
        self.assertLess(result['after_gap'], result['before_gap'])
        self.assertGreater(result['items_reassigned'], 0)

    def test_automatic_never_moves_item_outside_original_prefix9_and_cycle(self):
        _, family_a_items = self.add_family(
            'URRST2STC', 3, [(10, 12, 1), (20, 1, 1)])
        self.add_family('URRST2STD', 3, [(30, 1, 2)])

        result = auto_balance_service.optimize(
            self.project_id, [], 12, max_passes=25, similarity_enabled=False,
            distribution_strategy='horizontal', geography_mode='off')
        assignment = {row['item_id']: row['plan_id'] for row in result['assignment_results']}
        conn = database.get_db_connection()
        try:
            for item_id in family_a_items:
                target = conn.execute('SELECT legacy_code,cycle FROM plans WHERE id=?',
                                      (assignment[item_id],)).fetchone()
                self.assertEqual(auto_balance_service.get_plan_prefix9(target['legacy_code']), 'URRST2STC')
                self.assertEqual(target['cycle'], 3)
        finally:
            conn.close()

    def test_manual_cross_family_requires_warning_and_auto_refuses_to_preserve_it(self):
        _, family_a_items = self.add_family('URRST2STC', 2, [(10, 4, 1)])
        family_b_plans, _ = self.add_family('URRST2STD', 2, [(20, 2, 1)])
        session = manual_balance_service.start_session(self.project_id, 'zero', 12)
        target_ids = {family_a_items[0]: family_b_plans[0]}

        with self.assertRaisesRegex(ValueError, 'FAMILY_MISMATCH_CONFIRMATION_REQUIRED'):
            manual_balance_service.move_items(
                self.project_id, session['id'], family_a_items, 101, target_ids)
        moved = manual_balance_service.move_items(
            self.project_id, session['id'], family_a_items, 101, target_ids,
            allow_family_mismatch=True)
        self.assertTrue(moved['warnings'])

        with self.assertRaisesRegex(ValueError, 'fora da família original'):
            auto_balance_service.optimize(
                self.project_id, [], 12, max_passes=5, similarity_enabled=False,
                manual_session_id=session['id'], preserve_manual=True)

        rebalanced = auto_balance_service.optimize(
            self.project_id, [], 12, max_passes=5, similarity_enabled=False,
            manual_session_id=session['id'], preserve_manual=False)
        assignment = {row['item_id']: row['plan_id'] for row in rebalanced['assignment_results']}
        conn = database.get_db_connection()
        try:
            target = conn.execute('SELECT legacy_code FROM plans WHERE id=?',
                                  (assignment[family_a_items[0]],)).fetchone()
            self.assertEqual(auto_balance_service.get_plan_prefix9(target['legacy_code']), 'URRST2STC')
        finally:
            conn.close()

    def test_manual_move_blocks_saved_separate_rule(self):
        _, left = self.add_family('URRST2SEP', 2, [(10, 2, 1)])
        _, right = self.add_family('URRST2OUT', 2, [(20, 2, 2)])
        auto_balance_service.save_rules(self.project_id, [{
            'name': 'Acessos incompatíveis', 'type': 'separate',
            'enforcement': 'mandatory', 'item_ids': [left[0], right[0]]
        }])
        session = manual_balance_service.start_session(self.project_id, 'zero', 12)
        manual_balance_service.move_items(self.project_id, session['id'], left, 101)
        with self.assertRaisesRegex(ValueError, 'Acessos incompatíveis'):
            manual_balance_service.move_items(self.project_id, session['id'], right, 101)

    def test_vertical_strategy_fills_stops_in_identifier_order(self):
        _, item_ids = self.add_family(
            'URRST2VER', 12,
            [(10, 1, 1), (20, 1, 1), (30, 1, 1), (40, 1, 1)])
        result = auto_balance_service.optimize(
            self.project_id, [], 12, max_passes=1, similarity_enabled=False,
            distribution_strategy='vertical', vertical_tolerance=0)
        self.assertEqual(result['distribution_strategy'], 'vertical')
        self.assertEqual(result['vertical_target_hh'], 0.3)
        self.assertEqual(result['stops_after'][:4], [1.0, 1.0, 1.0, 1.0])
        self.assertEqual(result['stops_after'][4:], [0.0] * 8)
        assigned = {row['item_id']: row['plan_id'] for row in result['assignment_results']}
        conn = database.get_db_connection()
        try:
            references = [conn.execute('SELECT reference_counter FROM plans WHERE id=?',
                                       (assigned[item_id],)).fetchone()[0] for item_id in item_ids]
        finally:
            conn.close()
        self.assertEqual(references, [101, 102, 103, 104])


if __name__ == '__main__':
    unittest.main()
