import QtQuick
import Quickshell
import Quickshell.Hyprland
import qs.Ui

BarWidget {
    id: root
    moduleName: "vantaglass.entertainment"

    readonly property var screen: QsWindow.window?.screen ?? null
    readonly property var monitor: screen ? Hyprland.monitorFor(screen) : null
    readonly property var entertainment: Hyprland.workspaces.values.find(workspace => workspace.name === "entertainment")
    visible: !!entertainment && entertainment.toplevels.values.length > 0
        && monitor?.activeWorkspace?.name !== "entertainment"
    implicitWidth: icon.implicitWidth
    implicitHeight: icon.implicitHeight

    BarIconButton {
        id: icon
        anchors.fill: parent
        bar: root.bar
        text: "󰊴"
        tooltipText: qsTr("Entertainment")
        onPressed: function(button) {
            if (button === Qt.LeftButton)
                Quickshell.execDetached(["omarchy-shell", "vantaglass.entertainment", "openDashboard"]);
        }
    }
}
