import QtQuick
import qs.Ui as Native
import qs.Commons
import qs.Commons as Commons

// Keep the stock drag, wheel, RTL, snapping and secondary-click behavior.
// Only continuous level controls use a filled capsule. Text size keeps notches.
Native.PanelSlider {
    id: root
    property bool capsule: true
    readonly property bool vantaglassTheme: capsule && Commons.Color.pick("vantaglass.identity", "") === "vantaglass"
    trackHeight: vantaglassTheme ? Style.space(24) : Math.max(4, Math.round(Style.spacing.controlHeight * 0.11))
    knobSize: vantaglassTheme ? 0 : Math.max(14, Math.round(Style.spacing.controlHeight * 0.38))
    implicitHeight: vantaglassTheme ? Style.space(30) : Math.max(Style.space(22), knobSize + Style.spacing.md)
    trackColor: vantaglassTheme ? Util.alpha("#000000", 0.15) : (bar ? Util.alpha("#000000", Style.selectedFillAlpha) : "#333")
    fillColor: vantaglassTheme ? "#FFFFFF" : Commons.Color.foreground

    // A subtle perimeter keeps white fill legible on the light material.
    Rectangle {
        visible: root.vantaglassTheme
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.verticalCenter: parent.verticalCenter
        height: root.trackHeight
        radius: height / 2
        color: "transparent"
        border.width: 1
        border.color: Util.alpha(Commons.Color.foreground, 0.1)
    }
}
