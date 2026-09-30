"""Live list of currently open windows for the GUI's "Add mapping" window
picker.

Event-driven, not polled: a KWin script reports the windows already open
when the watch starts, then stays loaded and reports each window
launched or closed after that via KWin's own windowAdded/windowRemoved
signals, for as long as the picker dialog is open.
"""

import itertools
import logging
import os

from PySide6.QtCore import QObject, QTimer, Slot
from PySide6.QtDBus import QDBusConnection

from . import dbus_utils, paths

LIST_SCRIPT_PATH = paths.REPO_ROOT / "kwin-script" / "list-windows.js"

PICKER_SERVICE = "com.seralth.IRProfileSwitcher.Picker"
PICKER_PATH = "/Picker"

KWIN_SERVICE = "org.kde.KWin"
KWIN_PATH = "/Scripting"
KWIN_INTERFACE = "org.kde.kwin.Scripting"

logger = logging.getLogger(__name__)

_alive_receivers: list = []
_script_ids = itertools.count()


class _Receiver(QObject):
    def __init__(self, on_initial, on_added, on_removed):
        super().__init__()
        self._on_initial = on_initial
        self._on_added = on_added
        self._on_removed = on_removed

    @Slot(list, list)
    def ReceiveWindowList(self, classes, captions):
        self._on_initial(list(zip(classes, captions)))

    @Slot(str, str)
    def WindowAdded(self, window_class, caption):
        self._on_added(window_class, caption)

    @Slot(str)
    def WindowRemoved(self, window_class):
        self._on_removed(window_class)


def _kwin_call(method: str, args: list):
    bus = QDBusConnection.sessionBus()
    dbus_utils.call(bus, KWIN_SERVICE, KWIN_PATH, KWIN_INTERFACE, method, args)


def watch_open_windows(on_initial, on_added, on_removed, on_error, timeout_ms: int = 2000):
    """Start a live window watch for as long as the picker dialog is open.

    Calls `on_initial(pairs)` once with the windows open at watch-start
    (or an empty list if nothing responds within timeout_ms), then calls
    `on_added(window_class, caption)` for every window launched after
    that and `on_removed(window_class)` for every window closed after
    that, until the returned stop function is called. Calls
    `on_error(message)` if the window list is not available.

    Returns a `stop()` function -- call it when the dialog closes to
    unload the KWin script and unregister the DBus service.
    """
    bus = QDBusConnection.sessionBus()
    # Each picker loads the script under its own name, so closing one
    # picker never unloads a script another picker loaded.
    script_name = f"ir-profile-switcher-picker-{os.getpid()}-{next(_script_ids)}"
    state = {"initial_fired": False, "stopped": False, "loaded": False}

    def fire_initial(pairs):
        if state["initial_fired"]:
            return
        state["initial_fired"] = True
        on_initial(pairs)

    receiver = _Receiver(fire_initial, on_added, on_removed)
    # Keep a reference alive at module scope so it isn't garbage collected
    # while the KWin script is still calling back.
    _alive_receivers.append(receiver)

    def stop():
        if state["stopped"]:
            return
        state["stopped"] = True
        if state["loaded"]:
            try:
                _kwin_call("unloadScript", [script_name])
            except RuntimeError:
                logger.warning("Could not unload the window picker's KWin script", exc_info=True)
        bus.unregisterObject(PICKER_PATH)
        bus.unregisterService(PICKER_SERVICE)
        if receiver in _alive_receivers:
            _alive_receivers.remove(receiver)

    if not bus.registerService(PICKER_SERVICE):
        on_error(
            "Another window list is open in a different Profile Switcher window. "
            "Type the window class instead."
        )
        fire_initial([])
        state["stopped"] = True
        _alive_receivers.remove(receiver)
        return stop
    bus.registerObject(
        PICKER_PATH,
        PICKER_SERVICE,
        receiver,
        QDBusConnection.RegisterOption.ExportAllSlots,
    )

    try:
        _kwin_call("loadScript", [str(LIST_SCRIPT_PATH), script_name])
        state["loaded"] = True
        _kwin_call("start", [])
    except RuntimeError as e:
        on_error(
            "Could not get the list of open windows from KWin. "
            f"Type the window class instead.\n\n{e}"
        )
        fire_initial([])
        stop()
        return stop

    QTimer.singleShot(timeout_ms, lambda: fire_initial([]))
    return stop
