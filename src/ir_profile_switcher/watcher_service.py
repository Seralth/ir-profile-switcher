"""Session-bus service that receives window-activation notifications from
the KWin script and switches input-remapper presets accordingly.

Behavior:
- Unmapped windows are ignored entirely -- whatever preset was last active
  stays active.
- Before starting a preset, the watcher asks input-remapper whether the
  device is already injecting the preset the watcher last started. If so,
  the start is skipped: every start_injecting restarts the injection and
  briefly interrupts the device.
- A window only counts as handled after every target switched. Focusing
  the same window again retries a failed switch.
- While a mapped window is focused, a health check runs every 30 s and
  re-applies any preset input-remapper lost (device reconnect,
  input-remapper restart). A preset stopped on purpose, for example in
  input-remapper's own window, stays stopped. The health check also runs
  shortly after the system resumes.
- Mappings are re-read from disk on every notification, so GUI edits take
  effect immediately without restarting the watcher.
"""

import logging

from PySide6.QtCore import SLOT, QObject, QTimer, Slot
from PySide6.QtDBus import QDBusConnection

from . import ir_client, mappings, notify

logger = logging.getLogger(__name__)

SERVICE_NAME = "com.seralth.IRProfileSwitcher"
OBJECT_PATH = "/Switcher"

HEALTH_CHECK_INTERVAL_MS = 30_000
# Devices take a moment to come back after resume.
RESUME_CHECK_DELAY_MS = 5_000

# get_state values (input-remapper's InjectorState) that mean the device
# is injecting. STARTING is included so a check right after a switch does
# not restart an injection that is still starting up.
INJECTING_STATES = ("RUNNING", "STARTING")
# get_state values that mean input-remapper lost a preset without anyone
# asking: the injector died, the daemon restarted, or the device grab was
# lost. "STOPPED" is not one of them: someone stopped the preset on purpose.
DROPOUT_STATES = ("FAILED", "UNKNOWN", "NO_GRAB")


def valid_targets(window_class: str, targets) -> list[tuple[str, str]]:
    """(device, preset) pairs from a mapping's targets. Malformed entries
    are logged and skipped."""
    if not isinstance(targets, list):
        logger.error("Mapping for %s has no valid targets list, skipping it", window_class)
        return []
    pairs = []
    for target in targets:
        device = target.get("device") if isinstance(target, dict) else None
        preset = target.get("preset") if isinstance(target, dict) else None
        if not (isinstance(device, str) and device and isinstance(preset, str) and preset):
            logger.error("Skipping malformed target %r in mapping for %s", target, window_class)
            continue
        pairs.append((device, preset))
    return pairs


class WatcherService(QObject):
    def __init__(self):
        super().__init__()
        # The last window handled completely. Only set after every target
        # switched, so focusing the same window again retries a failure.
        self._active_window_class: str | None = None
        # The focused window, while it has a mapping. The health check
        # re-applies this window's presets.
        self._focused_mapped_class: str | None = None
        # device -> the preset this watcher last started on that device.
        # get_state only says whether a device is injecting, not which
        # preset, so this record fills that gap.
        self._started: dict[str, str] = {}

        self._health_timer = QTimer(self)
        self._health_timer.setInterval(HEALTH_CHECK_INTERVAL_MS)
        self._health_timer.timeout.connect(self.check_health)

    @Slot(str)
    def NotifyWindow(self, window_class: str):
        if window_class == self._active_window_class:
            return

        try:
            targets = mappings.find_targets(window_class, mappings.load())
        except (OSError, ValueError, TypeError):
            # Leave the window unrecorded so its next focus tries again.
            logger.exception("Could not read mappings for %s", window_class)
            return

        if targets is None:
            logger.debug("Unmapped window %s, leaving preset as-is", window_class)
            self._active_window_class = window_class
            self._focused_mapped_class = None
            self._health_timer.stop()
            return

        self._focused_mapped_class = window_class
        self._health_timer.start()
        if self._apply(window_class, targets, health_check=False):
            self._active_window_class = window_class
        else:
            self._active_window_class = None

    def check_health(self):
        """Re-apply the focused window's presets that input-remapper is no
        longer injecting, and retry targets that failed to switch."""
        window_class = self._focused_mapped_class
        if window_class is None:
            self._health_timer.stop()
            return
        try:
            targets = mappings.find_targets(window_class, mappings.load())
        except (OSError, ValueError, TypeError):
            logger.exception("Could not read mappings for %s", window_class)
            return
        if targets is None:
            # The mapping was removed while the window stayed focused.
            self._focused_mapped_class = None
            self._health_timer.stop()
            return
        if self._apply(window_class, targets, health_check=True):
            self._active_window_class = window_class

    def check_health_soon(self, delay_ms: int = RESUME_CHECK_DELAY_MS):
        if self._focused_mapped_class is not None:
            QTimer.singleShot(delay_ms, self.check_health)

    def _state(self, device: str) -> str:
        """input-remapper's state for the device, or "unreachable"."""
        try:
            return ir_client.get_state(device)
        except RuntimeError as e:
            logger.debug("get_state failed for %r: %s", device, e)
            return "unreachable"

    def _apply(self, window_class: str, targets, *, health_check: bool) -> bool:
        """Switch every valid target that is not already running. Returns
        True when every valid target is running afterwards.

        The health check only re-applies a preset this watcher started
        when input-remapper lost it (DROPOUT_STATES). A preset someone
        stopped on purpose stays stopped. A target whose switch failed is
        always tried again."""
        all_ok = True
        switched = []
        for device, preset in valid_targets(window_class, targets):
            state = self._state(device)
            ours = self._started.get(device) == preset
            if ours and health_check and state not in DROPOUT_STATES:
                continue
            if ours and not health_check and state in INJECTING_STATES:
                continue
            if health_check:
                logger.warning(
                    "%s: device=%r is not running preset=%r (state %s), re-applying",
                    window_class,
                    device,
                    preset,
                    state,
                )
            try:
                ok = ir_client.start_injecting(device, preset)
                reason = "input-remapper refused the preset."
            except RuntimeError as e:
                ok = False
                reason = str(e)
            (logger.info if ok else logger.error)(
                "%s -> device=%r preset=%r ok=%s", window_class, device, preset, ok
            )
            if ok:
                self._started[device] = preset
                switched.append({"device": device, "preset": preset})
            else:
                self._started.pop(device, None)
                all_ok = False
                notify.notify_failure(device, preset, reason)
        if switched and not health_check:
            notify.notify_switch(window_class, switched)
        return all_ok


class _ResumeListener(QObject):
    """Receives logind's PrepareForSleep signal. Kept apart from
    WatcherService so the slot is not exported on the watcher's DBus
    object."""

    def __init__(self, on_resume):
        super().__init__()
        self._on_resume = on_resume

    @Slot(bool)
    def onPrepareForSleep(self, sleeping: bool):
        if not sleeping:
            logger.info("System resumed, checking presets soon")
            self._on_resume()


def watch_resume(service: WatcherService) -> QObject | None:
    """Run the health check shortly after every resume. Returns the
    listener, which the caller must keep alive, or None if logind is not
    reachable."""
    listener = _ResumeListener(service.check_health_soon)
    ok = QDBusConnection.systemBus().connect(
        "org.freedesktop.login1",
        "/org/freedesktop/login1",
        "org.freedesktop.login1.Manager",
        "PrepareForSleep",
        listener,
        SLOT("onPrepareForSleep(bool)"),
    )
    if not ok:
        logger.warning("Could not watch for resume; presets are still checked every 30 s")
        return None
    return listener


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
