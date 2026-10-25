
from pathlib import Path
from tempfile import TemporaryDirectory

from sanctum_keeper.database import KeeperDatabase
from sanctum_keeper.executor import execute_plans
from sanctum_keeper.models import ActionSpec, Condition, Rule
from sanctum_keeper.planner import PlanStatus, plan_files
from sanctum_keeper.safety import SafetyPolicy
from sanctum_keeper.scanner import scan_folder


def main():
    # This demo uses an isolated temporary workspace.
    with TemporaryDirectory(prefix="sanctum_demo_") as temp:
        root = Path(temp)
        downloads = root / "Downloads"
        sorted_folder = root / "Sorted"
        downloads.mkdir()
        sorted_folder.mkdir()

        # Create harmless sample files.
        invoice = downloads / "invoice.pdf"
        invoice.write_bytes(b"%PDF-1.4\nSample invoice for demo\n")

        notes = downloads / "notes.txt"
        notes.write_text("These notes should remain unchanged.\n",
                         encoding="utf-8")

        # Keep all database activity inside the temporary workspace.
        database = KeeperDatabase(root / "keeper.sqlite3")
        policy = SafetyPolicy(include_platform_paths=False)

        database.add_watched_folder(downloads)

        # Rule: rename PDFs, then move them into Sorted.
        invoice_rule = Rule(
            name="Process PDF invoices",
            conditions=(
                Condition("extension", "equals", ".pdf"),
            ),
            actions=(
                ActionSpec("rename", "invoice_processed.pdf"),
                ActionSpec("move", str(sorted_folder)),
            ),
        )

        database.save_rules([invoice_rule])

        print("\n=== 1. SCAN ===")
        files = scan_folder(downloads, policy)

        for file in files:
            print(f"Found: {file.filename} ({file.size_bytes} bytes)")

        print("\n=== 2. LOAD RULES FROM SQLITE ===")
        rules = database.list_rules()

        for rule in rules:
            print(f"Rule: {rule.name} | Enabled: {rule.enabled}")

        print("\n=== 3. READ-ONLY PREVIEW ===")
        plans = plan_files(files, rules, policy=policy)

        for item in plans:
            print(f"\nFile: {item.source.name}")
            print(f"Matched rule: {item.rule_name or 'None'}")
            print(f"Status: {item.status.value}")

            for index, action in enumerate(item.actions, start=1):
                print(f"  {index}. {action.kind.value.upper()}")
                print(f"     From: {action.source}")
                print(f"     To:   {action.destination}")

            if item.reason:
                print(f"Reason: {item.reason}")

        # Prove the preview has not changed the files.
        assert invoice.exists(), "Preview unexpectedly changed the source"
        assert not (sorted_folder / "invoice_processed.pdf").exists(), (
            "Preview unexpectedly created the destination"
        )

        print("\nPreview check passed: no files changed.")

        # In a real interactive application, ask the user here.
        answer = input("\nExecute this preview? Type YES to continue: ")

        if answer.strip() != "YES":
            print("Execution cancelled. No planned operations executed.")
            return

        print("\n=== 4. EXECUTE CONFIRMED PLAN ===")
        results = execute_plans(
            plans,
            database,
            confirmed=True,
            policy=policy,
        )

        for result in results:
            print(
                f"{result.source.name}: {result.status}"
                + (
                    f" — {result.message}"
                    if result.message
                    else ""
                )
            )

        # Verify the main end-to-end result.
        final_invoice = sorted_folder / "invoice_processed.pdf"

        assert final_invoice.exists(), (
            "Expected processed invoice was not found"
        )
        assert not invoice.exists(), (
            "Original invoice still exists after the completed move"
        )
        assert notes.exists(), (
            "Unmatched notes file should remain untouched"
        )
        assert (
            final_invoice.read_bytes()
            == b"%PDF-1.4\nSample invoice for demo\n"
        ), "Final file content differs from the original"

        print("\n=== 5. SQLITE OPERATION HISTORY ===")
        history = database.list_operations()

        for entry in reversed(history):
            print(
                f"ID={entry['id']} | "
                f"Action={entry['operation_type']} | "
                f"Status={entry['status']}"
            )
            print(f"  Source:      {entry['source_path']}")
            print(f"  Destination: {entry['destination_path']}")

        assert len(history) == 2, (
            f"Expected 2 journal entries; got {len(history)}"
        )
        assert all(
            entry["status"] == "SUCCEEDED"
            for entry in history
        ), "One or more journal entries did not succeed"

        print("\nALL DEMO CHECKS PASSED.")
        print("Rename, move, preview and SQLite history verified.")


if __name__ == "__main__":
    main()
