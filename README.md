# The Sanctum Keeper

**Offline, rule-based file organization — Backend Prototype**

The Sanctum Keeper is a Python backend prototype that organizes files using user-defined rules. It supports read-only previews, explicit execution confirmation, file-operation verification, and a local SQLite operation journal.

The prototype runs locally and does not use a remote API or cloud backend.

## Team

- **Team:** ObliqForge
- **Team ID:** 400
- **Members:** Mohammad Yalnaaz and Nipun Gupta
- **Event:** Softablitz 2026

## Implemented Features

- Rule conditions based on filename, extension, file size, and file age.
- Ordered rules with first-match-wins behavior.
- Safe scanning of direct-child files in selected folders.
- Filtering of temporary files such as `.part`, `.tmp`, and `.crdownload`.
- Read-only planning and destination-conflict checks.
- Rename, move, copy, and reversible quarantine file-operation primitives.
- Explicit confirmation before executing a planned operation.
- SHA-256 checks to verify file contents during supported operations.
- SQLite persistence for watched folders, rules, and operation history.
- Tests for rule matching, path safety, planning, file operations, persistence, and execution.

## Technology Stack

- Python 3.11+
- `pathlib`, `hashlib`, `shutil`, and other Python standard-library modules
- SQLite through Python's built-in `sqlite3`
- `unittest` for automated testing

No frontend UI or external database server is required for the current prototype.

## Setup

Install Python 3.11 or later and open a terminal in the project directory.

Check the installed Python version:

```powershell
python --version
```

No additional packages are needed for the current implementation.

## Run the Tests

```powershell
python -m unittest discover -s tests -v
```

The current test suite has passed **44 tests** in the development environment.

## Run the End-to-End Demo

```powershell
python demo.py
```

The demo creates an isolated temporary workspace containing sample files. It then:

1. Scans the sample folder.
2. Loads the saved rule from SQLite.
3. Builds and displays a read-only plan.
4. Requests explicit confirmation before execution.
5. Renames and moves the matching file.
6. Verifies the resulting file and displays operation history.

Type `YES` when prompted to execute the demo plan. Any other response cancels execution.

The demo uses temporary sample data and automatically cleans up its workspace when it exits.

## How the Backend Works

```text
Folder Scanner
      |
      v
Rule Engine
      |
      v
Read-only Planner
      |
      v
Explicit Confirmation
      |
      v
File Operations
      |
      v
SQLite Operation Journal
```

The scanner discovers eligible files, the rule engine finds the first matching enabled rule, and the planner calculates proposed actions without modifying files. The executor rechecks important preconditions before applying the confirmed plan and records operation outcomes in SQLite.

## Current Limitations

This is an early backend prototype, not a production-ready desktop application.

- No graphical user interface is included.
- Automatic background folder monitoring is not yet implemented.
- Undo functionality is not yet implemented.
- Advanced recovery of interrupted operations is not implemented.
- The demo validates a specific workflow; it does not prove every possible filesystem scenario is safe.

These limitations will be addressed in future development.

## Safety Notes

Run demonstrations only against disposable sample data. Never use important personal folders for testing. Review the preview before confirming any file operation, and keep backups of important files.

## License

No license has been specified yet.
