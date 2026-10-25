import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from sanctum_keeper.safety import (
    PathValidationError,
    SafetyPolicy,
    validate_watch_folder,
    validate_watch_folders,
)


def isolated_policy(*protected_paths: Path) -> SafetyPolicy:
    return SafetyPolicy(
        protected_paths=tuple(protected_paths),
        include_platform_paths=False,
    )


class SafetyTests(unittest.TestCase):
    def test_accepts_valid_folder(self):
        with TemporaryDirectory() as temp:
            folder = Path(temp) / "Downloads"
            folder.mkdir()

            result = validate_watch_folder(
                folder,
                isolated_policy(),
            )

            self.assertEqual(result, folder.resolve())

    def test_rejects_filesystem_root(self):
        root = Path(Path.cwd().anchor)

        with self.assertRaises(PathValidationError):
            validate_watch_folder(root, isolated_policy())

    def test_rejects_protected_folder_and_its_parent(self):
        with TemporaryDirectory() as temp:
            base = Path(temp)
            protected = base / "app_data"
            child = protected / "nested"
            protected.mkdir()
            child.mkdir()

            policy = isolated_policy(protected)

            with self.assertRaises(PathValidationError):
                validate_watch_folder(child, policy)

            # Watching the parent would include protected app data.
            with self.assertRaises(PathValidationError):
                validate_watch_folder(base, policy)

    def test_rejects_overlapping_watched_folders(self):
        with TemporaryDirectory() as temp:
            parent = Path(temp) / "Downloads"
            child = parent / "Nested"

            child.mkdir(parents=True)

            with self.assertRaises(PathValidationError):
                validate_watch_folders(
                    [parent, child],
                    isolated_policy(),
                )

    def test_rejects_more_than_three_folders(self):
        with TemporaryDirectory() as temp:
            folders = []

            for number in range(4):
                folder = Path(temp) / f"folder_{number}"
                folder.mkdir()
                folders.append(folder)

            with self.assertRaises(PathValidationError):
                validate_watch_folders(
                    folders,
                    isolated_policy(),
                )


if __name__ == "__main__":
    unittest.main()