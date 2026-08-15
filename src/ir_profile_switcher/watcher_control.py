"""Enable/disable/start/stop this app's own background watcher
(ir-profile-switcher.service, a systemd --user unit) from inside the GUI,
so using this tool never requires knowing or typing systemctl by hand.
"""

import subprocess

SERVICE_NAME = "ir-profile-switcher.service"


def is_enabled() -> bool:
    result = subprocess.run(
        ["systemctl", "--user", "is-enabled", SERVICE_NAME],
        capture_output=True,
        text=True,
    )
    return result.stdout.strip() == "enabled"


def is_active() -> bool:
    result = subprocess.run(
        ["systemctl", "--user", "is-active", SERVICE_NAME],
        capture_output=True,
        text=True,
    )
    return result.stdout.strip() == "active"


def enable_and_start() -> tuple[bool, str]:
    result = subprocess.run(
        ["systemctl", "--user", "enable", "--now", SERVICE_NAME],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return False, result.stderr.strip()
    return True, "Watcher enabled and started."


def disable_and_stop() -> tuple[bool, str]:
    result = subprocess.run(
        ["systemctl", "--user", "disable", "--now", SERVICE_NAME],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return False, result.stderr.strip()
    return True, "Watcher disabled and stopped."
