"""Checks that input-remapper is actually installed and running as its own
systemd service (root-owned input-remapper.service) rather than the
on-demand pkexec path that input-remapper falls back to -- which is what
prompts for a password every single time it's launched. If we find it
installed but not running as the service, we fix that once here instead of
letting every preset-switch attempt trigger its own prompt.

This tool never installs input-remapper itself -- if it's missing
entirely, that's reported, not silently acted on.
"""

import shutil
import subprocess

SERVICE_NAME = "input-remapper.service"


def is_installed() -> bool:
    if shutil.which("input-remapper-control") is None:
        return False
    result = subprocess.run(
        ["systemctl", "list-unit-files", SERVICE_NAME, "--no-legend"],
        capture_output=True,
        text=True,
    )
    return bool(result.stdout.strip())


def is_service_active() -> bool:
    result = subprocess.run(
        ["systemctl", "is-active", SERVICE_NAME], capture_output=True, text=True
    )
    return result.stdout.strip() == "active"


def status() -> str:
    if not is_installed():
        return "not_installed"
    if not is_service_active():
        return "installed_not_running"
    return "ok"


def ensure_service_running() -> tuple[bool, str]:
    """Attempts to enable+start input-remapper.service via pkexec if it's
    installed but not active. Returns (ok, message). Only ever prompts for
    a password here -- once, on the actual fix -- not on every preset
    switch.
    """
    if not is_installed():
        return False, (
            "input-remapper is not installed (missing input-remapper-control "
            "binary or its systemd service unit)."
        )
    if is_service_active():
        return True, "input-remapper.service is already running."

    result = subprocess.run(
        ["pkexec", "systemctl", "enable", "--now", SERVICE_NAME],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0 or not is_service_active():
        return False, f"Failed to start {SERVICE_NAME}: {result.stderr.strip()}"
    return True, f"{SERVICE_NAME} enabled and started."
