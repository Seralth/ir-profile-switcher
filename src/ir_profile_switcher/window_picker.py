"""Live list of currently open windows for the GUI's "Add mapping" window
picker.

Event-driven, not polled: a KWin script reports the windows already open
when the watch starts, then stays loaded and reports each window
launched or closed after that via KWin's own windowAdded/windowRemoved
signals, for as long as the picker dialog is open.
"""

from pathlib import Path

from PySide6.QtCore import QObject, QTimer, Slot
from PySide6.QtDBus import QDBusConnection, QDBusMessage

LIST_SCRIPT_PATH = (
    Path(__file__).resolve().parent.parent.parent / "kwin-script" / "list-windows.js"
)

PICKER_SERVICE = "com.seralth.IRProfileSwitcher.Picker"
PICKER_PATH = "/Picker"

KWIN_SERVICE = "org.kde.KWin"
KWIN_PATH = "/Scripting"
KWIN_INTERFACE = "org.kde.kwin.Scripting"

_alive_receivers: list = []


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
    msg = QDBusMessage.createMethodCall(KWIN_SERVICE, KWIN_PATH, KWIN_INTERFACE, method)
    msg.setArguments(args)
    bus.call(msg)


def watch_open_windows(on_initial, on_added, on_removed, timeout_ms: int = 2000):
    """Start a live window watch for as long as the picker dialog is open.

    Calls `on_initial(pairs)` once with the windows open at watch-start
    (or an empty list if nothing responds within timeout_ms), then calls
    `on_added(window_class, caption)` for every window launched after
    that and `on_removed(window_class)` for every window closed after
    that, until the returned stop function is called.

    Returns a `stop()` function -- call it when the dialog closes to
    unload the KWin script and unregister the DBus service.
    """
    bus = QDBusConnection.sessionBus()
    state = {"initial_fired": False, "stopped": False}

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
        _kwin_call("unloadScript", [str(LIST_SCRIPT_PATH)])
        bus.unregisterObject(PICKER_PATH)
        bus.unregisterService(PICKER_SERVICE)
        if receiver in _alive_receivers:
            _alive_receivers.remove(receiver)

    if not bus.registerService(PICKER_SERVICE):
        fire_initial([])
        return stop
    bus.registerObject(
        PICKER_PATH,
        PICKER_SERVICE,
        receiver,
        QDBusConnection.RegisterOption.ExportAllSlots,
    )

    _kwin_call("unloadScript", [str(LIST_SCRIPT_PATH)])
    _kwin_call("loadScript", [str(LIST_SCRIPT_PATH)])
    _kwin_call("start", [])

    QTimer.singleShot(timeout_ms, lambda: fire_initial([]))
    return stop
