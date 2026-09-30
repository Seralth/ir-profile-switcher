"""Writes the launcher entry and the watcher's systemd --user unit.

Both point at wherever this checkout lives, so they are generated here
rather than shipped with a fixed path.
"""

import shlex
import shutil
import subprocess
import sys
from pathlib import Path

from . import paths

SERVICE_NAME = "ir-profile-switcher.service"
UNIT_PATH = Path.home() / ".config" / "systemd" / "user" / SERVICE_NAME
DESKTOP_PATH = Path.home() / ".local" / "share" / "applications" / "ir-profile-switcher.desktop"
MAIN_PATH = paths.REPO_ROOT / "src" / "main.py"


def _unit_command(*args: str) -> str:
    # systemd reads % as a specifier and $ as a variable, so double them.
    command = shlex.join([sys.executable, str(MAIN_PATH), *args])
    return command.replace("%", "%%").replace("$", "$$")


def _desktop_command(*args: str) -> str:
    # Desktop entries only accept double quotes and read % as a field code.
    # The file format unescapes backslashes once more before the quoting rules
    # apply, so each escaping backslash is written twice.
    words = []
    for word in [sys.executable, str(MAIN_PATH), *args]:
        word = word.replace("%", "%%")
        if any(c in word for c in " \t\n\"'\\><~|&;$*?#()`"):
            for c in '\\"`$':
                word = word.replace(c, "\\\\" + c)
            word = f'"{word}"'
        words.append(word)
    return " ".join(words)


def unit_text() -> str:
    return f"""[Unit]
Description=Input Remapper Profile Switcher (window-aware preset watcher)
After=graphical-session.target
PartOf=graphical-session.target
StartLimitIntervalSec=300
StartLimitBurst=5

[Service]
Type=simple
ExecStart={_unit_command("--watcher")}
Restart=on-failure
RestartSec=10

[Install]
WantedBy=graphical-session.target
"""


def desktop_text() -> str:
    return f"""[Desktop Entry]
Type=Application
Name=Input Remapper Profile Switcher
Icon={paths.ICON_PATH}
Exec={_desktop_command()}
Terminal=false
Categories=Settings;
Comment=Manage which input-remapper preset each program uses
"""


def _write(path: Path, text: str) -> bool:
    """Write text to path, replacing any file or symlink there. Returns
    True if anything changed."""
    if path.is_file() and not path.is_symlink() and path.read_text() == text:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        path.unlink()
    path.write_text(text)
    return True


def install_unit() -> None:
    if _write(UNIT_PATH, unit_text()):
        subprocess.run(["systemctl", "--user", "daemon-reload"], capture_output=True)


def _refresh_menu() -> None:
    if shutil.which("kbuildsycoca6"):
        subprocess.run(["kbuildsycoca6"], capture_output=True)


def install() -> None:
    install_unit()
    _write(DESKTOP_PATH, desktop_text())
    _refresh_menu()
    # uninstall() disables the watcher, so a reinstall must enable it again.
    # Without this, the watcher runs until the next login and then stays off.
    subprocess.run(["systemctl", "--user", "enable", "--now", SERVICE_NAME], capture_output=True)


def uninstall() -> None:
    subprocess.run(["systemctl", "--user", "disable", "--now", SERVICE_NAME], capture_output=True)
    for path in (UNIT_PATH, DESKTOP_PATH):
        if path.is_symlink() or path.exists():
            path.unlink()
    subprocess.run(["systemctl", "--user", "daemon-reload"], capture_output=True)
    _refresh_menu()
