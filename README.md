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
