import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import Quickshell
import Quickshell.Hyprland
import Quickshell.Io
import Quickshell.Wayland

PanelWindow {
    id: dashboard
    required property var shell
    readonly property var monitor: screen ? Hyprland.monitorFor(screen) : null
    readonly property var workspace: monitor?.activeWorkspace
    readonly property string workspaceName: workspace?.name ?? ""
    readonly property bool focusedMonitor: monitor?.focused ?? false
    readonly property bool enabledHere: workspaceName !== "" && shell.enabled.includes(workspaceName)
    readonly property var localWindows: Hyprland.toplevels.values.filter(window =>
        window.workspace === workspace && /^([a-f0-9]+|0x[a-f0-9]+)$/i.test(window.address))
    readonly property var applications: DesktopEntries.applications.values.filter(app =>
        !app.noDisplay && !localWindows.some(window => appFor(window)?.id === app.id)
    ).sort((a, b) => a.name.localeCompare(b.name))
    readonly property var rows: [localWindows, applications]
    readonly property var labels: JSON.parse(labelsFile.text() || "{}")
    readonly property real unit: Math.max(0.64, Math.min(1.4, width / 1440, height / 810))
    readonly property color ink: "#f7f7f7"
    readonly property color muted: "#b4b4b4"
    property int row: 1
    property int column: 0
    property string closing: ""
    property string notice: ""
    property string launching: ""
    property string lastInput: ""
    property bool lastInputFromDevice: false
    property double lastInputAt: 0
    readonly property var launchedWindow: launching ? localWindows.find(window => appFor(window)?.id === launching) : null
    property bool hadWindows: false

    anchors { top: true; bottom: true; left: true; right: true }
    exclusionMode: ExclusionMode.Ignore
    WlrLayershell.layer: WlrLayer.Overlay
    WlrLayershell.namespace: "vantaglass-entertainment"
    WlrLayershell.keyboardFocus: focusedMonitor ? WlrKeyboardFocus.Exclusive : WlrKeyboardFocus.None
    color: "#090909"
    visible: enabledHere && !shell.hiddenWorkspaces[workspaceName]

    FileView {
        id: labelsFile
        path: Qt.resolvedUrl("i18n/en.json")
        blockLoading: true
    }

    onVisibleChanged: {
        if (visible) {
            input.forceActiveFocus();
            clampSelection();
        } else {
            closing = "";
        }
    }
    onWorkspaceNameChanged: {
        row = localWindows.length ? 0 : 1;
        column = 0;
        closing = "";
        notice = "";
        launching = "";
    }
    onLocalWindowsChanged: {
        if (!localWindows.length && hadWindows && enabledHere)
            shell.setDashboardHidden(workspaceName, false);
        hadWindows = localWindows.length > 0;
    }
    onLaunchedWindowChanged: {
        if (launchedWindow)
            Qt.callLater(presentLaunch);
    }
    function presentLaunch() {
        if (launchedWindow && !windowCommand.running && !presentTimer.running) {
            const window = launchedWindow;
            launching = "";
            launchTimer.stop();
            openWindow(window);
        }
    }
    onRowsChanged: clampSelection()

    function appFor(window) {
        const appId = window.wayland?.appId || window.lastIpcObject?.class || "";
        return DesktopEntries.heuristicLookup(appId);
    }

    function clampSelection() {
        if (!rows[row].length && rows[1 - row].length)
            row = 1 - row;
        column = Math.max(0, Math.min(column, rows[row].length - 1));
    }

    function openWindow(window) {
        if (windowCommand.running || presentTimer.running)
            return;
        windowCommand.presenting = true;
        windowCommand.operationWorkspace = workspaceName;
        windowCommand.command = ["python", shell.helper, "fullscreen", workspaceName, window.address];
        // Let the keyboard-exclusive layer unmap before focusing the app.
        shell.setDashboardHidden(workspaceName, true);
        presentTimer.start();
    }

    function handleInput(action, fromDevice) {
        const now = Date.now();
        // A Linux remote can deliver the same key through both evdev and Wayland.
        if (lastInput === action && lastInputFromDevice !== fromDevice && now - lastInputAt < 65)
            return;
        lastInput = action;
        lastInputFromDevice = fromDevice;
        lastInputAt = now;
        act(action);
    }

    function act(action) {
        if (!visible || !focusedMonitor)
            return;
        const selected = rows[row][column];
        if (closing) {
            if (action === "select") {
                if (windowCommand.running)
                    return;
                windowCommand.presenting = false;
                windowCommand.command = ["python", shell.helper, "close", workspaceName, closing];
                windowCommand.running = true;
            }
            closing = "";
            return;
        }
        switch (action) {
        case "left": column--; break;
        case "right": column++; break;
        case "up": if (localWindows.length) row = 0; break;
        case "down": if (applications.length) row = 1; break;
        case "back":
            if (localWindows.length)
                shell.setDashboardHidden(workspaceName, true);
            else
                exitMode();
            return;
        case "exit": exitMode(); return;
        case "close":
            if (row === 0 && selected)
                closing = selected.address;
            return;
        case "select":
            if (selected && row === 0)
                openWindow(selected);
            else if (selected && !launching) {
                launching = selected.id;
                notice = "";
                launchTimer.restart();
                if (selected.runInTerminal)
                    Quickshell.execDetached(["xdg-terminal-exec", ...selected.command]);
                else
                    selected.execute();
            }
            return;
        }
        clampSelection();
    }

    function exitMode() {
        if (modeCommand.running)
            return;
        modeCommand.command = ["python", shell.helper, "disable", workspaceName];
        modeCommand.running = true;
    }

    Process {
        id: modeCommand
        onExited: (code, status) => {
            if (code !== 0) dashboard.notice = dashboard.labels.actionFailed;
        }
    }
    Process {
        id: windowCommand
        stderr: SplitParser { onRead: line => console.warn(line) }
        property bool presenting: false
        property string operationWorkspace: ""
        onExited: (code, status) => {
            if (code !== 0) {
                if (presenting)
                    dashboard.shell.setDashboardHidden(operationWorkspace, false);
                dashboard.notice = dashboard.labels.actionFailed;
            }
        }
    }
    Timer {
        id: presentTimer
        interval: 100
        onTriggered: {
            if (dashboard.enabledHere && dashboard.workspaceName === windowCommand.operationWorkspace)
                windowCommand.running = true;
            else
                dashboard.shell.setDashboardHidden(windowCommand.operationWorkspace, false);
        }
    }
    Timer {
        id: launchTimer
        interval: 10000
        onTriggered: {
            dashboard.launching = "";
            dashboard.notice = dashboard.labels.launchFailed;
        }
    }
    Connections {
        target: dashboard.shell
        enabled: dashboard.visible && dashboard.focusedMonitor
        function onAction(name) { dashboard.handleInput(name, true); }
    }

    FocusScope {
        id: input
        anchors.fill: parent
        focus: true
        Keys.onPressed: event => {
            const bindings = {
                [Qt.Key_Left]: "left", [Qt.Key_Right]: "right",
                [Qt.Key_Up]: "up", [Qt.Key_Down]: "down",
                [Qt.Key_Return]: "select", [Qt.Key_Enter]: "select",
                [Qt.Key_Select]: "select", [Qt.Key_Space]: "select",
                [Qt.Key_Escape]: "back", [Qt.Key_Back]: "back",
                [Qt.Key_Delete]: "close", [Qt.Key_Menu]: "close",
                [Qt.Key_F10]: "exit", [Qt.Key_Exit]: "exit"
            };
            const action = bindings[event.key];
            if (action) {
                event.accepted = true;
                if (!event.isAutoRepeat || ["left", "right", "up", "down"].includes(action))
                    dashboard.handleInput(action, false);
            }
        }

        Rectangle {
            anchors.fill: parent
            gradient: Gradient {
                GradientStop { position: 0; color: "#202020" }
                GradientStop { position: 0.54; color: "#0b0b0b" }
                GradientStop { position: 1; color: "#000000" }
            }
        }

        ColumnLayout {
            anchors.fill: parent
            anchors.margins: 58 * dashboard.unit
            spacing: 22 * dashboard.unit

            RowLayout {
                Layout.fillWidth: true
                Text {
                    Layout.fillWidth: true
                    text: dashboard.labels.title ?? ""
                    font.pixelSize: 50 * dashboard.unit
                    font.weight: Font.DemiBold
                    color: dashboard.ink
                }
                Text {
                    text: dashboard.workspaceName
                    textFormat: Text.PlainText
                    font.pixelSize: 20 * dashboard.unit
                    color: dashboard.muted
                }
            }

            DeckRow {
                Layout.fillWidth: true
                Layout.fillHeight: true
                dashboard: dashboard
                index: 0
                heading: dashboard.labels.running ?? ""
                visible: dashboard.localWindows.length > 0
            }
            DeckRow {
                Layout.fillWidth: true
                Layout.fillHeight: true
                dashboard: dashboard
                index: 1
                heading: dashboard.labels.library ?? ""
                visible: dashboard.applications.length > 0
            }
            Text {
                visible: !dashboard.localWindows.length && !dashboard.applications.length
                Layout.fillHeight: true
                text: dashboard.labels.empty ?? ""
                font.pixelSize: 22 * dashboard.unit
                color: dashboard.muted
            }

            RowLayout {
                Layout.fillWidth: true
                spacing: 22 * dashboard.unit
                Text {
                    Layout.fillWidth: true
                    text: dashboard.launching ? dashboard.labels.working :
                        dashboard.notice || "↵  /  A   " + (dashboard.row === 0 ? dashboard.labels.resume : dashboard.labels.open)
                    textFormat: Text.PlainText
                    font.pixelSize: 18 * dashboard.unit
                    color: dashboard.ink
                }
                Text {
                    visible: dashboard.row === 0 && dashboard.localWindows.length > 0
                    text: "Del  /  X   " + dashboard.labels.close
                    font.pixelSize: 18 * dashboard.unit
                    color: dashboard.muted
                }
                Text {
                    text: "Esc  /  B   " + dashboard.labels.back + "     F10  /  ≡   " + dashboard.labels.leave
                    font.pixelSize: 18 * dashboard.unit
                    color: dashboard.muted
                }
            }
        }

        Rectangle {
            anchors.fill: parent
            visible: dashboard.closing !== ""
            color: "#aa000000"
            MouseArea { anchors.fill: parent; onClicked: dashboard.act("back") }
            Rectangle {
                anchors.centerIn: parent
                width: 510 * dashboard.unit
                height: 170 * dashboard.unit
                radius: 22 * dashboard.unit
                color: "#161616"
                border.color: "#6b6b6b"
                Column {
                    anchors.centerIn: parent
                    spacing: 18 * dashboard.unit
                    Text {
                        text: dashboard.labels.confirm ?? ""
                        color: dashboard.ink
                        font.pixelSize: 30 * dashboard.unit
                    }
                    Text {
                        text: "↵  /  A   " + dashboard.labels.close + "      Esc  /  B   " + dashboard.labels.back
                        color: dashboard.muted
                        font.pixelSize: 18 * dashboard.unit
                    }
                }
            }
        }
    }
}
