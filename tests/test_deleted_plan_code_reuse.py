import http.server
import json
import os
import socket
import sqlite3
import tempfile
import threading
import unittest
import urllib.error
import urllib.parse
import urllib.request

import app
from core import database, migrations, models


class DeletedPlanCodeTestCase(unittest.TestCase):
    """Shared isolated database helpers for the plan-code regression tests."""

    def setUp(self):
        self._old_db_path = database.DB_PATH
        self._old_migrations_run = database._migrations_run
        self._temp_dir = tempfile.TemporaryDirectory(prefix="pm13_plan_code_")
        database.DB_PATH = os.path.join(self._temp_dir.name, "plan-code.db")
        database._migrations_run = False

        conn = database.get_db_connection()
        migrations.run_migrations(conn)
        conn.close()

        self.project_id = models.create_project(
            name=f"Projeto {self.id()}",
            description="Regressao de codigo de plano excluido",
            area="TESTE",
            current_counter=100,
            default_horizon=12,
            utilization_factor=1.0,
        )

    def tearDown(self):
        database.DB_PATH = self._old_db_path
        database._migrations_run = self._old_migrations_run
        self._temp_dir.cleanup()

    def create_plan(self, code, description="Plano de teste"):
        return models.create_plan(
            project_id=self.project_id,
            legacy_code=code,
            description=description,
            cycle=2,
            unit="PRD",
            cycle_text="2P",
            opening_horizon=36.0,
            reference_counter=102,
            start_stop=2,
        )

    @staticmethod
    def raw_row(table, row_id):
        conn = database.get_db_connection()
        try:
            row = conn.execute(
                f'SELECT * FROM "{table}" WHERE id = ?', (row_id,)
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def assert_foreign_keys_valid(self):
        conn = database.get_db_connection()
        try:
            self.assertEqual(conn.execute("PRAGMA foreign_key_check").fetchall(), [])
        finally:
            conn.close()

    @staticmethod
    def plan_code_conflict_exceptions():
        """Allow the storage error or its domain-level translation at this layer."""
        domain_error = getattr(models, "PlanCodeConflict", None)
        if isinstance(domain_error, type) and issubclass(domain_error, Exception):
            return (domain_error, sqlite3.IntegrityError)
        return (sqlite3.IntegrityError,)


class TestDeletedPlanCodeModels(DeletedPlanCodeTestCase):
    def test_rename_to_deleted_code_keeps_tombstone_ids_and_item_link(self):
        deleted_plan_id = self.create_plan("PLAN-CODE-FREE", "Plano a excluir")
        target_plan_id = self.create_plan("PLAN-CODE-TARGET", "Plano a renomear")
        item_id = models.create_item(
            project_id=self.project_id,
            legacy_identifier="ITEM-CODE-REUSE",
            plan_id=deleted_plan_id,
            object_type="EQUIPAMENTO",
            object_code="EQ-CODE-REUSE",
            gpm="042",
            work_center="CT-01",
            condition_code="A",
            priority=1,
            legacy_start=100,
            description="Item que deve manter seu vinculo",
            duration_hours=2.0,
            headcount=1,
        )

        self.assertTrue(
            models.delete_plan(
                deleted_plan_id,
                item_action="transfer",
                target_plan_id=target_plan_id,
            )
        )
        self.assertTrue(
            models.update_plan(
                target_plan_id,
                "  plan-code-free  ",
                "Plano renomeado",
                2,
                "PRD",
                "2P",
                36.0,
                102,
                start_stop=2,
            )
        )

        tombstone = self.raw_row("plans", deleted_plan_id)
        renamed = self.raw_row("plans", target_plan_id)
        item = self.raw_row("maintenance_items", item_id)

        self.assertEqual(tombstone["id"], deleted_plan_id)
        self.assertEqual(tombstone["legacy_code"], "PLAN-CODE-FREE")
        self.assertIsNotNone(tombstone["deleted_at"])
        self.assertEqual(renamed["id"], target_plan_id)
        self.assertEqual(renamed["legacy_code"], "PLAN-CODE-FREE")
        self.assertIsNone(renamed["deleted_at"])
        self.assertEqual(item["id"], item_id)
        self.assertEqual(item["plan_id"], target_plan_id)
        self.assertEqual(models.get_item(item_id)["plan_code"], "PLAN-CODE-FREE")
        self.assert_foreign_keys_valid()

    def test_create_with_deleted_code_works_but_active_duplicate_does_not(self):
        deleted_plan_id = self.create_plan("PLAN-CODE-RECYCLED", "Plano antigo")
        self.assertTrue(models.delete_plan(deleted_plan_id))

        replacement_id = self.create_plan(
            "  plan-code-recycled  ", "Plano novo com codigo liberado"
        )
        self.assertNotEqual(replacement_id, deleted_plan_id)
        self.assertEqual(
            self.raw_row("plans", deleted_plan_id)["legacy_code"],
            "PLAN-CODE-RECYCLED",
        )
        self.assertEqual(models.get_plan(replacement_id)["legacy_code"], "PLAN-CODE-RECYCLED")

        with self.assertRaises(self.plan_code_conflict_exceptions()):
            self.create_plan("PLAN-CODE-RECYCLED", "Duplicata ativa")

        active = models.list_plans(
            self.project_id, {"search": "PLAN-CODE-RECYCLED"}, limit=100
        )
        self.assertEqual([plan["id"] for plan in active], [replacement_id])
        self.assert_foreign_keys_valid()


class TestDeletedPlanCodeHttp(DeletedPlanCodeTestCase):
    def setUp(self):
        super().setUp()
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.bind(("127.0.0.1", 0))
        self.port = sock.getsockname()[1]
        sock.close()
        self.server = http.server.ThreadingHTTPServer(
            ("127.0.0.1", self.port), app.PM13RequestHandler
        )
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        super().tearDown()

    def request(self, method, path, body=None, expected=200):
        data = json.dumps(body).encode("utf-8") if body is not None else None
        headers = {"Content-Type": "application/json"} if body is not None else {}
        request = urllib.request.Request(
            f"http://127.0.0.1:{self.port}{path}",
            data=data,
            headers=headers,
            method=method,
        )
        try:
            response = urllib.request.urlopen(request, timeout=10)
            payload = json.loads(response.read().decode("utf-8"))
            self.assertEqual(response.status, expected)
            return payload
        except urllib.error.HTTPError as exc:
            payload = json.loads(exc.read().decode("utf-8"))
            self.assertEqual(exc.code, expected, payload)
            return payload

    def plan_payload(self, code, description):
        return {
            "project_id": self.project_id,
            "legacy_code": code,
            "description": description,
            "cycle": 2,
            "unit": "PRD",
            "cycle_text": "2P",
            "opening_horizon": 36,
            "reference_counter": 102,
            "start_stop": 2,
        }

    def assert_clear_active_conflict(self, payload, active_id, code, description):
        self.assertEqual(payload.get("error_code"), "PLAN_CODE_CONFLICT")
        conflict = payload.get("conflict") or {}
        self.assertEqual(conflict.get("plan_id"), active_id)
        self.assertEqual(conflict.get("legacy_code"), code)
        self.assertEqual(conflict.get("description"), description)
        message = str(payload.get("error") or "")
        self.assertIn(code, message.upper())
        message_lower = message.lower()
        self.assertNotIn("unique", message_lower)
        self.assertNotIn("constraint", message_lower)
        self.assertNotIn("plans.", message_lower)

    def test_create_reuses_deleted_code_and_active_conflicts_return_409(self):
        original = self.request(
            "POST",
            "/api/plans",
            self.plan_payload("HTTP-CODE-REUSE", "Plano excluido"),
        )
        self.request("DELETE", f"/api/plans/{original['id']}")

        replacement_description = "Plano ativo substituto"
        replacement = self.request(
            "POST",
            "/api/plans",
            self.plan_payload("  http-code-reuse  ", replacement_description),
        )
        self.assertNotEqual(replacement["id"], original["id"])

        post_conflict = self.request(
            "POST",
            "/api/plans",
            self.plan_payload("HTTP-CODE-REUSE", "Duplicata por criacao"),
            expected=409,
        )
        self.assert_clear_active_conflict(
            post_conflict,
            replacement["id"],
            "HTTP-CODE-REUSE",
            replacement_description,
        )

        other = self.request(
            "POST",
            "/api/plans",
            self.plan_payload("HTTP-CODE-OTHER", "Outro plano ativo"),
        )
        put_conflict = self.request(
            "PUT",
            f"/api/plans/{other['id']}",
            {"legacy_code": " http-code-reuse "},
            expected=409,
        )
        self.assert_clear_active_conflict(
            put_conflict,
            replacement["id"],
            "HTTP-CODE-REUSE",
            replacement_description,
        )
        self.assertEqual(models.get_plan(other["id"])["legacy_code"], "HTTP-CODE-OTHER")

        tombstone = self.raw_row("plans", original["id"])
        self.assertEqual(tombstone["legacy_code"], "HTTP-CODE-REUSE")
        self.assertIsNotNone(tombstone["deleted_at"])
        self.assert_foreign_keys_valid()

    def test_deleted_code_rename_survives_undo_redo_with_stable_ids_and_links(self):
        source = self.request(
            "POST",
            "/api/plans",
            self.plan_payload("HTTP-CODE-SOURCE", "Plano origem"),
        )
        target = self.request(
            "POST",
            "/api/plans",
            self.plan_payload("HTTP-CODE-TARGET", "Plano destino"),
        )
        item_id = models.create_item(
            project_id=self.project_id,
            legacy_identifier="HTTP-ITEM-LINK",
            plan_id=source["id"],
            object_type="EQUIPAMENTO",
            object_code="EQ-HTTP-LINK",
            gpm="042",
            work_center="CT-HTTP",
            condition_code="A",
            priority=1,
            legacy_start=100,
            description="Item para testar historico",
            duration_hours=1.0,
            headcount=1,
        )

        query = urllib.parse.urlencode(
            {"item_action": "transfer", "target_plan_id": target["id"]}
        )
        self.request("DELETE", f"/api/plans/{source['id']}?{query}")
        self.request(
            "PUT",
            f"/api/plans/{target['id']}",
            {"legacy_code": "HTTP-CODE-SOURCE"},
        )
        self.assert_current_reused_state(source["id"], target["id"], item_id)

        # Undo rename: source remains deleted, target and link keep their IDs.
        self.request("POST", "/api/history/undo", {"project_id": self.project_id})
        self.assertIsNotNone(self.raw_row("plans", source["id"])["deleted_at"])
        self.assertEqual(models.get_plan(target["id"])["legacy_code"], "HTTP-CODE-TARGET")
        self.assertEqual(models.get_item(item_id)["plan_id"], target["id"])

        # Undo delete: the complete relationship graph returns to its old IDs.
        self.request("POST", "/api/history/undo", {"project_id": self.project_id})
        self.assertEqual(models.get_plan(source["id"])["legacy_code"], "HTTP-CODE-SOURCE")
        self.assertEqual(models.get_plan(target["id"])["legacy_code"], "HTTP-CODE-TARGET")
        self.assertEqual(models.get_item(item_id)["plan_id"], source["id"])

        self.request("POST", "/api/history/redo", {"project_id": self.project_id})
        self.assertIsNotNone(self.raw_row("plans", source["id"])["deleted_at"])
        self.assertEqual(models.get_item(item_id)["plan_id"], target["id"])

        self.request("POST", "/api/history/redo", {"project_id": self.project_id})
        self.assert_current_reused_state(source["id"], target["id"], item_id)
        self.assert_foreign_keys_valid()

    def assert_current_reused_state(self, source_id, target_id, item_id):
        source = self.raw_row("plans", source_id)
        target = self.raw_row("plans", target_id)
        item = self.raw_row("maintenance_items", item_id)
        self.assertEqual(source["legacy_code"], "HTTP-CODE-SOURCE")
        self.assertIsNotNone(source["deleted_at"])
        self.assertEqual(target["id"], target_id)
        self.assertEqual(target["legacy_code"], "HTTP-CODE-SOURCE")
        self.assertIsNone(target["deleted_at"])
        self.assertEqual(item["id"], item_id)
        self.assertEqual(item["plan_id"], target_id)


class TestDeletedPlanCodeLegacyMigration(unittest.TestCase):
    """Upgrade a real legacy UNIQUE table without losing IDs or foreign keys."""

    def setUp(self):
        self._old_db_path = database.DB_PATH
        self._old_migrations_run = database._migrations_run
        self._temp_dir = tempfile.TemporaryDirectory(prefix="pm13_plan_code_upgrade_")
        self.db_path = os.path.join(self._temp_dir.name, "legacy.db")
        database.DB_PATH = self.db_path
        database._migrations_run = False
        self._create_legacy_database()

    def tearDown(self):
        database.DB_PATH = self._old_db_path
        database._migrations_run = self._old_migrations_run
        self._temp_dir.cleanup()

    def _create_legacy_database(self):
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA foreign_keys = ON")
        conn.executescript(
            """
            CREATE TABLE projects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                description TEXT,
                area TEXT,
                current_counter INTEGER NOT NULL DEFAULT 0,
                default_horizon INTEGER NOT NULL DEFAULT 12,
                utilization_factor REAL NOT NULL DEFAULT 1.0,
                status TEXT NOT NULL DEFAULT 'ACTIVE',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                deleted_at DATETIME
            );
            CREATE TABLE plans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                legacy_code TEXT NOT NULL,
                description TEXT NOT NULL,
                character_count INTEGER NOT NULL,
                cycle INTEGER NOT NULL,
                unit TEXT NOT NULL,
                cycle_text TEXT NOT NULL,
                opening_horizon REAL NOT NULL,
                reference_counter INTEGER,
                phase INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'ACTIVE',
                notes TEXT,
                validation_status TEXT NOT NULL DEFAULT 'OK',
                validation_issues_json TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                deleted_at DATETIME,
                UNIQUE(project_id, legacy_code)
            );
            CREATE TABLE maintenance_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                plan_id INTEGER REFERENCES plans(id) ON DELETE SET NULL,
                team_id INTEGER,
                legacy_identifier TEXT NOT NULL,
                object_type TEXT NOT NULL DEFAULT 'EQUIPAMENTO',
                object_code TEXT NOT NULL,
                gpm TEXT NOT NULL,
                work_center TEXT NOT NULL,
                condition_code TEXT NOT NULL,
                priority INTEGER NOT NULL,
                legacy_start INTEGER,
                description TEXT NOT NULL,
                character_count INTEGER NOT NULL,
                duration_hours REAL NOT NULL,
                headcount INTEGER,
                hh REAL NOT NULL,
                order_type TEXT NOT NULL DEFAULT 'PM13',
                status TEXT NOT NULL DEFAULT 'ACTIVE',
                notes TEXT,
                validation_status TEXT NOT NULL DEFAULT 'OK',
                validation_issues_json TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                deleted_at DATETIME,
                UNIQUE(project_id, legacy_identifier)
            );
            INSERT INTO projects (
                id, name, description, area, current_counter,
                default_horizon, utilization_factor
            ) VALUES (41, 'Projeto legado', 'Antes da migracao', 'TESTE', 100, 12, 1.0);
            INSERT INTO plans (
                id, project_id, legacy_code, description, character_count,
                cycle, unit, cycle_text, opening_horizon, reference_counter,
                phase, status, deleted_at
            ) VALUES
                (101, 41, 'LEGACY-ACTIVE', 'Plano ativo', 11,
                 2, 'PRD', '2P', 36, 102, 2, 'ACTIVE', NULL),
                (102, 41, 'LEGACY-REUSABLE', 'Plano excluido', 14,
                 2, 'PRD', '2P', 36, 102, 2, 'ACTIVE', '2026-08-12T10:00:00');
            INSERT INTO maintenance_items (
                id, project_id, plan_id, legacy_identifier, object_type,
                object_code, gpm, work_center, condition_code, priority,
                legacy_start, description, character_count, duration_hours,
                headcount, hh
            ) VALUES (
                201, 41, 101, 'LEGACY-ITEM', 'EQUIPAMENTO', 'EQ-LEGACY',
                '042', 'CT-LEGACY', 'A', 1, 100, 'Item legado', 11, 2, 1, 2
            );
            """
        )
        conn.close()

    def test_upgrade_releases_deleted_code_and_preserves_graph_and_sequence(self):
        conn = database.get_db_connection()
        migrations.run_migrations(conn)
        conn.close()

        active_before = models.get_plan(101)
        item_before = models.get_item(201)
        self.assertEqual(active_before["legacy_code"], "LEGACY-ACTIVE")
        self.assertEqual(item_before["plan_id"], 101)

        replacement_id = models.create_plan(
            project_id=41,
            legacy_code="LEGACY-REUSABLE",
            description="Plano criado apos migracao",
            cycle=2,
            unit="PRD",
            cycle_text="2P",
            opening_horizon=36,
            reference_counter=102,
            start_stop=2,
        )
        self.assertGreater(replacement_id, 102)

        conn = database.get_db_connection()
        try:
            rows = conn.execute(
                """SELECT id, legacy_code, deleted_at FROM plans
                   WHERE project_id=41 AND legacy_code='LEGACY-REUSABLE'
                   ORDER BY id"""
            ).fetchall()
            self.assertEqual([row["id"] for row in rows], [102, replacement_id])
            self.assertIsNotNone(rows[0]["deleted_at"])
            self.assertIsNone(rows[1]["deleted_at"])
            self.assertEqual(
                conn.execute(
                    "SELECT plan_id FROM maintenance_items WHERE id=201"
                ).fetchone()["plan_id"],
                101,
            )
            self.assertEqual(conn.execute("PRAGMA foreign_key_check").fetchall(), [])
        finally:
            conn.close()

        domain_error = getattr(models, "PlanCodeConflict", None)
        expected_errors = (sqlite3.IntegrityError,)
        if isinstance(domain_error, type) and issubclass(domain_error, Exception):
            expected_errors = (domain_error, sqlite3.IntegrityError)
        with self.assertRaises(expected_errors):
            models.create_plan(
                project_id=41,
                legacy_code="LEGACY-REUSABLE",
                description="Duplicata ativa",
                cycle=2,
                unit="PRD",
                cycle_text="2P",
                opening_horizon=36,
                reference_counter=102,
                start_stop=2,
            )


if __name__ == "__main__":
    unittest.main()
