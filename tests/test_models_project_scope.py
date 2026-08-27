import os
import tempfile
import unittest

from core import database, migrations, models


class TestModelsProjectScope(unittest.TestCase):
    """Regression tests for read-only plan listing and project-scoped bulk writes."""

    def setUp(self):
        self._old_db_path = database.DB_PATH
        self._old_migrations_run = database._migrations_run
        self._temp_dir = tempfile.TemporaryDirectory()
        database.DB_PATH = os.path.join(self._temp_dir.name, "models-project-scope.db")
        database._migrations_run = False

        conn = database.get_db_connection()
        migrations.run_migrations(conn)
        conn.close()

        self.project_a = self._create_project("Projeto A")
        self.project_b = self._create_project("Projeto B")

        self.plan_a = self._create_plan(
            self.project_a, "PLAN-A", "PLANO DO PROJETO A", start_stop=1
        )
        self.plan_b = self._create_plan(
            self.project_b, "PLAN-B", "PLANO DO PROJETO B", start_stop=2
        )
        self.item_a = self._create_item(
            self.project_a, self.plan_a, "ITEM-A", "CT-A"
        )
        self.item_b = self._create_item(
            self.project_b, self.plan_b, "ITEM-B", "CT-B"
        )

    def tearDown(self):
        database.DB_PATH = self._old_db_path
        database._migrations_run = self._old_migrations_run
        self._temp_dir.cleanup()

    @staticmethod
    def _create_project(name):
        return models.create_project(
            name=name,
            description=f"Descrição de {name}",
            area="Área de teste",
            current_counter=106,
            default_horizon=12,
            utilization_factor=1.0,
        )

    @staticmethod
    def _create_plan(project_id, code, description, start_stop):
        return models.create_plan(
            project_id=project_id,
            legacy_code=code,
            description=description,
            cycle=6,
            unit="PRD",
            cycle_text="6 PARADAS",
            opening_horizon=35.0,
            reference_counter=106 + start_stop,
            start_stop=start_stop,
        )

    @staticmethod
    def _create_item(project_id, plan_id, identifier, work_center):
        return models.create_item(
            project_id=project_id,
            legacy_identifier=identifier,
            plan_id=plan_id,
            object_type="EQUIPAMENTO",
            object_code=f"OBJ-{identifier}",
            gpm="042",
            work_center=work_center,
            condition_code="A",
            priority=1,
            legacy_start=106,
            description=f"Item {identifier}",
            duration_hours=2.0,
            headcount=1,
        )

    @staticmethod
    def _row(table, record_id):
        conn = database.get_db_connection()
        try:
            row = conn.execute(
                f"SELECT * FROM {table} WHERE id = ?", (record_id,)
            ).fetchone()
            return dict(row)
        finally:
            conn.close()

    def test_list_plans_does_not_autofill_or_write_plan(self):
        autofill_candidate = self._create_plan(
            self.project_a,
            "PLAN-6P2",
            "REP PREVENTIVA MANUT SIST-C 6P2",
            start_stop=0,
        )
        conn = database.get_db_connection()
        try:
            conn.execute(
                """
                UPDATE plans
                   SET phase = 0,
                       reference_counter = 321,
                       cycle_text = 'VALOR ORIGINAL'
                 WHERE id = ?
                """,
                (autofill_candidate,),
            )
            conn.commit()
        finally:
            conn.close()

        before = self._row("plans", autofill_candidate)
        listed = models.list_plans(self.project_a, limit=100)
        after = self._row("plans", autofill_candidate)

        self.assertIn(autofill_candidate, [plan["id"] for plan in listed])
        self.assertEqual(after, before)
        listed_candidate = next(
            plan for plan in listed if plan["id"] == autofill_candidate
        )
        self.assertEqual(listed_candidate["phase"], 0)
        self.assertEqual(listed_candidate["reference_counter"], 321)
        self.assertEqual(listed_candidate["cycle_text"], "VALOR ORIGINAL")

    def test_bulk_update_items_ignores_ids_from_another_project(self):
        updated = models.bulk_update_items(
            self.project_a,
            [self.item_a, self.item_b],
            {"work_center": "CT-ALTERADO", "priority": 7},
        )

        item_a = self._row("maintenance_items", self.item_a)
        item_b = self._row("maintenance_items", self.item_b)
        self.assertEqual(updated, 1)
        self.assertEqual(item_a["work_center"], "CT-ALTERADO")
        self.assertEqual(item_a["priority"], 7)
        self.assertEqual(item_b["work_center"], "CT-B")
        self.assertEqual(item_b["priority"], 1)

    def test_bulk_update_plans_ignores_ids_from_another_project(self):
        updated = models.bulk_update_plans(
            self.project_a,
            [self.plan_a, self.plan_b],
            {"cycle_text": "ALTERADO", "phase": 9},
        )

        plan_a = self._row("plans", self.plan_a)
        plan_b = self._row("plans", self.plan_b)
        self.assertEqual(updated, 1)
        self.assertEqual(plan_a["cycle_text"], "ALTERADO")
        self.assertEqual(plan_a["phase"], 9)
        self.assertEqual(plan_b["cycle_text"], "6 PARADAS")
        self.assertEqual(plan_b["phase"], 2)

    def test_bulk_assign_plan_ignores_item_ids_from_another_project(self):
        replacement_plan_a = self._create_plan(
            self.project_a,
            "PLAN-A-DESTINO",
            "PLANO DE DESTINO DO PROJETO A",
            start_stop=3,
        )

        updated = models.bulk_assign_plan(
            self.project_a,
            [self.item_a, self.item_b],
            replacement_plan_a,
        )

        item_a = self._row("maintenance_items", self.item_a)
        item_b = self._row("maintenance_items", self.item_b)
        self.assertEqual(updated, 1)
        self.assertEqual(item_a["plan_id"], replacement_plan_a)
        self.assertEqual(item_b["plan_id"], self.plan_b)


if __name__ == "__main__":
    unittest.main()
