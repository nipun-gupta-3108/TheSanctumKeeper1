
import os
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from collections.abc import Sequence

from sanctum_keeper.models import (
    ActionType,
    FileSnapshot,
    Rule,
)
from sanctum_keeper.rules import first_matching_rule
from sanctum_keeper.safety import (
    PathValidationError,
    SafetyPolicy,
    validate_watch_folder,
)


class PlanStatus(str, Enum):
    READY = "READY"
    NO_MATCH = "NO_MATCH"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True)
class PlannedAction:
    kind: ActionType
    source: Path
    destination: Path


@dataclass(frozen=True)
class PlanItem:
    source: Path
    rule_name: str | None
    actions: tuple[PlannedAction, ...]
    status: PlanStatus
    reason: str | None = None

    @property
    def final_path(self) -> Path:
        if self.actions:
            return self.actions[-1].destination
        return self.source


def _path_key(path: Path) -> str:
    """Use case-insensitive comparison for Windows-style file paths."""
    return os.path.normcase(str(path.resolve(strict=False))).casefold()


def _overlaps(first: Path, second: Path) -> bool:
    first = first.resolve(strict=False)
    second = second.resolve(strict=False)

    try:
        return (
            first == second
            or first.is_relative_to(second)
            or second.is_relative_to(first)
        )
    except ValueError:
        return False


def _validate_quarantine_directory(
    folder: Path,
    source_parent: Path,
    policy: SafetyPolicy,
) -> Path:
    """Validate the configured quarantine destination without creating it."""

    folder = folder.expanduser()

    if folder.is_symlink():
        raise PathValidationError(
            "Quarantine directory cannot be a symbolic link"
        )

    folder = folder.resolve(strict=False)

    if folder.parent == folder:
        raise PathValidationError(
            "Filesystem roots cannot be quarantine directories"
        )

    if folder.exists() and not folder.is_dir():
        raise PathValidationError(
            "Quarantine destination is not a directory"
        )

    if _overlaps(folder, source_parent):
        raise PathValidationError(
            "Quarantine directory must be separate from the watched folder"
        )

    for protected in policy.protected_paths:
        if _overlaps(folder, protected):
            raise PathValidationError(
                "Quarantine directory overlaps a protected path"
            )

    # On Windows, never allow quarantine inside system/application
    # installation directories. The designated app-data quarantine is
    # handled separately from ordinary user-selected destinations.
    if policy.include_platform_paths and os.name == "nt":
        for name in (
            "WINDIR",
            "ProgramFiles",
            "ProgramFiles(x86)",
            "ProgramData",
        ):
            value = os.environ.get(name)
            if value and _overlaps(folder, Path(value)):
                raise PathValidationError(
                    f"Quarantine overlaps protected system path: {value}"
                )

        appdata_roots = [
            os.environ.get("APPDATA"),
            os.environ.get("LOCALAPPDATA"),
        ]

        for value in appdata_roots:
            if not value:
                continue

            appdata = Path(value).resolve(strict=False)

            if _overlaps(folder, appdata):
                expected = (
                    appdata / "TheSanctumKeeper" / "quarantine"
                ).resolve(strict=False)

                if _path_key(folder) != _path_key(expected):
                    raise PathValidationError(
                        "Only the designated app quarantine may be "
                        "inside application data"
                    )

    return folder


def plan_file(
    file: FileSnapshot,
    rules: Sequence[Rule],
    *,
    quarantine_dir: str | Path | None = None,
    policy: SafetyPolicy | None = None,
    reserved_targets: set[str] | None = None,
) -> PlanItem:
    """
    Build a plan for one file. This function never changes file contents
    or performs rename, move, copy, or quarantine operations.
    """

    policy = policy or SafetyPolicy()
    reserved_targets = reserved_targets if reserved_targets is not None else set()

    matched_rule = first_matching_rule(file, rules)

    if matched_rule is None:
        return PlanItem(
            source=file.path,
            rule_name=None,
            actions=(),
            status=PlanStatus.NO_MATCH,
            reason="No enabled rule matched",
        )

    current = file.path.resolve(strict=True)
    planned_actions: list[PlannedAction] = []
    pending_targets: set[str] = set()

    try:
        for index, spec in enumerate(matched_rule.actions):
            if spec.kind == ActionType.RENAME:
                destination = current.with_name(spec.target)

            elif spec.kind in {ActionType.MOVE, ActionType.COPY}:
                destination_folder = validate_watch_folder(
                    spec.target,
                    policy,
                )
                destination = destination_folder / current.name

            elif spec.kind == ActionType.QUARANTINE:
                if index != len(matched_rule.actions) - 1:
                    raise ValueError(
                        "Quarantine must be the final action in a rule"
                    )

                if quarantine_dir is None:
                    raise ValueError(
                        "A quarantine directory has not been configured"
                    )

                destination_folder = _validate_quarantine_directory(
                    Path(quarantine_dir),
                    current.parent,
                    policy,
                )
                destination = destination_folder / current.name

            else:
                raise ValueError(f"Unsupported action: {spec.kind}")

            destination = destination.resolve(strict=False)
            destination_key = _path_key(destination)
            current_key = _path_key(current)

            # An action targeting the same path is a no-op.
            if destination_key == current_key:
                continue

            # Never plan to overwrite an existing file or symlink.
            if destination.exists() or destination.is_symlink():
                raise ValueError(
                    f"Destination already exists: {destination}"
                )

            # Prevent two planned files from using the same destination.
            if (
                destination_key in reserved_targets
                or destination_key in pending_targets
            ):
                raise ValueError(
                    f"Destination is reserved by another planned action: "
                    f"{destination}"
                )

            planned_actions.append(
                PlannedAction(
                    kind=spec.kind,
                    source=current,
                    destination=destination,
                )
            )

            pending_targets.add(destination_key)

            # Simulate the action chain. After COPY, subsequent actions
            # operate on the copied path, leaving the original untouched.
            current = destination

    except (OSError, ValueError, RuntimeError) as exc:
        return PlanItem(
            source=file.path,
            rule_name=matched_rule.name,
            actions=tuple(planned_actions),
            status=PlanStatus.BLOCKED,
            reason=str(exc),
        )

    reserved_targets.update(pending_targets)

    return PlanItem(
        source=file.path,
        rule_name=matched_rule.name,
        actions=tuple(planned_actions),
        status=PlanStatus.READY,
        reason=(
            "No filesystem changes required"
            if not planned_actions
            else None
        ),
    )


def plan_files(
    files: Sequence[FileSnapshot],
    rules: Sequence[Rule],
    *,
    quarantine_dir: str | Path | None = None,
    policy: SafetyPolicy | None = None,
) -> list[PlanItem]:
    """Plan multiple files while detecting destination collisions."""

    reserved_targets: set[str] = set()
    results = []

    for file in files:
        result = plan_file(
            file,
            rules,
            quarantine_dir=quarantine_dir,
            policy=policy,
            reserved_targets=reserved_targets,
        )
        results.append(result)

    return results
