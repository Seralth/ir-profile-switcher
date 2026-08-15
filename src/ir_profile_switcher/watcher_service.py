"""Session-bus service that receives window-activation notifications from
the KWin script and switches input-remapper presets accordingly.

Behavior (per spec):
- Unmapped windows are ignored entirely -- whatever preset was last active
  stays active.
- A mapped window only triggers a switch if it's a *different* mapping
  than the one currently active (avoids redundant re-injection on every
  focus event within the same program).
- Mappings are re-read from disk on every notification, so GUI edits take
  effect immediately without restarting the watcher.
"""

import logging

from PySide6.QtCore import QObject, Slot
from PySide6.QtDBus import QDBusConnection

from . import ir_client, mappings

logger = logging.getLogger(__name__)

SERVICE_NAME = "com.seralth.IRProfileSwitcher"
OBJECT_PATH = "/Switcher"


class WatcherService(QObject):
    def __init__(self):
        super().__init__()
        self._active_window_class: str | None = None
        self._active_targets_key: tuple | None = None

    @Slot(str)
    def NotifyWindow(self, window_class: str):
        if window_class == self._active_window_class:
            return
        self._active_window_class = window_class

        current_mappings = mappings.load()
        targets = mappings.find_targets(window_class, current_mappings)
        if targets is None:
            logger.debug("Unmapped window %s, leaving preset as-is", window_class)
            return

        targets_key = tuple(sorted((t["device"], t["preset"]) for t in targets))
        if targets_key == self._active_targets_key:
            return

        for target in targets:
            device = target["device"]
            preset = target["preset"]
            try:
                ok = ir_client.start_injecting(device, preset)
                logger.info(
                    "%s -> device=%r preset=%r ok=%s", window_class, device, preset, ok
                )
            except RuntimeError:
                logger.exception(
                    "Failed switching device=%r to preset=%r", device, preset
                )
        self._active_targets_key = targets_key


def register() -> WatcherService:
    service = WatcherService()
    bus = QDBusConnection.sessionBus()
    if not bus.isConnected():
        raise RuntimeError("Could not connect to the DBus session bus")
    if not bus.registerService(SERVICE_NAME):
        raise RuntimeError(f"Could not register DBus service {SERVICE_NAME}")
    if not bus.registerObject(
        OBJECT_PATH,
        SERVICE_NAME,
        service,
        QDBusConnection.RegisterOption.ExportAllSlots,
    ):
        raise RuntimeError(f"Could not register DBus object {OBJECT_PATH}")
    return service
