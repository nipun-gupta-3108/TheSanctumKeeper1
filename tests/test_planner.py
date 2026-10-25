
import tempfile
import unittest
from pathlib import Path

from sanctum_keeper.models import (
    ActionSpec,
    FileSnapshot,
    Rule,
)
from sanctum_keeper.models import (
    ActionSpec,
    Condition,
    FileSnapshot,
    Rule,
)
from sanctum_keeper.planner import (
    PlanStatus,
    plan_file,
    plan_files,
)
from sanctum_keeper.safety import SafetyPolicy


def test_policy():
    return SafetyPolicy(include_platform_paths=False)


class PlannerTests(unittest.TestCase):
    def test_preview_does_not_change_files(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "invoice.pdf"
            destination = root / "Sorted"
            destination.mkdir()

            source.write_text("original content", encoding="utf-8")

            snapshot = FileSnapshot.from_path(source)

            rule = Rule(
                name="Move invoices",
                conditions=(
                    Condition("extension", "equals", ".pdf"),
                ),
                actions=(
                    ActionSpec("move", str(destination)),
                ),
            )

            result = plan_file(
                snapshot,
                [rule],
                policy=test_policy(),
            )

            self.assertEqual(result.status, PlanStatus.READY)
            self.assertEqual(
                source.read_text(encoding="utf-8"),
                "original content",
            )
            self.assertFalse((destination / "invoice.pdf").exists())

    def test_no_matching_rule(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "notes.txt"
            source.write_text("notes", encoding="utf-8")

            from sanctum_keeper.models import Condition
            rule = Rule(
                name="PDF files",
                conditions=(Condition("extension", "equals", ".pdf"),),
                actions=(ActionSpec("move", str(root)),),
            )

            result = plan_file(
                FileSnapshot.from_path(source),
                [rule],
                policy=test_policy(),
            )

            self.assertEqual(result.status, PlanStatus.NO_MATCH)

    def test_rename_then_move_is_planned_in_order(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "invoice.pdf"
            destination = root / "Invoices"
            destination.mkdir()
            source.write_text("invoice", encoding="utf-8")

            from sanctum_keeper.models import Condition
            rule = Rule(
                name="Rename and move",
                conditions=(Condition("filename", "contains", "invoice"),),
                actions=(
                    ActionSpec("rename", "processed.pdf"),
                    ActionSpec("move", str(destination)),
                ),
            )

            result = plan_file(
                FileSnapshot.from_path(source),
                [rule],
                policy=test_policy(),
            )

            self.assertEqual(result.status, PlanStatus.READY)
            self.assertEqual(len(result.actions), 2)
            self.assertEqual(
                result.actions[0].destination.name,
                "processed.pdf",
            )
            self.assertEqual(
                result.actions[1].source.name,
                "processed.pdf",
            )
            self.assertEqual(
                result.final_path,
                destination / "processed.pdf",
            )
            self.assertTrue(source.exists())

    def test_existing_destination_blocks_plan(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "invoice.pdf"
            destination = root / "Sorted"
            destination.mkdir()
            (destination / source.name).write_text(
                "do not overwrite",
                encoding="utf-8",
            )
            source.write_text("source", encoding="utf-8")

            from sanctum_keeper.models import Condition
            rule = Rule(
                name="Move PDF",
                conditions=(Condition("extension", "equals", ".pdf"),),
                actions=(ActionSpec("move", str(destination)),),
            )

            result = plan_file(
                FileSnapshot.from_path(source),
                [rule],
                policy=test_policy(),
            )

            self.assertEqual(result.status, PlanStatus.BLOCKED)
            self.assertTrue(source.exists())
            self.assertEqual(
                (destination / source.name).read_text(encoding="utf-8"),
                "do not overwrite",
            )

    def test_duplicate_planned_destinations_are_blocked(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            destination = root / "Sorted"
            destination.mkdir()

            first = root / "one.pdf"
            second = root / "two.pdf"
            first.write_text("one", encoding="utf-8")
            second.write_text("two", encoding="utf-8")

            from sanctum_keeper.models import Condition
            rule = Rule(
                name="Rename all PDFs",
                conditions=(Condition("extension", "equals", ".pdf"),),
                actions=(ActionSpec("rename", "same.pdf"),),
            )

            results = plan_files(
                [
                    FileSnapshot.from_path(first),
                    FileSnapshot.from_path(second),
                ],
                [rule],
                policy=test_policy(),
            )

            self.assertEqual(results[0].status, PlanStatus.READY)
            self.assertEqual(results[1].status, PlanStatus.BLOCKED)

    def test_quarantine_plan_does_not_create_directory(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source_folder = root / "Downloads"
            source_folder.mkdir()
            quarantine = root / "AppData" / "quarantine"
            source = source_folder / "old.txt"
            source.write_text("old file", encoding="utf-8")

            from sanctum_keeper.models import Condition
            rule = Rule(
                name="Quarantine old files",
                conditions=(Condition("extension", "equals", ".txt"),),
                actions=(ActionSpec("quarantine"),),
            )

            result = plan_file(
                FileSnapshot.from_path(source),
                [rule],
                quarantine_dir=quarantine,
                policy=test_policy(),
            )

            self.assertEqual(result.status, PlanStatus.READY)
            self.assertFalse(quarantine.exists())
            self.assertTrue(source.exists())


if __name__ == "__main__":
    unittest.main()
