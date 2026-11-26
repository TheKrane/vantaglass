# Vantaglass

A dark Omarchy theme with black translucent menus, rounded controls, and a forest wallpaper.

## Install

Tested with Omarchy 4.5.0-3 and Hyprland 0.56.2. Run this as your normal desktop user:

```sh
curl -fsSL https://raw.githubusercontent.com/TheKrane/vantaglass/main/bootstrap.sh | bash
```

The installer backs up your configuration and preserves your wallpaper, font, and bar layout. Other themes stay installed. The shell may restart during installation.

You can also download a release, extract it, and run `./install.sh`.

## Use

Choose **Vantaglass** in Omarchy's theme picker, or run:

```sh
omarchy theme set vantaglass
```

Switching to another theme restores the native panels. Switching back enables Vantaglass again.

## Entertainment

Press **Super+E** or **Home** on your controller or configured TV remote to enter the dedicated Entertainment workspace. **Super+Up** takes the stage app fullscreen and **Super+Down** brings back the shelf. **Leave** returns to your previous workspace.

The shelf shows live Hyprland windows beside app icons. Selecting a window opens it fullscreen and moves the previous stage window into the selected slot. Stage and shelf windows follow the active display's aspect ratio.

Drag a running app from the shelf onto the stage to swap the two windows while keeping the shelf open. Dropping outside the stage leaves both windows in place.

On regular workspaces, a controller icon appears beside the workspace numbers while Entertainment has open windows. Click it to return to Entertainment. The top bar hides on the display showing Entertainment.

**Up** and **Down** switch between **Open & recent** and **All apps**. Both start with open Entertainment windows. The default list follows with apps you've used on stage, most recent first. **All apps** follows with the launcher catalog in alphabetical order.

| Action | Keyboard | Controller | TV remote |
| --- | --- | --- | --- |
| Switch between Stage and Apps | Super+Up or Super+Down | Guide | Home |
| Take the current app fullscreen | Esc | B | Back |
| Switch app lists | Up or Down | D-pad Up or Down | Up or Down |
| Browse or change page | Left or Right, Page Up or Down | D-pad Left or Right | Left or Right |
| Open or swap windows | Enter | A | OK |
| Close a shelf window | Delete, then Enter | X, then A | Menu, then OK |
| Leave Entertainment while browsing | F10 | Start | Exit |

**Super+E** or **Home** toggles between fullscreen and the shelf.

Controllers use SDL2 (`sdl2-compat` on Arch). To use a TV remote's Home button anywhere, set `VANTAGLASS_REMOTE_DEVICE` in your session environment to its Linux event device under `/dev/input/by-id/`. The session user needs read access to that device. HDMI-CEC remotes need a bridge that sends Linux input events.

## Optional overrides

**Zen Browser.** Open the profile folder from `about:support`. Copy [zen.css](themes/vantaglass/zen.css) into its `chrome` directory and add this line at the top of `chrome/userChrome.css`:

```css
@import url("zen.css");
```

In `about:config`, enable `toolkit.legacyUserProfileCustomizations.stylesheets` and `zen.theme.acrylic-urlbar`, then fully quit and reopen Zen. The override styles browser menus and the address popup. The popup uses backdrop blur on Zen builds that support it.

**Single tiled window.** Copy [single-window.lua](assets/single-window.lua) into `~/.config/hypr/`, then add `require("hypr.single-window")` at the end of `~/.config/hypr/hyprland.lua` and run `hyprctl reload`. A lone tiled window in dwindle uses 75% of the available width and height, centered. Floating windows are excluded from the count.

## Updates

Vantaglass checks for updates when you run an Omarchy update, including through the top-bar update button. It uses Omarchy's supported `post-update` hook.

To update it separately:

```sh
~/.local/bin/vantaglass update
```

Only compatible stable releases are installed. If an Omarchy update changes its shell interfaces, Vantaglass uses native panels until a compatible release is available. A failed download won't stop the Omarchy update.

## Uninstall

```sh
~/.local/bin/vantaglass uninstall
```

If Vantaglass is selected, uninstall restores your previous theme. Otherwise, it keeps the theme you're using. Backups and archived edits remain in `~/.local/state/vantaglass/`.

## Troubleshooting

Check the installed version and compatibility:

```sh
~/.local/bin/vantaglass status
~/.local/bin/vantaglass doctor
```

## Credits

The wallpaper is [Dense forest under fog](https://unsplash.com/photos/qFjIV1MxDvE) by Nathan Anderson. It is distributed under CC0; see [the source record](https://commons.wikimedia.org/wiki/File:Dense_forest_under_fog_(Unsplash).jpg) and [wallpaper credit](licenses/wallpaper.txt).

Vantaglass uses Omarchy's shell components under the MIT license. See [ATTRIBUTION.md](ATTRIBUTION.md). Development instructions are in [CONTRIBUTING.md](CONTRIBUTING.md).
