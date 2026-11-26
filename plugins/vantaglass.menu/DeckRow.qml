import QtQuick
import Quickshell
import Quickshell.Widgets
import qs.Commons as Commons

Item {
    id: tile
    required property var modelData
    required property bool current
    required property string iconSource
    required property bool canDrag
    required property var stageContains
    readonly property bool liveWindow: !!modelData.address
    readonly property string caption: modelData.window?.title || modelData.app?.name || qsTr("Window")
    signal chosen(string action)
    signal droppedOnStage(string address)

    Rectangle {
        anchors.fill: parent
        radius: Commons.Style.space(10)
        color: tile.liveWindow ? "transparent" : (tile.current ? "#464646" : "#262626")
        border.color: pointer.overStage ? "#ffffff" : pointer.dragging ? "#99ffffff"
            : tile.current ? "#edffffff" : "#48ffffff"
        border.width: tile.current || pointer.dragging ? 2 : 1
        Behavior on border.color { ColorAnimation { duration: Commons.Style.duration(110) } }
    }

    IconImage {
        anchors.centerIn: parent
        width: height
        height: Commons.Style.space(52)
        visible: !tile.liveWindow
        source: visible ? tile.iconSource || Quickshell.iconPath(tile.modelData.app?.icon || "application-x-executable", true) : ""
    }

    Text {
        anchors { top: parent.bottom; topMargin: 5; left: parent.left; right: parent.right }
        textFormat: Text.PlainText
        text: tile.caption
        color: "white"
        elide: Text.ElideRight
        horizontalAlignment: Text.AlignHCenter
        font.family: Commons.Style.font.family
        font.pixelSize: Commons.Style.font.body
    }

    MouseArea {
        id: pointer
        anchors.fill: parent
        acceptedButtons: Qt.LeftButton | Qt.RightButton
        preventStealing: true
        property point pressPosition
        property string grabbedAddress: ""
        property bool moved: false
        readonly property bool dragging: pressed && moved && tile.canDrag && grabbedAddress === tile.modelData.address
        readonly property bool overStage: dragging && tile.stageContains(mapToItem(null, mouseX, mouseY))
        cursorShape: overStage ? Qt.DragMoveCursor : dragging ? Qt.ClosedHandCursor
            : tile.canDrag ? Qt.OpenHandCursor : Qt.PointingHandCursor

        onPressed: mouse => {
            pressPosition = Qt.point(mouse.x, mouse.y);
            grabbedAddress = tile.canDrag && mouse.button === Qt.LeftButton ? tile.modelData.address : "";
            moved = false;
        }
        onPositionChanged: mouse => {
            if (!pressed || moved) return;
            moved = Math.hypot(mouse.x - pressPosition.x, mouse.y - pressPosition.y) >= Application.styleHints.startDragDistance;
        }
        onReleased: mouse => {
            if (moved && grabbedAddress && tile.canDrag && grabbedAddress === tile.modelData.address
                    && tile.stageContains(mapToItem(null, mouse.x, mouse.y)))
                tile.droppedOnStage(grabbedAddress);
            grabbedAddress = "";
        }
        onCanceled: grabbedAddress = ""
        onClicked: mouse => {
            if (!moved) tile.chosen(mouse.button === Qt.RightButton ? "close" : "select");
        }
    }
}
