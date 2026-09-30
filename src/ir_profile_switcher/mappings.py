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


def find_mapping(window_class: str, mappings: list[dict]) -> dict | None:
    """The mapping entry for window_class, or None if unmapped.

    Classes match without regard to case. An exact match wins if two
    mappings differ only in case. Entries that are not a mapping at all
    are skipped.
    """
    entries = [
        e for e in mappings if isinstance(e, dict) and isinstance(e.get("window_class"), str)
    ]
    for entry in entries:
        if entry["window_class"] == window_class:
            return entry
    wanted = window_class.casefold()
    for entry in entries:
        if entry["window_class"].casefold() == wanted:
            return entry
    return None


def find_targets(window_class: str, mappings: list[dict]) -> list[dict] | None:
    """Targets of the mapping for window_class, or None if unmapped."""
    entry = find_mapping(window_class, mappings)
    return None if entry is None else entry.get("targets", [])
