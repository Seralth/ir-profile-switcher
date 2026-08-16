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

from pathlib import Path

from . import json_store

MAPPINGS_PATH = Path.home() / ".config" / "ir-profile-switcher" / "mappings.json"


def load() -> list[dict]:
    return json_store.read_json(MAPPINGS_PATH, [])


def save(mappings: list[dict]) -> None:
    json_store.write_json(MAPPINGS_PATH, mappings)


def find_targets(window_class: str, mappings: list[dict]) -> list[dict] | None:
    for entry in mappings:
        if entry["window_class"] == window_class:
            return entry["targets"]
    return None
