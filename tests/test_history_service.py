import os
import sqlite3
import tempfile
import unittest

from core import database, history_service, migrations


class TestProjectHistoryService(unittest.TestCase):
    def setUp(self):
        fd, self.db_path = tempfile.mkstemp(prefix="pm13_history_", suffix=".db")
        os.close(fd)
        database.DB_PATH = self.db_path

        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        migrations.run_migrations(conn)
        self.project_id = self._seed_project(conn, "Projeto Histórico")
        conn.commit()
        conn.close()

    def tearDown(self):
        try:
            os.remove(self.db_path)
        except FileNotFoundError:
            pass

    def _seed_project(self, conn, name):
        cursor = conn.execute(
            """INSERT INTO projects
               (name, description, area, current_counter, default_horizon,
                utilization_factor, status)
               VALUES (?, 'Original', 'MS2', 106, 12, 1.0, 'ACTIVE')""",
            (name,),
        )
        project_id = cursor.lastrowid
        conn.execute(
            "INSERT INTO project_settings(project_id, code_pattern) VALUES (?, 'ORIGINAL-*')",
            (project_id,),
        )
        conn.execute(
            """INSERT INTO shifts(project_id, name, sequence, duration_hours, active)
               VALUES (?, 'Turno 1', 1, 10.5, 1)""",
            (project_id,),
        )
        conn.execute(
            """INSERT INTO cycle_catalog
               (project_id, cycle, unit, cycle_text, opening_horizon, active)
               VALUES (?, 2, 'PRD', '2 P', 12, 1)""",
            (project_id,),
        )
        team_id = conn.execute(
            """INSERT INTO work_teams
               (project_id, name, num_shifts, shift_hours, headcount_per_shift,
                tool_time_percent, stop_days)
               VALUES (?, 'Equipe A', 1, 9, 2, 90, 1)""",
            (project_id,),
        ).lastrowid
        plan_id = conn.execute(
            """INSERT INTO plans
               (project_id, legacy_code, description, character_count, cycle,
                unit, cycle_text, opening_horizon, reference_counter, status)
               VALUES (?, 'PLAN-01', 'Plano original', 14, 2, 'PRD', '2 P',
                       12, 108, 'ACTIVE')""",
            (project_id,),
        ).lastrowid
        item_id = conn.execute(
            """INSERT INTO maintenance_items
               (project_id, plan_id, team_id, legacy_identifier, object_type,
                object_code, gpm, work_center, condition_code, priority,
                description, character_count, duration_hours, hh, status)
               VALUES (?, ?, ?, 'ITEM-01', 'EQUIPAMENTO', 'EQ-01', '042',
                       'MEC01', 'A', 1, 'Item original', 13, 2, 4, 'ACTIVE')""",
            (project_id, plan_id, team_id),
        ).lastrowid
        operation_id = conn.execute(
            """INSERT INTO item_operations
               (project_id, item_id, operation_code, suboperation_code,
                short_text, unit, headcount, hours, status)
               VALUES (?, ?, '0010', '', 'Operação original', 'H', 2, 2,
                       'ACTIVE')""",
            (project_id, item_id),
        ).lastrowid
        conn.execute(
            """INSERT INTO operation_long_texts
               (project_id, operation_id, line_sequence, text)
               VALUES (?, ?, 1, 'Texto original')""",
            (project_id, operation_id),
        )
        conn.execute(
            """INSERT INTO auto_balance_rules
               (project_id, name, rule_type, item_ids_json, active)
               VALUES (?, 'Regra A', 'together', ?, 1)""",
            (project_id, f"[{item_id}]"),
        )
        return project_id

    def _one(self, sql, params=()):
        conn = database.get_db_connection()
        try:
            row = conn.execute(sql, params).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def _count(self, table):
        return self._one(
            f"SELECT COUNT(*) AS amount FROM {table} WHERE project_id=?",
            (self.project_id,),
        )["amount"]

    def test_deep_graph_is_restored_by_undo_and_redo(self):
        original_ids = {
            "plan": self._one(
                "SELECT id FROM plans WHERE project_id=?", (self.project_id,)
            )["id"],
            "item": self._one(
                "SELECT id FROM maintenance_items WHERE project_id=?",
                (self.project_id,),
            )["id"],
            "operation": self._one(
                "SELECT id FROM item_operations WHERE project_id=?",
                (self.project_id,),
            )["id"],
            "text": self._one(
                "SELECT id FROM operation_long_texts WHERE project_id=?",
                (self.project_id,),
            )["id"],
        }

        def remove_graph_and_edit_configuration(conn):
            conn.execute(
                "DELETE FROM maintenance_items WHERE project_id=?",
                (self.project_id,),
            )
            conn.execute("DELETE FROM plans WHERE project_id=?", (self.project_id,))
            conn.execute(
                "UPDATE work_teams SET name='Equipe alterada' WHERE project_id=?",
                (self.project_id,),
            )
            conn.execute(
                "UPDATE project_settings SET code_pattern='NOVO-*' WHERE project_id=?",
                (self.project_id,),
            )
            conn.execute(
                "UPDATE projects SET current_counter=200 WHERE id=?",
                (self.project_id,),
            )

        history_service.run_project_change(
            self.project_id,
            "Excluir estrutura para teste",
            remove_graph_and_edit_configuration,
        )
        self.assertEqual(self._count("plans"), 0)
        self.assertEqual(self._count("maintenance_items"), 0)
        self.assertEqual(self._count("item_operations"), 0)
        self.assertEqual(self._count("operation_long_texts"), 0)

        undone = history_service.undo(self.project_id)
        self.assertEqual(undone["action"], "Excluir estrutura para teste")
        for table in (
            "plans",
            "maintenance_items",
            "item_operations",
            "operation_long_texts",
            "work_teams",
            "project_settings",
            "shifts",
            "cycle_catalog",
            "auto_balance_rules",
        ):
            self.assertEqual(self._count(table), 1, table)
        self.assertEqual(
            self._one("SELECT id FROM plans WHERE project_id=?", (self.project_id,))["id"],
            original_ids["plan"],
        )
        self.assertEqual(
            self._one(
                "SELECT id, plan_id, team_id FROM maintenance_items WHERE project_id=?",
                (self.project_id,),
            )["id"],
            original_ids["item"],
        )
        self.assertEqual(
            self._one(
                "SELECT id, item_id FROM item_operations WHERE project_id=?",
                (self.project_id,),
            )["id"],
            original_ids["operation"],
        )
        self.assertEqual(
            self._one(
                "SELECT id, operation_id, text FROM operation_long_texts WHERE project_id=?",
                (self.project_id,),
            )["id"],
            original_ids["text"],
        )
        self.assertEqual(
            self._one("SELECT current_counter FROM projects WHERE id=?", (self.project_id,))[
                "current_counter"
            ],
            106,
        )
        self.assertEqual(
            self._one(
                "SELECT code_pattern FROM project_settings WHERE project_id=?",
                (self.project_id,),
            )["code_pattern"],
            "ORIGINAL-*",
        )

        history_service.redo(self.project_id)
        self.assertEqual(self._count("plans"), 0)
        self.assertEqual(self._count("maintenance_items"), 0)
        self.assertEqual(
            self._one("SELECT current_counter FROM projects WHERE id=?", (self.project_id,))[
                "current_counter"
            ],
            200,
        )

    def test_cursor_order_and_new_change_clears_redo_branch(self):
        def set_description(value):
            return lambda conn: conn.execute(
                "UPDATE projects SET description=? WHERE id=?",
                (value, self.project_id),
            )

        history_service.run_project_change(
            self.project_id, "Descrição A", set_description("A")
        )
        history_service.run_project_change(
            self.project_id, "Descrição B", set_description("B")
        )
        history_service.undo(self.project_id)
        self.assertEqual(
            self._one("SELECT description FROM projects WHERE id=?", (self.project_id,))[
                "description"
            ],
            "A",
        )
        self.assertTrue(history_service.get_history_state(self.project_id)["can_redo"])

        history_service.run_project_change(
            self.project_id, "Descrição C", set_description("C")
        )
        state = history_service.get_history_state(self.project_id)
        self.assertFalse(state["can_redo"])
        self.assertEqual(state["undo_action"], "Descrição C")
        with self.assertRaises(history_service.NothingToRedo):
            history_service.redo(self.project_id)
        self.assertEqual(
            [entry["action"] for entry in history_service.list_history(self.project_id)],
            ["Descrição C", "Descrição A"],
        )

    def test_noop_does_not_create_history_or_clear_redo(self):
        history_service.run_project_change(
            self.project_id,
            "Alterar contador",
            lambda conn: conn.execute(
                "UPDATE projects SET current_counter=107 WHERE id=?",
                (self.project_id,),
            ),
        )
        history_service.undo(self.project_id)

        history_service.run_project_change(
            self.project_id,
            "Sem mudança",
            lambda conn: conn.execute("SELECT 1"),
        )
        self.assertEqual(len(history_service.list_history(self.project_id)), 1)
        self.assertTrue(history_service.get_history_state(self.project_id)["can_redo"])
        history_service.redo(self.project_id)
        self.assertEqual(
            self._one("SELECT current_counter FROM projects WHERE id=?", (self.project_id,))[
                "current_counter"
            ],
            107,
        )

    def test_history_limit_is_enforced_per_project(self):
        for counter in range(107, 113):
            history_service.run_project_change(
                self.project_id,
                f"Contador {counter}",
                lambda conn, value=counter: conn.execute(
                    "UPDATE projects SET current_counter=? WHERE id=?",
                    (value, self.project_id),
                ),
                history_limit=3,
            )
        self.assertEqual(len(history_service.list_history(self.project_id)), 3)
        self.assertEqual(
            [entry["action"] for entry in history_service.list_history(self.project_id)],
            ["Contador 112", "Contador 111", "Contador 110"],
        )

    def test_failed_mutation_rolls_back_data_and_history(self):
        def fail_after_write(conn):
            conn.execute(
                "UPDATE projects SET current_counter=999 WHERE id=?",
                (self.project_id,),
            )
            raise RuntimeError("falha simulada")

        with self.assertRaisesRegex(RuntimeError, "falha simulada"):
            history_service.run_project_change(
                self.project_id, "Alteração com falha", fail_after_write
            )
        self.assertEqual(
            self._one("SELECT current_counter FROM projects WHERE id=?", (self.project_id,))[
                "current_counter"
            ],
            106,
        )
        self.assertEqual(history_service.list_history(self.project_id), [])

    def test_external_checkpoint_wraps_self_committing_legacy_mutation(self):
        token = history_service.begin_external_change(self.project_id)
        legacy_conn = database.get_db_connection()
        try:
            legacy_conn.execute(
                "UPDATE projects SET current_counter=321 WHERE id=?",
                (self.project_id,),
            )
            legacy_conn.commit()
        finally:
            legacy_conn.close()
        history_id = history_service.finalize_external_change(
            token, "Alteração legada", {"route": "/teste"}
        )

        self.assertIsInstance(history_id, int)
        self.assertFalse(token.active)
        self.assertEqual(
            history_service.list_history(self.project_id)[0]["metadata"],
            {"route": "/teste"},
        )
        history_service.undo(self.project_id)
        self.assertEqual(
            self._one("SELECT current_counter FROM projects WHERE id=?", (self.project_id,))[
                "current_counter"
            ],
            106,
        )


if __name__ == "__main__":
    unittest.main()
