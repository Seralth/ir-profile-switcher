"""Talks to input-remapper: device/preset discovery and preset activation.

Device and preset names are never hardcoded here — they are discovered by
listing input-remapper's own presets directory (a fixed convention of
input-remapper itself, not anything specific to this machine's hardware)
and by calling its DBus service, which reports whatever it currently knows
about on the running system.
"""

from pathlib import Path

from PySide6.QtDBus import QDBusConnection

from . import dbus_utils

PRESETS_DIR = Path.home() / ".config" / "input-remapper-2" / "presets"

SERVICE = "inputremapper.Control"
OBJECT_PATH = "/inputremapper/Control"
INTERFACE = "inputremapper.Control"


def list_devices() -> list[str]:
    """Devices that currently have at least one preset on disk."""
    if not PRESETS_DIR.is_dir():
        return []
    return sorted(p.name for p in PRESETS_DIR.iterdir() if p.is_dir())


def list_presets(device: str) -> list[str]:
    """Presets that exist on disk for the given device."""
    device_dir = PRESETS_DIR / device
    if not device_dir.is_dir():
        return []
    return sorted(p.stem for p in device_dir.glob("*.json"))


def _system_bus_call(method: str, args: list):
    bus = QDBusConnection.systemBus()
    return dbus_utils.call(bus, SERVICE, OBJECT_PATH, INTERFACE, method, args)


def start_injecting(device: str, preset: str) -> bool:
    result = _system_bus_call("start_injecting", [device, preset])
    return bool(result[0]) if result else False


def get_state(device: str) -> str:
    result = _system_bus_call("get_state", [device])
    return str(result[0]) if result else ""
