// Notifies com.seralth.IRProfileSwitcher over DBus whenever a window is
// activated (focused), or launched already focused. A window launched in
// the background is not reported. No polling — purely event-driven via
// KWin's own signals.

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
workspace.windowAdded.connect(function (window) {
    if (window === workspace.activeWindow) {
        notify(window);
    }
});

if (workspace.activeWindow) {
    notify(workspace.activeWindow);
}
