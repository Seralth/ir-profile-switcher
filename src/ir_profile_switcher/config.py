"""App-level config: which systemd service name to treat as
"input-remapper's service", whether switches show a notification, and
what happens when a game closes.

The service name defaults to the known name, but can be manually
repointed via the GUI's service picker if it's ever renamed or installed
differently than expected.
"""

from pathlib import Path

from . import json_store

CONFIG_PATH = Path.home() / ".config" / "ir-profile-switcher" / "config.json"
DEFAULT_INPUT_REMAPPER_SERVICE = "input-remapper.service"
# on_game_close values: "revert" returns the game's devices to default,
# "keep" leaves the game's preset running.
ON_GAME_CLOSE_CHOICES = ("revert", "keep")


def _load() -> dict:
    return json_store.read_json(CONFIG_PATH, {})


def _save(data: dict) -> None:
    json_store.write_json(CONFIG_PATH, data)


def get_input_remapper_service() -> str:
    return _load().get("input_remapper_service", DEFAULT_INPUT_REMAPPER_SERVICE)


def set_input_remapper_service(name: str) -> None:
    data = _load()
    data["input_remapper_service"] = name
    _save(data)


def get_notifications_enabled() -> bool:
    return _load().get("notifications_enabled", True)


def set_notifications_enabled(enabled: bool) -> None:
    data = _load()
    data["notifications_enabled"] = enabled
    _save(data)


def get_on_game_close() -> str:
    value = _load().get("on_game_close", "revert")
    return value if value in ON_GAME_CLOSE_CHOICES else "revert"


def set_on_game_close(value: str) -> None:
    data = _load()
    data["on_game_close"] = value
    _save(data)
