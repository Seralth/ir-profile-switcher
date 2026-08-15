import argparse
import logging
import sys

from PySide6.QtCore import QCoreApplication


def run_watcher():
    from ir_profile_switcher import kwin_loader, preflight, watcher_service

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    state = preflight.status()
    if state == "not_installed":
        logging.critical(
            "input-remapper is not installed -- cannot switch presets. "
            "Install it, then restart this watcher."
        )
        sys.exit(1)
    elif state == "installed_not_running":
        logging.warning(
            "input-remapper.service is not running as a service (would "
            "otherwise prompt for a password on every preset switch). "
            "Attempting to enable and start it now."
        )
        ok, message = preflight.ensure_service_running()
        (logging.info if ok else logging.error)(message)

    app = QCoreApplication(sys.argv)
    service = watcher_service.register()  # noqa: F841 -- keep alive, holds DBus registration
    kwin_loader.load_and_start()
    logging.info("Watcher running: DBus service registered, KWin script loaded.")
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
    args = parser.parse_args()

    if args.watcher:
        run_watcher()
    else:
        run_gui()
