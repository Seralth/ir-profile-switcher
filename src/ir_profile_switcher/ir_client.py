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


SYS_INPUT_DIR = Path("/sys/class/input")


def _read(path: Path) -> str:
    try:
        return path.read_text().strip()
    except OSError:
        return ""


def connected_group_keys(device: str) -> list[str]:
    """input-remapper's group keys for every connected hardware device
    whose group is named `device`.

    input-remapper names a group after its shortest device name. When
    several connected devices share that name, the keys are "name",
    "name 2", "name 3", and so on. The same mouse plugged in by cable
    while its wireless dongle is also connected shows up twice. Both
    groups load presets from the folder named `device`.

    input-remapper has no DBus method that lists groups, so this repeats
    its grouping from sysfs: same unique key (bus, vendor, product, uniq,
    first part of phys), skipping its own forwarded devices and devices
    with no buttons or axes. Returns [device] when nothing matches, so a
    disconnected device still reports a failure as before.
    """
    groups: dict[str, list[str]] = {}
    for node in SYS_INPUT_DIR.glob("input*"):
        name = _read(node / "name")
        phys = _read(node / "phys")
        if not name or name.startswith("input-remapper") or phys.startswith("input-remapper"):
            continue
        caps = [_read(node / "capabilities" / c) for c in ("key", "rel", "abs")]
        if all(c in ("", "0") for c in caps):
            continue
        key = "_".join(
            [
                _read(node / "id" / "bustype"),
                _read(node / "id" / "vendor"),
                _read(node / "id" / "product"),
                _read(node / "uniq"),
                phys.split("/")[0] or "-",
            ]
        )
        groups.setdefault(key, []).append(name)
    count = sum(1 for names in groups.values() if min(names, key=len) == device)
    if count == 0:
        return [device]
    return [device] + [f"{device} {i}" for i in range(2, count + 1)]


def _system_bus_call(method: str, args: list):
    bus = QDBusConnection.systemBus()
    return dbus_utils.call(bus, SERVICE, OBJECT_PATH, INTERFACE, method, args)


def _send_config_dir() -> None:
    # The daemon forgets which user's config dir to use whenever it restarts
    # (e.g. during a system update), and then refuses every preset until told
    # again. Telling it before every start is cheap and keeps running injections.
    _system_bus_call("set_config_dir", [str(CONFIG_DIR)])


def start_injecting(device: str, preset: str) -> bool:
    _send_config_dir()
    result = _system_bus_call("start_injecting", [device, preset])
    return bool(result[0]) if result else False


def get_state(device: str) -> str:
    """input-remapper's injector state for the device, e.g. "RUNNING",
    "STARTING", "FAILED", "STOPPED", "NO_GRAB", or "UNKNOWN" when
    input-remapper has no injection for the device (for example after
    input-remapper restarted)."""
    result = _system_bus_call("get_state", [device])
    return str(result[0]) if result else ""


def stop_injecting(device: str) -> None:
    _system_bus_call("stop_injecting", [device])


def autoload_single(device: str) -> None:
    """Start the device's own autoload preset, if input-remapper has one
    set for it. Does nothing for a device without an autoload preset."""
    _send_config_dir()
    _system_bus_call("autoload_single", [device])
