"""Fetches a live list of currently open windows via a one-shot KWin script,
for the GUI's "Add mapping" window picker.
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
    def __init__(self, on_result):
        super().__init__()
        self._on_result = on_result

    @Slot(list, list)
    def ReceiveWindowList(self, classes, captions):
        self._on_result(list(zip(classes, captions)))


def _kwin_call(method: str, args: list):
    bus = QDBusConnection.sessionBus()
    msg = QDBusMessage.createMethodCall(KWIN_SERVICE, KWIN_PATH, KWIN_INTERFACE, method)
    msg.setArguments(args)
    bus.call(msg)


def list_open_windows(callback, timeout_ms: int = 2000) -> None:
    """Asynchronously fetch open windows as [(window_class, caption), ...].

    Calls `callback(pairs)` exactly once -- with real data, or an empty
    list if nothing responds within timeout_ms.
    """
    bus = QDBusConnection.sessionBus()
    state = {"fired": False}

    def finish(pairs):
        if state["fired"]:
            return
        state["fired"] = True
        bus.unregisterObject(PICKER_PATH)
        bus.unregisterService(PICKER_SERVICE)
        if receiver in _alive_receivers:
            _alive_receivers.remove(receiver)
        callback(pairs)

    receiver = _Receiver(finish)
    # Keep a reference alive at module scope so it isn't garbage collected
    # before the KWin script calls back.
    _alive_receivers.append(receiver)

    if not bus.registerService(PICKER_SERVICE):
        finish([])
        return
    bus.registerObject(
        PICKER_PATH,
        PICKER_SERVICE,
        receiver,
        QDBusConnection.RegisterOption.ExportAllSlots,
    )

    _kwin_call("unloadScript", [str(LIST_SCRIPT_PATH)])
    _kwin_call("loadScript", [str(LIST_SCRIPT_PATH)])
    _kwin_call("start", [])

    QTimer.singleShot(timeout_ms, lambda: finish([]))
