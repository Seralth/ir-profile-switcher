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
- `input-remapper` running as a service (`systemctl --user enable --now
  input-remapper.service` or the system-level equivalent)
- Python 3, PySide6 (`pacman -S pyside6` on Arch/CachyOS)

## Usage

Run the GUI to manage mappings:

```sh
python3 src/main.py
```

Run the background watcher (what actually does the switching):

```sh
python3 src/main.py --watcher
```

Or install it as a systemd user service so it starts at login:

```sh
mkdir -p ~/.config/systemd/user
ln -s "$(pwd)/systemd/ir-profile-switcher.service" ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now ir-profile-switcher.service
```

## Status

First working version. KDE/Wayland only for now.
