// Reports windows to com.seralth.IRProfileSwitcher over DBus:
// - the focused window, whenever a window is activated or launched
//   already focused. A window launched in the background is not reported
//   as focused.
// - every window that opens or closes, so the watcher knows when a
//   program's last window is gone.
// - caption changes, so notifications can use the program's own name.
// On load, the windows already open are reported first. No polling —
// purely event-driven via KWin's own signals.
//
// Windows are told apart by KWin's internalId, a UUID that stays the same
// for the whole life of a window.

var SERVICE = "com.seralth.IRProfileSwitcher";
var PATH = "/Switcher";

function windowId(window) {
    return String(window.internalId);
}

function watchCaption(window) {
    window.captionChanged.connect(function () {
        if (window.resourceClass) {
            callDBus(
                SERVICE,
                PATH,
                SERVICE,
                "CaptionChanged",
                window.resourceClass,
                window.caption || ""
            );
        }
    });
}

function notifyFocus(window) {
    if (!window || !window.resourceClass) {
        return;
    }
    callDBus(
        SERVICE,
        PATH,
        SERVICE,
        "NotifyWindow",
        window.resourceClass,
        window.caption || ""
    );
}

workspace.windowActivated.connect(notifyFocus);

workspace.windowAdded.connect(function (window) {
    if (!window || !window.resourceClass) {
        return;
    }
    watchCaption(window);
    callDBus(
        SERVICE,
        PATH,
        SERVICE,
        "WindowAdded",
        windowId(window),
        window.resourceClass,
        window.caption || "",
        window === workspace.activeWindow
    );
});

workspace.windowRemoved.connect(function (window) {
    if (!window || !window.resourceClass) {
        return;
    }
    callDBus(
        SERVICE,
        PATH,
        SERVICE,
        "WindowRemoved",
        windowId(window),
        window.resourceClass
    );
});

var list = workspace.windowList();
var ids = [];
var classes = [];
var captions = [];
for (var i = 0; i < list.length; i++) {
    if (list[i].resourceClass) {
        watchCaption(list[i]);
        ids.push(windowId(list[i]));
        classes.push(list[i].resourceClass);
        captions.push(list[i].caption || "");
    }
}
callDBus(SERVICE, PATH, SERVICE, "OpenWindows", ids, classes, captions);

notifyFocus(workspace.activeWindow);
