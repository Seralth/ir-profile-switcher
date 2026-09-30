"""Desktop notifications from the watcher: preset switches, games
closing, and failures.

Uses notify-send rather than a raw org.freedesktop.Notifications DBus call:
that interface's replaces_id/expire_timeout arguments are UINT32/INT32,
and PySide6's QDBusMessage.setArguments() marshals plain Python ints as
whatever type it guesses, which isn't reliably correct here. notify-send
is the standard, desktop-agnostic tool for exactly this and ships with
every DE's notification daemon.

notify-send is started and never waited on, so a slow notification
daemon cannot stall the watcher.
"""

import logging
import shutil
import subprocess
import time

from . import config, paths

logger = logging.getLogger(__name__)

APP_NAME = "Input Remapper Profile Switcher"

# Failure notices per device are sent at most this often.
FAILURE_INTERVAL_S = 5 * 60

_last_failure_notice: dict[str, float] = {}


def _send(summary: str, body: str, *, urgency: str = "normal", expire_ms: int = 4000) -> None:
    if shutil.which("notify-send") is None:
        logger.debug("notify-send not found, skipping notification")
        return
    try:
        subprocess.Popen(
            [
                "notify-send",
                f"--app-name={APP_NAME}",
                f"--icon={paths.ICON_PATH}",
                f"--urgency={urgency}",
                f"--expire-time={expire_ms}",
                summary,
                body,
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except OSError:
        logger.exception("Failed to send notification")


def notify_switch(window_class: str, targets: list[dict]) -> None:
    if not config.get_notifications_enabled():
        return
    body = ", ".join(f"{t['device']} → {t['preset']}" for t in targets)
    _send(f"Switched preset for {window_class}", body)


def short_device_name(device: str) -> str:
    """Drop a repeated first word, as in "Razer Razer DeathAdder V3 Pro"."""
    words = device.split(" ")
    if len(words) > 1 and words[0] == words[1]:
        words = words[1:]
    return " ".join(words)


def notify_game_closed(name: str, devices: list[str]) -> None:
    if not config.get_notifications_enabled():
        return
    names = ", ".join(short_device_name(d) for d in devices)
    _send(f"{name} closed — {names} back to default", "")


def notify_failure(device: str, preset: str, reason: str) -> None:
    """Tell the user a preset could not be applied. Sent even when switch
    notifications are turned off, and at most once per device every
    FAILURE_INTERVAL_S."""
    now = time.monotonic()
    last = _last_failure_notice.get(device)
    if last is not None and now - last < FAILURE_INTERVAL_S:
        return
    _last_failure_notice[device] = now
    _send(
        f"Could not switch {device} to {preset}",
        reason,
        expire_ms=10000,
    )


def notify_problem(summary: str, body: str) -> None:
    """A problem that stops switching from working. Always sent."""
    _send(summary, body, urgency="critical", expire_ms=0)
