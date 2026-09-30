"""Keeps the switcher.js KWin script loaded in the running KWin instance.

At start, a copy of the script left loaded by an earlier watcher is
unloaded, then the current file is loaded and started. KWin's DBus may
not be ready yet at login, so loading is retried with backoff for up to
2 minutes. When KWin restarts, the script is loaded again. When the
watcher stops cleanly, the script is unloaded.
"""

import logging
import time

from PySide6.QtCore import QObject, QTimer
from PySide6.QtDBus import QDBusConnection, QDBusServiceWatcher

from . import dbus_utils, notify, paths

logger = logging.getLogger(__name__)

SCRIPT_PATH = paths.REPO_ROOT / "kwin-script" / "switcher.js"
# KWin names a script loaded without an explicit name after its file path.
SCRIPT_NAME = str(SCRIPT_PATH)

SERVICE = "org.kde.KWin"
OBJECT_PATH = "/Scripting"
INTERFACE = "org.kde.kwin.Scripting"

RETRY_LIMIT_S = 120
FIRST_RETRY_S = 1
MAX_RETRY_S = 30
# KWin unloads a script on its next event loop pass, so the reload waits
# a moment after an unload.
AFTER_UNLOAD_S = 0.5


def _call(method: str, args: list):
    bus = QDBusConnection.sessionBus()
    return dbus_utils.call(bus, SERVICE, OBJECT_PATH, INTERFACE, method, args)


def _is_loaded() -> bool:
    result = _call("isScriptLoaded", [SCRIPT_NAME])
    return bool(result and result[0])


class ScriptKeeper(QObject):
    def __init__(self):
        super().__init__()
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._attempt)
        self._deadline = 0.0
        self._delay_s = FIRST_RETRY_S
        self._fresh = False

        self._kwin_watcher = QDBusServiceWatcher(
            SERVICE,
            QDBusConnection.sessionBus(),
            QDBusServiceWatcher.WatchModeFlag.WatchForRegistration
            | QDBusServiceWatcher.WatchModeFlag.WatchForUnregistration,
            self,
        )
        self._kwin_watcher.serviceRegistered.connect(self._on_kwin_registered)
        self._kwin_watcher.serviceUnregistered.connect(self._on_kwin_unregistered)

    def start(self) -> None:
        """Replace any loaded copy of the script with the current file,
        retrying in the background until it works or RETRY_LIMIT_S passes."""
        self._deadline = time.monotonic() + RETRY_LIMIT_S
        self._delay_s = FIRST_RETRY_S
        self._fresh = True
        self._timer.start(0)

    def stop(self) -> None:
        """Stop retrying and unload the script."""
        self._timer.stop()
        try:
            _call("unloadScript", [SCRIPT_NAME])
        except RuntimeError as e:
            logger.warning("Could not unload the KWin script: %s", e)

    def _on_kwin_registered(self, _name: str) -> None:
        logger.info("KWin is back on DBus, loading the KWin script again")
        self.start()

    def _on_kwin_unregistered(self, _name: str) -> None:
        logger.warning("KWin left DBus, waiting for KWin to come back")
        self._timer.stop()

    def _attempt(self) -> None:
        try:
            if not SCRIPT_PATH.is_file():
                raise RuntimeError(f"KWin script not found: {SCRIPT_PATH}")
            if _is_loaded():
                # A copy from an earlier run may be an old version of the
                # file, so unload it and load the file again.
                if not self._fresh:
                    raise RuntimeError("KWin has not unloaded the old script yet")
                self._fresh = False
                _call("unloadScript", [SCRIPT_NAME])
                self._timer.start(int(AFTER_UNLOAD_S * 1000))
                return
            self._fresh = False
            result = _call("loadScript", [str(SCRIPT_PATH)])
            if not result or int(result[0]) < 0:
                raise RuntimeError("KWin refused to load the script")
            _call("start", [])
        except RuntimeError as e:
            self._retry_later(e)
            return
        logger.info("KWin script loaded")

    def _retry_later(self, error: Exception) -> None:
        remaining = self._deadline - time.monotonic()
        if remaining <= 0:
            logger.error(
                "Could not load the KWin script within %ds: %s. Switching is off "
                "until KWin restarts or the watcher is restarted.",
                RETRY_LIMIT_S,
                error,
            )
            notify.notify_problem(
                "Profile switching is off",
                "Could not load the KWin script. Open Profile Switcher and "
                "restart the watcher.",
            )
            return
        logger.warning("KWin script not loaded yet (%s), retrying in %ds", error, self._delay_s)
        self._timer.start(int(min(self._delay_s, remaining) * 1000))
        self._delay_s = min(self._delay_s * 2, MAX_RETRY_S)
