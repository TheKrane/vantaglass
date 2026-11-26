"""Translate SDL game-controller input and an optional Linux remote into UI actions."""

import ctypes
import os
import struct
import time

# SDL's standard game-controller layout provides a common mapping for pads.
BUTTONS = {
    0: "select", 1: "back", 2: "close", 3: "fullscreen", 5: "home", 6: "exit",
    11: "up", 12: "down", 13: "left", 14: "right",
}
REPEATING_ACTIONS = {"left", "right"}

# Linux EV_KEY codes for a dedicated media remote. Open it read-only and leave
# event delivery to the compositor and other applications intact.
REMOTE_KEYS = {
    103: "up", 108: "down", 105: "left", 106: "right",
    28: "select", 352: "select", 353: "select",
    158: "back", 174: "exit", 1: "back",
    139: "close", 172: "home", 102: "home", 372: "fullscreen",
}
INPUT_EVENT = struct.Struct("@llHHi")


class ControllerInput:
    def __init__(self):
        self.sdl = ctypes.CDLL("libSDL2-2.0.so.0")
        signatures = {
            "SDL_Init": ([ctypes.c_uint32], ctypes.c_int),
            "SDL_SetHint": ([ctypes.c_char_p, ctypes.c_char_p], ctypes.c_int),
            "SDL_NumJoysticks": ([], ctypes.c_int),
            "SDL_JoystickGetDeviceInstanceID": ([ctypes.c_int], ctypes.c_int32),
            "SDL_IsGameController": ([ctypes.c_int], ctypes.c_int),
            "SDL_GameControllerOpen": ([ctypes.c_int], ctypes.c_void_p),
            "SDL_GameControllerClose": ([ctypes.c_void_p], None),
            "SDL_GameControllerUpdate": ([], None),
            "SDL_GameControllerGetButton": ([ctypes.c_void_p, ctypes.c_int], ctypes.c_uint8),
            "SDL_GameControllerGetAxis": ([ctypes.c_void_p, ctypes.c_int], ctypes.c_int16),
            "SDL_Quit": ([], None),
        }
        for name, (args, result) in signatures.items():
            function = getattr(self.sdl, name)
            function.argtypes = args
            function.restype = result
        self.sdl.SDL_SetHint(b"SDL_JOYSTICK_ALLOW_BACKGROUND_EVENTS", b"1")
        # SDL_INIT_GAMECONTROLLER initializes joystick support and never opens a window.
        if self.sdl.SDL_Init(0x2000):
            raise RuntimeError("SDL could not initialize game controllers.")
        self.devices = {}
        self.held = {}
        self.scan_at = 0.0

    def scan(self):
        devices = {}
        for index in range(self.sdl.SDL_NumJoysticks()):
            if not self.sdl.SDL_IsGameController(index):
                continue
            instance = self.sdl.SDL_JoystickGetDeviceInstanceID(index)
            handle = self.devices.pop(instance, None) or self.sdl.SDL_GameControllerOpen(index)
            if handle:
                devices[instance] = handle
        for device in self.devices.values():
            self.sdl.SDL_GameControllerClose(device)
        self.devices = devices

    def events(self, now):
        self.sdl.SDL_GameControllerUpdate()
        if now >= self.scan_at:
            self.scan()
            self.scan_at = now + 1.0
        pressed = set()
        for instance, device in self.devices.items():
            for button, action in BUTTONS.items():
                if self.sdl.SDL_GameControllerGetButton(device, button):
                    pressed.add((instance, action))
            x, y = (self.sdl.SDL_GameControllerGetAxis(device, axis) for axis in (0, 1))
            if max(abs(x), abs(y)) >= 18000:
                direction = ("left" if x < 0 else "right") if abs(x) >= abs(y) else ("up" if y < 0 else "down")
                pressed.add((instance, direction))
        self.held = {key: self.held.get(key, 0.0) for key in pressed}
        for key, due in self.held.items():
            if now >= due:
                action = key[1]
                self.held[key] = now + (0.14 if due else 0.40) if action in REPEATING_ACTIONS else float("inf")
                yield action


class RemoteInput:
    def __init__(self, path):
        self.path = path
        self.fd = None
        self.retry_at = 0.0

    def events(self, now):
        if self.fd is None and now >= self.retry_at:
            self.retry_at = now + 2.0
            try:
                self.fd = os.open(self.path, os.O_RDONLY | os.O_NONBLOCK | os.O_CLOEXEC)
            except OSError:
                return
        if self.fd is None:
            return
        try:
            events = os.read(self.fd, INPUT_EVENT.size * 32)
            if not events:
                os.close(self.fd)
                self.fd = None
                return
        except BlockingIOError:
            return
        except OSError:
            os.close(self.fd)
            self.fd = None
            return
        for _, _, kind, key, value in INPUT_EVENT.iter_unpack(events):
            action = REMOTE_KEYS.get(key)
            if kind == 1 and action and (value == 1 or value == 2 and action in REPEATING_ACTIONS):
                yield action


def run():
    sources = []
    try:
        sources.append(ControllerInput())
    except (OSError, RuntimeError):
        pass
    path = os.environ.get("VANTAGLASS_REMOTE_DEVICE")
    if path and os.path.realpath(path).startswith("/dev/input/event"):
        sources.append(RemoteInput(path))
    while sources:
        now = time.monotonic()
        for source in sources:
            for action in source.events(now):
                print(action, flush=True)
        time.sleep(0.025)
