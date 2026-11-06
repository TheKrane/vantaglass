import QtQuick
import "../vantaglass.style" as Glass

// Inert visual fixture: checked/focused state is fixed, no device callbacks.
Item {
    property var bar: null
    property string moduleName: "vantaglass.switch-fixture"
    implicitWidth: states.implicitWidth
    implicitHeight: states.implicitHeight
    Row {
        id: states
        spacing: 8
        Glass.CompactSwitch { checked: true; hasCursor: true; interactive: false }
        Glass.CompactSwitch { checked: true; hasCursor: false; interactive: false }
        Glass.CompactSwitch { checked: false; hasCursor: true; interactive: false }
        Glass.CompactSwitch { checked: false; hasCursor: false; interactive: false }
    }
}
