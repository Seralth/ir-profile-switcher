// Live: connects to KWin's own windowAdded/windowRemoved signals so the
// picker tracks programs launching and closing immediately, then reports
// the windows already open at watch-start. Stays loaded for as long as
// the "Add mapping" dialog is open; unloaded when the dialog closes. No
// polling.

function windowInfo(window) {
    return window && window.resourceClass
        ? [window.resourceClass, window.caption || ""]
        : null;
}

workspace.windowAdded.connect(function (window) {
    var info = windowInfo(window);
    if (!info) {
        return;
    }
    callDBus(
        "com.seralth.IRProfileSwitcher.Picker",
        "/Picker",
        "com.seralth.IRProfileSwitcher.Picker",
        "WindowAdded",
        info[0],
        info[1]
    );
});

workspace.windowRemoved.connect(function (window) {
    var info = windowInfo(window);
    if (!info) {
        return;
    }
    callDBus(
        "com.seralth.IRProfileSwitcher.Picker",
        "/Picker",
        "com.seralth.IRProfileSwitcher.Picker",
        "WindowRemoved",
        info[0]
    );
});

var list = workspace.windowList();
var classes = [];
var captions = [];
for (var i = 0; i < list.length; i++) {
    var info = windowInfo(list[i]);
    if (info) {
        classes.push(info[0]);
        captions.push(info[1]);
    }
}
callDBus(
    "com.seralth.IRProfileSwitcher.Picker",
    "/Picker",
    "com.seralth.IRProfileSwitcher.Picker",
    "ReceiveWindowList",
    classes,
    captions
);
