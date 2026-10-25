from collections.abc import Sequence

from sanctum_keeper.models import (
    Condition,
    ConditionField,
    ConditionOperator,
    FileSnapshot,
    Rule,
)


def condition_matches(
    condition: Condition,
    file: FileSnapshot,
) -> bool:
    if condition.field == ConditionField.FILENAME:
        actual = file.filename.casefold()
        expected = str(condition.value).casefold()

    elif condition.field == ConditionField.EXTENSION:
        actual = file.extension.casefold()
        expected = str(condition.value).casefold()

    elif condition.field == ConditionField.SIZE_BYTES:
        actual = file.size_bytes
        expected = condition.value

    else:
        actual = file.age_days
        expected = condition.value

    operator = condition.operator

    if operator == ConditionOperator.EQUALS:
        return actual == expected

    if operator == ConditionOperator.NOT_EQUALS:
        return actual != expected

    if operator == ConditionOperator.CONTAINS:
        return expected in actual

    if operator == ConditionOperator.STARTS_WITH:
        return actual.startswith(expected)

    if operator == ConditionOperator.ENDS_WITH:
        return actual.endswith(expected)

    if operator == ConditionOperator.GREATER_THAN:
        return actual > expected

    if operator == ConditionOperator.GREATER_OR_EQUAL:
        return actual >= expected

    if operator == ConditionOperator.LESS_THAN:
        return actual < expected

    if operator == ConditionOperator.LESS_OR_EQUAL:
        return actual <= expected

    raise ValueError(f"Unsupported operator: {operator}")


def rule_matches(rule: Rule, file: FileSnapshot) -> bool:
    if not rule.enabled:
        return False

    return all(
        condition_matches(condition, file)
        for condition in rule.conditions
    )


def first_matching_rule(
    file: FileSnapshot,
    rules: Sequence[Rule],
) -> Rule | None:
    for rule in rules:
        if rule_matches(rule, file):
            return rule

    return None