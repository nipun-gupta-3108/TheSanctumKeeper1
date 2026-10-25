import tempfile
import unittest
from pathlib import Path

from sanctum_keeper.file_ops import (
    FileOperationError,
    compute_file_signature,
    copy_file,
    move_file,
    quarantine_file,
    rename_file,
)
from sanctum_keeper.safety import SafetyPolicy


def test_policy():
    return SafetyPolicy(include_platform_paths=False)


class FileOperationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.source_dir = self.root / "Downloads"
        self.destination_dir = self.root / "Sorted"
        self.source_dir.mkdir()
        self.destination_dir.mkdir()
        self.policy = test_policy()

    def tearDown(self):
        self.temp.cleanup()

    def create_file(self, name="invoice.txt", content="original data"):
        path = self.source_dir / name
        path.write_text(content, encoding="utf-8")
        return path

    def test_signature_contains_correct_size_and_hash(self):
        source = self.create_file()
        signature = compute_file_signature(source, self.policy)

        self.assertEqual(signature.size_bytes, len(b"original data"))
        self.assertEqual(len(signature.sha256), 64)

    def test_copy_retains_original_and_verifies_content(self):
        source = self.create_file()
        destination = self.destination_dir / source.name

        result = copy_file(source, destination, self.policy)

        self.assertTrue(source.exists())
        self.assertTrue(destination.exists())
        self.assertEqual(destination.read_text(encoding="utf-8"), "original data")
        self.assertEqual(
            result.sha256,
            compute_file_signature(source, self.policy).sha256,
        )

    def test_move_removes_source_after_copy(self):
        source = self.create_file()
        destination = self.destination_dir / source.name

        result = move_file(source, destination, self.policy)

        self.assertFalse(source.exists())
        self.assertTrue(destination.exists())
        self.assertEqual(result, destination.resolve())
        self.assertEqual(destination.read_text(encoding="utf-8"), "original data")

    def test_rename_preserves_content(self):
        source = self.create_file()
        result = rename_file(source, "renamed.txt", self.policy)

        self.assertFalse(source.exists())
        self.assertTrue(result.exists())
        self.assertEqual(result.name, "renamed.txt")
        self.assertEqual(result.read_text(encoding="utf-8"), "original data")

    def test_existing_destination_is_never_overwritten(self):
        source = self.create_file(content="source")
        destination = self.destination_dir / source.name
        destination.write_text("keep this", encoding="utf-8")

        with self.assertRaises(FileOperationError):
            move_file(source, destination, self.policy)

        self.assertTrue(source.exists())
        self.assertEqual(
            destination.read_text(encoding="utf-8"),
            "keep this",
        )

    def test_quarantine_moves_file_to_separate_directory(self):
        source = self.create_file()
        quarantine = self.root / "AppData" / "quarantine"

        result = quarantine_file(source, quarantine, self.policy)

        self.assertFalse(source.exists())
        self.assertTrue(result.exists())
        self.assertEqual(result.parent, quarantine.resolve())
        self.assertEqual(result.read_text(encoding="utf-8"), "original data")

    def test_quarantine_refuses_source_folder(self):
        source = self.create_file()

        with self.assertRaises(FileOperationError):
            quarantine_file(source, self.source_dir, self.policy)

        self.assertTrue(source.exists())

    def test_copy_refuses_missing_destination_directory(self):
        source = self.create_file()
        destination = self.root / "missing" / "file.txt"

        with self.assertRaises(FileOperationError):
            copy_file(source, destination, self.policy)

        self.assertTrue(source.exists())
        self.assertFalse(destination.exists())

    def test_rename_refuses_invalid_name(self):
        source = self.create_file()

        with self.assertRaises(FileOperationError):
            rename_file(source, "../unsafe.txt", self.policy)

        self.assertTrue(source.exists())


if __name__ == "__main__":
    unittest.main()