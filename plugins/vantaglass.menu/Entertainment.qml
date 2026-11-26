import QtQuick
import Quickshell
import Quickshell.Hyprland
import Quickshell.Io
import qs.Commons as Commons

Item {
    id: root

    property var shell: null
    readonly property string workspaceName: "entertainment"
    readonly property var entertainmentWorkspace: Hyprland.workspaces.values.find(workspace => workspace.name === workspaceName)
    readonly property var focusedWorkspace: Hyprland.focusedMonitor?.activeWorkspace ?? Hyprland.focusedWorkspace
    readonly property bool focused: focusedWorkspace?.name === workspaceName
    readonly property string helper: Quickshell.env("HOME") + "/.local/share/vantaglass/runtime/entertainment/mode.py"
    readonly property var appLibrary: shell?.appLibrary ?? null
    readonly property int recentLimit: 32
    property bool browsing: true
    property var applications: []
    property var recentApps: []
    property bool historyReady: false

    onAppLibraryChanged: refreshApplications()

    function refreshApplications() {
        applications = appLibrary ? appLibrary.sortedEntries("").map(row => row.entry) : [];
    }

    function validAppId(id) {
        return typeof id === "string" && id.length > 0 && id.length <= 255;
    }

    function loadRecentApps(ids) {
        if (historyReady) return;
        const pending = recentApps.length > 0;
        recentApps = Array.from(new Set(recentApps.concat(ids.filter(validAppId)))).slice(0, recentLimit);
        historyReady = true;
        if (pending) history.setText(JSON.stringify(recentApps));
    }

    function rememberApp(id) {
        if (!validAppId(id) || recentApps[0] === id) return;
        recentApps = [id, ...recentApps.filter(previous => previous !== id)].slice(0, recentLimit);
        if (historyReady) history.setText(JSON.stringify(recentApps));
    }

    Connections {
        target: root.appLibrary
        function onAppsChanged() { root.refreshApplications(); }
    }

    FileView {
        id: history
        path: Quickshell.env("HOME") + "/.local/state/vantaglass/entertainment-recents.json"
        printErrors: false
        onLoaded: {
            const contents = text();
            let ids = [];
            try {
                if (contents.length <= 65536) ids = JSON.parse(contents);
            } catch (error) {
                console.warn("Unable to read Entertainment recents", error);
            }
            root.loadRecentApps(Array.isArray(ids) ? ids : []);
        }
        onLoadFailed: root.loadRecentApps([])
        onSaveFailed: error => console.warn("Unable to save Entertainment recents", error)
    }

    function open() {
        if (focused) {
            action("browse");
        } else if (!workspaceCommand.running) {
            workspaceCommand.exec(["python", helper, "enter"]);
        }
    }

    function leave() {
        if (focused && !workspaceCommand.running)
            workspaceCommand.exec(["python", helper, "leave"]);
    }

    function toggle() {
        if (focused) action(browsing ? "stage" : "browse");
        else open();
    }

    Process {
        id: workspaceCommand
        stderr: SplitParser { onRead: line => console.warn(line) }
    }

    Commons.ShellIpc {
        target: "vantaglass.entertainment"
        function openDashboard(): string {
            root.open();
            return "ok";
        }
        function status(): string {
            return JSON.stringify({
                workspace: root.focusedWorkspace?.name ?? "", browsing: root.browsing,
                shelf: shelves.instances.map(item => ({
                    workspace: item.workspace?.name ?? "", visible: item.visible, shown: item.shelfShown,
                    fullscreen: !!item.fullscreenWindow, width: item.width, height: item.height,
                    appList: item.appList, entries: item.page.map(tile => tile.address || tile.app?.id)
                }))
            });
        }
        function input(action: string): void { root.route(action); }
    }

    signal action(string name)

    function route(name) {
        if (name === "home") {
            toggle();
        } else if (focused && browsing) action(name);
    }

    GlobalShortcut {
        appid: "vantaglass"
        name: "entertainment"
        description: qsTr("Enter or return to Entertainment")
        onPressed: root.toggle()
    }

    GlobalShortcut {
        appid: "vantaglass"
        name: "entertainment-stage"
        description: qsTr("Focus the Entertainment stage")
        onPressed: if (root.focused) root.action("stage")
    }

    GlobalShortcut {
        appid: "vantaglass"
        name: "entertainment-apps"
        description: qsTr("Focus the Entertainment app shelf")
        onPressed: if (root.focused) root.action("browse")
    }

    Process {
        command: ["python", root.helper, "input"]
        running: true
        stdout: SplitParser { onRead: line => root.route(line) }
    }

    Variants {
        id: shelves
        model: Quickshell.screens
        delegate: Dashboard {
            required property var modelData
            screen: modelData
            controller: root
        }
    }
}
