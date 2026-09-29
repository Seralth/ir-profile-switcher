"""Shared read/write helpers for this app's small JSON state files."""

import json
import os
from pathlib import Path
from typing import TypeVar

T = TypeVar("T")


def read_json(path: Path, default: T) -> T:
    if not path.is_file():
        return default
    with path.open("r") as f:
        return json.load(f)


def write_json(path: Path, data) -> None:
    # Write a temp file and swap it in, so a reader never sees a half-written file.
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with tmp.open("w") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, path)
