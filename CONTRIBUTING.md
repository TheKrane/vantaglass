# Contributing

Run the tests before submitting a change:

```sh
python -m unittest discover -s tests -v
```

Build a release archive:

```sh
python tools/package.py
```

Run graphical tests on Omarchy. The VM test needs QEMU and KVM access. The shell test uses Sway, bubblewrap, grim, wtype, and ImageMagick:

```sh
python tools/shell_harness.py --renderer opengl
python tools/vm_harness.py --integration
```

The VM uses a separate home directory and virtual GPU. Test output stays in `validation/` and is not included in releases.

When updating support for a new Omarchy version, review the upstream changes before updating `compatibility.json`. Changes to copied shell components should retain their upstream behavior and license notices.

To capture a theme-switcher preview in the VM:

```sh
python tools/vm_harness.py --preview
```

The screenshot is saved to `validation/vm-preview/preview.png`.
