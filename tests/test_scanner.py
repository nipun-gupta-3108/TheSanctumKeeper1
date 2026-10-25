import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from sanctum_keeper.scanner import scan_folder, scan_folders
from sanctum_keeper.safety import (
    PathValidationError,
    SafetyPolicy,
)


def isolated_policy() -> SafetyPolicy:
    return SafetyPolicy(include_platform_paths=False)


class ScannerTests(unittest.TestCase):
    def test_scans_only_direct_children_and_ignores_temporary_files(self):
        with TemporaryDirectory() as temp:
            folder = Path(temp) / "Downloads"
            folder.mkdir()

            (folder / "invoice.pdf").write_text(
                "sample invoice",
                encoding="utf-8",
            )
            (folder / "unfinished.tmp").write_text(
                "incomplete",
                encoding="utf-8",
            )
            (folder / "download.zip.crdownload").write_text(
                "downloading",
                encoding="utf-8",
            )
            (folder / "partial.part").write_text(
                "partial",
                encoding="utf-8",
            )

            nested = folder / "Nested"
            nested.mkdir()
            (nested / "inside.pdf").write_text(
                "nested file",
                encoding="utf-8",
            )

            snapshots = scan_folder(folder, isolated_policy())

            self.assertEqual(
                [snapshot.filename for snapshot in snapshots],
                ["invoice.pdf"],
            )

            # Scanning must not change file contents.
            self.assertEqual(
                (folder / "invoice.pdf").read_text(encoding="utf-8"),
                "sample invoice",
            )

    def test_scans_multiple_non_overlapping_folders(self):
        with TemporaryDirectory() as temp:
            base = Path(temp)
            first = base / "First"
            second = base / "Second"

            first.mkdir()
            second.mkdir()

            (first / "one.txt").write_text("one", encoding="utf-8")
            (second / "two.txt").write_text("two", encoding="utf-8")

            snapshots = scan_folders(
                [first, second],
                isolated_policy(),
            )

            self.assertEqual(
                {snapshot.filename for snapshot in snapshots},
                {"one.txt", "two.txt"},
            )

    def test_rejects_a_protected_folder(self):
        with TemporaryDirectory() as temp:
            folder = Path(temp) / "protected"
            folder.mkdir()

            policy = SafetyPolicy(
                protected_paths=(folder,),
                include_platform_paths=False,
            )

            with self.assertRaises(PathValidationError):
                scan_folder(folder, policy)


if __name__ == "__main__":
    unittest.main()