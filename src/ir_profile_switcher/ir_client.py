"""Talks to input-remapper: device/preset discovery and preset activation.

Device and preset names are never hardcoded here — they are discovered by
listing input-remapper's own presets directory (a fixed convention of
input-remapper itself, not anything specific to this machine's hardware)
and by calling its DBus service, which reports whatever it currently knows
about on the running system.
"""

from pathlib import Path

from PySide6.QtDBus import QDBusConnection, QDBusMessage

CONFIG_DIR = Path.home() / ".config" / "input-remapper-2"
PRESETS_DIR = CONFIG_DIR / "presets"

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
    if not bus.isConnected():
        raise RuntimeError("Could not connect to the DBus system bus")
    msg = QDBusMessage.createMethodCall(SERVICE, OBJECT_PATH, INTERFACE, method)
    msg.setArguments(args)
    reply = bus.call(msg)
    if reply.type() == QDBusMessage.MessageType.ErrorMessage:
        raise RuntimeError(f"{method} failed: {reply.errorMessage()}")
    return reply.arguments()


def start_injecting(device: str, preset: str) -> bool:
    # The daemon forgets which user's config dir to use whenever it restarts
    # (e.g. during a system update), and then refuses every preset until told
    # again. Telling it on every switch is cheap and keeps running injections.
    _system_bus_call("set_config_dir", [str(CONFIG_DIR)])
    result = _system_bus_call("start_injecting", [device, preset])
    return bool(result[0]) if result else False


def get_state(device: str) -> str:
    result = _system_bus_call("get_state", [device])
    return str(result[0]) if result else ""
