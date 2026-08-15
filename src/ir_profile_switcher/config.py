"""App-level config -- currently just which systemd service name to treat
as "input-remapper's service." Defaults to the known name, but can be
manually repointed via the GUI's service picker if it's ever renamed or
installed differently than expected.
"""

import json
from pathlib import Path

CONFIG_PATH = Path.home() / ".config" / "ir-profile-switcher" / "config.json"
DEFAULT_INPUT_REMAPPER_SERVICE = "input-remapper.service"


def _load() -> dict:
    if not CONFIG_PATH.is_file():
        return {}
    with CONFIG_PATH.open("r") as f:
        return json.load(f)


def _save(data: dict) -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with CONFIG_PATH.open("w") as f:
        json.dump(data, f, indent=2)


def get_input_remapper_service() -> str:
    return _load().get("input_remapper_service", DEFAULT_INPUT_REMAPPER_SERVICE)


def set_input_remapper_service(name: str) -> None:
    data = _load()
    data["input_remapper_service"] = name
    _save(data)
