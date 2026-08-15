"""Loads the switcher.js KWin script into the running KWin instance."""

from pathlib import Path

from PySide6.QtDBus import QDBusConnection, QDBusMessage

SCRIPT_PATH = Path(__file__).resolve().parent.parent.parent / "kwin-script" / "switcher.js"

SERVICE = "org.kde.KWin"
OBJECT_PATH = "/Scripting"
INTERFACE = "org.kde.kwin.Scripting"


def _call(method: str, args: list):
    bus = QDBusConnection.sessionBus()
    if not bus.isConnected():
        raise RuntimeError("Could not connect to the DBus session bus")
    msg = QDBusMessage.createMethodCall(SERVICE, OBJECT_PATH, INTERFACE, method)
    msg.setArguments(args)
    reply = bus.call(msg)
    if reply.type() == QDBusMessage.MessageType.ErrorMessage:
        raise RuntimeError(f"{method} failed: {reply.errorMessage()}")
    return reply.arguments()


def load_and_start() -> None:
    if not SCRIPT_PATH.is_file():
        raise FileNotFoundError(f"KWin script not found: {SCRIPT_PATH}")
    is_loaded = _call("isScriptLoaded", [str(SCRIPT_PATH)])
    if not (is_loaded and is_loaded[0]):
        _call("loadScript", [str(SCRIPT_PATH)])
    _call("start", [])
