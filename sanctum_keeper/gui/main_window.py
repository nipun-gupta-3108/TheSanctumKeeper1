
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

        self.tabs.addTab(
            self._placeholder(
                "Operation Preview",
                "Dry-run preview will be added next.",
            ),
            "Preview",
        )

        self.tabs.addTab(
            self._placeholder(
                "Operation History",
                "SQLite operation history will be added next.",
            ),
            "History",
        )

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
