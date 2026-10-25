
import tempfile
import unittest
from pathlib import Path

from sanctum_keeper.database import KeeperDatabase
from sanctum_keeper.models import (
    ActionSpec,
    Condition,
    Rule,
)


class DatabaseTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.db_path = self.root / "keeper.sqlite3"
        self.db = KeeperDatabase(self.db_path)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_database_initializes(self):
        self.assertTrue(self.db_path.exists())

    def test_watched_folders_persist(self):
        folder = self.root / "Downloads"
        folder.mkdir()

        self.assertTrue(self.db.add_watched_folder(folder))
        self.assertFalse(self.db.add_watched_folder(folder))
        self.assertEqual(
            self.db.list_watched_folders(),
            [folder.resolve()],
        )

        # Reopen database to verify persistence.
        reopened = KeeperDatabase(self.db_path)
        self.assertEqual(
            reopened.list_watched_folders(),
            [folder.resolve()],
        )

    def test_rules_persist_in_order(self):
        first = Rule(
            name="Invoice rule",
            conditions=(
                Condition("filename", "contains", "invoice"),
                Condition("size_bytes", "gt", 1000),
            ),
            actions=(
                ActionSpec("rename", "processed.pdf"),
                ActionSpec("move", str(self.root / "Invoices")),
            ),
        )

        second = Rule(
            name="Text rule",
            conditions=(Condition("extension", "equals", ".txt"),),
            actions=(ActionSpec("quarantine"),),
            enabled=False,
        )

        self.db.save_rules([first, second])

        # Simulate application restart.
        reopened = KeeperDatabase(self.db_path)
        loaded = reopened.list_rules()

        self.assertEqual(len(loaded), 2)
        self.assertEqual(loaded[0].name, "Invoice rule")
        self.assertEqual(loaded[1].name, "Text rule")
        self.assertFalse(loaded[1].enabled)

        self.assertEqual(
            loaded[0].conditions[1].value,
            1000,
        )
        self.assertEqual(
            loaded[0].actions[0].target,
            "processed.pdf",
        )
        self.assertEqual(
            loaded[0].actions[1].kind.value,
            "move",
        )
        self.assertIsNone(loaded[1].actions[0].target)

    def test_saving_rules_replaces_previous_list(self):
        original = Rule(
            name="Original",
            conditions=(Condition("extension", "equals", ".pdf"),),
            actions=(ActionSpec("quarantine"),),
        )
        replacement = Rule(
            name="Replacement",
            conditions=(Condition("extension", "equals", ".txt"),),
            actions=(ActionSpec("quarantine"),),
        )

        self.db.save_rules([original])
        self.db.save_rules([replacement])

        loaded = self.db.list_rules()
        self.assertEqual([rule.name for rule in loaded], ["Replacement"])

    def test_operation_journal_status_transition(self):
        operation_id = self.db.start_operation(
            "move",
            self.root / "source.txt",
            self.root / "destination.txt",
            source_size=12,
            source_sha256="a" * 64,
        )

        pending = self.db.list_operations()
        self.assertEqual(pending[0]["id"], operation_id)
        self.assertEqual(pending[0]["status"], "PENDING")

        self.db.finish_operation(
            operation_id,
            "SUCCEEDED",
            result_size=12,
            result_sha256="b" * 64,
        )

        completed = self.db.list_operations()[0]
        self.assertEqual(completed["status"], "SUCCEEDED")
        self.assertEqual(completed["result_size"], 12)
        self.assertEqual(completed["result_sha256"], "b" * 64)
        self.assertIsNotNone(completed["completed_at"])

    def test_operation_must_be_pending_before_finishing(self):
        operation_id = self.db.start_operation(
            "copy",
            self.root / "source.txt",
        )

        self.db.finish_operation(operation_id, "FAILED")

        with self.assertRaises(ValueError):
            self.db.finish_operation(operation_id, "SUCCEEDED")

    def test_invalid_hash_is_rejected(self):
        with self.assertRaises(ValueError):
            self.db.start_operation(
                "move",
                self.root / "source.txt",
                source_sha256="invalid",
            )


if __name__ == "__main__":
    unittest.main()
