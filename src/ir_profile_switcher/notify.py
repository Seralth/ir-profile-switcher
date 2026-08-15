"""Desktop notification when the watcher switches presets.

Uses notify-send rather than a raw org.freedesktop.Notifications DBus call:
that interface's replaces_id/expire_timeout arguments are UINT32/INT32,
and PySide6's QDBusMessage.setArguments() marshals plain Python ints as
whatever type it guesses, which isn't reliably correct here. notify-send
is the standard, desktop-agnostic tool for exactly this and ships with
every DE's notification daemon.
"""

import logging
import shutil
import subprocess
from pathlib import Path

from . import config

logger = logging.getLogger(__name__)

ICON_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "ir-profile-switcher.svg"


def notify_switch(window_class: str, targets: list[dict]) -> None:
    if not config.get_notifications_enabled():
        return
    if shutil.which("notify-send") is None:
        logger.debug("notify-send not found, skipping notification")
        return

    body = ", ".join(f"{t['device']} → {t['preset']}" for t in targets)
    try:
        subprocess.run(
            [
                "notify-send",
                "--app-name=Input Remapper Profile Switcher",
                f"--icon={ICON_PATH}",
                "--expire-time=4000",
                f"Switched preset for {window_class}",
                body,
            ],
            check=False,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        logger.exception("Failed to send switch notification")
