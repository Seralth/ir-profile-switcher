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
- The KWin script also reports every window that opens and closes. When
  the last window of a mapped program closes and none comes back within
  CLOSE_GRACE_MS, the program counts as closed. Then, unless the
  on_game_close setting is "keep", the watcher stops the presets it
  started for that program, if the devices still run them, and asks
  input-remapper to start each device's own autoload preset. Focus
  changes never do this.
- A mapping's on_start command runs when the first window of its
  program opens. Its on_exit command runs when the program closes, as
  above, whatever on_game_close says.
- Programs already open when the KWin script loads do not count as
  newly started. A preset such a program's device already injects is
  taken over rather than started again.
- Mappings are re-read from disk on every notification, so GUI edits take
  effect immediately without restarting the watcher.
"""

import logging

from PySide6.QtCore import SLOT, QObject, QTimer, Slot
from PySide6.QtDBus import QDBusConnection

from . import actions, config, ir_client, mappings, notify

logger = logging.getLogger(__name__)

SERVICE_NAME = "com.seralth.IRProfileSwitcher"
OBJECT_PATH = "/Switcher"

HEALTH_CHECK_INTERVAL_MS = 30_000
# Devices take a moment to come back after resume.
RESUME_CHECK_DELAY_MS = 5_000

# After the last window of a mapped program closes, the watcher waits this
# long for a window of the same class to come back before it treats the
# program as closed. Games open and close launcher, shader-compile and
# crash-reporter windows while they start.
CLOSE_GRACE_MS = 10_000

# get_state values (input-remapper's InjectorState) that mean the device
# is injecting. STARTING is included so a check right after a switch does
# not restart an injection that is still starting up.
INJECTING_STATES = ("RUNNING", "STARTING")
# get_state values that mean input-remapper lost a preset without anyone
# asking: the injector died, the daemon restarted, or the device grab was
# lost. "STOPPED" is not one of them: someone stopped the preset on purpose.
DROPOUT_STATES = ("FAILED", "UNKNOWN", "NO_GRAB")


def class_key(window_class: str) -> str:
    """Window classes match without regard to case."""
    return window_class.casefold()


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
        # device -> class key of the mapping that preset was started for.
        self._started_for: dict[str, str] = {}
        # KWin window id -> window class, for every open window.
        self._windows: dict[str, str] = {}
        # class key -> timer that ends the grace period after the class's
        # last window closed.
        self._close_timers: dict[str, QTimer] = {}
        # Class keys that were already open when the KWin script loaded
        # and have not been focused since. Their running presets are taken
        # over instead of started again.
        self._already_open: set[str] = set()
        # class key -> the latest non-empty window caption of that class.
        # Notifications use it as the program's name.
        self._captions: dict[str, str] = {}

        self._health_timer = QTimer(self)
        self._health_timer.setInterval(HEALTH_CHECK_INTERVAL_MS)
        self._health_timer.timeout.connect(self.check_health)

    @Slot(str, str)
    def NotifyWindow(self, window_class: str, caption: str):
        """A window was focused."""
        self._remember_caption(window_class, caption)
        self._focus(window_class)

    @Slot(str, str, str, bool)
    def WindowAdded(self, window_id: str, window_class: str, caption: str, active: bool):
        key = class_key(window_class)
        first = not self._is_open(key) and key not in self._close_timers
        self._windows[window_id] = window_class
        self._remember_caption(window_class, caption)
        self._cancel_close(key)
        if active:
            self._focus(window_class)
        if first:
            self._started_program(window_class)

    @Slot(str, str)
    def WindowRemoved(self, window_id: str, window_class: str):
        window_class = self._windows.pop(window_id, None)
        if window_class is None:
            return
        key = class_key(window_class)
        if not self._is_open(key) and key not in self._close_timers:
            self._start_close(window_class)

    @Slot(str, str)
    def CaptionChanged(self, window_class: str, caption: str):
        self._remember_caption(window_class, caption)

    @Slot(list, list, list)
    def OpenWindows(self, window_ids, window_classes, captions):
        """The windows open when the KWin script loaded: at watcher start,
        and again after KWin restarts."""
        old_keys = {class_key(c): c for c in self._windows.values()}
        self._windows = {str(i): str(c) for i, c in zip(window_ids, window_classes)}
        for window_class, caption in zip(window_classes, captions):
            self._remember_caption(str(window_class), str(caption))
        new_keys = {class_key(c) for c in self._windows.values()}
        for key in new_keys:
            self._cancel_close(key)
            if key not in old_keys:
                self._already_open.add(key)
        for key, window_class in old_keys.items():
            if key not in new_keys and key not in self._close_timers:
                self._start_close(window_class)

    def _remember_caption(self, window_class: str, caption: str) -> None:
        if caption:
            self._captions[class_key(window_class)] = caption

    def _name(self, window_class: str, entry: dict) -> str:
        """The program's name for notifications: its window caption, else
        the name saved with the mapping, else the window class."""
        name = entry.get("name")
        return (
            self._captions.get(class_key(window_class))
            or (name if isinstance(name, str) and name else None)
            or window_class
        )

    def _is_open(self, key: str) -> bool:
        return any(class_key(c) == key for c in self._windows.values())

    def _start_close(self, window_class: str) -> None:
        """Start the grace period after the last window of a class closed."""
        timer = QTimer(self)
        timer.setSingleShot(True)
        timer.setInterval(CLOSE_GRACE_MS)
        timer.timeout.connect(lambda: self._closed(window_class))
        self._close_timers[class_key(window_class)] = timer
        timer.start()

    def _cancel_close(self, key: str) -> None:
        timer = self._close_timers.pop(key, None)
        if timer is not None:
            timer.stop()
            timer.deleteLater()

    def _started_program(self, window_class: str) -> None:
        """The first window of a class opened."""
        try:
            entry = mappings.find_mapping(window_class, mappings.load())
        except (OSError, ValueError, TypeError):
            logger.exception("Could not read mappings for %s", window_class)
            return
        if entry is not None:
            self._run_command(window_class, entry, "on_start", "start")

    def _run_command(self, window_class: str, entry: dict, field: str, when: str) -> None:
        command = entry.get(field)
        if isinstance(command, str) and command.strip():
            actions.run(command, self._name(window_class, entry), when)

    def _closed(self, window_class: str) -> None:
        """No window of the class came back within the grace period."""
        key = class_key(window_class)
        self._cancel_close(key)
        self._already_open.discard(key)
        if self._is_open(key):
            return
        try:
            entry = mappings.find_mapping(window_class, mappings.load())
        except (OSError, ValueError, TypeError):
            logger.exception("Could not read mappings for %s", window_class)
            entry = None
        name = self._name(window_class, entry) if entry is not None else window_class
        if entry is None:
            self._captions.pop(key, None)
            return
        logger.info("%s (%s) closed", window_class, name)
        if config.get_on_game_close() == "revert":
            self._revert(window_class, name)
        self._run_command(window_class, entry, "on_exit", "exit")
        self._captions.pop(key, None)

    def _revert(self, window_class: str, name: str) -> None:
        """Stop the presets this watcher started for the class's mapping,
        if the devices still run them, and start each device's own
        autoload preset, if it has one."""
        key = class_key(window_class)
        reverted = []
        for device in [d for d, k in self._started_for.items() if k == key]:
            del self._started_for[device]
            preset = self._started.pop(device, None)
            state = self._state(device)
            if state not in INJECTING_STATES:
                continue
            try:
                ir_client.stop_injecting(device)
            except RuntimeError as e:
                logger.error("Could not stop preset=%r on device=%r: %s", preset, device, e)
                continue
            logger.info("%s closed -> stopped preset=%r on device=%r", window_class, preset, device)
            reverted.append(device)
            try:
                ir_client.autoload_single(device)
            except RuntimeError as e:
                logger.warning("Could not start the autoload preset for %r: %s", device, e)
        if self._focused_mapped_class and class_key(self._focused_mapped_class) == key:
            self._focused_mapped_class = None
            self._health_timer.stop()
        if self._active_window_class and class_key(self._active_window_class) == key:
            self._active_window_class = None
        if reverted:
            notify.notify_game_closed(name, reverted)

    def _focus(self, window_class: str):
        if window_class == self._active_window_class:
            return
        key = class_key(window_class)
        take_over = key in self._already_open
        self._already_open.discard(key)

        try:
            entry = mappings.find_mapping(window_class, mappings.load())
        except (OSError, ValueError, TypeError):
            # Leave the window unrecorded so its next focus tries again.
            logger.exception("Could not read mappings for %s", window_class)
            return

        if entry is None:
            logger.debug("Unmapped window %s, leaving preset as-is", window_class)
            self._active_window_class = window_class
            self._focused_mapped_class = None
            self._health_timer.stop()
            return

        self._focused_mapped_class = window_class
        self._health_timer.start()
        if self._apply(window_class, entry, health_check=False, take_over=take_over):
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
            entry = mappings.find_mapping(window_class, mappings.load())
        except (OSError, ValueError, TypeError):
            logger.exception("Could not read mappings for %s", window_class)
            return
        if entry is None:
            # The mapping was removed while the window stayed focused.
            self._focused_mapped_class = None
            self._health_timer.stop()
            return
        if self._apply(window_class, entry, health_check=True):
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

    def _apply(
        self, window_class: str, entry: dict, *, health_check: bool, take_over: bool = False
    ) -> bool:
        """Switch every valid target that is not already running. Returns
        True when every valid target is running afterwards.

        The health check only re-applies a preset this watcher started
        when input-remapper lost it (DROPOUT_STATES). A preset someone
        stopped on purpose stays stopped. A target whose switch failed is
        always tried again.

        With take_over, a device that already injects and has no preset
        from this watcher yet is counted as running the mapped preset. That
        is for programs that were open before the watcher started."""
        all_ok = True
        switched = []
        reapplied = []
        for device, preset in valid_targets(window_class, entry.get("targets")):
            state = self._state(device)
            ours = self._started.get(device) == preset
            if ours and health_check and state not in DROPOUT_STATES:
                continue
            if ours and not health_check and state in INJECTING_STATES:
                continue
            if take_over and device not in self._started and state in INJECTING_STATES:
                logger.info(
                    "%s: device=%r already injecting, taking it over as preset=%r",
                    window_class,
                    device,
                    preset,
                )
                self._started[device] = preset
                self._started_for[device] = class_key(window_class)
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
                self._started_for[device] = class_key(window_class)
                switched.append({"device": device, "preset": preset})
                if health_check and ours:
                    reapplied.append(device)
            else:
                self._started.pop(device, None)
                self._started_for.pop(device, None)
                all_ok = False
                notify.notify_failure(device, preset, reason)
        if switched and not health_check:
            notify.notify_switch(self._name(window_class, entry), switched)
        if reapplied:
            notify.notify_reapplied(self._name(window_class, entry), reapplied)
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
