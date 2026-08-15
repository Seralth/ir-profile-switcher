"""Load/save the program -> (device, preset) mapping file.

Schema:
[
  {
    "window_class": "steam_app_1422450",
    "targets": [
      {"device": "Razer Razer DeathAdder V3 Pro", "preset": "Deadlock"}
    ]
  },
  ...
]
"""

import json
from pathlib import Path

MAPPINGS_PATH = Path.home() / ".config" / "ir-profile-switcher" / "mappings.json"


def load() -> list[dict]:
    if not MAPPINGS_PATH.is_file():
        return []
    with MAPPINGS_PATH.open("r") as f:
        return json.load(f)


def save(mappings: list[dict]) -> None:
    MAPPINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with MAPPINGS_PATH.open("w") as f:
        json.dump(mappings, f, indent=2)


def find_targets(window_class: str, mappings: list[dict]) -> list[dict] | None:
    for entry in mappings:
        if entry["window_class"] == window_class:
            return entry["targets"]
    return None
