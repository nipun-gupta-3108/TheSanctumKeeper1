from dataclasses import dataclass
from enum import Enum
from pathlib import Path
import time


class ConditionField(str, Enum):
    FILENAME = "filename"
    EXTENSION = "extension"
    SIZE_BYTES = "size_bytes"
    AGE_DAYS = "age_days"


class ConditionOperator(str, Enum):
    EQUALS = "equals"
    NOT_EQUALS = "not_equals"
    CONTAINS = "contains"
    STARTS_WITH = "starts_with"
    ENDS_WITH = "ends_with"
    GREATER_THAN = "gt"
    GREATER_OR_EQUAL = "gte"
    LESS_THAN = "lt"
    LESS_OR_EQUAL = "lte"


class ActionType(str, Enum):
    RENAME = "rename"
    MOVE = "move"
    COPY = "copy"
    QUARANTINE = "quarantine"


TEXT_OPERATORS = {
    ConditionOperator.EQUALS,
    ConditionOperator.NOT_EQUALS,
    ConditionOperator.CONTAINS,
    ConditionOperator.STARTS_WITH,
    ConditionOperator.ENDS_WITH,
}

NUMBER_OPERATORS = {
    ConditionOperator.EQUALS,
    ConditionOperator.NOT_EQUALS,
    ConditionOperator.GREATER_THAN,
    ConditionOperator.GREATER_OR_EQUAL,
    ConditionOperator.LESS_THAN,
    ConditionOperator.LESS_OR_EQUAL,
}

ALLOWED_OPERATORS = {
    ConditionField.FILENAME: TEXT_OPERATORS,
    ConditionField.EXTENSION: {
        ConditionOperator.EQUALS,
        ConditionOperator.NOT_EQUALS,
    },
    ConditionField.SIZE_BYTES: NUMBER_OPERATORS,
    ConditionField.AGE_DAYS: NUMBER_OPERATORS,
}


@dataclass(frozen=True)
class Condition:
    field: ConditionField
    operator: ConditionOperator
    value: str | int | float

    def __post_init__(self):
        try:
            field = ConditionField(self.field)
            operator = ConditionOperator(self.operator)
        except (ValueError, TypeError) as exc:
            raise ValueError("Invalid condition field or operator") from exc

        object.__setattr__(self, "field", field)
        object.__setattr__(self, "operator", operator)

        if operator not in ALLOWED_OPERATORS[field]:
            raise ValueError(
                f"Operator {operator.value} is not supported "
                f"for field {field.value}"
            )

        if field in {
            ConditionField.FILENAME,
            ConditionField.EXTENSION,
        }:
            if not isinstance(self.value, str) or not self.value:
                raise ValueError("Text conditions require a non-empty string")

        else:
            if (
                isinstance(self.value, bool)
                or not isinstance(self.value, (int, float))
                or self.value < 0
            ):
                raise ValueError(
                    "Numeric conditions require a non-negative number"
                )

            if field == ConditionField.SIZE_BYTES:
                if not isinstance(self.value, int):
                    raise ValueError("File size must be an integer in bytes")


@dataclass(frozen=True)
class ActionSpec:
    kind: ActionType
    target: str | None = None

    def __post_init__(self):
        try:
            kind = ActionType(self.kind)
        except (ValueError, TypeError) as exc:
            raise ValueError("Invalid action type") from exc

        object.__setattr__(self, "kind", kind)

        if kind == ActionType.RENAME:
            if not self.target:
                raise ValueError("Rename requires a new filename")

            invalid_chars = '<>:"/\\|?*'

            if (
                self.target in {".", ".."}
                or self.target.endswith((" ", "."))
                or any(char in self.target for char in invalid_chars)
            ):
                raise ValueError("Rename target must be a valid filename")

        elif kind in {ActionType.MOVE, ActionType.COPY}:
            if not self.target or not self.target.strip():
                raise ValueError(f"{kind.value} requires a destination folder")

        elif kind == ActionType.QUARANTINE:
            if self.target is not None:
                raise ValueError("Quarantine uses the configured app directory")


@dataclass(frozen=True)
class Rule:
    name: str
    conditions: tuple[Condition, ...]
    actions: tuple[ActionSpec, ...]
    enabled: bool = True

    def __post_init__(self):
        object.__setattr__(self, "conditions", tuple(self.conditions))
        object.__setattr__(self, "actions", tuple(self.actions))

        if not self.name.strip():
            raise ValueError("Rule name cannot be empty")

        if not self.conditions:
            raise ValueError("A rule must have at least one condition")

        if not self.actions:
            raise ValueError("A rule must have at least one action")


@dataclass(frozen=True)
class FileSnapshot:
    path: Path
    size_bytes: int
    modified_at: float
    captured_at: float

    @classmethod
    def from_path(cls, path: Path) -> "FileSnapshot":
        path = Path(path).resolve(strict=True)

        if not path.is_file():
            raise ValueError(f"Not a regular file: {path}")

        stat = path.stat()

        return cls(
            path=path,
            size_bytes=stat.st_size,
            modified_at=stat.st_mtime,
            captured_at=time.time(),
        )

    @property
    def filename(self) -> str:
        return self.path.name

    @property
    def extension(self) -> str:
        return self.path.suffix.lower()

    @property
    def age_days(self) -> float:
        elapsed = max(0.0, self.captured_at - self.modified_at)
        return elapsed / 86400