"""Transactional undo/redo history for project-scoped data.

The history is intentionally stored as full, compressed project snapshots.  The
PM13 data model is small enough for snapshots to be practical and, unlike
entity-specific inverse commands, a snapshot restores the complete relationship
graph (plans -> items -> operations -> long texts) without losing identifiers.

Callers should execute a user-visible mutation through :func:`run_project_change`
and use the connection passed to the mutator.  This keeps the data change and
its history entry in the same SQLite transaction::

    def change(conn):
        conn.execute("UPDATE plans SET description=? WHERE id=?", (text, plan_id))

    run_project_change(project_id, "Editar plano", change)

Undo and redo only move the history cursor and restore a stored snapshot; they
never create another history entry.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
import zlib
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

from core.database import get_db_connection


SNAPSHOT_VERSION = 1
DEFAULT_HISTORY_LIMIT = 50

# Tables are listed in parent-before-child insertion order.  Only project-owned
# business data belongs here.  Imports, audit_log and project_history are event
# logs and deliberately are not rewound.
PROJECT_TABLES: Tuple[str, ...] = (
    "shifts",
    "cycle_catalog",
    "work_teams",
    "project_settings",
    "plans",
    "maintenance_items",
    "item_priorimeter",
    "auto_balance_rules",
    "manual_balance_sessions",
    "manual_balance_assignments",
    "item_operations",
    "operation_long_texts",
)

# Explicit child-before-parent order avoids relying on deferred cascades while a
# snapshot is restored.
DELETE_ORDER: Tuple[str, ...] = (
    "operation_long_texts",
    "item_operations",
    "manual_balance_assignments",
    "manual_balance_sessions",
    "auto_balance_rules",
    "item_priorimeter",
    "maintenance_items",
    "plans",
    "project_settings",
    "cycle_catalog",
    "shifts",
    "work_teams",
)


class HistoryError(RuntimeError):
    """Base exception for history operations."""


class HistoryProjectNotFound(HistoryError):
    """Raised when the requested project does not exist."""


class NothingToUndo(HistoryError):
    """Raised when the project has no applied action to undo."""


class NothingToRedo(HistoryError):
    """Raised when the project has no undone action to redo."""


_project_locks_guard = threading.Lock()
_project_locks: Dict[int, Any] = {}


def _get_project_lock(project_id: int):
    with _project_locks_guard:
        return _project_locks.setdefault(int(project_id), threading.RLock())


@dataclass
class ExternalChangeToken:
    """Opaque checkpoint held while a legacy, self-committing mutation runs."""

    project_id: int
    before: Dict[str, Any] = field(repr=False)
    _lock: Any = field(repr=False)
    active: bool = True
    history_id: Optional[int] = None


def ensure_history_schema(conn: sqlite3.Connection) -> None:
    """Create the persistent history table and indexes if necessary.

    The function does not commit.  It is therefore safe both during startup
    migrations and inside a business transaction.
    """

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS project_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            action TEXT NOT NULL,
            metadata_json TEXT,
            before_snapshot BLOB NOT NULL,
            after_snapshot BLOB NOT NULL,
            before_hash TEXT NOT NULL,
            after_hash TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'APPLIED'
                CHECK(status IN ('APPLIED', 'UNDONE')),
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            undone_at DATETIME,
            redone_at DATETIME
        )
        """
    )
    conn.execute(
        """CREATE INDEX IF NOT EXISTS idx_project_history_cursor
           ON project_history(project_id, status, id)"""
    )


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone() is not None


def _rows_as_dicts(cursor: sqlite3.Cursor) -> List[Dict[str, Any]]:
    columns = [item[0] for item in cursor.description or ()]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def capture_project_snapshot(
    conn: sqlite3.Connection, project_id: int
) -> Dict[str, Any]:
    """Capture all undoable data for ``project_id`` using ``conn``.

    Rows are ordered by primary key so serialized snapshots are deterministic.
    Soft-deleted rows are included because undo must faithfully restore state.
    """

    project_cursor = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,))
    projects = _rows_as_dicts(project_cursor)
    if not projects:
        raise HistoryProjectNotFound(f"Projeto {project_id} não encontrado.")

    tables: Dict[str, List[Dict[str, Any]]] = {"projects": projects}
    for table in PROJECT_TABLES:
        if not _table_exists(conn, table):
            tables[table] = []
            continue
        cursor = conn.execute(
            f'SELECT * FROM "{table}" WHERE project_id = ? ORDER BY id',
            (project_id,),
        )
        tables[table] = _rows_as_dicts(cursor)

    return {
        "version": SNAPSHOT_VERSION,
        "project_id": int(project_id),
        "tables": tables,
    }


def _snapshot_bytes(snapshot: Dict[str, Any]) -> bytes:
    raw = json.dumps(
        snapshot,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return zlib.compress(raw, level=6)


def _snapshot_hash(snapshot_blob: bytes) -> str:
    # Hash the canonical uncompressed representation indirectly.  zlib output is
    # deterministic for the same input and Python/zlib settings used here.
    return hashlib.sha256(snapshot_blob).hexdigest()


def _decode_snapshot(blob: bytes) -> Dict[str, Any]:
    try:
        value = json.loads(zlib.decompress(blob).decode("utf-8"))
    except (TypeError, ValueError, zlib.error, UnicodeDecodeError) as exc:
        raise HistoryError("Snapshot do histórico está corrompido.") from exc
    if value.get("version") != SNAPSHOT_VERSION or not isinstance(value.get("tables"), dict):
        raise HistoryError("Versão de snapshot do histórico não suportada.")
    return value


def _table_columns(conn: sqlite3.Connection, table: str) -> List[str]:
    return [row[1] for row in conn.execute(f'PRAGMA table_info("{table}")').fetchall()]


def _validated_rows(
    snapshot: Dict[str, Any], table: str, project_id: int
) -> Iterable[Dict[str, Any]]:
    rows = snapshot.get("tables", {}).get(table, [])
    if not isinstance(rows, list):
        raise HistoryError(f"Snapshot inválido para a tabela {table}.")
    for row in rows:
        if not isinstance(row, dict):
            raise HistoryError(f"Linha inválida no snapshot da tabela {table}.")
        expected = row.get("id") if table == "projects" else row.get("project_id")
        if int(expected) != int(project_id):
            raise HistoryError("Snapshot pertence a outro projeto.")
        yield row


def _insert_snapshot_rows(
    conn: sqlite3.Connection,
    table: str,
    rows: Iterable[Dict[str, Any]],
) -> None:
    available = set(_table_columns(conn, table))
    for row in rows:
        # Intersection makes old snapshots forward-compatible with additive
        # schema migrations.  Required new fields must have a database default.
        columns = [column for column in row.keys() if column in available]
        if not columns:
            raise HistoryError(f"Snapshot sem colunas válidas para {table}.")
        names = ", ".join(f'"{column}"' for column in columns)
        placeholders = ", ".join("?" for _ in columns)
        conn.execute(
            f'INSERT INTO "{table}" ({names}) VALUES ({placeholders})',
            tuple(row[column] for column in columns),
        )


def validate_project_foreign_keys(conn: sqlite3.Connection, project_id: int) -> None:
    """Fail a restore if SQLite or cross-project relationships are invalid."""

    project_id = int(project_id)
    project_tables = {"projects", *PROJECT_TABLES, "project_history"}
    relevant = []
    for violation in conn.execute("PRAGMA foreign_key_check").fetchall():
        table, rowid, parent, fk_index = violation[:4]
        if table not in project_tables or not _table_exists(conn, table):
            continue
        columns = set(_table_columns(conn, table))
        owner_column = "id" if table == "projects" else "project_id"
        if owner_column not in columns:
            continue
        owner = conn.execute(
            f'SELECT "{owner_column}" FROM "{table}" WHERE rowid=?', (rowid,)
        ).fetchone()
        if owner is not None and int(owner[0]) == project_id:
            relevant.append((table, rowid, parent, fk_index))

    semantic_checks = (
        (
            "maintenance_items.plan_id",
            """SELECT 1 FROM maintenance_items child
               JOIN plans parent ON parent.id=child.plan_id
               WHERE child.project_id=? AND child.plan_id IS NOT NULL
                 AND parent.project_id<>child.project_id LIMIT 1""",
        ),
        (
            "maintenance_items.team_id",
            """SELECT 1 FROM maintenance_items child
               JOIN work_teams parent ON parent.id=child.team_id
               WHERE child.project_id=? AND child.team_id IS NOT NULL
                 AND parent.project_id<>child.project_id LIMIT 1""",
        ),
        (
            "item_operations.item_id",
            """SELECT 1 FROM item_operations child
               JOIN maintenance_items parent ON parent.id=child.item_id
               WHERE child.project_id=? AND parent.project_id<>child.project_id LIMIT 1""",
        ),
        (
            "operation_long_texts.operation_id",
            """SELECT 1 FROM operation_long_texts child
               JOIN item_operations parent ON parent.id=child.operation_id
               WHERE child.project_id=? AND parent.project_id<>child.project_id LIMIT 1""",
        ),
    )
    invalid_relations = []
    for label, sql in semantic_checks:
        if conn.execute(sql, (project_id,)).fetchone() is not None:
            invalid_relations.append(label)

    if relevant or invalid_relations:
        details = ", ".join(invalid_relations) or repr(relevant[:3])
        raise HistoryError(f"Restauração violaria vínculos do projeto: {details}")


def restore_project_snapshot(
    conn: sqlite3.Connection, project_id: int, snapshot: Dict[str, Any]
) -> None:
    """Replace current project data with ``snapshot`` without committing."""

    if int(snapshot.get("project_id", -1)) != int(project_id):
        raise HistoryError("Snapshot pertence a outro projeto.")

    project_rows = list(_validated_rows(snapshot, "projects", project_id))
    if len(project_rows) != 1:
        raise HistoryError("Snapshot não contém exatamente um projeto.")
    if conn.execute("SELECT 1 FROM projects WHERE id = ?", (project_id,)).fetchone() is None:
        # History rows use ON DELETE CASCADE, so this normally only happens when
        # restore_project_snapshot is used directly with a detached snapshot.
        _insert_snapshot_rows(conn, "projects", project_rows)
    else:
        available = set(_table_columns(conn, "projects"))
        row = project_rows[0]
        columns = [column for column in row if column != "id" and column in available]
        assignments = ", ".join(f'"{column}" = ?' for column in columns)
        conn.execute(
            f'UPDATE projects SET {assignments} WHERE id = ?',
            tuple(row[column] for column in columns) + (project_id,),
        )

    # Defer checks until the caller commits while still inserting in dependency
    # order.  This also protects future additive cross-references.
    conn.execute("PRAGMA defer_foreign_keys = ON")
    for table in DELETE_ORDER:
        if _table_exists(conn, table):
            conn.execute(f'DELETE FROM "{table}" WHERE project_id = ?', (project_id,))

    for table in PROJECT_TABLES:
        if _table_exists(conn, table):
            rows = _validated_rows(snapshot, table, project_id)
            _insert_snapshot_rows(conn, table, rows)

    validate_project_foreign_keys(conn, project_id)


def record_project_change(
    conn: sqlite3.Connection,
    project_id: int,
    action: str,
    before: Dict[str, Any],
    after: Dict[str, Any],
    metadata: Optional[Dict[str, Any]] = None,
    history_limit: int = DEFAULT_HISTORY_LIMIT,
) -> Optional[int]:
    """Record one already-executed change using the caller's transaction.

    Returns the history id, or ``None`` for a no-op.  A real new action removes
    the redo branch before being inserted.
    """

    ensure_history_schema(conn)
    before_blob = _snapshot_bytes(before)
    after_blob = _snapshot_bytes(after)
    before_hash = _snapshot_hash(before_blob)
    after_hash = _snapshot_hash(after_blob)
    if before_hash == after_hash:
        return None

    if not str(action or "").strip():
        raise ValueError("A descrição da alteração é obrigatória.")

    # Branch semantics: after undo, any normal alteration invalidates redo.
    conn.execute(
        "DELETE FROM project_history WHERE project_id = ? AND status = 'UNDONE'",
        (project_id,),
    )
    cursor = conn.execute(
        """
        INSERT INTO project_history (
            project_id, action, metadata_json, before_snapshot, after_snapshot,
            before_hash, after_hash, status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, 'APPLIED')
        """,
        (
            project_id,
            str(action).strip(),
            json.dumps(metadata, ensure_ascii=False, sort_keys=True)
            if metadata is not None
            else None,
            before_blob,
            after_blob,
            before_hash,
            after_hash,
        ),
    )
    history_id = int(cursor.lastrowid)

    limit = max(1, int(history_limit or DEFAULT_HISTORY_LIMIT))
    conn.execute(
        """
        DELETE FROM project_history
        WHERE project_id = ?
          AND id NOT IN (
              SELECT id FROM project_history
              WHERE project_id = ?
              ORDER BY id DESC LIMIT ?
          )
        """,
        (project_id, project_id, limit),
    )
    return history_id


def run_project_change(
    project_id: int,
    action: str,
    mutator: Callable[[sqlite3.Connection], Any],
    metadata: Optional[Dict[str, Any]] = None,
    history_limit: int = DEFAULT_HISTORY_LIMIT,
    conn: Optional[sqlite3.Connection] = None,
) -> Any:
    """Run ``mutator`` and save one undo step in the same transaction.

    When a connection is supplied, this function starts and owns a transaction
    only if the connection was not already in one.  The mutator must not commit
    or close the connection.
    """

    project_lock = _get_project_lock(project_id)
    project_lock.acquire()
    owns_connection = conn is None
    connection = None
    started_transaction = False
    try:
        connection = conn or get_db_connection()
        started_transaction = not connection.in_transaction
        if started_transaction:
            connection.execute("BEGIN IMMEDIATE")
        ensure_history_schema(connection)
        before = capture_project_snapshot(connection, project_id)
        result = mutator(connection)
        after = capture_project_snapshot(connection, project_id)
        record_project_change(
            connection,
            project_id,
            action,
            before,
            after,
            metadata=metadata,
            history_limit=history_limit,
        )
        if started_transaction:
            connection.commit()
        return result
    except Exception:
        if connection is not None and started_transaction and connection.in_transaction:
            connection.rollback()
        raise
    finally:
        if owns_connection and connection is not None:
            connection.close()
        project_lock.release()


def begin_external_change(project_id: int) -> ExternalChangeToken:
    """Capture a checkpoint for a legacy mutation that opens its own connection.

    A process-local lock is held until :func:`finalize_external_change` or
    :func:`abort_external_change` is called, so wrapped HTTP mutations for the
    same project cannot interleave.  Because the legacy mutation commits through
    another SQLite connection, its data commit and the subsequent history insert
    cannot be one database transaction.  New code should prefer
    :func:`run_project_change`; this adapter exists to make current model methods
    undoable without a risky all-at-once refactor.
    """

    project_id = int(project_id)
    lock = _get_project_lock(project_id)
    lock.acquire()
    connection = None
    try:
        connection = get_db_connection()
        before = capture_project_snapshot(connection, project_id)
        return ExternalChangeToken(project_id=project_id, before=before, _lock=lock)
    except Exception:
        lock.release()
        raise
    finally:
        if connection is not None:
            connection.close()


def finalize_external_change(
    token: ExternalChangeToken,
    action: str,
    metadata: Optional[Dict[str, Any]] = None,
    history_limit: int = DEFAULT_HISTORY_LIMIT,
) -> Optional[int]:
    """Capture post-mutation state and persist an external mutation's history."""

    if not isinstance(token, ExternalChangeToken) or not token.active:
        raise HistoryError("Checkpoint externo inválido ou já finalizado.")

    connection = None
    try:
        connection = get_db_connection()
        connection.execute("BEGIN IMMEDIATE")
        after = capture_project_snapshot(connection, token.project_id)
        token.history_id = record_project_change(
            connection,
            token.project_id,
            action,
            token.before,
            after,
            metadata=metadata,
            history_limit=history_limit,
        )
        connection.commit()
        return token.history_id
    except Exception:
        if connection is not None and connection.in_transaction:
            connection.rollback()
        raise
    finally:
        if connection is not None:
            connection.close()
        token.active = False
        token._lock.release()


def abort_external_change(token: ExternalChangeToken) -> None:
    """Release a checkpoint after a mutation known to have rolled back."""

    if not isinstance(token, ExternalChangeToken) or not token.active:
        return
    token.active = False
    token._lock.release()


@contextmanager
def external_project_change(
    project_id: int,
    action: str,
    metadata: Optional[Dict[str, Any]] = None,
    history_limit: int = DEFAULT_HISTORY_LIMIT,
):
    """Context-manager adapter around current self-committing model methods.

    Even when the wrapped call raises, finalization checks whether it committed a
    partial change and records that state if necessary.  The original exception
    is then propagated.
    """

    token = begin_external_change(project_id)
    try:
        yield token
    except Exception:
        finalize_external_change(
            token,
            action,
            metadata=metadata,
            history_limit=history_limit,
        )
        raise
    else:
        finalize_external_change(
            token,
            action,
            metadata=metadata,
            history_limit=history_limit,
        )


def _history_entry(row: sqlite3.Row) -> Dict[str, Any]:
    metadata = json.loads(row["metadata_json"]) if row["metadata_json"] else None
    return {
        "id": row["id"],
        "project_id": row["project_id"],
        "action": row["action"],
        "metadata": metadata,
        "status": row["status"],
        "created_at": row["created_at"],
        "undone_at": row["undone_at"],
        "redone_at": row["redone_at"],
    }


def _move_cursor(project_id: int, direction: str) -> Dict[str, Any]:
    project_id = int(project_id)
    project_lock = _get_project_lock(project_id)
    project_lock.acquire()
    connection = None
    try:
        connection = get_db_connection()
        connection.execute("BEGIN IMMEDIATE")
        ensure_history_schema(connection)
        if direction == "undo":
            row = connection.execute(
                """SELECT * FROM project_history
                   WHERE project_id = ? AND status = 'APPLIED'
                   ORDER BY id DESC LIMIT 1""",
                (project_id,),
            ).fetchone()
            if row is None:
                raise NothingToUndo("Não há alteração para desfazer.")
            snapshot = _decode_snapshot(row["before_snapshot"])
            restore_project_snapshot(connection, project_id, snapshot)
            connection.execute(
                """UPDATE project_history
                   SET status='UNDONE', undone_at=CURRENT_TIMESTAMP
                   WHERE id=?""",
                (row["id"],),
            )
        elif direction == "redo":
            row = connection.execute(
                """SELECT * FROM project_history
                   WHERE project_id = ? AND status = 'UNDONE'
                   ORDER BY id ASC LIMIT 1""",
                (project_id,),
            ).fetchone()
            if row is None:
                raise NothingToRedo("Não há alteração para refazer.")
            snapshot = _decode_snapshot(row["after_snapshot"])
            restore_project_snapshot(connection, project_id, snapshot)
            connection.execute(
                """UPDATE project_history
                   SET status='APPLIED', redone_at=CURRENT_TIMESTAMP
                   WHERE id=?""",
                (row["id"],),
            )
        else:
            raise ValueError("Direção de histórico inválida.")

        row = connection.execute(
            "SELECT * FROM project_history WHERE id=?", (row["id"],)
        ).fetchone()
        connection.commit()
        return _history_entry(row)
    except Exception:
        if connection is not None and connection.in_transaction:
            connection.rollback()
        raise
    finally:
        if connection is not None:
            connection.close()
        project_lock.release()


def undo(project_id: int) -> Dict[str, Any]:
    """Undo the newest applied action for a project."""

    return _move_cursor(project_id, "undo")


def redo(project_id: int) -> Dict[str, Any]:
    """Redo the oldest undone action for a project."""

    return _move_cursor(project_id, "redo")


def get_history_state(project_id: int) -> Dict[str, Any]:
    """Return cursor availability and labels for toolbar buttons."""

    connection = get_db_connection()
    try:
        ensure_history_schema(connection)
        connection.commit()
        undo_row = connection.execute(
            """SELECT id, action, created_at FROM project_history
               WHERE project_id=? AND status='APPLIED'
               ORDER BY id DESC LIMIT 1""",
            (project_id,),
        ).fetchone()
        redo_row = connection.execute(
            """SELECT id, action, created_at FROM project_history
               WHERE project_id=? AND status='UNDONE'
               ORDER BY id ASC LIMIT 1""",
            (project_id,),
        ).fetchone()
        return {
            "project_id": int(project_id),
            "can_undo": undo_row is not None,
            "can_redo": redo_row is not None,
            "undo_action": undo_row["action"] if undo_row else None,
            "redo_action": redo_row["action"] if redo_row else None,
            # Label aliases keep the service payload directly consumable by the
            # toolbar while retaining the explicit *_action names for APIs.
            "undo_label": undo_row["action"] if undo_row else None,
            "redo_label": redo_row["action"] if redo_row else None,
            "undo_created_at": undo_row["created_at"] if undo_row else None,
            "redo_created_at": redo_row["created_at"] if redo_row else None,
        }
    finally:
        connection.close()


def list_history(project_id: int, limit: int = 50) -> List[Dict[str, Any]]:
    """List lightweight history metadata, newest first (no snapshot payloads)."""

    connection = get_db_connection()
    try:
        ensure_history_schema(connection)
        connection.commit()
        rows = connection.execute(
            """SELECT id, project_id, action, metadata_json, status,
                      created_at, undone_at, redone_at
               FROM project_history WHERE project_id=?
               ORDER BY id DESC LIMIT ?""",
            (project_id, max(1, min(int(limit), 200))),
        ).fetchall()
        return [_history_entry(row) for row in rows]
    finally:
        connection.close()
