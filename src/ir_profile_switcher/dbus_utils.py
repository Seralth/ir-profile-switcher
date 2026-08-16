"""Shared low-level DBus method-call helper with consistent error
handling, used by every module that talks to a DBus service directly.
"""

from PySide6.QtDBus import QDBusConnection, QDBusMessage


def call(bus: QDBusConnection, service: str, path: str, interface: str, method: str, args: list):
    """Make a DBus method call and return its reply arguments.

    Raises RuntimeError if the bus isn't connected or the call errors.
    """
    if not bus.isConnected():
        raise RuntimeError("Could not connect to the DBus bus")
    msg = QDBusMessage.createMethodCall(service, path, interface, method)
    msg.setArguments(args)
    reply = bus.call(msg)
    if reply.type() == QDBusMessage.MessageType.ErrorMessage:
        raise RuntimeError(f"{method} failed: {reply.errorMessage()}")
    return reply.arguments()
