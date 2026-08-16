"""Loads the switcher.js KWin script into the running KWin instance."""

from PySide6.QtDBus import QDBusConnection

from . import dbus_utils, paths

SCRIPT_PATH = paths.REPO_ROOT / "kwin-script" / "switcher.js"

SERVICE = "org.kde.KWin"
OBJECT_PATH = "/Scripting"
INTERFACE = "org.kde.kwin.Scripting"


def _call(method: str, args: list):
    bus = QDBusConnection.sessionBus()
    return dbus_utils.call(bus, SERVICE, OBJECT_PATH, INTERFACE, method, args)


def load_and_start() -> None:
    if not SCRIPT_PATH.is_file():
        raise FileNotFoundError(f"KWin script not found: {SCRIPT_PATH}")
    is_loaded = _call("isScriptLoaded", [str(SCRIPT_PATH)])
    if not (is_loaded and is_loaded[0]):
        _call("loadScript", [str(SCRIPT_PATH)])
    _call("start", [])
