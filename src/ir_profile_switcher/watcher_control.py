"""Enable/disable/start/stop this app's own background watcher
(ir-profile-switcher.service, a systemd --user unit) from inside the GUI,
so using this tool never requires knowing or typing systemctl by hand.
"""

import subprocess
from pathlib import Path

SERVICE_NAME = "ir-profile-switcher.service"

# The unit file lives in this repo (not a package), so it's never on
# systemd's default search path -- unlike a real installed package, there's
# nothing to discover it unless we put a symlink there ourselves.
SOURCE_UNIT_FILE = (
    Path(__file__).resolve().parent.parent.parent / "systemd" / SERVICE_NAME
)
INSTALLED_UNIT_LINK = Path.home() / ".config" / "systemd" / "user" / SERVICE_NAME


def _ensure_unit_installed() -> None:
    """(Re)create the symlink systemd needs to find our unit file at all.

    `systemctl disable` on a unit that only exists via a manual symlink
    (rather than a properly packaged one) removes that symlink outright,
    not just its enablement -- so a later `enable` has nothing to find
    unless this runs first.
    """
    INSTALLED_UNIT_LINK.parent.mkdir(parents=True, exist_ok=True)
    if INSTALLED_UNIT_LINK.is_symlink() and not INSTALLED_UNIT_LINK.exists():
        INSTALLED_UNIT_LINK.unlink()  # broken symlink (target moved/deleted)
    if not INSTALLED_UNIT_LINK.exists():
        INSTALLED_UNIT_LINK.symlink_to(SOURCE_UNIT_FILE)
        subprocess.run(["systemctl", "--user", "daemon-reload"], capture_output=True)


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
    _ensure_unit_installed()
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
