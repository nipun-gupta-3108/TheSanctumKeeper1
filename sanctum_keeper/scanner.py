from pathlib import Path

from sanctum_keeper.models import FileSnapshot
from sanctum_keeper.safety import (
    SafetyPolicy,
    validate_watch_folder,
    validate_watch_folders,
)


IGNORED_SUFFIXES = {
    ".crdownload",
    ".part",
    ".tmp",
}


class ScanError(RuntimeError):
    """Raised when a folder cannot be scanned."""


def is_ignored_file(path: Path) -> bool:
    """Return True for temporary or incomplete files."""

    return path.suffix.casefold() in IGNORED_SUFFIXES


def _scan_validated_folder(folder: Path) -> list[FileSnapshot]:
    """Scan direct-child regular files in an already validated folder."""

    snapshots = []

    try:
        entries = sorted(
            folder.iterdir(),
            key=lambda path: path.name.casefold(),
        )
    except OSError as exc:
        raise ScanError(f"Cannot scan folder: {folder}") from exc

    for entry in entries:
        try:
            # Never follow symbolic links.
            if entry.is_symlink():
                continue

            # Ignore directories; scanning is deliberately non-recursive.
            if not entry.is_file():
                continue

            if is_ignored_file(entry):
                continue

            snapshot = FileSnapshot.from_path(entry)

            # Protect against a path resolving outside the scanned folder.
            if snapshot.path.parent != folder:
                continue

            snapshots.append(snapshot)

        except (OSError, ValueError):
            # A file might disappear or become inaccessible during scanning.
            # It will be considered again on a subsequent scan.
            continue

    return snapshots


def scan_folder(
    folder: str | Path,
    policy: SafetyPolicy | None = None,
) -> list[FileSnapshot]:
    """Safely scan one folder without modifying its files."""

    resolved = validate_watch_folder(folder, policy)
    return _scan_validated_folder(resolved)


def scan_folders(
    folders: list[str | Path] | tuple[str | Path, ...],
    policy: SafetyPolicy | None = None,
) -> list[FileSnapshot]:
    """Validate and scan up to three non-overlapping folders."""

    resolved_folders = validate_watch_folders(folders, policy)

    files = []

    for folder in resolved_folders:
        files.extend(_scan_validated_folder(folder))

    return files