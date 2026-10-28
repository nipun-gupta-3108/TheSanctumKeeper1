
from pathlib import Path
from PySide6.QtWidgets import QDialog

from sanctum_keeper.gui.rule_editor import RuleEditorDialog
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)
from PySide6.QtWidgets import (
    QHeaderView,
    QTableWidget,
    QTableWidgetItem,
)

from sanctum_keeper.executor import execute_plans
from sanctum_keeper.file_ops import default_quarantine_dir
from sanctum_keeper.planner import PlanStatus, plan_files
from sanctum_keeper.scanner import scan_folders
from sanctum_keeper.database import KeeperDatabase
from sanctum_keeper.safety import (
    PathValidationError,
    SafetyPolicy,
    validate_watch_folder,
    validate_watch_folders,
)


class MainWindow(QMainWindow):
    def __init__(self, database: KeeperDatabase):
        super().__init__()

        self.database = database
        self.policy = SafetyPolicy()

        self.setWindowTitle("The Sanctum Keeper")
        self.resize(1100, 700)

        self._build_ui()
        self.refresh_folders()
        self.refresh_rules()
        self.refresh_history()

    def _build_ui(self):
        central = QWidget()
        root_layout = QVBoxLayout(central)

        title = QLabel("The Sanctum Keeper")
        title.setStyleSheet(
            "font-size: 25px; font-weight: bold;"
        )

        subtitle = QLabel(
            "Offline, rule-driven file organization"
        )

        root_layout.addWidget(title)
        root_layout.addWidget(subtitle)

        self.tabs = QTabWidget()
        root_layout.addWidget(self.tabs)

        # Tab 1: Watched folders
        folder_page = QWidget()
        folder_layout = QVBoxLayout(folder_page)

        folder_layout.addWidget(
            QLabel("Choose up to three folders to manage.")
        )

        self.folder_list = QListWidget()
        self.folder_list.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )

        folder_layout.addWidget(self.folder_list)

        folder_buttons = QHBoxLayout()

        self.add_folder_button = QPushButton("Add Folder")
        self.remove_folder_button = QPushButton(
            "Remove Selected"
        )

        self.add_folder_button.clicked.connect(
            self.add_folder
        )
        self.remove_folder_button.clicked.connect(
            self.remove_folder
        )

        folder_buttons.addWidget(self.add_folder_button)
        folder_buttons.addWidget(self.remove_folder_button)

        folder_layout.addLayout(folder_buttons)

        self.tabs.addTab(folder_page, "Folders")

        # Temporary placeholders for later implementation
        self.tabs.addTab(self._build_rules_page(), "Rules")

        self.tabs.addTab(self._build_preview_page(), "Preview")

        self.tabs.addTab(self._build_history_page(), "History")

        self.setCentralWidget(central)

    @staticmethod
    def _placeholder(title_text: str, description: str):
        page = QWidget()
        layout = QVBoxLayout(page)

        title = QLabel(title_text)
        title.setStyleSheet(
            "font-size: 20px; font-weight: bold;"
        )

        message = QLabel(description)
        message.setWordWrap(True)

        layout.addWidget(title)
        layout.addWidget(message)
        layout.addStretch()

        return page

    def refresh_folders(self):
        self.folder_list.clear()

        for folder in self.database.list_watched_folders():
            item = QListWidgetItem(str(folder))

            # Store the actual path separately from display text.
            item.setData(
                Qt.ItemDataRole.UserRole,
                str(folder),
            )

            if not folder.is_dir():
                item.setToolTip(
                    "This folder no longer exists. Remove it "
                    "and select a valid folder."
                )

            self.folder_list.addItem(item)

    def add_folder(self):
        selected = QFileDialog.getExistingDirectory(
            self,
            "Select a folder to watch",
        )

        if not selected:
            return

        folder = Path(selected).expanduser()

        try:
            folder = validate_watch_folder(
                folder,
                self.policy,
            )

            saved_folders = (
                self.database.list_watched_folders()
            )

            if any(
                old.resolve(strict=False)
                == folder.resolve(strict=False)
                for old in saved_folders
            ):
                QMessageBox.information(
                    self,
                    "Already Added",
                    "This folder is already in the list.",
                )
                return

            if len(saved_folders) >= 3:
                QMessageBox.warning(
                    self,
                    "Folder Limit",
                    "You can select at most three folders.",
                )
                return

            # Ignore invalid stale entries when checking the
            # current valid folders for path overlap.
            valid_existing = []

            for old in saved_folders:
                try:
                    valid_existing.append(
                        validate_watch_folder(
                            old,
                            self.policy,
                        )
                    )
                except (PathValidationError, OSError):
                    continue

            validate_watch_folders(
                [*valid_existing, folder],
                self.policy,
            )

            self.database.add_watched_folder(folder)
            self.refresh_folders()

        except (PathValidationError, OSError, ValueError) as exc:
            QMessageBox.warning(
                self,
                "Folder Cannot Be Added",
                str(exc),
            )

        except Exception as exc:
            QMessageBox.critical(
                self,
                "Error",
                f"Could not save the folder:\n{exc}",
            )

    def remove_folder(self):
        item = self.folder_list.currentItem()

        if item is None:
            QMessageBox.information(
                self,
                "Select a Folder",
                "Select a folder to remove first.",
            )
            return

        folder = Path(
            item.data(Qt.ItemDataRole.UserRole)
        )

        removed = self.database.remove_watched_folder(folder)

        if not removed:
            QMessageBox.warning(
                self,
                "Not Found",
                "The folder was not present in the database.",
            )

        self.refresh_folders()
    
    def _build_rules_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)

        layout.addWidget(
            QLabel(
                "Rules execute in order. "
                "The first matching enabled rule wins."
            )
        )

        self.rule_list = QListWidget()
        self.rule_list.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        layout.addWidget(self.rule_list)

        buttons = QHBoxLayout()

        self.new_rule_button = QPushButton("New Rule")
        self.edit_rule_button = QPushButton("Edit Rule")
        self.delete_rule_button = QPushButton("Delete Rule")
        self.move_up_button = QPushButton("Move Up")
        self.move_down_button = QPushButton("Move Down")

        buttons.addWidget(self.new_rule_button)
        buttons.addWidget(self.edit_rule_button)
        buttons.addWidget(self.delete_rule_button)
        buttons.addWidget(self.move_up_button)
        buttons.addWidget(self.move_down_button)

        layout.addLayout(buttons)

        self.new_rule_button.clicked.connect(self.add_rule)
        self.edit_rule_button.clicked.connect(self.edit_rule)
        self.delete_rule_button.clicked.connect(self.delete_rule)
        self.move_up_button.clicked.connect(
            lambda: self.move_rule(-1)
        )
        self.move_down_button.clicked.connect(
            lambda: self.move_rule(1)
        )

        self.rule_list.itemDoubleClicked.connect(
            lambda _item: self.edit_rule()
        )

        return page

    def refresh_rules(self, select_index=None):
        self.rule_list.clear()
        rules = self.database.list_rules()

        for index, rule in enumerate(rules):
            status = "Enabled" if rule.enabled else "Disabled"

            item = QListWidgetItem(
                f"{index + 1}. {rule.name} | {status}"
            )
            item.setData(Qt.ItemDataRole.UserRole, index)
            self.rule_list.addItem(item)

        if select_index is not None:
            if 0 <= select_index < self.rule_list.count():
                self.rule_list.setCurrentRow(select_index)

    def _selected_rule_index(self):
        item = self.rule_list.currentItem()

        if item is None:
            QMessageBox.information(
                self,
                "Select a Rule",
                "Please select a rule first.",
            )
            return None

        return item.data(Qt.ItemDataRole.UserRole)

    def _persist_rules(self, rules, select_index=None):
        try:
            self.database.save_rules(rules)
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Save Failed",
                str(exc),
            )
            self.refresh_rules()
            return

        self.refresh_rules(select_index)

    def add_rule(self):
        dialog = RuleEditorDialog(self)

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        rule = dialog.get_rule()

        if rule is None:
            return

        rules = self.database.list_rules()
        rules.append(rule)

        self._persist_rules(rules, len(rules) - 1)

    def edit_rule(self):
        index = self._selected_rule_index()

        if index is None:
            return

        rules = self.database.list_rules()
        dialog = RuleEditorDialog(self, rules[index])

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        updated_rule = dialog.get_rule()

        if updated_rule is None:
            return

        rules[index] = updated_rule
        self._persist_rules(rules, index)

    def delete_rule(self):
        index = self._selected_rule_index()

        if index is None:
            return

        answer = QMessageBox.question(
            self,
            "Delete Rule",
            "Are you sure you want to delete this rule?",
            QMessageBox.StandardButton.Yes
            | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if answer != QMessageBox.StandardButton.Yes:
            return

        rules = self.database.list_rules()
        rules.pop(index)

        next_index = min(index, len(rules) - 1)

        self._persist_rules(
            rules,
            next_index if next_index >= 0 else None,
        )

    def move_rule(self, offset):
        index = self._selected_rule_index()

        if index is None:
            return

        rules = self.database.list_rules()
        new_index = index + offset

        if not 0 <= new_index < len(rules):
            return

        rules[index], rules[new_index] = (
            rules[new_index],
            rules[index],
        )

        self._persist_rules(rules, new_index)
    
    def _build_preview_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)

        layout.addWidget(
            QLabel(
                "Review planned file operations before execution. "
                "Building a preview does not modify files."
            )
        )

        buttons = QHBoxLayout()

        self.build_preview_button = QPushButton("Build Preview")
        self.execute_preview_button = QPushButton(
            "Confirm and Execute"
        )

        self.execute_preview_button.setEnabled(False)

        self.build_preview_button.clicked.connect(
            self.build_preview
        )
        self.execute_preview_button.clicked.connect(
            self.execute_preview
        )

        buttons.addWidget(self.build_preview_button)
        buttons.addWidget(self.execute_preview_button)

        layout.addLayout(buttons)

        self.preview_table = QTableWidget(0, 6)
        self.preview_table.setHorizontalHeaderLabels(
            [
                "Source",
                "Matched Rule",
                "Actions",
                "Final Destination",
                "Status",
                "Details",
            ]
        )

        self.preview_table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self.preview_table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.preview_table.setAlternatingRowColors(True)

        header = self.preview_table.horizontalHeader()
        header.setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents
        )
        header.setStretchLastSection(True)

        layout.addWidget(self.preview_table)

        self.current_plans = []
        self.quarantine_dir = None

        return page

    def build_preview(self):
        folders = self.database.list_watched_folders()
        rules = self.database.list_rules()

        self.current_plans = []
        self.preview_table.setRowCount(0)
        self.execute_preview_button.setEnabled(False)

        if not folders:
            QMessageBox.information(
                self,
                "No Folders",
                "Add a watched folder before building a preview.",
            )
            return

        if not rules:
            QMessageBox.information(
                self,
                "No Rules",
                "Create at least one rule before building a preview.",
            )
            return

        try:
            # Create the configured quarantine path reference.
            # This does not itself move any files.
            self.quarantine_dir = default_quarantine_dir()

            # Scan only the validated direct-child files.
            files = scan_folders(
                folders,
                policy=self.policy,
            )

            # Build a read-only plan.
            plans = plan_files(
                files,
                rules,
                policy=self.policy,
                quarantine_dir=self.quarantine_dir,
            )

        except Exception as exc:
            QMessageBox.critical(
                self,
                "Preview Failed",
                str(exc),
            )
            return

        self.current_plans = plans
        self.preview_table.setRowCount(len(plans))

        for row, plan in enumerate(plans):
            action_text = " -> ".join(
                (
                    f"{action.kind.value}: "
                    f"{action.source.name} -> "
                    f"{action.destination}"
                )
                for action in plan.actions
            )

            values = [
                str(plan.source),
                plan.rule_name or "-",
                action_text or "-",
                str(plan.final_path),
                plan.status.value,
                plan.reason or "",
            ]

            for column, value in enumerate(values):
                self.preview_table.setItem(
                    row,
                    column,
                    QTableWidgetItem(value),
                )

        executable_count = sum(
            1
            for plan in plans
            if plan.status == PlanStatus.READY and plan.actions
        )

        self.execute_preview_button.setEnabled(
            executable_count > 0
        )

        QMessageBox.information(
            self,
            "Preview Ready",
            f"Files scanned: {len(files)}\n"
            f"Plans created: {len(plans)}\n"
            f"Executable plans: {executable_count}\n\n"
            "Review the table before executing anything.",
        )

    def execute_preview(self):
        plans = self.current_plans

        executable_count = sum(
            1
            for plan in plans
            if plan.status == PlanStatus.READY and plan.actions
        )

        if executable_count == 0:
            QMessageBox.information(
                self,
                "Nothing to Execute",
                "Build a fresh preview containing executable plans.",
            )
            return

        answer = QMessageBox.warning(
            self,
            "Confirm File Operations",
            f"Execute {executable_count} file plan(s)?\n\n"
            "Files may be renamed, moved, copied or quarantined. "
            "Review the preview and confirm only if it is correct.",
            QMessageBox.StandardButton.Yes
            | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if answer != QMessageBox.StandardButton.Yes:
            return

        self.execute_preview_button.setEnabled(False)

        try:
            results = execute_plans(
                plans,
                self.database,
                confirmed=True,
                policy=self.policy,
                quarantine_dir=self.quarantine_dir,
            )

        except Exception as exc:
            QMessageBox.critical(
                self,
                "Execution Failed",
                str(exc),
            )
            return

        succeeded = 0
        failed = 0

        for row, result in enumerate(results):
            if result.status == "SUCCEEDED":
                succeeded += 1
            elif result.status not in {"NO_MATCH", "NO_OP"}:
                failed += 1

            self.preview_table.setItem(
                row,
                4,
                QTableWidgetItem(result.status),
            )

            self.preview_table.setItem(
                row,
                5,
                QTableWidgetItem(result.message or ""),
            )

        # An executed preview must not be reused.
        self.current_plans = []

        # Reload operation history from SQLite.
        self.refresh_history()

        QMessageBox.information(
            self,
            "Execution Finished",
            f"Successful actions: {succeeded}\n"
            f"Failed or review-required items: {failed}\n\n"
            "Build a fresh preview before the next execution.",
        )
    
    def _build_history_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)

        title = QLabel("Operation History")
        title.setStyleSheet(
            "font-size: 20px; font-weight: bold;"
        )
        layout.addWidget(title)

        layout.addWidget(
            QLabel(
                "Review file operations recorded in the local SQLite journal."
            )
        )

        self.history_table = QTableWidget(0, 7)

        self.history_table.setHorizontalHeaderLabels(
            [
                "ID",
                "Operation",
                "Source",
                "Destination",
                "Status",
                "Created At",
                "Error / Details",
            ]
        )

        self.history_table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )

        self.history_table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )

        self.history_table.setAlternatingRowColors(True)

        header = self.history_table.horizontalHeader()
        header.setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents
        )
        header.setStretchLastSection(True)

        layout.addWidget(self.history_table)

        self.refresh_history_button = QPushButton("Refresh History")
        self.refresh_history_button.clicked.connect(
            self.refresh_history
        )

        layout.addWidget(self.refresh_history_button)

        return page


    def refresh_history(self):
        try:
            operations = self.database.list_operations(limit=100)
        except Exception as exc:
            QMessageBox.critical(
                self,
                "History Error",
                f"Could not load operation history:\n{exc}",
            )
            return

        self.history_table.setRowCount(len(operations))

        for row, operation in enumerate(operations):
            values = [
                operation.get("id", ""),
                operation.get("operation_type", ""),
                operation.get("source_path", ""),
                operation.get("destination_path") or "-",
                operation.get("status", ""),
                operation.get("created_at", ""),
                operation.get("error") or "-",
            ]

            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))

                self.history_table.setItem(
                    row,
                    column,
                    item,
                )