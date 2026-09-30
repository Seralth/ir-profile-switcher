# Input Remapper Profile Switcher

Automatically switches [input-remapper](https://github.com/sezanzeb/input-remapper)
presets based on which program is running or focused, on KDE Plasma
(Wayland or X11 via KWin). Includes a Qt GUI for managing which program
maps to which preset(s) per device.

## Why

input-remapper doesn't support per-application preset switching on its
own. This adds that on top, without depending on X11-only tools (like
`xdotool`/`devilspie2`) or GTK.

## How it works

- A small KWin script watches window activation/launch events natively
  (no polling) and reports the focused window's class over DBus.
- A Python watcher service matches that against your mappings and calls
  input-remapper's own DBus service (`inputremapper.Control`) directly to
  switch presets — no shelling out to `input-remapper-control`.
- Devices and presets are never hardcoded: both are discovered live from
  `~/.config/input-remapper-2/presets/` and input-remapper's DBus
  interface, so the same app works on any machine/device set without code
  changes.
- One program mapping can drive multiple devices at once (e.g. mouse +
  keyboard + keypad switching together).
- Focusing an unmapped window leaves the current preset active — it only
  changes when a different mapped program is focused. A program that
  opens in the background does not switch the preset.
- Window classes match without regard to case.
- The watcher does not restart a preset that is already running.
  Restarting a preset briefly interrupts the device.
- While a mapped program is focused, the watcher checks every 30 seconds
  that input-remapper still runs the program's presets, and again shortly
  after resume. A preset that input-remapper lost is applied again. This
  covers a device reconnect and an input-remapper restart. A preset you
  stop on purpose, for example in input-remapper's own window, stays
  stopped until the next switch.
- A failed switch is retried on the next focus and on the next check.

## Requirements

- KDE Plasma (KWin) on Wayland or X11
- `input-remapper` installed and running as its systemd service (the
  GUI's Fix button enables and starts the service -- see below, no
  manual `systemctl` needed)
- Python 3, PySide6 (`pacman -S pyside6` on Arch/CachyOS)

## Install

Clone the repo anywhere, then from inside it:

```sh
python3 src/main.py --install
```

`--install` adds the app menu entry and the background watcher's systemd
user service, both pointing at wherever this copy of the repo lives, then
enables and starts the watcher. Run it again after moving the repo. The
watcher can also be switched on and off from the GUI.

`--install` also adds `ir-profile-switcher-failed.service`. systemd runs
this unit when the watcher keeps crashing and systemd stops restarting
the watcher. The unit shows a "Profile switcher stopped" notification.

To remove everything again:

```sh
python3 src/main.py --uninstall
```

## Usage

Launch "Input Remapper Profile Switcher" from the KDE app menu, or:

```sh
python3 src/main.py
```

The GUI's status row shows whether input-remapper is installed and
running as a service, and whether this app's own watcher is enabled --
with buttons to fix, enable/disable, or (if input-remapper's service unit
is ever renamed) search and repoint at the right one. The status rows
update every 5 seconds. No terminal commands needed for day-to-day use,
install, or uninstall.

## Notifications

- A switch shows a short notification. The GUI has a checkbox to turn
  switch notifications off.
- A failed switch always shows a notification, at most once per device
  every 5 minutes.
- The watcher never asks for a password. When input-remapper's service
  is not running, the watcher shows one notification and keeps running.
  Switching starts working once the service runs. Use the GUI's Fix
  button to start the service.
- When the watcher cannot load its KWin script within 2 minutes of
  starting, the watcher shows a notification. The watcher loads the
  KWin script again whenever KWin restarts.

The background watcher (what actually does the switching) also runs
standalone if needed:

```sh
python3 src/main.py --watcher
```

## Status

First working version. KDE/Wayland only for now.

## License

MIT — see [LICENSE](LICENSE).
