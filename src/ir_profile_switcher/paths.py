"""Shared repo-root path.

The app runs from a checkout rather than an installed package, so every
module that needs a path under the repo (KWin scripts, the icon, the
systemd unit) derives it from here instead of independently re-deriving
Path(__file__).resolve().parent.parent.parent.
"""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
ICON_PATH = REPO_ROOT / "data" / "ir-profile-switcher.svg"
