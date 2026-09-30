"""Shared helpers for running `systemctl` without ever hanging the caller."""

import subprocess

# systemctl normally answers in milliseconds. A stuck systemd must not
# freeze the GUI or the watcher, so every call gives up after this long.
TIMEOUT_S = 10


def run(cmd: list[str], timeout: float = TIMEOUT_S) -> subprocess.CompletedProcess:
    """Run cmd and capture its text output. A command that times out or
    cannot start is returned as a failed result instead of raising."""
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(cmd, 1, "", f"{cmd[0]} timed out after {timeout:g}s")
    except OSError as e:
        return subprocess.CompletedProcess(cmd, 1, "", str(e))


def is_unit_state(state: str, unit: str, *, user: bool = False) -> bool:
    """True if `systemctl is-<state> <unit>` reports exactly that state."""
    cmd = ["systemctl"]
    if user:
        cmd.append("--user")
    cmd += [f"is-{state}", unit]
    return run(cmd).stdout.strip() == state
