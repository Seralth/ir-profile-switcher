"""Shared helper for querying systemd unit state via `systemctl`."""

import subprocess


def is_unit_state(state: str, unit: str, *, user: bool = False) -> bool:
    """True if `systemctl is-<state> <unit>` reports exactly that state."""
    cmd = ["systemctl"]
    if user:
        cmd.append("--user")
    cmd += [f"is-{state}", unit]
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.stdout.strip() == state
