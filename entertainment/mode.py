#!/usr/bin/env python3
"""Workspace preferences and compositor actions for the entertainment dashboard."""

import argparse
import fcntl
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

import remote

SHELL_PATH = Path(__file__).with_name("shell.qml")
STATE = Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local/state") / "vantaglass"
MODE_FILE = STATE / "entertainment.json"


def hyprctl(*args):
    return subprocess.check_output(["hyprctl", *args], text=True, timeout=4)


def active_workspace():
    workspace = json.loads(hyprctl("-j", "activeworkspace"))
    if workspace["id"] == 0 or workspace["name"].startswith("special:"):
        raise RuntimeError("Choose a regular workspace first.")
    return workspace["name"]


def load_modes():
    try:
        modes = json.loads(MODE_FILE.read_text())
    except FileNotFoundError:
        return []
    if not isinstance(modes, list) or not all(isinstance(name, str) for name in modes):
        raise RuntimeError("The entertainment workspace list is invalid.")
    return modes


def save_modes(modes):
    with tempfile.NamedTemporaryFile(mode="w", dir=STATE, delete=False) as output:
        try:
            json.dump(modes, output)
            output.flush()
            Path(output.name).replace(MODE_FILE)
        finally:
            Path(output.name).unlink(missing_ok=True)


def change_mode(action, name=None):
    name = name or active_workspace()
    if len(name) > 200 or name.startswith("special:"):
        raise RuntimeError("Choose a regular workspace first.")
    STATE.mkdir(parents=True, exist_ok=True)
    with (STATE / "entertainment.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        modes = load_modes()
        add = action == "enable" or action == "toggle" and name not in modes
        if add and name not in modes and len(modes) >= 100:
            raise RuntimeError("Entertainment mode supports up to 100 workspaces.")
        updated = list(dict.fromkeys(modes + [name])) if add else [item for item in modes if item != name]
        save_modes(updated)
    if add:
        start()


def start():
    if load_modes():
        env = os.environ.copy()
        # The menu or boot hook can carry launch tokens for its own workspace.
        env.pop("HL_INITIAL_WORKSPACE_TOKEN", None)
        env.pop("XDG_ACTIVATION_TOKEN", None)
        subprocess.run(["qs", "--path", str(SHELL_PATH), "--no-duplicate", "--daemonize"],
                       env=env, check=True, timeout=8)


def window_operation(action, workspace, address):
    if not re.fullmatch(r"(?:0x)?[0-9a-fA-F]{1,16}", address):
        raise RuntimeError("Invalid window address.")
    address = "0x" + address.removeprefix("0x").lower()
    # Validate the workspace inside the same compositor request as the action.
    # Lua's decimal byte escapes allow any valid workspace name as literal text.
    escaped = "".join(f"\\{byte:03}" for byte in workspace.encode())
    target = f'hl.get_window("address:{address}")'
    if action == "fullscreen":
        operation = '''
            local previous = w.workspace.fullscreen_window
            if previous and previous.address ~= w.address then
                local mode = previous.fullscreen == 1 and "maximized" or "fullscreen"
                local leave = hl.dispatch(hl.dsp.window.fullscreen({window=previous, mode=mode, action="unset"}))
                if not leave.ok then return leave.error end
            end
            local focus = hl.dispatch(hl.dsp.focus({window=w}))
            if not focus.ok then return focus.error end
            local enter = hl.dispatch(hl.dsp.window.fullscreen({window=w, mode="fullscreen", action="set"}))
            if not enter.ok then return enter.error end
            if w.fullscreen ~= 2 and w.fullscreen ~= 3 then return "fullscreen failed" end
        '''
        failure = "Could not make the window fullscreen."
    else:
        operation = '''
            local close = hl.dispatch(hl.dsp.window.close({window=w}))
            if not close.ok then return close.error end
        '''
        failure = "Could not close the window."
    script = (f'local w={target}; if not w or not w.workspace or w.workspace.name~="{escaped}" '
              'then return "stale" end; ' + operation + '; return "ok"')
    result = hyprctl("repl", script).strip()
    if result == "stale":
        raise RuntimeError("The window is no longer available on this workspace.")
    if result != "ok":
        raise RuntimeError(f"{failure} {result}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    for action in ("enable", "disable", "toggle"):
        commands.add_parser(action).add_argument("workspace", nargs="?")
    for action in ("fullscreen", "close"):
        command = commands.add_parser(action)
        command.add_argument("workspace")
        command.add_argument("address")
    for action in ("start", "show", "status", "input", "stop"):
        commands.add_parser(action)
    args = parser.parse_args()
    if args.action in {"enable", "disable", "toggle"}:
        change_mode(args.action, args.workspace)
    elif args.action in {"fullscreen", "close"}:
        window_operation(args.action, args.workspace, args.address)
    elif args.action == "start":
        start()
    elif args.action == "stop":
        subprocess.run(["qs", "--path", str(SHELL_PATH), "kill"], timeout=4)
    elif args.action == "show":
        if active_workspace() not in load_modes():
            raise RuntimeError("Entertainment mode is disabled on this workspace.")
        start()
        subprocess.run(["qs", "--path", str(SHELL_PATH), "ipc", "call", "entertainment", "openDashboard"], check=True, timeout=4)
    elif args.action == "status":
        print(json.dumps(load_modes()))
    else:
        remote.run()


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        sys.exit(str(error))
