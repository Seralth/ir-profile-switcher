"""Checks that input-remapper is actually installed and running as its own
systemd service (root-owned, name configurable -- see config.py) rather
than the on-demand pkexec path that input-remapper falls back to, which is
what prompts for a password every single time it's launched. If we find it
installed but not running as the service, we fix that once here instead of
letting every preset-switch attempt trigger its own prompt.

This tool never installs input-remapper itself -- if it's missing
entirely, that's reported, not silently acted on. If the binary is found
but the configured service name isn't, that's also reported distinctly
(not conflated with "not installed") -- the GUI's service picker lets the
user repoint the configured name if it's been renamed.
"""

import shutil
import subprocess

from . import config


def has_binary() -> bool:
    return shutil.which("input-remapper-control") is not None


def has_service_unit(service_name: str | None = None) -> bool:
    service_name = service_name or config.get_input_remapper_service()
    result = subprocess.run(
        ["systemctl", "list-unit-files", service_name, "--no-legend"],
        capture_output=True,
        text=True,
    )
    return bool(result.stdout.strip())


def is_service_active(service_name: str | None = None) -> bool:
    service_name = service_name or config.get_input_remapper_service()
    result = subprocess.run(
        ["systemctl", "is-active", service_name], capture_output=True, text=True
    )
    return result.stdout.strip() == "active"


def is_service_enabled(service_name: str | None = None) -> bool:
    service_name = service_name or config.get_input_remapper_service()
    result = subprocess.run(
        ["systemctl", "is-enabled", service_name], capture_output=True, text=True
    )
    return result.stdout.strip() == "enabled"


def status() -> str:
    """One of: "not_installed", "binary_found_no_service",
    "installed_not_running", "ok".
    """
    if not has_service_unit():
        return "binary_found_no_service" if has_binary() else "not_installed"
    if not is_service_active():
        return "installed_not_running"
    return "ok"


def ensure_service_running() -> tuple[bool, str]:
    """Attempts to enable+start input-remapper's service via pkexec if it's
    installed but not active. Returns (ok, message). Only ever prompts for
    a password here -- once, on the actual fix -- not on every preset
    switch. Never guesses at a service name; if it can't find the
    configured one, it reports that rather than acting on a guess.
    """
    service_name = config.get_input_remapper_service()
    state = status()

    if state == "not_installed":
        return False, (
            "input-remapper is not installed (missing input-remapper-control "
            "binary and its systemd service unit)."
        )
    if state == "binary_found_no_service":
        return False, (
            f"Found the input-remapper-control binary, but no systemd service "
            f"named '{service_name}'. It may have been renamed -- use "
            "'Pick service...' to search your installed services and point "
            "this at the right one."
        )
    if state == "ok":
        return True, f"{service_name} is already running."

    result = subprocess.run(
        ["pkexec", "systemctl", "enable", "--now", service_name],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0 or not is_service_active(service_name):
        return False, f"Failed to start {service_name}: {result.stderr.strip()}"
    return True, f"{service_name} enabled and started."


def disable_service() -> tuple[bool, str]:
    """Disables + stops input-remapper's service, returning it to the
    state it's in on a fresh install (not running as a service, falling
    back to its own on-demand pkexec prompt) -- so this app can be
    uninstalled without leaving behind a change nobody can easily revert.
    """
    service_name = config.get_input_remapper_service()
    if not has_service_unit(service_name):
        return False, f"No service named '{service_name}' to disable."

    result = subprocess.run(
        ["pkexec", "systemctl", "disable", "--now", service_name],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return False, f"Failed to disable {service_name}: {result.stderr.strip()}"
    return True, f"{service_name} disabled and stopped (back to default state)."


def list_all_service_units() -> list[str]:
    """All service unit names known to systemd (system-level), for the
    GUI's search-and-pick fallback.
    """
    result = subprocess.run(
        ["systemctl", "list-unit-files", "--type=service", "--all", "--no-legend"],
        capture_output=True,
        text=True,
    )
    names = []
    for line in result.stdout.splitlines():
        parts = line.split()
        if parts:
            names.append(parts[0])
    return sorted(names)
