
from dataclasses import dataclass
from pathlib import Path

from sanctum_keeper.database import KeeperDatabase
from sanctum_keeper.file_ops import (
    FileOperationError,
    compute_file_signature,
    copy_file,
    inspect_file_signature,
    move_file,
    quarantine_file,
    rename_file,
)
from sanctum_keeper.models import ActionType
from sanctum_keeper.planner import PlanItem, PlanStatus
from sanctum_keeper.safety import SafetyPolicy


class ExecutionNotConfirmedError(PermissionError):
    """Raised when execution is attempted without explicit confirmation."""


@dataclass(frozen=True)
class ExecutionResult:
    source: Path
    status: str
    completed_actions: int = 0
    message: str | None = None


def execute_plan_item(
    item: PlanItem,
    database: KeeperDatabase,
    *,
    confirmed: bool = False,
    policy: SafetyPolicy | None = None,
    quarantine_dir: str | Path | None = None,
) -> ExecutionResult:
    """Execute one previewed item after checking its preconditions."""

    if not confirmed:
        raise ExecutionNotConfirmedError(
            "Execution requires explicit confirmation."
        )

    policy = policy or SafetyPolicy()

    if item.status == PlanStatus.NO_MATCH:
        return ExecutionResult(
            item.source, "NO_MATCH", message=item.reason
        )

    if item.status == PlanStatus.BLOCKED:
        return ExecutionResult(
            item.source, "BLOCKED", message=item.reason
        )

    if not item.actions:
        return ExecutionResult(
            item.source, "NO_OP", message="No filesystem changes required"
        )

    # Reject plans that do not retain the initial preview metadata.
    if item.source_size is None or item.source_modified_at is None:
        return ExecutionResult(
            item.source,
            "STALE_PREVIEW",
            message="Plan is missing its original file metadata",
        )

    # Revalidate the source against the preview before doing anything.
    try:
        initial_signature = compute_file_signature(item.source, policy)
        current_stat = item.source.stat()
    except (OSError, RuntimeError, ValueError) as exc:
        return ExecutionResult(
            item.source,
            "STALE_PREVIEW",
            message=f"Cannot validate original source: {exc}",
        )

    if (
        initial_signature.size_bytes != item.source_size
        or current_stat.st_mtime != item.source_modified_at
    ):
        return ExecutionResult(
            item.source,
            "STALE_PREVIEW",
            message="File changed since preview; nothing was executed",
        )

    expected_signature = initial_signature
    completed = 0

    for action in item.actions:
        # Each action must receive the file state produced by the
        # preceding action, not an unexpectedly changed file.
        try:
            current_signature = compute_file_signature(
                action.source, policy
            )
        except (OSError, RuntimeError, ValueError) as exc:
            return ExecutionResult(
                item.source,
                "NEEDS_REVIEW",
                completed,
                f"Cannot validate action source: {exc}",
            )

        if current_signature != expected_signature:
            return ExecutionResult(
                item.source,
                "NEEDS_REVIEW",
                completed,
                f"Source changed before action: {action.source}",
            )

        # Record intent before attempting the filesystem mutation.
        try:
            operation_id = database.start_operation(
                action.kind,
                action.source,
                action.destination,
                source_size=current_signature.size_bytes,
                source_sha256=current_signature.sha256,
            )
        except Exception as exc:
            # No filesystem action has been attempted yet.
            return ExecutionResult(
                item.source,
                "FAILED",
                completed,
                f"Could not record operation intent: {exc}",
            )

        try:
            if action.kind == ActionType.RENAME:
                result_path = rename_file(
                    action.source,
                    action.destination.name,
                    policy,
                )

            elif action.kind == ActionType.MOVE:
                result_path = move_file(
                    action.source,
                    action.destination,
                    policy,
                )

            elif action.kind == ActionType.COPY:
                copy_file(
                    action.source,
                    action.destination,
                    policy,
                )
                result_path = action.destination

            elif action.kind == ActionType.QUARANTINE:
                if quarantine_dir is None:
                    raise FileOperationError(
                        "Pass the same quarantine directory used during preview"
                    )

                result_path = quarantine_file(
                    action.source,
                    quarantine_dir,
                    policy,
                )

            else:
                raise FileOperationError(
                    f"Unsupported action: {action.kind}"
                )

            result_path = Path(result_path).resolve(strict=False)
            expected_destination = action.destination.resolve(
                strict=False
            )

            if result_path != expected_destination:
                raise FileOperationError(
                    f"Operation produced an unexpected path: {result_path}"
                )

            # Verify the actual output content before logging success.
            result_signature = inspect_file_signature(result_path)

            if (
                result_signature.size_bytes != current_signature.size_bytes
                or result_signature.sha256 != current_signature.sha256
            ):
                raise FileOperationError(
                    "Output content did not match the original file"
                )

            database.finish_operation(
                operation_id,
                "SUCCEEDED",
                result_size=result_signature.size_bytes,
                result_sha256=result_signature.sha256,
            )

            expected_signature = result_signature
            completed += 1

        except Exception as exc:
            # An error can occur after some filesystem changes have
            # already happened. Never guess that nothing was changed.
            message = str(exc)

            try:
                database.finish_operation(
                    operation_id,
                    "NEEDS_REVIEW",
                    error=message,
                )
            except Exception as journal_error:
                message += (
                    f"; journal update failed: {journal_error}. "
                    "The operation may still be pending in the database."
                )

            return ExecutionResult(
                item.source,
                "NEEDS_REVIEW",
                completed,
                message,
            )

    return ExecutionResult(
        item.source,
        "SUCCEEDED",
        completed,
        "All planned actions completed and verified",
    )


def execute_plans(
    items: list[PlanItem],
    database: KeeperDatabase,
    *,
    confirmed: bool = False,
    policy: SafetyPolicy | None = None,
    quarantine_dir: str | Path | None = None,
) -> list[ExecutionResult]:
    """Execute a batch only after one explicit confirmation."""

    if not confirmed:
        raise ExecutionNotConfirmedError(
            "Preview the plans and obtain confirmation before execution."
        )

    results = []

    for item in items:
        result = execute_plan_item(
            item,
            database,
            confirmed=True,
            policy=policy,
            quarantine_dir=quarantine_dir,
        )
        results.append(result)

    return results
