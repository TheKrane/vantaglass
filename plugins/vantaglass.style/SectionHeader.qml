import QtQuick
import qs.Commons
import qs.Commons as Commons

Item {
    id: root
    property string text: ""
    property alias font: label.font
    property real topPadding: 0
    property color foreground: Commons.Color.foreground
    property string fontFamily: Style.font.family
    implicitWidth: label.implicitWidth
    implicitHeight: label.implicitHeight
    Text {
        id: label
        textFormat: Text.PlainText
        text: root.text.length && root.text === root.text.toLocaleUpperCase()
            ? (root.text.charAt(0) + root.text.slice(1).toLocaleLowerCase()).replace(/^Dns\b/, "DNS") : root.text
        color: root.foreground
        font.family: root.fontFamily
        font.pixelSize: Style.font.body
        font.weight: Font.DemiBold
    }
}
