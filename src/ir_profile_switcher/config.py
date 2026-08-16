"""App-level config -- currently just which systemd service name to treat
as "input-remapper's service." Defaults to the known name, but can be
manually repointed via the GUI's service picker if it's ever renamed or
installed differently than expected.
"""

from pathlib import Path

from . import json_store

CONFIG_PATH = Path.home() / ".config" / "ir-profile-switcher" / "config.json"
DEFAULT_INPUT_REMAPPER_SERVICE = "input-remapper.service"


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
