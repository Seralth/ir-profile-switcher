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
  changes when a different mapped program is launched or focused.

## Requirements

- KDE Plasma (KWin) on Wayland or X11
- `input-remapper` installed (its own systemd service is checked and
  fixed automatically by this app -- see below, no manual `systemctl`
  needed)
- Python 3, PySide6 (`pacman -S pyside6` on Arch/CachyOS)

## Install

Symlink the app into the places KDE and systemd look for it:

```sh
# Show up in the KDE application menu
mkdir -p ~/.local/share/applications
ln -s "$(pwd)/ir-profile-switcher.desktop" ~/.local/share/applications/
kbuildsycoca6 --noincremental

# Background watcher, starts at login
mkdir -p ~/.config/systemd/user
ln -s "$(pwd)/systemd/ir-profile-switcher.service" ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now ir-profile-switcher.service
```

(The watcher's enable button in the GUI recreates its own symlink if it
ever goes missing, so this only needs doing once by hand.)

## Usage

Launch "Input Remapper Profile Switcher" from the KDE app menu, or:

```sh
python3 src/main.py
```

The GUI's status row shows whether input-remapper is installed and
running as a service, and whether this app's own watcher is enabled --
with buttons to fix, enable/disable, or (if input-remapper's service unit
is ever renamed) search and repoint at the right one. No terminal
commands needed for day-to-day use, install, or uninstall.

The background watcher (what actually does the switching) also runs
standalone if needed:

```sh
python3 src/main.py --watcher
```

## Status

First working version. KDE/Wayland only for now.
