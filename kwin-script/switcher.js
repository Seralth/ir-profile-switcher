// Notifies com.seralth.IRProfileSwitcher over DBus whenever a window is
// activated (focused) or newly added (launched). No polling — purely
// event-driven via KWin's own signals.

function notify(window) {
    if (!window || !window.resourceClass) {
        return;
    }
    callDBus(
        "com.seralth.IRProfileSwitcher",
        "/Switcher",
        "com.seralth.IRProfileSwitcher",
        "NotifyWindow",
        window.resourceClass
    );
}

workspace.windowActivated.connect(notify);
workspace.windowAdded.connect(notify);

if (workspace.activeWindow) {
    notify(workspace.activeWindow);
}
