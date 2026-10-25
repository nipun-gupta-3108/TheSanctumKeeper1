import os
from dataclasses import dataclass
from pathlib import Path
from collections.abc import Sequence


class PathValidationError(ValueError):
    """Raised when a folder is not safe to watch."""


@dataclass(frozen=True)
class SafetyPolicy:
    max_watched_folders: int = 3
    protected_paths: tuple[Path, ...] = ()
    include_platform_paths: bool = True

    def __post_init__(self):
        if (
            isinstance(self.max_watched_folders, bool)
            or not isinstance(self.max_watched_folders, int)
            or self.max_watched_folders < 1
        ):
            raise ValueError("Maximum watched folders must be positive")

        paths = tuple(Path(path).expanduser() for path in self.protected_paths)
        object.__setattr__(self, "protected_paths", paths)


def platform_protected_paths() -> tuple[Path, ...]:
    """Return common Windows system and application-data locations."""

    if os.name != "nt":
        return ()

    paths = []

    environment_names = (
        "WINDIR",
        "ProgramFiles",
        "ProgramFiles(x86)",
        "ProgramData",
        "APPDATA",
        "LOCALAPPDATA",
    )

    for name in environment_names:
        value = os.environ.get(name)
        if value:
            paths.append(Path(value))

    # Protect the parent AppData folder too, not just Local and Roaming.
    local_appdata = os.environ.get("LOCALAPPDATA")
    if local_appdata:
        paths.append(Path(local_appdata).parent)

    # Resolve and remove duplicate paths.
    resolved = {
        path.expanduser().resolve(strict=False)
        for path in paths
    }

    return tuple(sorted(resolved, key=str))


def _is_within(path: Path, parent: Path) -> bool:
    try:
        return path == parent or path.is_relative_to(parent)
    except ValueError:
        # Different Windows drives cannot contain one another.
        return False


def _paths_overlap(first: Path, second: Path) -> bool:
    """True if either path is the same as, or inside, the other."""

    return _is_within(first, second) or _is_within(second, first)


def validate_watch_folder(
    folder: str | Path,
    policy: SafetyPolicy | None = None,
) -> Path:
    """Validate and return the canonical path of one watched folder."""

    policy = policy or SafetyPolicy()
    candidate = Path(folder).expanduser()

    if candidate.is_symlink():
        raise PathValidationError("Symbolic-link folders cannot be watched")

    try:
        resolved = candidate.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise PathValidationError(
            f"Folder does not exist or cannot be accessed: {candidate}"
        ) from exc

    if not resolved.is_dir():
        raise PathValidationError(f"Not a directory: {resolved}")

    # Reject filesystem roots, e.g. C:\ or /.
    if resolved.parent == resolved:
        raise PathValidationError("Filesystem roots cannot be watched")

    protected = list(policy.protected_paths)

    if policy.include_platform_paths:
        protected.extend(platform_protected_paths())

    for protected_path in protected:
        protected_resolved = protected_path.resolve(strict=False)

        if _paths_overlap(resolved, protected_resolved):
            raise PathValidationError(
                f"Folder overlaps a protected location: {protected_resolved}"
            )

    return resolved


def validate_watch_folders(
    folders: Sequence[str | Path],
    policy: SafetyPolicy | None = None,
) -> tuple[Path, ...]:
    """Validate a complete list of watched folders."""

    policy = policy or SafetyPolicy()

    if len(folders) > policy.max_watched_folders:
        raise PathValidationError(
            f"At most {policy.max_watched_folders} folders can be watched"
        )

    resolved_folders = tuple(
        validate_watch_folder(folder, policy)
        for folder in folders
    )

    for index, current in enumerate(resolved_folders):
        for other in resolved_folders[index + 1:]:
            if _paths_overlap(current, other):
                raise PathValidationError(
                    f"Watched folders must not overlap: "
                    f"{current} and {other}"
                )

    return resolved_folders