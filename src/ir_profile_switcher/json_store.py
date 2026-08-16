"""Shared read/write helpers for this app's small JSON state files."""

import json
from pathlib import Path
from typing import TypeVar

T = TypeVar("T")


def read_json(path: Path, default: T) -> T:
    if not path.is_file():
        return default
    with path.open("r") as f:
        return json.load(f)


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as f:
        json.dump(data, f, indent=2)
