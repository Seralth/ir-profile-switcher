import argparse
import logging
import signal
import socket
import sys

from PySide6.QtCore import QCoreApplication, QSocketNotifier


def _quit_on_signals(app) -> None:
    """Quit the Qt event loop on SIGTERM/SIGINT, so a `systemctl stop`
    runs the clean shutdown. Python only handles signals when it runs
    code, so the signal wakes the event loop through a socket."""
    read_sock, write_sock = socket.socketpair()
    read_sock.setblocking(False)
    write_sock.setblocking(False)
    signal.set_wakeup_fd(write_sock.fileno())
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: app.quit())
    notifier = QSocketNotifier(read_sock.fileno(), QSocketNotifier.Type.Read, app)
    notifier.activated.connect(lambda *_: read_sock.recv(64))
    # Keep the sockets alive as long as the app.
    app._signal_socks = (read_sock, write_sock, notifier)


def run_watcher():
    from ir_profile_switcher import config, kwin_loader, notify, preflight, watcher_service

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    state = preflight.status()
    service_name = config.get_input_remapper_service()
    if state == "not_installed":
        logging.critical(
            "input-remapper is not installed -- cannot switch presets. "
            "Install it, then restart this watcher."
        )
        sys.exit(1)
    elif state == "binary_found_no_service":
        logging.error(
            "Found input-remapper's binary, but no systemd service named "
            "'%s' -- it may have been renamed. Open the GUI and use "
            "'Pick service...' to point this at the right one. Running anyway.",
            service_name,
        )
    elif state == "installed_not_running":
        # Never prompt for a password from here. The GUI's Fix button does
        # that. Switching starts working as soon as the service runs.
        logging.error(
            "'%s' is not running. Presets cannot switch until it runs. "
            "Open Profile Switcher and press Fix. Running anyway.",
            service_name,
        )
        notify.notify_problem(
            "input-remapper is not running",
            "input-remapper is not running — open Profile Switcher to fix",
        )

    app = QCoreApplication(sys.argv)
    _quit_on_signals(app)
    service = watcher_service.register()
    resume_listener = watcher_service.watch_resume(service)  # noqa: F841 -- keep alive
    kwin_script = kwin_loader.ScriptKeeper()
    app.aboutToQuit.connect(kwin_script.stop)
    kwin_script.start()
    logging.info("Watcher running: DBus service registered, loading the KWin script.")
    sys.exit(app.exec())


def run_gui():
    from PySide6.QtWidgets import QApplication

    from ir_profile_switcher.gui import MainWindow

    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--watcher", action="store_true", help="Run headless watcher (no GUI)"
    )
    parser.add_argument(
        "--install",
        action="store_true",
        help="Add the app menu entry and the background watcher's service",
    )
    parser.add_argument(
        "--uninstall",
        action="store_true",
        help="Stop the watcher and remove its service and the app menu entry",
    )
    args = parser.parse_args()

    if args.install or args.uninstall:
        from ir_profile_switcher import install

        if args.install:
            install.install()
        else:
            install.uninstall()
    elif args.watcher:
        run_watcher()
    else:
        run_gui()
