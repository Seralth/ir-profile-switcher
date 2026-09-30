"""Runs a mapping's start and exit commands.

Each command runs as `/bin/sh -c <command>` in the home folder, without
the watcher waiting for it. The command gets the watcher's environment
minus agent variables (names starting with CLAUDE, and AI_AGENT). A
command still running after TIMEOUT_S is killed along with anything it
started in its process group. The exit code is logged, and a non-zero
exit shows a failure notification.
"""

import logging
import os
import signal
import subprocess
import threading
from pathlib import Path

from . import notify

logger = logging.getLogger(__name__)

TIMEOUT_S = 60


def clean_env() -> dict[str, str]:
    return {
        name: value
        for name, value in os.environ.items()
        if not name.startswith("CLAUDE") and name != "AI_AGENT"
    }


def run(command: str, program: str, when: str) -> subprocess.Popen | None:
    """Start command for program. `when` is "start" or "exit" and is only
    used in logs and notifications."""
    try:
        proc = subprocess.Popen(
            ["/bin/sh", "-c", command],
            cwd=Path.home(),
            env=clean_env(),
            stdin=subprocess.DEVNULL,
            # Its own process group, so the timeout also stops what it started.
            start_new_session=True,
        )
    except OSError as e:
        logger.error("%s: could not run the %s command %r: %s", program, when, command, e)
        notify.notify_action_failed(program, when, str(e))
        return None
    logger.info("%s: running the %s command %r (pid %d)", program, when, command, proc.pid)

    timed_out = threading.Event()

    def kill():
        timed_out.set()
        logger.warning(
            "%s: the %s command still runs after %ds, stopping it", program, when, TIMEOUT_S
        )
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass

    killer = threading.Timer(TIMEOUT_S, kill)
    killer.daemon = True
    killer.start()

    def wait():
        code = proc.wait()
        killer.cancel()
        if timed_out.is_set():
            reason = f"It ran longer than {TIMEOUT_S} seconds and was stopped."
        else:
            reason = f"It exited with code {code}."
        (logger.info if code == 0 else logger.error)(
            "%s: the %s command exited with code %d", program, when, code
        )
        if code != 0:
            notify.notify_action_failed(program, when, reason)

    threading.Thread(target=wait, daemon=True).start()
    return proc
