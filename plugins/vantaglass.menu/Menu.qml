import QtQuick
import qs.Commons
import qs.Commons as Commons

// Omarchy's native row, header and spacing metrics drive the menu. Keep its
// original 18px margin independent of the denser system-panel spacing.
BaseMenu {
    id: root
    readonly property bool vantaglassTheme: Commons.Color.pick("vantaglass.identity", "") === "vantaglass"
    Binding {
        target: root
        property: "contentMargin"
        value: Style.space(18)
        when: root.vantaglassTheme
        restoreMode: Binding.RestoreBindingOrValue
    }
}
