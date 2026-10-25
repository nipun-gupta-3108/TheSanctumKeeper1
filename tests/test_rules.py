import unittest
from pathlib import Path

from sanctum_keeper.models import (
    ActionSpec,
    Condition,
    FileSnapshot,
    Rule,
)
from sanctum_keeper.rules import (
    condition_matches,
    first_matching_rule,
)


class RuleEngineTests(unittest.TestCase):
    def setUp(self):
        self.file = FileSnapshot(
            path=Path("/virtual/Invoice.PDF"),
            size_bytes=2 * 1024 * 1024,
            modified_at=1_000,
            captured_at=1_000 + (10 * 86400),
        )

    def test_filename_matching_is_case_insensitive(self):
        condition = Condition("filename", "contains", "invoice")

        self.assertTrue(condition_matches(condition, self.file))

    def test_extension_matching_is_case_insensitive(self):
        condition = Condition("extension", "equals", ".pdf")

        self.assertTrue(condition_matches(condition, self.file))

    def test_size_condition(self):
        condition = Condition("size_bytes", "gt", 1_048_576)

        self.assertTrue(condition_matches(condition, self.file))

    def test_age_condition(self):
        condition = Condition("age_days", "gte", 10)

        self.assertTrue(condition_matches(condition, self.file))

    def test_first_matching_enabled_rule_wins(self):
        first = Rule(
            name="Invoice rule",
            conditions=(
                Condition("filename", "contains", "invoice"),
                Condition("extension", "equals", ".pdf"),
            ),
            actions=(ActionSpec("move", "/virtual/invoices"),),
        )

        second = Rule(
            name="Generic PDF rule",
            conditions=(Condition("extension", "equals", ".pdf"),),
            actions=(ActionSpec("move", "/virtual/pdfs"),),
        )

        disabled = Rule(
            name="Disabled rule",
            conditions=(Condition("filename", "contains", "invoice"),),
            actions=(ActionSpec("move", "/virtual/disabled"),),
            enabled=False,
        )

        result = first_matching_rule(
            self.file,
            [disabled, first, second],
        )

        self.assertIsNotNone(result)
        self.assertEqual(result.name, "Invoice rule")

    def test_returns_none_when_nothing_matches(self):
        rule = Rule(
            name="Image rule",
            conditions=(Condition("extension", "equals", ".png"),),
            actions=(ActionSpec("move", "/virtual/images"),),
        )

        self.assertIsNone(first_matching_rule(self.file, [rule]))

    def test_invalid_operator_for_extension_is_rejected(self):
        with self.assertRaises(ValueError):
            Condition("extension", "contains", ".pdf")


if __name__ == "__main__":
    unittest.main()