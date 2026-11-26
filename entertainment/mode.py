#!/usr/bin/env python3
"""Connect Omarchy's Entertainment shelf to its Hyprland workspace."""

import argparse
import json
import re
import subprocess
import sys

import remote


def lua(script):
    result = subprocess.check_output(["hyprctl", "repl", script], text=True, timeout=4).strip()
    if result != "ok" and not result.startswith("{"):
        raise RuntimeError(result or "Hyprland did not accept the Entertainment request.")
    return result


def focused():
    return 'local active = hl.get_active_workspace(); ' \
           'if not active or active.name ~= "entertainment" then return "Entertainment is not focused" end; '


def window_address(address):
    if not re.fullmatch(r"(?:0x)?[0-9a-fA-F]{1,16}", address):
        raise RuntimeError("Invalid window address.")
    return "0x" + address.removeprefix("0x").lower()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    for action in ("enter", "leave", "show", "input", "snapshot", "status", "restore", "fullscreen"):
        sub.add_parser(action)
    for action in ("select", "promote", "close"):
        sub.add_parser(action).add_argument("address")
    sub.add_parser("page").add_argument("offset", type=int)
    args = parser.parse_args()
    if args.action == "input":
        remote.run()
    elif args.action == "show":
        subprocess.run(["omarchy-shell", "vantaglass.entertainment", "openDashboard"], check=True, timeout=5)
    elif args.action == "enter":
        lua('if not vantaglass_entertainment then return "The Entertainment layout is unavailable" end; '
            'hl.dispatch(hl.dsp.focus({workspace="name:entertainment"})); return "ok"')
    elif args.action == "restore":
        lua(focused() + 'return vantaglass_entertainment.restore(active)')
    elif args.action in {"select", "fullscreen"}:
        address = f'"{window_address(args.address)}"' if args.action == "select" else "nil"
        lua(focused() + f'return vantaglass_entertainment.present(active, {address})')
    elif args.action == "promote":
        address = window_address(args.address)
        lua(focused() + f'return vantaglass_entertainment.promote(active, "{address}")')
    elif args.action == "close":
        address = window_address(args.address)
        lua(focused() + f'local w = hl.get_window("address:{address}"); '
            'if not w or not w.workspace or w.workspace.name ~= "entertainment" '
            'then return "That window has left Entertainment" end; '
            'hl.dispatch(hl.dsp.window.close({window=w})); return "ok"')
    elif args.action == "leave":
        lua(focused() + 'hl.dispatch(hl.dsp.focus({workspace="previous_per_monitor"})); return "ok"')
    elif args.action in {"snapshot", "status"}:
        value = json.loads(lua('if not vantaglass_entertainment then return "{}" end; '
                               'return vantaglass_entertainment.snapshot()'))
        value["windows"] = [address for address in value.get("windows", []) if address]
        print(json.dumps(value))
    elif args.action == "page":
        offset = max(0, min(10000, args.offset))
        lua(focused() + f'hl.dispatch(hl.dsp.layout("page {offset}")); return "ok"')


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        sys.exit(str(error))
