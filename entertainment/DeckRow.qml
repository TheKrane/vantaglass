import QtQuick
import Quickshell
import Quickshell.Wayland
import Quickshell.Widgets

Item {
    id: row
    required property var dashboard
    required property int index
    required property string heading
    readonly property bool running: index === 0
    readonly property bool selected: dashboard.row === index
    readonly property real unit: dashboard.unit
    readonly property int cardWidth: Math.round((running ? 312 : 212) * unit)

    Connections {
        target: row.dashboard
        function onColumnChanged() { row.revealSelection(); }
        function onRowChanged() { row.revealSelection(); }
    }

    function revealSelection() {
        if (selected && deck.count)
            deck.positionViewAtIndex(dashboard.column, ListView.Contain);
    }

    Text {
        id: title
        text: row.heading
        font.pixelSize: 22 * row.unit
        font.weight: Font.DemiBold
        color: row.dashboard.ink
    }

    ListView {
        id: deck
        anchors { top: title.bottom; topMargin: 12 * row.unit; left: parent.left; right: parent.right; bottom: parent.bottom }
        model: row.dashboard.rows[row.index]
        orientation: ListView.Horizontal
        spacing: 14 * row.unit
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        currentIndex: row.selected ? row.dashboard.column : -1
        onCountChanged: row.revealSelection()

        delegate: Item {
            id: tile
            required property int index
            required property var modelData
            readonly property bool active: row.selected && row.dashboard.column === index
            readonly property bool inView: x + width > deck.contentX && x < deck.contentX + deck.width
            readonly property var app: row.running ? row.dashboard.appFor(modelData) : modelData
            readonly property string caption: (row.running ? modelData?.title || app?.name : app?.name) || qsTr("Window")

            width: row.cardWidth
            height: Math.min(deck.height, (row.running ? 224 : 172) * row.unit)

            Rectangle {
                anchors.fill: parent
                radius: 17 * row.unit
                color: tile.active ? "#333333" : "#222222"
                border.width: tile.active ? 2 : 1
                border.color: tile.active ? "#eeeeee" : "#565656"
            }

            Rectangle {
                anchors { top: parent.top; left: parent.left; right: parent.right; bottom: captionText.top; margins: 8 * row.unit }
                radius: 13 * row.unit
                color: "#101010"
                clip: true

                Text {
                    anchors.centerIn: parent
                    visible: row.running && !capture.item?.hasContent
                    text: row.dashboard.labels.previewPending ?? ""
                    font.pixelSize: 13 * row.unit
                    color: row.dashboard.muted
                }

                Loader {
                    id: capture
                    anchors.fill: parent
                    active: row.running && row.dashboard.visible && tile.inView && !!tile.modelData?.wayland
                    sourceComponent: ScreencopyView {
                        id: preview
                        paintCursor: false
                        constraintSize: Qt.size(parent.width, parent.height)
                        anchors.centerIn: parent
                        captureSource: tile.modelData?.wayland ?? null
                        live: false
                        Timer {
                            running: !!preview.captureSource
                            repeat: true
                            triggeredOnStart: true
                            interval: tile.active ? 500 : 1100
                            onTriggered: preview.captureFrame()
                        }
                    }
                }

                IconImage {
                    id: appIcon
                    anchors.centerIn: parent
                    visible: !row.running
                    width: Math.min(parent.height * .67, 74 * row.unit)
                    height: width
                    source: row.running ? "" : tile.app?.icon?.startsWith("/") ? "file://" + tile.app.icon :
                        Quickshell.iconPath(tile.app?.icon || "application-x-executable", "application-x-executable")
                }

                Text {
                    anchors.centerIn: parent
                    visible: !row.running && appIcon.status !== Image.Ready
                    text: tile.caption.charAt(0).toUpperCase()
                    font.pixelSize: 42 * row.unit
                    font.weight: Font.DemiBold
                    color: row.dashboard.muted
                }
            }

            Text {
                id: captionText
                anchors { left: parent.left; right: parent.right; bottom: parent.bottom; margins: 12 * row.unit }
                text: tile.caption
                textFormat: Text.PlainText
                elide: Text.ElideRight
                color: row.dashboard.ink
                font.pixelSize: 16 * row.unit
            }

            TapHandler {
                acceptedButtons: Qt.LeftButton | Qt.RightButton
                onTapped: (point, button) => {
                    row.dashboard.row = row.index;
                    row.dashboard.column = tile.index;
                    row.dashboard.act(button === Qt.RightButton ? "close" : "select");
                }
            }
        }
    }
}
