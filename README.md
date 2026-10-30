# The Sanctum Keeper

**Offline, rule-driven file organization for Windows**

The Sanctum Keeper is a local desktop file organizer. Users select folders, define ordered rules, inspect a read-only preview of proposed file operations, and explicitly confirm execution. The application records attempted operations in a local SQLite journal.

The project is developed by **Team ObliqForge** for **Softablitz 2026**.

## Team

- **Team:** ObliqForge
- **Team ID:** 400
- **Members:** Mohammad Yalnaaz and Nipun Gupta
- **Event:** Softablitz 2026

## Current Features

### Desktop application

- PySide6 desktop interface with **Folders**, **Rules**, **Preview**, and **History** tabs.
- Add and remove up to three watched folders.
- Validate selected folders and reject protected, root, and overlapping folder paths.
- Persist watched-folder configuration and rules in SQLite.

### Rule builder

- Create and edit rules through a visual rule editor.
- Conditions can inspect filename, extension, file size (bytes), and file age (days).
- Multiple conditions in one rule are combined with AND semantics.
- Supported text and numeric comparison operators are validated by the rule model.
- Rules can be enabled or disabled, deleted, and reordered.
- Enabled rules are evaluated in order; the first matching rule wins.

### Preview and execution

- Scan direct-child files in selected folders; scanning is non-recursive.
- Ignore incomplete download files with `.part`, `.tmp`, and `.crdownload` suffixes.
- Preview proposed rename, move, copy, and app-managed quarantine actions.
- Show matched rule, planned actions, destination, status, and planning details.
- Preview is read-only. No file mutation occurs while the plan is being built.
- Require explicit user confirmation before executing a plan.
- Revalidate file state before execution and avoid overwriting existing destinations.
- Use SHA-256 verification in supported file operations.

### Operation history

- Record operation intents and outcomes in a local SQLite journal.
- Display operation type, source, destination, status, timestamp, and error details.
- Refresh the history view from the local database.

## Technology Stack

- Python 3.11+
- PySide6 / Qt Widgets
- SQLite through Python's built-in `sqlite3` module
- Python standard library: `pathlib`, `hashlib`, `shutil`, and related modules
- pytest for automated tests

The application does not require a remote API, cloud backend, or external database server.

## Setup

The current desktop application targets Windows 10/11.

1. Install Python 3.11 or later.
2. Clone the repository and open a terminal in the project directory.
3. Create and activate a virtual environment:

   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```

4. Install the project dependencies:

   ```powershell
   python -m pip install --upgrade pip
   python -m pip install -r requirements.txt
   ```

## Run the Desktop Application

From the repository root, with the virtual environment activated:

```powershell
python app.py
```

On Windows, the SQLite database is stored under:

```text
%LOCALAPPDATA%\TheSanctumKeeper\keeper.sqlite3
```

This keeps application data separate from the folders selected for organization.

## Run the Tests

```powershell
python -m pytest
```

## Run the Backend Demonstration

The command-line demonstration creates an isolated temporary workspace and sample files. It scans the workspace, loads a saved rule, displays a read-only plan, asks for explicit confirmation, executes the sample operation, and verifies the resulting file and operation history.

```powershell
python demo.py
```

Type `YES` only when you want the temporary demonstration to execute its planned operation. Any other response cancels it. The temporary workspace is cleaned up when the demo exits.

## Architecture Overview

```text
PySide6 Desktop UI
      |
      +---- Folder selection and visual rule management
      |
      +---- Read-only preview request
                    |
                    v
              Folder Scanner
                    |
                    v
                Rule Engine
                    |
                    v
              Read-only Planner
                    |
             User confirmation
                    |
                    v
                 Executor
                    |
                    v
             Safe File Operations
                    |
                    v
           SQLite Operation Journal
```

The GUI uses the existing scanner, rule engine, planner, executor, file-operation helpers, and SQLite database layer. The planner calculates proposed operations without performing filesystem mutations. The executor rechecks important preconditions before applying a confirmed plan and records operation outcomes.

## Current Limitations / Work in Progress

The following items are **not yet implemented in the current repository version**:

- Automatic background monitoring of watched folders for newly arriving files.
- Undo controls and safe reversal of recorded operations.
- Recovery classification for unfinished operations after an application restart.
- Background worker integration for scanning and execution. These tasks currently run synchronously from the GUI, so large jobs may temporarily make the interface unresponsive.
- PyInstaller packaging and a distributable Windows executable.

The current GUI supports explicit, user-triggered preview and execution. It does not automatically process new files in the background.

## Safety Notes

- Test only with disposable sample folders before using the application with personal data.
- Review the preview carefully before confirming file operations.
- Keep backups of important files.
- Existing destinations are not intentionally overwritten.
- The application is an evolving hackathon prototype, not yet a production-grade file management utility.

## License

No license has been specified yet.
