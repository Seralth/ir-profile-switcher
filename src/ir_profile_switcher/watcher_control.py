"""Enable/disable/start/stop this app's own background watcher
(ir-profile-switcher.service, a systemd --user unit) from inside the GUI,
so using this tool never requires knowing or typing systemctl by hand.
"""

import subprocess

from . import install, systemctl_utils

SERVICE_NAME = install.SERVICE_NAME


def is_enabled() -> bool:
    return systemctl_utils.is_unit_state("enabled", SERVICE_NAME, user=True)


def is_active() -> bool:
    return systemctl_utils.is_unit_state("active", SERVICE_NAME, user=True)


def enable_and_start() -> tuple[bool, str]:
    # `systemctl disable` can remove the unit file along with its
    # enablement, so (re)write it before every enable.
    install.install_unit()
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
