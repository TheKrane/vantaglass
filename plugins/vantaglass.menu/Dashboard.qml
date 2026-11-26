import QtQuick
import QtQuick.Layouts
import QtQuick.Shapes
import Quickshell
import Quickshell.Hyprland
import Quickshell.Io
import Quickshell.Wayland
import qs.Commons as Commons

PanelWindow {
    id: shelf

    required property var controller
    readonly property var monitor: screen ? Hyprland.monitorFor(screen) : null
    readonly property var workspace: monitor?.activeWorkspace
    readonly property bool focused: monitor?.focused ?? false
    readonly property var localWindows: controller.entertainmentWorkspace?.toplevels.values ?? []
    readonly property bool inEntertainment: workspace?.name === controller.workspaceName
    readonly property var fullscreenWindow: localWindows.find(window => (Number(window.lastIpcObject?.fullscreen) & 2) !== 0) ?? null
    readonly property bool shelfShown: inEntertainment && controller.browsing && !fullscreenWindow
    readonly property var geometry: layout.geometry
    readonly property int tileWidth: geometry.tileWidth ?? 0
    readonly property int tileHeight: geometry.tileHeight ?? 0
    readonly property int stride: tileWidth + (geometry.gap ?? 0)
    readonly property int tileLeft: geometry.tileX ?? 0
    readonly property int tileTop: geometry.tileY ?? 0
    readonly property int columns: geometry.columns ?? 1

    property var layout: ({ windows: [], offset: 0, geometry: {} })
    property string appList: "recent"
    property int selection: 0
    property string launching: ""
    property string closing: ""
    property string notice: ""
    property var pendingView: null
    property bool mappedWhileBrowsing: false
    property string lastInput: ""
    property bool lastInputFromDevice: false
    property double lastInputAt: 0
    readonly property string mainAddress: layout.windows[0] ?? ""
    readonly property int pageNumber: 1 + Math.floor(layout.offset / columns)
    readonly property int pageCount: Math.max(1, Math.ceil(tiles.length / columns))
    readonly property var tiles: {
        const windows = new Map(localWindows.map(window => [addressOf(window), window]));
        const running = layout.windows.slice(1).map(address => {
            const window = windows.get(address);
            return { address, window, app: window ? appFor(window) : null };
        });
        const launched = new Set(localWindows.map(window => appFor(window)?.id));
        const available = controller.applications.filter(app => !launched.has(app.id));
        const byId = new Map(available.map(app => [app.id, app]));
        const apps = appList === "all" ? available : controller.recentApps.map(id => byId.get(id)).filter(Boolean);
        return running.concat(apps.map(app => ({ address: "", window: null, app })));
    }
    readonly property var page: tiles.slice(layout.offset, layout.offset + columns)
    readonly property var launchedWindow: launching ? localWindows.find(window => appFor(window)?.id === launching) : null

    anchors { bottom: true; left: true; right: true }
    margins.bottom: geometry.bottom ?? 14
    implicitHeight: geometry.shelfHeight ?? 170
    exclusiveZone: 0
    exclusionMode: ExclusionMode.Normal
    WlrLayershell.namespace: "vantaglass-entertainment"
    // A top layer fades with the Omarchy bar when Hyprland enters fullscreen.
    WlrLayershell.layer: WlrLayer.Top
    WlrLayershell.keyboardFocus: shelfShown && focused
        ? WlrKeyboardFocus.Exclusive : WlrKeyboardFocus.None
    color: "transparent"
    surfaceFormat.opaque: false
    // Let Hyprland fade an existing shelf. Mapping a new top layer over an
    // already-fullscreen app would put it in front of the app.
    visible: inEntertainment && (mappedWhileBrowsing || !fullscreenWindow)
    mask: shelfShown && geometry.shelfWidth ? shelfRegion : emptyRegion

    Region { id: emptyRegion }

    Region {
        id: shelfRegion
        item: shelfSurface
    }

    Commons.Translations {
        id: strings
        directory: Qt.resolvedUrl("entertainment-i18n")
    }

    onVisibleChanged: if (visible) refresh.restart()
    onInEntertainmentChanged: {
        if (inEntertainment) {
            mappedWhileBrowsing = !fullscreenWindow;
            refresh.restart();
            controller.browsing = !fullscreenWindow;
        }
        else {
            mappedWhileBrowsing = false;
            closing = "";
            launching = "";
            launchTimer.stop();
            notice = "";
            pendingView = null;
        }
    }
    onFullscreenWindowChanged: {
        if (!inEntertainment) return;
        if (fullscreenWindow) controller.rememberApp(appFor(fullscreenWindow)?.id);
        else mappedWhileBrowsing = true;
        if (!actionProcess.running) controller.browsing = !fullscreenWindow;
    }
    onLocalWindowsChanged: if (visible) refresh.restart()
    readonly property int outputHeight: screen?.height ?? 0
    onWidthChanged: if (inEntertainment) refresh.restart()
    onOutputHeightChanged: if (inEntertainment) refresh.restart()
    onColumnsChanged: if (visible) refresh.restart()
    onLayoutChanged: if (visible && focused) pageTimer.restart()
    onTilesChanged: selection = Math.min(selection, Math.max(0, tiles.length - 1))
    onSelectionChanged: if (visible && focused) pageTimer.restart()
    onLaunchedWindowChanged: if (launchedWindow) Qt.callLater(presentLaunch)

    function addressOf(window) {
        const value = String(window?.address ?? "").toLowerCase();
        return value.startsWith("0x") ? value : "0x" + value;
    }

    function appFor(window) {
        return window ? DesktopEntries.heuristicLookup(window.wayland?.appId || window.lastIpcObject?.class || "") : null;
    }

    function presentLaunch() {
        if (!shelfShown || !launchedWindow || actionProcess.running) return;
        const window = launchedWindow;
        launching = "";
        launchTimer.stop();
        selectWindow(addressOf(window));
    }

    function selectWindow(address) {
        changeView("select", address);
    }

    function stageContains(point) {
        const g = geometry;
        const y = point.y + g.shelfY;
        return point.x >= g.stageX && point.x < g.stageX + g.stageWidth
            && y >= g.stageY && y < g.stageY + g.stageHeight;
    }

    function handleInput(action, fromDevice) {
        const now = Date.now();
        if (lastInput === action && lastInputFromDevice !== fromDevice && now - lastInputAt < 65) return;
        lastInput = action;
        lastInputFromDevice = fromDevice;
        lastInputAt = now;
        act(action);
    }

    function browseShelf() {
        if (inEntertainment && focused) changeView("restore");
    }

    function focusStage() {
        if (mainAddress) changeView("fullscreen");
    }

    function changeView(operation, address) {
        if (actionProcess.running) {
            pendingView = { operation, address };
            return;
        }
        closing = "";
        controller.browsing = operation === "restore" || operation === "promote";
        if (controller.browsing) input.forceActiveFocus();
        actionProcess.exec(address
            ? ["python", controller.helper, operation, address]
            : ["python", controller.helper, operation]);
    }

    function movePage(direction) {
        const target = (Math.floor(selection / columns) + direction) * columns;
        selection = Math.max(0, Math.min(Math.max(0, tiles.length - 1), target));
    }

    function switchAppList() {
        selection = 0;
        appList = appList === "recent" ? "all" : "recent";
    }

    function act(action) {
        if (!inEntertainment || !focused) return;
        if (action === "browse") {
            browseShelf();
            return;
        }
        if (action === "stage") {
            focusStage();
            return;
        }
        if (!shelfShown) return;
        if (closing) {
            if (action === "select") {
                if (actionProcess.running) return;
                actionProcess.exec(["python", controller.helper, "close", closing]);
            }
            closing = "";
            return;
        }

        const selected = tiles[selection];
        switch (action) {
        case "left": selection = Math.max(0, selection - 1); break;
        case "right": selection = Math.min(Math.max(0, tiles.length - 1), selection + 1); break;
        case "previousPage": movePage(-1); break;
        case "nextPage": movePage(1); break;
        case "up":
        case "down": switchAppList(); break;
        case "back":
        case "fullscreen": focusStage(); break;
        case "exit": controller.leave(); break;
        case "close":
            if (selected?.window) closing = selected.address;
            break;
        case "select":
            if (actionProcess.running || !selected) break;
            if (selected.address && selected.window) selectWindow(selected.address);
            else if (!selected.address && selected.app && !launching) launch(selected.app);
            break;
        }
    }

    function launch(app) {
        launching = app.id;
        notice = "";
        launchTimer.restart();
        const command = app.runInTerminal
            ? ["xdg-terminal-exec", ...app.command.filter(word => !/^%[a-zA-Z]$/.test(word))]
            : ["gtk-launch", app.id + ".desktop"];
        Quickshell.execDetached(["env", "-u", "HL_INITIAL_WORKSPACE_TOKEN", "-u", "XDG_ACTIVATION_TOKEN", ...command]);
    }

    function shapePath() {
        const width = shelfSurface.width;
        const height = shelfSurface.height;
        const r = 18;
        if (width < r * 2 || height < r * 2) return "";
        let path = `M ${r} 0 H ${width - r} Q ${width} 0 ${width} ${r} V ${height - r} Q ${width} ${height} ${width - r} ${height} H ${r} Q 0 ${height} 0 ${height - r} V ${r} Q 0 0 ${r} 0 Z`;
        for (let i = 0; i < page.length; i++) {
            if (!page[i].address) continue;
            const x = tileLeft - geometry.shelfX + stride * i;
            path += ` M ${x} ${tileTop} h ${tileWidth} v ${tileHeight} h -${tileWidth} Z`;
        }
        return path;
    }

    Connections {
        target: Hyprland
        enabled: shelf.inEntertainment
        function onRawEvent(event) {
            if (event.name === "fullscreen") Hyprland.refreshToplevels();
            if (["openwindow", "closewindow", "movewindow", "configreloaded", "monitoradded", "monitorremoved"].includes(event.name))
                refresh.restart();
        }
    }
    Connections {
        target: shelf.controller
        enabled: shelf.inEntertainment && shelf.focused
        function onAction(name) { shelf.handleInput(name, true); }
        function onBrowsingChanged() { if (shelf.controller.browsing) input.forceActiveFocus(); }
    }

    Timer {
        id: pageTimer
        interval: 45
        onTriggered: {
            if (!shelf.focused || !shelf.visible) return;
            const offset = Math.floor(shelf.selection / shelf.columns) * shelf.columns;
            if (offset === shelf.layout.offset) return;
            if (pageProcess.running) restart();
            else pageProcess.exec(["python", shelf.controller.helper, "page", String(offset)]);
        }
    }
    Timer {
        id: refresh
        interval: 70
        onTriggered: {
            if (!shelf.visible) return;
            if (snapshotProcess.running) restart();
            else snapshotProcess.exec(["python", shelf.controller.helper, "snapshot"]);
        }
    }
    Timer {
        id: launchTimer
        interval: 10000
        onTriggered: {
            shelf.launching = "";
            shelf.notice = strings.t("launchFailed");
        }
    }
    Process {
        id: pageProcess
        stderr: SplitParser { onRead: line => console.warn(line) }
        onExited: refresh.restart()
    }
    Process {
        id: actionProcess
        stderr: SplitParser { onRead: line => console.warn(line) }
        onExited: code => {
            if (code !== 0) {
                shelf.notice = strings.t("actionFailed");
                shelf.controller.browsing = !shelf.fullscreenWindow;
            }
            refresh.restart();
            const next = shelf.pendingView;
            shelf.pendingView = null;
            if (next && shelf.inEntertainment && shelf.focused)
                Qt.callLater(shelf.changeView, next.operation, next.address);
            else if (shelf.launching && shelf.launchedWindow)
                Qt.callLater(shelf.presentLaunch);
        }
    }
    Process {
        id: snapshotProcess
        stdout: StdioCollector {
            onStreamFinished: {
                try {
                    const next = JSON.parse(text);
                    if (Array.isArray(next.windows) && next.geometry?.columns > 0) shelf.layout = next;
                } catch (error) {
                    console.warn("Unable to read Entertainment layout", error);
                }
            }
        }
    }

    FocusScope {
        id: input
        anchors.fill: parent
        focus: true
        Keys.onPressed: event => {
            const bindings = {
                [Qt.Key_Left]: "left", [Qt.Key_Right]: "right", [Qt.Key_Up]: "up", [Qt.Key_Down]: "down",
                [Qt.Key_Return]: "select", [Qt.Key_Enter]: "select", [Qt.Key_Select]: "select",
                [Qt.Key_Escape]: "back", [Qt.Key_Back]: "back", [Qt.Key_Delete]: "close", [Qt.Key_Menu]: "close",
                [Qt.Key_PageUp]: "previousPage", [Qt.Key_PageDown]: "nextPage", [Qt.Key_F]: "fullscreen",
                [Qt.Key_Zoom]: "fullscreen",
                [Qt.Key_F10]: "exit", [Qt.Key_Exit]: "exit"
            };
            const action = bindings[Commons.Util.readingKey(event)];
            if (!action) return;
            if ((action === "up" || action === "down") && event.modifiers !== Qt.NoModifier) return;
            event.accepted = true;
            if (!event.isAutoRepeat || action === "left" || action === "right") shelf.handleInput(action, false);
        }

        Item {
            id: shelfSurface
            x: shelf.geometry.shelfX ?? 0
            width: shelf.geometry.shelfWidth ?? 0
            height: parent.height
            readonly property real inset: Math.max(12, shelf.tileLeft - x)

            Shape {
                anchors.fill: parent
                ShapePath {
                    fillRule: ShapePath.OddEvenFill
                    fillColor: "#b3000000"
                    strokeWidth: -1
                    PathSvg { path: shelf.shapePath() }
                }
            }

            Rectangle {
                anchors.fill: parent
                color: "transparent"
                border.color: "#55ffffff"
                border.width: 1
                radius: 18
            }

            Text {
                anchors { horizontalCenter: parent.horizontalCenter; top: parent.top; topMargin: shelf.tileTop }
                width: Math.max(0, parent.width - shelfSurface.inset * 2)
                height: shelf.tileHeight
                visible: shelf.tiles.length === 0
                horizontalAlignment: Text.AlignHCenter
                verticalAlignment: Text.AlignVCenter
                wrapMode: Text.WordWrap
                textFormat: Text.PlainText
                color: "#bfbfbf"
                font.family: Commons.Style.font.family
                font.pixelSize: Commons.Style.font.body
                text: strings.t(shelf.appList === "recent" ? "emptyRecent" : "emptyAll")
            }

            Repeater {
                model: shelf.page
                delegate: DeckRow {
                    required property int index
                    x: shelf.tileLeft - shelfSurface.x + shelf.stride * index
                    y: shelf.tileTop
                    width: shelf.tileWidth
                    height: shelf.tileHeight
                    current: shelf.layout.offset + index === shelf.selection
                    canDrag: !!modelData.window && shelf.shelfShown && shelf.focused && !shelf.closing && !actionProcess.running
                    stageContains: point => shelf.stageContains(point)
                    iconSource: shelf.controller.shell?.appLibrary?.iconSource(modelData.app?.icon || "application-x-executable") || ""
                    onChosen: action => {
                        shelf.controller.browsing = true;
                        shelf.selection = shelf.layout.offset + index;
                        shelf.act(action);
                    }
                    onDroppedOnStage: address => shelf.changeView("promote", address)
                }
            }

            RowLayout {
                anchors { left: parent.left; right: parent.right; bottom: parent.bottom; leftMargin: shelfSurface.inset; rightMargin: shelfSurface.inset; bottomMargin: 6 }
                height: 19
                spacing: 5
                Text {
                    Layout.fillWidth: true
                    textFormat: Text.PlainText
                    elide: Text.ElideRight
                    color: "#bfbfbf"
                    font.family: Commons.Style.font.family
                    font.pixelSize: Commons.Style.font.body
                    text: shelf.closing ? strings.t("confirm") : shelf.launching ? strings.t("working") :
                        shelf.notice || strings.t("browseControls")
                }

                ShelfButton {
                    label: "‹"
                    visible: shelf.pageCount > 1
                    enabled: shelf.pageNumber > 1
                    Layout.preferredHeight: 19
                    onTriggered: shelf.movePage(-1)
                }
                Text {
                    visible: shelf.pageCount > 1
                    text: strings.t("page").arg(shelf.pageNumber).arg(shelf.pageCount)
                    font.family: Commons.Style.font.family
                    font.pixelSize: Commons.Style.font.body
                    color: "#bebebe"
                }
                ShelfButton {
                    label: "›"
                    visible: shelf.pageCount > 1
                    enabled: shelf.pageNumber < shelf.pageCount
                    Layout.preferredHeight: 19
                    onTriggered: shelf.movePage(1)
                }
                ShelfButton {
                    label: strings.t(shelf.appList === "recent" ? "recentList" : "allList")
                    Layout.preferredHeight: 19
                    onTriggered: shelf.act("down")
                }
                ShelfButton {
                    label: strings.t("leave")
                    Layout.preferredHeight: 19
                    onTriggered: shelf.controller.leave()
                }
            }
        }
    }

    component ShelfButton: Rectangle {
        id: button
        required property string label
        signal triggered()
        implicitHeight: 19
        implicitWidth: buttonText.implicitWidth + 20
        radius: 7
        opacity: enabled ? 1 : .35
        color: hover.hovered ? "#383838" : "#202020"
        Behavior on color { ColorAnimation { duration: Commons.Style.duration(110) } }

        Text {
            id: buttonText
            anchors { left: parent.left; right: parent.right; verticalCenter: parent.verticalCenter; margins: 10 }
            textFormat: Text.PlainText
            text: button.label
            elide: Text.ElideRight
            horizontalAlignment: Text.AlignHCenter
            color: "white"
            font.family: Commons.Style.font.family
            font.pixelSize: Commons.Style.font.body
        }
        HoverHandler { id: hover; cursorShape: Qt.PointingHandCursor }
        TapHandler { onTapped: button.triggered() }
    }
}
