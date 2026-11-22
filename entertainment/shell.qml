import QtQuick
import Quickshell
import Quickshell.Hyprland
import Quickshell.Io

ShellRoot {
    id: root

    property var enabled: []
    property var hiddenWorkspaces: ({})
    property bool hasEnabledWorkspace: enabled.some(name => Hyprland.workspaces.values.some(
        workspace => workspace.name === name && !workspace.lastIpcObject?.special))
    readonly property string helper: decodeURIComponent(Qt.resolvedUrl("mode.py").toString()).replace(/^file:\/\//, "")
    readonly property var focusedWorkspace: Hyprland.focusedMonitor?.activeWorkspace ?? Hyprland.focusedWorkspace

    function setModes(value) {
        try {
            const workspaces = JSON.parse(value);
            if (Array.isArray(workspaces)) {
                const next = workspaces.filter(name => typeof name === "string").slice(0, 100);
                const retained = Object.create(null);
                for (const name of next) {
                    if (hiddenWorkspaces[name] === true)
                        retained[name] = true;
                }
                hiddenWorkspaces = retained;
                enabled = next;
            }
        } catch (error) {
            console.warn("Cannot read entertainment workspace settings:", error);
        }
    }

    function setDashboardHidden(name, value) {
        hiddenWorkspaces = Object.assign({}, hiddenWorkspaces, { [name]: value });
    }

    function revealDashboard() {
        const workspace = focusedWorkspace;
        if (workspace && enabled.includes(workspace.name))
            setDashboardHidden(workspace.name, false);
    }

    FileView {
        id: modes
        path: (Quickshell.env("XDG_STATE_HOME") || Quickshell.env("HOME") + "/.local/state")
            + "/vantaglass/entertainment.json"
        watchChanges: true
        onFileChanged: reload()
        onLoaded: root.setModes(text())
    }

    IpcHandler {
        target: "entertainment"
        function openDashboard(): string {
            root.revealDashboard();
            return JSON.stringify(root.hiddenWorkspaces);
        }
        function status(): string {
            return JSON.stringify({
                workspace: root.focusedWorkspace?.name ?? "",
                monitors: Hyprland.monitors.values.map(monitor => [monitor.name, monitor.activeWorkspace?.name, monitor.focused]),
                enabled: root.enabled,
                hidden: root.hiddenWorkspaces
            });
        }
        function input(action: string): void { root.route(action); }
    }

    signal action(string name)

    function route(name) {
        if (name === "home") {
            revealDashboard();
            return;
        }
        action(name);
    }

    Process {
        command: ["python", root.helper, "input"]
        running: root.hasEnabledWorkspace
        stdout: SplitParser {
            onRead: line => root.route(line)
        }
    }

    Variants {
        model: Quickshell.screens
        delegate: Dashboard {
            required property var modelData
            screen: modelData
            shell: root
        }
    }
}
