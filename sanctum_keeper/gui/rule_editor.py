from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from sanctum_keeper.models import (
    ALLOWED_OPERATORS,
    ActionSpec,
    ActionType,
    Condition,
    ConditionField,
    ConditionOperator,
    Rule,
)


FIELD_LABELS = {
    ConditionField.FILENAME: "Filename",
    ConditionField.EXTENSION: "Extension",
    ConditionField.SIZE_BYTES: "Size (bytes)",
    ConditionField.AGE_DAYS: "Age (days)",
}

OPERATOR_LABELS = {
    ConditionOperator.EQUALS: "Equals",
    ConditionOperator.NOT_EQUALS: "Does not equal",
    ConditionOperator.CONTAINS: "Contains",
    ConditionOperator.STARTS_WITH: "Starts with",
    ConditionOperator.ENDS_WITH: "Ends with",
    ConditionOperator.GREATER_THAN: "Greater than",
    ConditionOperator.GREATER_OR_EQUAL: "Greater than or equal",
    ConditionOperator.LESS_THAN: "Less than",
    ConditionOperator.LESS_OR_EQUAL: "Less than or equal",
}

ACTION_LABELS = {
    ActionType.RENAME: "Rename",
    ActionType.MOVE: "Move",
    ActionType.COPY: "Copy",
    ActionType.QUARANTINE: "Quarantine",
}


class ConditionRow(QWidget):
    remove_requested = Signal(object)

    def __init__(self, condition=None, parent=None):
        super().__init__(parent)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.field_combo = QComboBox()

        for field, label in FIELD_LABELS.items():
            self.field_combo.addItem(label, field.value)

        self.operator_combo = QComboBox()
        self.value_edit = QLineEdit()
        self.remove_button = QPushButton("Remove")

        if condition is not None:
            index = self.field_combo.findData(condition.field.value)
            self.field_combo.setCurrentIndex(index)

        layout.addWidget(self.field_combo)
        layout.addWidget(self.operator_combo)
        layout.addWidget(self.value_edit, 1)
        layout.addWidget(self.remove_button)

        initial_operator = (
            condition.operator.value if condition is not None else None
        )
        self._populate_operators(initial_operator)
        self._update_placeholder()

        self.field_combo.currentIndexChanged.connect(
            self._on_field_changed
        )

        self.remove_button.clicked.connect(
            lambda _checked=False: self.remove_requested.emit(self)
        )

        if condition is not None:
            self.value_edit.setText(str(condition.value))

    def _populate_operators(self, preferred_operator=None):
        previous = (
            preferred_operator
            if preferred_operator is not None
            else self.operator_combo.currentData()
        )

        field = ConditionField(self.field_combo.currentData())

        self.operator_combo.clear()

        for operator in ConditionOperator:
            if operator in ALLOWED_OPERATORS[field]:
                self.operator_combo.addItem(
                    OPERATOR_LABELS[operator],
                    operator.value,
                )

        index = self.operator_combo.findData(previous)

        if index >= 0:
            self.operator_combo.setCurrentIndex(index)

    def _on_field_changed(self, _index):
        self._populate_operators()
        self._update_placeholder()

    def _update_placeholder(self):
        field = ConditionField(self.field_combo.currentData())

        placeholders = {
            ConditionField.FILENAME: "e.g. invoice",
            ConditionField.EXTENSION: "e.g. .pdf",
            ConditionField.SIZE_BYTES: "e.g. 1048576 bytes",
            ConditionField.AGE_DAYS: "e.g. 30 days",
        }

        self.value_edit.setPlaceholderText(placeholders[field])

    def get_condition(self):
        field = ConditionField(self.field_combo.currentData())
        operator = ConditionOperator(self.operator_combo.currentData())
        raw_value = self.value_edit.text().strip()

        if not raw_value:
            raise ValueError(
                f"Enter a value for {FIELD_LABELS[field]}."
            )

        if field == ConditionField.SIZE_BYTES:
            try:
                value = int(raw_value)
            except ValueError as exc:
                raise ValueError(
                    "File size must be an integer number of bytes."
                ) from exc

        elif field == ConditionField.AGE_DAYS:
            try:
                value = float(raw_value)
            except ValueError as exc:
                raise ValueError(
                    "File age must be a number of days."
                ) from exc

        else:
            value = raw_value

        return Condition(field, operator, value)


class ActionRow(QWidget):
    remove_requested = Signal(object)

    def __init__(self, action=None, parent=None):
        super().__init__(parent)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.kind_combo = QComboBox()

        for kind, label in ACTION_LABELS.items():
            self.kind_combo.addItem(label, kind.value)

        self.target_edit = QLineEdit()
        self.browse_button = QPushButton("Browse...")
        self.remove_button = QPushButton("Remove")

        if action is not None:
            index = self.kind_combo.findData(action.kind.value)
            self.kind_combo.setCurrentIndex(index)

            if action.target:
                self.target_edit.setText(action.target)

        layout.addWidget(self.kind_combo)
        layout.addWidget(self.target_edit, 1)
        layout.addWidget(self.browse_button)
        layout.addWidget(self.remove_button)

        self.kind_combo.currentIndexChanged.connect(
            self._on_kind_changed
        )

        self.browse_button.clicked.connect(
            self._browse_destination
        )

        self.remove_button.clicked.connect(
            lambda _checked=False: self.remove_requested.emit(self)
        )

        self._on_kind_changed()

    def _on_kind_changed(self, _index=None):
        kind = ActionType(self.kind_combo.currentData())

        if kind == ActionType.RENAME:
            self.target_edit.setEnabled(True)
            self.target_edit.setPlaceholderText(
                "New filename, e.g. invoice.pdf"
            )
            self.browse_button.setVisible(False)

        elif kind in {ActionType.MOVE, ActionType.COPY}:
            self.target_edit.setEnabled(True)
            self.target_edit.setPlaceholderText(
                "Destination folder"
            )
            self.browse_button.setVisible(True)

        else:
            self.target_edit.clear()
            self.target_edit.setEnabled(False)
            self.target_edit.setPlaceholderText(
                "Uses the configured quarantine folder"
            )
            self.browse_button.setVisible(False)

    def _browse_destination(self):
        folder = QFileDialog.getExistingDirectory(
            self,
            "Choose destination folder",
            self.target_edit.text().strip() or "",
        )

        if folder:
            self.target_edit.setText(folder)

    def get_action(self):
        kind = ActionType(self.kind_combo.currentData())

        if kind == ActionType.QUARANTINE:
            target = None
        else:
            target = self.target_edit.text().strip()

        return ActionSpec(kind, target)


class RuleEditorDialog(QDialog):
    def __init__(self, parent=None, rule: Rule | None = None):
        super().__init__(parent)

        self._saved_rule = None

        self.setWindowTitle(
            "Edit Rule" if rule is not None else "Create Rule"
        )
        self.resize(850, 560)

        root_layout = QVBoxLayout(self)

        root_layout.addWidget(QLabel("Rule name"))

        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText(
            "e.g. Organize PDF invoices"
        )
        root_layout.addWidget(self.name_edit)

        self.enabled_checkbox = QCheckBox("Rule enabled")
        self.enabled_checkbox.setChecked(
            True if rule is None else rule.enabled
        )
        root_layout.addWidget(self.enabled_checkbox)

        # Conditions
        conditions_group = QGroupBox(
            "Conditions (all conditions must match)"
        )
        conditions_layout = QVBoxLayout(conditions_group)

        self.condition_rows_widget = QWidget()
        self.condition_rows_layout = QVBoxLayout(
            self.condition_rows_widget
        )
        self.condition_rows_layout.setContentsMargins(0, 0, 0, 0)

        conditions_layout.addWidget(self.condition_rows_widget)

        self.add_condition_button = QPushButton("+ Add Condition")
        self.add_condition_button.clicked.connect(
            lambda: self._add_condition_row()
        )
        conditions_layout.addWidget(self.add_condition_button)

        root_layout.addWidget(conditions_group)

        # Actions
        actions_group = QGroupBox(
            "Actions (executed in order)"
        )
        actions_layout = QVBoxLayout(actions_group)

        self.action_rows_widget = QWidget()
        self.action_rows_layout = QVBoxLayout(
            self.action_rows_widget
        )
        self.action_rows_layout.setContentsMargins(0, 0, 0, 0)

        actions_layout.addWidget(self.action_rows_widget)

        self.add_action_button = QPushButton("+ Add Action")
        self.add_action_button.clicked.connect(
            lambda: self._add_action_row()
        )
        actions_layout.addWidget(self.add_action_button)

        root_layout.addWidget(actions_group)

        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )

        button_box.accepted.connect(self._save_and_accept)
        button_box.rejected.connect(self.reject)

        root_layout.addWidget(button_box)

        self.condition_rows = []
        self.action_rows = []

        if rule is None:
            self._add_condition_row()
            self._add_action_row()
        else:
            self.name_edit.setText(rule.name)

            for condition in rule.conditions:
                self._add_condition_row(condition)

            for action in rule.actions:
                self._add_action_row(action)

        self._update_remove_buttons()

    def _add_condition_row(self, condition=None):
        row = ConditionRow(condition)
        row.remove_requested.connect(self._remove_condition_row)

        self.condition_rows.append(row)
        self.condition_rows_layout.addWidget(row)

        self._update_remove_buttons()

    def _remove_condition_row(self, row):
        if len(self.condition_rows) <= 1:
            return

        self.condition_rows.remove(row)
        self.condition_rows_layout.removeWidget(row)
        row.deleteLater()

        self._update_remove_buttons()

    def _add_action_row(self, action=None):
        row = ActionRow(action)
        row.remove_requested.connect(self._remove_action_row)

        self.action_rows.append(row)
        self.action_rows_layout.addWidget(row)

        self._update_remove_buttons()

    def _remove_action_row(self, row):
        if len(self.action_rows) <= 1:
            return

        self.action_rows.remove(row)
        self.action_rows_layout.removeWidget(row)
        row.deleteLater()

        self._update_remove_buttons()

    def _update_remove_buttons(self):
        for row in self.condition_rows:
            row.remove_button.setEnabled(
                len(self.condition_rows) > 1
            )

        for row in self.action_rows:
            row.remove_button.setEnabled(
                len(self.action_rows) > 1
            )

    def _save_and_accept(self):
        try:
            name = self.name_edit.text().strip()

            conditions = tuple(
                row.get_condition()
                for row in self.condition_rows
            )

            actions = tuple(
                row.get_action()
                for row in self.action_rows
            )

            self._saved_rule = Rule(
                name=name,
                conditions=conditions,
                actions=actions,
                enabled=self.enabled_checkbox.isChecked(),
            )

        except (TypeError, ValueError) as exc:
            QMessageBox.warning(
                self,
                "Invalid Rule",
                str(exc),
            )
            return

        self.accept()

    def get_rule(self) -> Rule | None:
        return self._saved_rule