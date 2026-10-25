import hashlib
import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

from sanctum_keeper.safety import (
    PathValidationError,
    SafetyPolicy,
    validate_watch_folder,
)


class FileOperationError(RuntimeError):
    """Raised when a safe file operation cannot be completed."""


@dataclass(frozen=True)
class FileSignature:
    size_bytes: int
    modified_ns: int
    sha256: str


def _signature_at(path: Path) -> FileSignature:
    """Calculate a file's size, modification time and SHA-256."""

    if path.is_symlink() or not path.is_file():
        raise FileOperationError(f"Not a regular file: {path}")

    try:
        before = path.stat()
        digest = hashlib.sha256()
        size = 0

        with path.open("rb") as file:
            while True:
                chunk = file.read(1024 * 1024)
                if not chunk:
                    break

                digest.update(chunk)
                size += len(chunk)

        after = path.stat()

    except OSError as exc:
        raise FileOperationError(
            f"Could not read file: {path}"
        ) from exc

    if (
        before.st_size != after.st_size
        or before.st_mtime_ns != after.st_mtime_ns
        or size != after.st_size
    ):
        raise FileOperationError(
            f"File changed while being read: {path}"
        )

    return FileSignature(
        size_bytes=size,
        modified_ns=after.st_mtime_ns,
        sha256=digest.hexdigest(),
    )


def compute_file_signature(
    path: str | Path,
    policy: SafetyPolicy | None = None,
) -> FileSignature:
    """Validate a source file and calculate its signature."""

    policy = policy or SafetyPolicy()
    candidate = Path(path).expanduser()

    if candidate.is_symlink():
        raise FileOperationError("Symbolic-link files are not supported")

    try:
        parent = validate_watch_folder(candidate.parent, policy)
        resolved = candidate.resolve(strict=True)

        if resolved.parent != parent or not resolved.is_file():
            raise FileOperationError(
                f"Invalid source file: {candidate}"
            )

        return _signature_at(resolved)

    except (OSError, RuntimeError, PathValidationError) as exc:
        raise FileOperationError(
            f"Source validation failed: {candidate}: {exc}"
        ) from exc


def _validate_source(
    source: str | Path,
    policy: SafetyPolicy,
) -> Path:
    candidate = Path(source).expanduser()

    if candidate.is_symlink():
        raise FileOperationError(
            "Symbolic-link sources are not supported"
        )

    try:
        parent = validate_watch_folder(candidate.parent, policy)
        resolved = candidate.resolve(strict=True)

        if resolved.parent != parent:
            raise FileOperationError(
                "Source must be a direct-child file"
            )

        if not resolved.is_file():
            raise FileOperationError(
                f"Source is not a regular file: {resolved}"
            )

        return resolved

    except (OSError, RuntimeError, PathValidationError) as exc:
        raise FileOperationError(
            f"Source validation failed: {candidate}: {exc}"
        ) from exc


def _validate_destination(
    destination: str | Path,
    policy: SafetyPolicy,
    allowed_quarantine_dir: Path | None = None,
) -> Path:
    candidate = Path(destination).expanduser()

    if candidate.name in {"", ".", ".."}:
        raise FileOperationError("Invalid destination filename")

    try:
        if allowed_quarantine_dir is not None:
            parent = allowed_quarantine_dir.resolve(strict=True)

            # This exception is limited to the already validated
            #, explicitly configured quarantine directory.
            if candidate.parent.resolve(strict=True) != parent:
                raise FileOperationError(
                    "Destination is outside the quarantine directory"
                )

        else:
            parent = validate_watch_folder(candidate.parent, policy)

        if not parent.is_dir():
            raise FileOperationError(
                f"Destination directory does not exist: {parent}"
            )

        target = parent / candidate.name

        if target.exists() or target.is_symlink():
            raise FileOperationError(
                f"Destination already exists: {target}"
            )

        return target

    except (OSError, RuntimeError, PathValidationError) as exc:
        raise FileOperationError(
            f"Destination validation failed: {candidate}: {exc}"
        ) from exc


def _copy_file(
    source: str | Path,
    destination: str | Path,
    policy: SafetyPolicy,
    allowed_quarantine_dir: Path | None = None,
) -> FileSignature:
    """Copy through a temporary file, verify, then publish without overwrite."""

    source_path = _validate_source(source, policy)
    destination_path = _validate_destination(
        destination,
        policy,
        allowed_quarantine_dir,
    )

    if os.path.normcase(str(source_path)).casefold() == (
        os.path.normcase(str(destination_path)).casefold()
    ):
        raise FileOperationError(
            "Source and destination must be different"
        )

    original_signature = _signature_at(source_path)

    temporary_path = None

    try:
        # Temporary file is on the destination filesystem so that
        # publishing with os.link is an atomic no-overwrite operation.
        file_descriptor, temp_name = tempfile.mkstemp(
            prefix=".sanctum_keeper_",
            suffix=".tmp",
            dir=destination_path.parent,
        )
        temporary_path = Path(temp_name)

        digest = hashlib.sha256()
        copied_size = 0

        with source_path.open("rb") as src:
            with os.fdopen(file_descriptor, "wb") as dst:
                while True:
                    chunk = src.read(1024 * 1024)

                    if not chunk:
                        break

                    dst.write(chunk)
                    digest.update(chunk)
                    copied_size += len(chunk)

                dst.flush()
                os.fsync(dst.fileno())

        copied_hash = digest.hexdigest()

        if (
            copied_size != original_signature.size_bytes
            or copied_hash != original_signature.sha256
        ):
            raise FileOperationError(
                "Copied content does not match the source"
            )

        if _signature_at(source_path) != original_signature:
            raise FileOperationError(
                "Source changed during copy; refusing to publish"
            )

        # Preserve ordinary file timestamps and permission bits.
        shutil.copystat(source_path, temporary_path)

        if _signature_at(source_path) != original_signature:
            raise FileOperationError(
                "Source changed before copy was finalized"
            )

        # os.link creates the destination only if the name is free.
        # It fails rather than replacing an existing destination.
        try:
            os.link(temporary_path, destination_path)
        except FileExistsError as exc:
            raise FileOperationError(
                f"Destination appeared during the operation: "
                f"{destination_path}"
            ) from exc

        # Verify the actual destination before reporting success.
        result_signature = _signature_at(destination_path)

        if (
            result_signature.size_bytes != original_signature.size_bytes
            or result_signature.sha256 != original_signature.sha256
        ):
            raise FileOperationError(
                "Destination verification failed; manual review required"
            )

        return result_signature

    except FileOperationError:
        raise

    except OSError as exc:
        raise FileOperationError(
            f"File operation failed: {exc}"
        ) from exc

    finally:
        if temporary_path is not None:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                # Leave an identifiable temporary file for review.
                pass


def copy_file(
    source: str | Path,
    destination: str | Path,
    policy: SafetyPolicy | None = None,
) -> FileSignature:
    """Create and verify a copy. The original file is retained."""

    return _copy_file(
        source,
        destination,
        policy or SafetyPolicy(),
    )


def move_file(
    source: str | Path,
    destination: str | Path,
    policy: SafetyPolicy | None = None,
) -> Path:
    """Verify the destination before removing the original file."""

    policy = policy or SafetyPolicy()
    source_path = _validate_source(source, policy)
    original_signature = _signature_at(source_path)

    _copy_file(source_path, destination, policy)

    # Recheck source immediately before removal.
    if _signature_at(source_path) != original_signature:
        raise FileOperationError(
            "Source changed after copying. Both files have been retained."
        )

    try:
        source_path.unlink()
    except OSError as exc:
        # The verified destination remains. Do not delete either copy
        # automatically if source removal fails.
        raise FileOperationError(
            "Destination was created, but the source could not be removed. "
            "Both files have been retained for review."
        ) from exc

    return Path(destination).resolve(strict=False)


def rename_file(
    source: str | Path,
    new_name: str,
    policy: SafetyPolicy | None = None,
) -> Path:
    """Rename a file without overwriting another file."""

    if (
        not isinstance(new_name, str)
        or not new_name
        or new_name in {".", ".."}
        or new_name.endswith((" ", "."))
        or any(char in new_name for char in '<>:"/\\|?*')
    ):
        raise FileOperationError("Invalid new filename")

    source_path = Path(source).expanduser()
    return move_file(
        source_path,
        source_path.parent / new_name,
        policy,
    )


def default_quarantine_dir() -> Path:
    """Return the app-managed quarantine location on Windows."""

    base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")

    if not base:
        raise FileOperationError(
            "Application data directory is unavailable; "
            "configure a quarantine directory explicitly"
        )

    return Path(base) / "TheSanctumKeeper" / "quarantine"


def _validate_quarantine_dir(
    quarantine_dir: str | Path,
    source_parent: Path,
    policy: SafetyPolicy,
) -> Path:
    candidate = Path(quarantine_dir).expanduser()

    if candidate.is_symlink():
        raise FileOperationError(
            "Quarantine directory cannot be a symbolic link"
        )

    resolved = candidate.resolve(strict=False)

    if resolved.parent == resolved:
        raise FileOperationError(
            "Filesystem roots cannot be quarantine directories"
        )

    try:
        if resolved == source_parent or resolved.is_relative_to(source_parent):
            raise FileOperationError(
                "Quarantine cannot be inside the watched source folder"
            )

        if source_parent.is_relative_to(resolved):
            raise FileOperationError(
                "Quarantine cannot contain the watched source folder"
            )

    except ValueError:
        pass

    for protected in policy.protected_paths:
        protected_path = protected.resolve(strict=False)

        if (
            resolved == protected_path
            or resolved.is_relative_to(protected_path)
            or protected_path.is_relative_to(resolved)
        ):
            raise FileOperationError(
                "Quarantine overlaps a protected path"
            )

    if policy.include_platform_paths and os.name == "nt":
        for name in (
            "WINDIR",
            "ProgramFiles",
            "ProgramFiles(x86)",
            "ProgramData",
        ):
            value = os.environ.get(name)

            if not value:
                continue

            protected = Path(value).resolve(strict=False)

            if (
                resolved == protected
                or resolved.is_relative_to(protected)
                or protected.is_relative_to(resolved)
            ):
                raise FileOperationError(
                    "Quarantine overlaps a protected system location"
                )

        for name in ("LOCALAPPDATA", "APPDATA"):
            value = os.environ.get(name)

            if not value:
                continue

            appdata = Path(value).resolve(strict=False)

            # Only the designated app-specific quarantine is permitted
            # beneath application data.
            if resolved.is_relative_to(appdata):
                expected = (
                    appdata / "TheSanctumKeeper" / "quarantine"
                ).resolve(strict=False)

                if resolved != expected:
                    raise FileOperationError(
                        "Only the designated quarantine directory may "
                        "be inside application data"
                    )

            elif appdata.is_relative_to(resolved):
                raise FileOperationError(
                    "Quarantine cannot contain application data"
                )

    return resolved


def quarantine_file(
    source: str | Path,
    quarantine_dir: str | Path | None = None,
    policy: SafetyPolicy | None = None,
) -> Path:
    """Move a file to quarantine without overwriting existing files."""

    policy = policy or SafetyPolicy()
    source_path = _validate_source(source, policy)

    if quarantine_dir is None:
        quarantine_dir = default_quarantine_dir()

    quarantine = _validate_quarantine_dir(
        quarantine_dir,
        source_path.parent,
        policy,
    )

    try:
        quarantine.mkdir(parents=True, exist_ok=True)

        if quarantine.is_symlink() or not quarantine.is_dir():
            raise FileOperationError(
                "Quarantine path is not a safe directory"
            )

        destination = quarantine / source_path.name

        return move_file_to_quarantine(
            source_path,
            destination,
            quarantine,
            policy,
        )

    except FileOperationError:
        raise
    except OSError as exc:
        raise FileOperationError(
            f"Could not prepare quarantine: {exc}"
        ) from exc


def move_file_to_quarantine(
    source: str | Path,
    destination: str | Path,
    quarantine_dir: Path,
    policy: SafetyPolicy,
) -> Path:
    """Internal quarantine move using the explicitly validated directory."""

    source_path = _validate_source(source, policy)
    original_signature = _signature_at(source_path)

    destination_path = _validate_destination(
        destination,
        policy,
        allowed_quarantine_dir=quarantine_dir,
    )

    _copy_file(
        source_path,
        destination_path,
        policy,
        allowed_quarantine_dir=quarantine_dir,
    )

    if _signature_at(source_path) != original_signature:
        raise FileOperationError(
            "Source changed after quarantine copy. Both files retained."
        )

    try:
        source_path.unlink()
    except OSError as exc:
        raise FileOperationError(
            "Quarantined copy exists, but original removal failed. "
            "Both files retained for review."
        ) from exc

    return destination_path