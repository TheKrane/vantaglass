import QtQuick
import qs.Commons
import qs.Commons as Commons

Item {
    id: root
    property bool checked: false
    property string accessibleName: Commons.I18n.t("audio.title")
    property int trackHeight: Style.space(19)
    property int cursorPad: 0
    property bool busy: false
    property bool interactive: true
    property bool hasCursor: false
    property color foreground: Commons.Color.foreground
    readonly property alias containsMouse: mouse.containsMouse
    signal hovered(bool isHovered)
    signal toggled()
    readonly property int trackWidth: Math.round(trackHeight * 32 / 19)
    implicitWidth: trackWidth + Math.max(Style.space(4), cursorPad * 2)
    implicitHeight: Math.max(Style.space(24), trackHeight + Style.space(5))
    activeFocusOnTab: interactive && !busy
    Keys.onSpacePressed: if (root.interactive && !root.busy) root.toggled()
    Keys.onReturnPressed: if (root.interactive && !root.busy) root.toggled()
    Accessible.role: Accessible.CheckBox
    Accessible.checkable: true
    Accessible.checked: checked
    Accessible.name: accessibleName
    Accessible.onToggleAction: if (root.interactive && !root.busy) root.toggled()

    Rectangle {
        id: track
        anchors.centerIn: parent
        width: root.trackWidth
        height: root.trackHeight
        radius: height / 2
        color: root.checked ? Commons.Color.accent : Util.alpha("#000000", 0.25)
        // The hit target is larger than the capsule. Paint focus on the
        // capsule itself so its outline and fill share one antialiased edge.
        border.width: root.hasCursor || root.activeFocus || !root.checked ? Style.space(1) : 0
        border.color: root.hasCursor || root.activeFocus ? root.foreground : Util.alpha(root.foreground, 0.14)
        Rectangle {
            width: Math.max(6, root.trackHeight - Style.space(4))
            height: width
            radius: width / 2
            anchors.verticalCenter: parent.verticalCenter
            x: root.checked !== LayoutMirroring.enabled ? track.width-width-Style.space(2) : Style.space(2)
            color: "white"
            Behavior on x { NumberAnimation { duration: Style.duration(120); easing.type: Easing.OutCubic } }
        }
    }
    MouseArea {
        id: mouse
        anchors.fill: parent
        hoverEnabled: true
        enabled: root.interactive
        cursorShape: Qt.PointingHandCursor
        onContainsMouseChanged: root.hovered(containsMouse)
        onPressed: if (!root.busy) root.forceActiveFocus()
        onClicked: if (!root.busy) root.toggled()
    }
}
