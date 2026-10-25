
import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from collections.abc import Sequence

from sanctum_keeper.models import (
    ActionSpec,
    ActionType,
    Condition,
    ConditionField,
    ConditionOperator,
    Rule,
)


class KeeperDatabase:
    SCHEMA_VERSION = 1

    def __init__(self, db_path: str | Path):
        self.path = Path(db_path).expanduser()

        # Create the parent directory if needed.
        self.path.parent.mkdir(parents=True, exist_ok=True)

        self.initialize()

    @contextmanager
    def _connection(self):
        connection = sqlite3.connect(str(self.path), timeout=5)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")

        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def initialize(self) -> None:
        """Create the database schema on first use."""

        with self._connection() as connection:
            version = connection.execute(
                "PRAGMA user_version"
            ).fetchone()[0]

            if version > self.SCHEMA_VERSION:
                raise RuntimeError(
                    f"Database version {version} is newer than "
                    f"supported version {self.SCHEMA_VERSION}"
                )

            if version == self.SCHEMA_VERSION:
                return

            connection.executescript("""
                CREATE TABLE IF NOT EXISTS watched_folders (
                    id INTEGER PRIMARY KEY,
                    path TEXT NOT NULL UNIQUE,
                    added_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS rules (
                    id INTEGER PRIMARY KEY,
                    name TEXT NOT NULL,
                    position INTEGER NOT NULL UNIQUE,
                    enabled INTEGER NOT NULL CHECK(enabled IN (0, 1))
                );

                CREATE TABLE IF NOT EXISTS conditions (
                    id INTEGER PRIMARY KEY,
                    rule_id INTEGER NOT NULL
                        REFERENCES rules(id) ON DELETE CASCADE,
                    position INTEGER NOT NULL,
                    field TEXT NOT NULL,
                    operator TEXT NOT NULL,
                    value_json TEXT NOT NULL,
                    UNIQUE(rule_id, position)
                );

                CREATE TABLE IF NOT EXISTS actions (
                    id INTEGER PRIMARY KEY,
                    rule_id INTEGER NOT NULL
                        REFERENCES rules(id) ON DELETE CASCADE,
                    position INTEGER NOT NULL,
                    kind TEXT NOT NULL,
                    target TEXT,
                    UNIQUE(rule_id, position)
                );

                CREATE TABLE IF NOT EXISTS operations (
                    id INTEGER PRIMARY KEY,
                    operation_type TEXT NOT NULL,
                    source_path TEXT NOT NULL,
                    destination_path TEXT,
                    status TEXT NOT NULL CHECK(
                        status IN (
                            'PENDING',
                            'SUCCEEDED',
                            'FAILED',
                            'NEEDS_REVIEW',
                            'UNDONE'
                        )
                    ),
                    error TEXT,
                    source_size INTEGER,
                    source_sha256 TEXT,
                    result_size INTEGER,
                    result_sha256 TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    completed_at TEXT
                );
            """)

            connection.execute(
                f"PRAGMA user_version = {self.SCHEMA_VERSION}"
            )

    @staticmethod
    def _normalise_path(path: str | Path) -> str:
        return str(Path(path).expanduser().resolve(strict=False))

    # ---------------- Watched folders ----------------

    def add_watched_folder(self, folder: str | Path) -> bool:
        """Return False if the path is already saved."""

        path = self._normalise_path(folder)

        with self._connection() as connection:
            cursor = connection.execute(
                """
                INSERT OR IGNORE INTO watched_folders(path)
                VALUES (?)
                """,
                (path,),
            )
            return cursor.rowcount == 1

    def remove_watched_folder(self, folder: str | Path) -> bool:
        path = self._normalise_path(folder)

        with self._connection() as connection:
            cursor = connection.execute(
                "DELETE FROM watched_folders WHERE path = ?",
                (path,),
            )
            return cursor.rowcount == 1

    def list_watched_folders(self) -> list[Path]:
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT path FROM watched_folders
                ORDER BY id
                """
            ).fetchall()

        return [Path(row["path"]) for row in rows]

    # ---------------- Rules ----------------

    def save_rules(self, rules: Sequence[Rule]) -> None:
        """
        Replace the saved rule list in one database transaction.
        List order determines rule priority.
        """

        with self._connection() as connection:
            connection.execute("DELETE FROM rules")

            for rule_position, rule in enumerate(rules):
                cursor = connection.execute(
                    """
                    INSERT INTO rules(name, position, enabled)
                    VALUES (?, ?, ?)
                    """,
                    (
                        rule.name,
                        rule_position,
                        int(rule.enabled),
                    ),
                )
                rule_id = cursor.lastrowid

                for position, condition in enumerate(rule.conditions):
                    connection.execute(
                        """
                        INSERT INTO conditions(
                            rule_id, position, field, operator, value_json
                        )
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        (
                            rule_id,
                            position,
                            condition.field.value,
                            condition.operator.value,
                            json.dumps(
                                condition.value,
                                allow_nan=False,
                            ),
                        ),
                    )

                for position, action in enumerate(rule.actions):
                    connection.execute(
                        """
                        INSERT INTO actions(
                            rule_id, position, kind, target
                        )
                        VALUES (?, ?, ?, ?)
                        """,
                        (
                            rule_id,
                            position,
                            action.kind.value,
                            action.target,
                        ),
                    )

    def list_rules(self) -> list[Rule]:
        """Load rules, preserving rule, condition and action order."""

        with self._connection() as connection:
            rule_rows = connection.execute(
                "SELECT * FROM rules ORDER BY position"
            ).fetchall()

            result = []

            for row in rule_rows:
                rule_id = row["id"]

                condition_rows = connection.execute(
                    """
                    SELECT * FROM conditions
                    WHERE rule_id = ?
                    ORDER BY position
                    """,
                    (rule_id,),
                ).fetchall()

                action_rows = connection.execute(
                    """
                    SELECT * FROM actions
                    WHERE rule_id = ?
                    ORDER BY position
                    """,
                    (rule_id,),
                ).fetchall()

                conditions = tuple(
                    Condition(
                        ConditionField(item["field"]),
                        ConditionOperator(item["operator"]),
                        json.loads(item["value_json"]),
                    )
                    for item in condition_rows
                )

                actions = tuple(
                    ActionSpec(
                        ActionType(item["kind"]),
                        item["target"],
                    )
                    for item in action_rows
                )

                result.append(
                    Rule(
                        name=row["name"],
                        conditions=conditions,
                        actions=actions,
                        enabled=bool(row["enabled"]),
                    )
                )

        return result

    # ---------------- Operation journal ----------------

    def start_operation(
        self,
        operation_type: str | ActionType,
        source: str | Path,
        destination: str | Path | None = None,
        *,
        source_size: int | None = None,
        source_sha256: str | None = None,
    ) -> int:
        """
        Record an operation intent before executing a file operation.
        This method does not perform filesystem changes.
        """

        if isinstance(operation_type, ActionType):
            operation_type = operation_type.value

        if not isinstance(operation_type, str) or not operation_type.strip():
            raise ValueError("Operation type cannot be empty")

        source_path = self._normalise_path(source)
        destination_path = (
            self._normalise_path(destination)
            if destination is not None
            else None
        )

        if source_size is not None and (
            isinstance(source_size, bool)
            or not isinstance(source_size, int)
            or source_size < 0
        ):
            raise ValueError("Source size must be a non-negative integer")

        if source_sha256 is not None:
            if (
                len(source_sha256) != 64
                or any(char not in "0123456789abcdefABCDEF"
                       for char in source_sha256)
            ):
                raise ValueError("Source SHA-256 must contain 64 hex digits")

        with self._connection() as connection:
            cursor = connection.execute(
                """
                INSERT INTO operations(
                    operation_type,
                    source_path,
                    destination_path,
                    status,
                    source_size,
                    source_sha256
                )
                VALUES (?, ?, ?, 'PENDING', ?, ?)
                """,
                (
                    operation_type,
                    source_path,
                    destination_path,
                    source_size,
                    source_sha256,
                ),
            )
            return int(cursor.lastrowid)

    def finish_operation(
        self,
        operation_id: int,
        status: str,
        *,
        error: str | None = None,
        result_size: int | None = None,
        result_sha256: str | None = None,
    ) -> None:
        """Finish an existing PENDING journal entry."""

        allowed_statuses = {
            "SUCCEEDED",
            "FAILED",
            "NEEDS_REVIEW",
            "UNDONE",
        }

        if status not in allowed_statuses:
            raise ValueError(f"Invalid final status: {status}")

        if result_size is not None and (
            isinstance(result_size, bool)
            or not isinstance(result_size, int)
            or result_size < 0
        ):
            raise ValueError("Result size must be a non-negative integer")

        if result_sha256 is not None:
            if (
                len(result_sha256) != 64
                or any(char not in "0123456789abcdefABCDEF"
                       for char in result_sha256)
            ):
                raise ValueError("Result SHA-256 must contain 64 hex digits")

        with self._connection() as connection:
            cursor = connection.execute(
                """
                UPDATE operations
                SET status = ?,
                    error = ?,
                    result_size = ?,
                    result_sha256 = ?,
                    completed_at = CURRENT_TIMESTAMP
                WHERE id = ? AND status = 'PENDING'
                """,
                (
                    status,
                    error,
                    result_size,
                    result_sha256,
                    operation_id,
                ),
            )

            if cursor.rowcount != 1:
                raise ValueError(
                    f"Operation {operation_id} does not exist "
                    "or is no longer pending"
                )

    def list_operations(self, limit: int = 100) -> list[dict]:
        if (
            isinstance(limit, bool)
            or not isinstance(limit, int)
            or not 1 <= limit <= 1000
        ):
            raise ValueError("Limit must be between 1 and 1000")

        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT * FROM operations
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

        return [dict(row) for row in rows]
