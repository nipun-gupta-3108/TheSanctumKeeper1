
import os
import tempfile
import unittest
from pathlib import Path

from sanctum_keeper.database import KeeperDatabase
from sanctum_keeper.executor import (
    ExecutionNotConfirmedError,
    execute_plans,
)
from sanctum_keeper.models import ActionSpec, Condition, FileSnapshot, Rule
from sanctum_keeper.planner import plan_file
from sanctum_keeper.safety import SafetyPolicy


def test_policy():
    return SafetyPolicy(include_platform_paths=False)


class ExecutorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.source_dir = self.root / "Downloads"
        self.destination_dir = self.root / "Sorted"
        self.source_dir.mkdir()
        self.destination_dir.mkdir()

        self.database = KeeperDatabase(self.root / "keeper.sqlite3")
        self.policy = test_policy()

    def tearDown(self):
        self.temp.cleanup()

    def make_source(self, name="invoice.txt", content="original data"):
        source = self.source_dir / name
        source.write_text(content, encoding="utf-8")
        return source

    def make_plan(self, source, actions, *, quarantine_dir=None):
        rule = Rule(
            name="Test rule",
            conditions=(Condition("extension", "equals", source.suffix),),
            actions=tuple(actions),
        )

        return plan_file(
            FileSnapshot.from_path(source),
            [rule],
            quarantine_dir=quarantine_dir,
            policy=self.policy,
        )

    def test_execution_requires_confirmation(self):
        source = self.make_source()
        item = self.make_plan(
            source,
            [ActionSpec("move", str(self.destination_dir))],
        )

        with self.assertRaises(ExecutionNotConfirmedError):
            execute_plans([item], self.database, policy=self.policy)

        self.assertTrue(source.exists())
        self.assertEqual(self.database.list_operations(), [])

    def test_successful_move_is_journaled(self):
        source = self.make_source()
        item = self.make_plan(
            source,
            [ActionSpec("move", str(self.destination_dir))],
        )

        results = execute_plans(
            [item],
            self.database,
            confirmed=True,
            policy=self.policy,
        )

        destination = self.destination_dir / source.name

        self.assertEqual(results[0].status, "SUCCEEDED")
        self.assertFalse(source.exists())
        self.assertTrue(destination.exists())

        history = self.database.list_operations()
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["status"], "SUCCEEDED")
        self.assertEqual(history[0]["operation_type"], "move")
        self.assertEqual(len(history[0]["source_sha256"]), 64)
        self.assertEqual(len(history[0]["result_sha256"]), 64)

    def test_copy_keeps_original_and_logs_success(self):
        source = self.make_source()
        item = self.make_plan(
            source,
            [ActionSpec("copy", str(self.destination_dir))],
        )

        results = execute_plans(
            [item],
            self.database,
            confirmed=True,
            policy=self.policy,
        )

        self.assertEqual(results[0].status, "SUCCEEDED")
        self.assertTrue(source.exists())
        self.assertTrue((self.destination_dir / source.name).exists())
        self.assertEqual(self.database.list_operations()[0]["status"], "SUCCEEDED")

    def test_rename_then_move_executes_in_order(self):
        source = self.make_source()
        item = self.make_plan(
            source,
            [
                ActionSpec("rename", "processed.txt"),
                ActionSpec("move", str(self.destination_dir)),
            ],
        )

        results = execute_plans(
            [item],
            self.database,
            confirmed=True,
            policy=self.policy,
        )

        destination = self.destination_dir / "processed.txt"

        self.assertEqual(results[0].status, "SUCCEEDED")
        self.assertFalse(source.exists())
        self.assertTrue(destination.exists())
        self.assertEqual(destination.read_text(encoding="utf-8"), "original data")

        history = self.database.list_operations()
        self.assertEqual(len(history), 2)
        self.assertTrue(
            all(row["status"] == "SUCCEEDED" for row in history)
        )

    def test_stale_preview_is_rejected(self):
        source = self.make_source(content="original")
        item = self.make_plan(
            source,
            [ActionSpec("move", str(self.destination_dir))],
        )

        # Change the file and deliberately advance its modification time.
        source.write_text("modified", encoding="utf-8")
        modified_time = source.stat().st_mtime + 10
        os.utime(source, (modified_time, modified_time))

        results = execute_plans(
            [item],
            self.database,
            confirmed=True,
            policy=self.policy,
        )

        self.assertEqual(results[0].status, "STALE_PREVIEW")
        self.assertTrue(source.exists())
        self.assertFalse((self.destination_dir / source.name).exists())
        self.assertEqual(self.database.list_operations(), [])

    def test_blocked_plan_is_not_executed(self):
        source = self.make_source()

        item = self.make_plan(
            source,
            [ActionSpec("move", str(self.destination_dir))],
        )

        # Introduce a conflicting destination after planning.
        destination = self.destination_dir / source.name
        destination.write_text("keep existing", encoding="utf-8")

        results = execute_plans(
            [item],
            self.database,
            confirmed=True,
            policy=self.policy,
        )

        # Execution revalidates; it must not overwrite the new file.
        self.assertEqual(results[0].status, "NEEDS_REVIEW")
        self.assertTrue(source.exists())
        self.assertEqual(
            destination.read_text(encoding="utf-8"),
            "keep existing",
        )

    def test_quarantine_is_journaled(self):
        source = self.make_source()
        quarantine = self.root / "AppData" / "quarantine"

        item = self.make_plan(
            source,
            [ActionSpec("quarantine")],
            quarantine_dir=quarantine,
        )

        results = execute_plans(
            [item],
            self.database,
            confirmed=True,
            policy=self.policy,
            quarantine_dir=quarantine,
        )

        quarantined_file = quarantine / source.name

        self.assertEqual(results[0].status, "SUCCEEDED")
        self.assertFalse(source.exists())
        self.assertTrue(quarantined_file.exists())

        history = self.database.list_operations()
        self.assertEqual(history[0]["status"], "SUCCEEDED")
        self.assertEqual(history[0]["operation_type"], "quarantine")


if __name__ == "__main__":
    unittest.main()
