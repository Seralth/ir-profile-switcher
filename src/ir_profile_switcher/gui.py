import logging
import threading
from collections import Counter

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from . import config, ir_client, mappings, paths, preflight, watcher_control, window_picker

logger = logging.getLogger(__name__)

LABEL_SEP = "   —   "
PLACEHOLDER_LOADING = "(loading open windows...)"
PLACEHOLDER_NO_WINDOWS = "(no windows found, type manually)"
STATUS_REFRESH_MS = 5000


def _format_label(window_class: str, caption: str) -> str:
    return f"{window_class}{LABEL_SEP}{caption}" if caption else window_class


def _read_status() -> dict:
    """Ask systemd for the state of input-remapper and of the watcher.
    Runs several systemctl commands, so the GUI calls it off the GUI
    thread."""
    ir_state = preflight.status()
    return {
        "ir_state": ir_state,
        "service_name": config.get_input_remapper_service(),
        "ir_enabled": preflight.is_service_enabled(),
        # ir_state can only be "ok" when is_service_active() was True, so
        # this avoids spawning a second identical `systemctl is-active`
        # subprocess just to re-derive what status() already determined.
        "ir_active": ir_state == "ok",
        "watcher_enabled": watcher_control.is_enabled(),
        "watcher_active": watcher_control.is_active(),
    }


class _StatusReader(QObject):
    """Runs _read_status() in a worker thread and emits the result on the
    GUI thread. One read runs at a time. A request during a read starts
    one more read after the current read."""

    done = Signal(dict)

    def __init__(self):
        super().__init__()
        self._lock = threading.Lock()
        self._busy = False
        self._again = False

    def request(self):
        with self._lock:
            if self._busy:
                self._again = True
                return
            self._busy = True
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        while True:
            try:
                self.done.emit(_read_status())
            except Exception:  # noqa: BLE001 -- a failed read must not stop later reads
                logger.exception("Could not read service status")
            with self._lock:
                if not self._again:
                    self._busy = False
                    return
                self._again = False


class ServicePickerDialog(QDialog):
    """Search-and-pick fallback for when input-remapper's service isn't
    found under the expected name (e.g. renamed in a newer version).
    Lets the user search all known systemd services and point this app at
    the right one instead of just failing.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Pick input-remapper's service")
        self.resize(480, 420)
        self.chosen_name: str | None = None

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Search installed systemd services:"))

        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Type to filter...")
        layout.addWidget(self.search_box)

        self.list_widget = QListWidget()
        self._all_names = preflight.list_all_service_units()
        self.list_widget.addItems(self._all_names)
        layout.addWidget(self.list_widget)

        self.search_box.textChanged.connect(self._filter)
        self.list_widget.itemDoubleClicked.connect(self._on_double_click)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _filter(self, text: str):
        text = text.lower()
        self.list_widget.clear()
        self.list_widget.addItems([n for n in self._all_names if text in n.lower()])

    def _on_double_click(self, item):
        self.chosen_name = item.text()
        self.accept()

    def _on_accept(self):
        item = self.list_widget.currentItem()
        if item is None:
            QMessageBox.warning(self, "No selection", "Pick a service from the list.")
            return
        self.chosen_name = item.text()
        self.accept()


class AddMappingDialog(QDialog):
    def __init__(self, parent=None, existing: dict | None = None):
        super().__init__(parent)
        self.setWindowTitle("Add mapping" if existing is None else "Edit mapping")
        self.resize(560, 420)
        self._devices = ir_client.list_devices()
        self._targets: list[dict] = []
        # Counts, not a set: several windows (e.g. multiple browser windows)
        # can share the same window_class, so the combo entry should only
        # disappear once the LAST window of that class closes.
        self._window_class_counts: Counter[str] = Counter()

        layout = QVBoxLayout(self)

        layout.addWidget(QLabel("Program (window class):"))
        self.window_combo = QComboBox()
        self.window_combo.setEditable(True)
        self.window_combo.setMinimumContentsLength(40)
        self.window_combo.view().setMinimumWidth(520)
        self.window_combo.addItem(PLACEHOLDER_LOADING)
        layout.addWidget(self.window_combo)
        self.window_error_label = QLabel()
        self.window_error_label.setWordWrap(True)
        self.window_error_label.hide()
        layout.addWidget(self.window_error_label)

        layout.addWidget(QLabel("Devices for this program:"))
        self.targets_table = QTableWidget(0, 3)
        self.targets_table.setHorizontalHeaderLabels(["Device", "Preset", ""])
        self.targets_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch
        )
        self.targets_table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch
        )
        self.targets_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        layout.addWidget(self.targets_table)

        if not self._devices:
            layout.addWidget(
                QLabel(
                    "No input-remapper devices with presets found "
                    "(nothing in ~/.config/input-remapper-2/presets)."
                )
            )
        else:
            add_row = QHBoxLayout()
            self.new_device_combo = QComboBox()
            self.new_device_combo.addItems(self._devices)
            self.new_preset_combo = QComboBox()
            self.new_device_combo.currentTextChanged.connect(self._refresh_preset_choices)
            self._refresh_preset_choices(self._devices[0])
            add_device_button = QPushButton("+ Add device")
            add_device_button.clicked.connect(self._add_target_row)
            add_row.addWidget(self.new_device_combo, stretch=1)
            add_row.addWidget(self.new_preset_combo, stretch=1)
            add_row.addWidget(add_device_button)
            layout.addLayout(add_row)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._stop_window_watch = window_picker.watch_open_windows(
            self._populate_windows,
            self._add_live_window,
            self._remove_live_window,
            self._show_window_error,
        )
        self.finished.connect(lambda _: self._stop_window_watch())

        if existing is not None:
            self.window_combo.setEditText(existing["window_class"])
            for target in existing["targets"]:
                self._targets.append(target)
            self._refresh_targets_table()

    def _refresh_preset_choices(self, device: str):
        self.new_preset_combo.clear()
        self.new_preset_combo.addItems(ir_client.list_presets(device))

    def _add_target_row(self):
        device = self.new_device_combo.currentText()
        preset = self.new_preset_combo.currentText()
        if not device or not preset:
            return
        self._targets = [t for t in self._targets if t["device"] != device]
        self._targets.append({"device": device, "preset": preset})
        self._refresh_targets_table()

    def _refresh_targets_table(self):
        self.targets_table.setRowCount(len(self._targets))
        for row, target in enumerate(self._targets):
            self.targets_table.setItem(row, 0, QTableWidgetItem(target["device"]))
            self.targets_table.setItem(row, 1, QTableWidgetItem(target["preset"]))
            remove_button = QPushButton("Remove")
            remove_button.clicked.connect(lambda _, d=target["device"]: self._remove_target(d))
            self.targets_table.setCellWidget(row, 2, remove_button)

    def _remove_target(self, device: str):
        self._targets = [t for t in self._targets if t["device"] != device]
        self._refresh_targets_table()

    def _show_window_error(self, message: str):
        self.window_error_label.setText(message)
        self.window_error_label.show()

    def _keep_text(self, change):
        """Run change() on the window list without changing the text shown.

        Qt replaces the edit text of an editable QComboBox when the list is
        cleared, when an item is added to an empty list, or when the
        selected item is removed. Without this, the class typed by the user
        or loaded for Edit could silently turn into another window's class
        once the window list arrives. The loading placeholder is the only
        text that may be replaced.
        """
        text = self.window_combo.currentText()
        keep = bool(text) and text not in (PLACEHOLDER_LOADING, PLACEHOLDER_NO_WINDOWS)
        change()
        if keep and self.window_combo.currentText() != text:
            self.window_combo.setCurrentIndex(-1)
            self.window_combo.setEditText(text)

    def _populate_windows(self, pairs):
        def change():
            self.window_combo.clear()
            self._window_class_counts.clear()
            for window_class, caption in pairs:
                self._add_live_window(window_class, caption)
            if not pairs:
                self.window_combo.addItem(PLACEHOLDER_NO_WINDOWS)

        self._keep_text(change)

    def _add_live_window(self, window_class: str, caption: str):
        self._window_class_counts[window_class] += 1
        if self._window_class_counts[window_class] > 1:
            return  # another window of this class is already in the list

        def change():
            # Replace the "(no windows found...)" placeholder the first time
            # a real window shows up, instead of leaving it in the list.
            if self.window_combo.count() == 1 and self.window_combo.itemData(0) is None:
                self.window_combo.clear()
            self.window_combo.addItem(_format_label(window_class, caption), window_class)

        self._keep_text(change)

    def _remove_live_window(self, window_class: str):
        if self._window_class_counts[window_class] <= 0:
            return
        self._window_class_counts[window_class] -= 1
        if self._window_class_counts[window_class] > 0:
            return  # other windows of this class are still open
        del self._window_class_counts[window_class]
        index = self.window_combo.findData(window_class)
        if index == -1:
            return

        def change():
            self.window_combo.removeItem(index)
            if self.window_combo.count() == 0:
                self.window_combo.addItem(PLACEHOLDER_NO_WINDOWS)

        self._keep_text(change)

    def _on_accept(self):
        # The text shown is what gets saved. A picked entry shows
        # "class   —   caption", so the class is the part before the
        # separator. Typed text is used as-is.
        text = self.window_combo.currentText().strip()
        window_class = text.split(LABEL_SEP)[0].strip()
        if not window_class or text in (PLACEHOLDER_LOADING, PLACEHOLDER_NO_WINDOWS):
            QMessageBox.warning(self, "Missing program", "Enter or pick a window class.")
            return

        if not self._targets:
            QMessageBox.warning(
                self, "No devices added", "Add at least one device and preset."
            )
            return

        self.result_mapping = {"window_class": window_class, "targets": self._targets}
        self.accept()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Input Remapper Profile Switcher")
        self.setWindowIcon(QIcon(str(paths.ICON_PATH)))
        self.resize(760, 440)

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["Program (window class)", "Devices / Presets"])
        self.table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.ResizeToContents
        )
        self.table.horizontalHeader().setMinimumSectionSize(220)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        layout.addWidget(self.table)

        button_row = QHBoxLayout()
        add_button = QPushButton("+ Add mapping")
        edit_button = QPushButton("Edit")
        remove_button = QPushButton("Remove selected")
        add_button.clicked.connect(self._add_mapping)
        edit_button.clicked.connect(self._edit_mapping)
        remove_button.clicked.connect(self._remove_mapping)
        button_row.addWidget(add_button)
        button_row.addWidget(edit_button)
        button_row.addWidget(remove_button)
        button_row.addStretch()
        layout.addLayout(button_row)

        ir_row = QHBoxLayout()
        self.ir_status_label = QLabel()
        self.ir_pick_button = QPushButton("Pick service...")
        self.ir_fix_button = QPushButton("Fix (enable + start)")
        self.ir_disable_button = QPushButton("Disable (return to default)")
        self.ir_pick_button.clicked.connect(self._pick_input_remapper_service)
        self.ir_fix_button.clicked.connect(self._fix_input_remapper)
        self.ir_disable_button.clicked.connect(self._disable_input_remapper)
        ir_row.addWidget(self.ir_status_label, stretch=1)
        ir_row.addWidget(self.ir_pick_button)
        ir_row.addWidget(self.ir_fix_button)
        ir_row.addWidget(self.ir_disable_button)
        layout.addLayout(ir_row)

        watcher_row = QHBoxLayout()
        self.watcher_status_label = QLabel()
        self.watcher_start_button = QPushButton("Enable + start")
        self.watcher_stop_button = QPushButton("Disable + stop")
        self.watcher_start_button.clicked.connect(self._start_watcher)
        self.watcher_stop_button.clicked.connect(self._stop_watcher)
        watcher_row.addWidget(self.watcher_status_label, stretch=1)
        watcher_row.addWidget(self.watcher_start_button)
        watcher_row.addWidget(self.watcher_stop_button)
        layout.addLayout(watcher_row)

        self.notify_checkbox = QCheckBox("Show a notification when the active profile switches")
        self.notify_checkbox.setChecked(config.get_notifications_enabled())
        self.notify_checkbox.toggled.connect(config.set_notifications_enabled)
        layout.addWidget(self.notify_checkbox)

        self.ir_status_label.setText("input-remapper: checking...")
        self.watcher_status_label.setText("Watcher service: checking...")
        for button in (
            self.ir_fix_button,
            self.ir_disable_button,
            self.watcher_start_button,
            self.watcher_stop_button,
        ):
            button.setEnabled(False)
        self.ir_pick_button.setVisible(False)

        self._status_reader = _StatusReader()
        self._status_reader.done.connect(self._show_status)
        self._status_timer = QTimer(self)
        self._status_timer.setInterval(STATUS_REFRESH_MS)
        self._status_timer.timeout.connect(self._refresh_status)
        self._status_timer.start()

        self._refresh_table()
        self._refresh_status()

    def _refresh_status(self):
        self._status_reader.request()

    def _show_status(self, status: dict):
        ir_state = status["ir_state"]
        service_name = status["service_name"]
        ir_text = {
            "ok": f"input-remapper: installed, running as a service ({service_name})",
            "installed_not_running": (
                f"input-remapper: installed, but '{service_name}' is NOT running "
                "(presets cannot switch until fixed)"
            ),
            "binary_found_no_service": (
                f"input-remapper: binary found, but no service named "
                f"'{service_name}' -- may have been renamed, use 'Pick service...'"
            ),
            "not_installed": "input-remapper: NOT installed",
        }[ir_state]
        self.ir_status_label.setText(ir_text)
        self.ir_fix_button.setEnabled(ir_state == "installed_not_running")
        self.ir_pick_button.setVisible(ir_state == "binary_found_no_service")
        self.ir_disable_button.setEnabled(status["ir_enabled"] or status["ir_active"])

        enabled = status["watcher_enabled"]
        active = status["watcher_active"]
        if enabled and active:
            watcher_text = "Watcher service: enabled, running"
        elif enabled and not active:
            watcher_text = "Watcher service: enabled, but not currently running"
        else:
            watcher_text = "Watcher service: not enabled (won't start at login)"
        self.watcher_status_label.setText(watcher_text)
        self.watcher_start_button.setEnabled(not (enabled and active))
        self.watcher_stop_button.setEnabled(enabled or active)

    def _pick_input_remapper_service(self):
        dialog = ServicePickerDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted and dialog.chosen_name:
            config.set_input_remapper_service(dialog.chosen_name)
            self._refresh_status()

    def _fix_input_remapper(self):
        ok, message = preflight.ensure_service_running()
        if not ok:
            QMessageBox.warning(self, "input-remapper", message)
        self._refresh_status()

    def _disable_input_remapper(self):
        confirm = QMessageBox.question(
            self,
            "Disable input-remapper's service",
            "Stop and disable input-remapper's background service?\n\n"
            "You can re-enable it anytime with the Fix button.",
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        ok, message = preflight.disable_service()
        if not ok:
            QMessageBox.warning(self, "input-remapper", message)
        self._refresh_status()

    def _start_watcher(self):
        ok, message = watcher_control.enable_and_start()
        if not ok:
            QMessageBox.warning(self, "Watcher", message)
        self._refresh_status()

    def _stop_watcher(self):
        ok, message = watcher_control.disable_and_stop()
        if not ok:
            QMessageBox.warning(self, "Watcher", message)
        self._refresh_status()

    def _refresh_table(self):
        self._mappings = mappings.load()
        self.table.setRowCount(len(self._mappings))
        for row, entry in enumerate(self._mappings):
            self.table.setItem(row, 0, QTableWidgetItem(entry["window_class"]))
            summary = ", ".join(f"{t['device']}: {t['preset']}" for t in entry["targets"])
            self.table.setItem(row, 1, QTableWidgetItem(summary))

    def _open_mapping_dialog(self, existing: dict | None = None):
        dialog = AddMappingDialog(self, existing=existing)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        new_mapping = dialog.result_mapping
        new_class = new_mapping["window_class"]
        old_class = existing["window_class"] if existing else None
        current = mappings.load()

        # Classes match without regard to case, so a mapping that differs
        # only in case would compete with the new one.
        clashes = [
            m
            for m in current
            if m["window_class"] != old_class
            and m["window_class"].casefold() == new_class.casefold()
        ]
        if clashes:
            confirm = QMessageBox.question(
                self,
                "Replace mapping",
                f"A mapping for '{clashes[0]['window_class']}' already exists.\n\n"
                "Replace the existing mapping?",
            )
            if confirm != QMessageBox.StandardButton.Yes:
                return
            current = [m for m in current if m not in clashes]

        # Editing keeps the mapping's place in the list.
        index = next(
            (i for i, m in enumerate(current) if m["window_class"] == old_class), len(current)
        )
        current = [m for m in current if m["window_class"] != old_class]
        current.insert(index, new_mapping)
        mappings.save(current)
        self._refresh_table()

    def _add_mapping(self):
        self._open_mapping_dialog()

    def _edit_mapping(self):
        row = self.table.currentRow()
        if row < 0:
            return
        self._open_mapping_dialog(existing=self._mappings[row])

    def _remove_mapping(self):
        row = self.table.currentRow()
        if row < 0:
            return
        existing = self._mappings[row]
        current = mappings.load()
        current = [m for m in current if m["window_class"] != existing["window_class"]]
        mappings.save(current)
        self._refresh_table()
