// One-shot: reports currently open windows back to the GUI's picker
// service. Loaded fresh and unloaded again each time the "Add mapping"
// dialog needs a live window list.
var list = workspace.windowList();
var classes = [];
var captions = [];
for (var i = 0; i < list.length; i++) {
    if (list[i].resourceClass) {
        classes.push(list[i].resourceClass);
        captions.push(list[i].caption || "");
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
