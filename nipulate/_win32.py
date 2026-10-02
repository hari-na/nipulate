"""ctypes bindings for the Windows calls nipulate uses. Imported only on Windows."""

from __future__ import annotations

import ctypes
import time
from ctypes import wintypes

from .protocol import VK_RETURN

user32 = ctypes.WinDLL("user32", use_last_error=True)

INPUT_MOUSE, INPUT_KEYBOARD = 0, 1

MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP = 0x0002, 0x0004
MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP = 0x0008, 0x0010
MOUSEEVENTF_MIDDLEDOWN, MOUSEEVENTF_MIDDLEUP = 0x0020, 0x0040
MOUSEEVENTF_WHEEL, MOUSEEVENTF_HWHEEL = 0x0800, 0x1000
MOUSEEVENTF_VIRTUALDESK, MOUSEEVENTF_ABSOLUTE = 0x4000, 0x8000

KEYEVENTF_EXTENDEDKEY, KEYEVENTF_KEYUP, KEYEVENTF_UNICODE = 0x0001, 0x0002, 0x0004

SM_XVIRTUALSCREEN, SM_YVIRTUALSCREEN, SM_CXVIRTUALSCREEN, SM_CYVIRTUALSCREEN = 76, 77, 78, 79

BUTTON_FLAGS = {
    "left": (MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP),
    "right": (MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP),
    "middle": (MOUSEEVENTF_MIDDLEDOWN, MOUSEEVENTF_MIDDLEUP),
}

# Keys that need the "extended" flag, or Windows reads them as their numpad twins.
EXTENDED_KEYS = {0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0x27, 0x28, 0x2D, 0x2E, 0x5B, 0x5C, 0x5D}


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG), ("mouseData", wintypes.DWORD),
                ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD), ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [("uMsg", wintypes.DWORD), ("wParamL", wintypes.WORD), ("wParamH", wintypes.WORD)]


class _INPUTUNION(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]


class INPUT(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = [("type", wintypes.DWORD), ("u", _INPUTUNION)]


user32.SendInput.argtypes = (wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int)
user32.SendInput.restype = wintypes.UINT
user32.GetCursorPos.argtypes = (ctypes.POINTER(wintypes.POINT),)
user32.GetSystemMetrics.argtypes = (ctypes.c_int,)
user32.MapVirtualKeyW.argtypes = (wintypes.UINT, wintypes.UINT)
user32.MapVirtualKeyW.restype = wintypes.UINT


def make_dpi_aware() -> None:
    """Work in physical pixels, so cursor positions match the screen on scaled (125%, 150%) displays."""
    try:
        user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))  # PER_MONITOR_AWARE_V2
    except (AttributeError, OSError):
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except (AttributeError, OSError):
            pass


def _send(inputs: list[INPUT]) -> int:
    if not inputs:
        return 0
    arr = (INPUT * len(inputs))(*inputs)
    return user32.SendInput(len(inputs), arr, ctypes.sizeof(INPUT))


def _mouse(flags: int, dx: int = 0, dy: int = 0, data: int = 0) -> INPUT:
    return INPUT(type=INPUT_MOUSE, mi=MOUSEINPUT(dx, dy, data & 0xFFFFFFFF, flags, 0, 0))


def _key(vk: int = 0, scan: int = 0, flags: int = 0) -> INPUT:
    return INPUT(type=INPUT_KEYBOARD, ki=KEYBDINPUT(vk, scan, flags, 0, 0))


def cursor_pos() -> tuple[int, int]:
    pt = wintypes.POINT()
    user32.GetCursorPos(ctypes.byref(pt))
    return pt.x, pt.y


def virtual_screen() -> tuple[int, int, int, int]:
    """``(left, top, width, height)`` of the box around all monitors."""
    gsm = user32.GetSystemMetrics
    return gsm(SM_XVIRTUALSCREEN), gsm(SM_YVIRTUALSCREEN), gsm(SM_CXVIRTUALSCREEN), gsm(SM_CYVIRTUALSCREEN)


def _normalize(pos: int, origin: int, size: int) -> int:
    # Windows maps a normalized coordinate n back to origin + n * size / 65536 (rounded down),
    # so round up here to land exactly on the wanted pixel.
    return -(-(pos - origin) * 65536 // size)


def move_cursor_by(dx: int, dy: int) -> None:
    """Move the cursor by whole pixels.

    Uses an absolute move to the new position rather than a relative one: Windows
    applies "Enhance pointer precision" and the pointer speed setting to relative
    moves, which would stack its acceleration on top of nipulate's.
    """
    x, y = cursor_pos()
    left, top, width, height = virtual_screen()
    x = min(left + width - 1, max(left, x + dx))
    y = min(top + height - 1, max(top, y + dy))
    flags = MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_VIRTUALDESK
    _send([_mouse(flags, _normalize(x, left, width), _normalize(y, top, height))])


def mouse_button(name: str, down: bool) -> None:
    down_flag, up_flag = BUTTON_FLAGS[name]
    _send([_mouse(down_flag if down else up_flag)])


def wheel(vertical: int, horizontal: int) -> None:
    inputs = []
    if vertical:
        inputs.append(_mouse(MOUSEEVENTF_WHEEL, data=vertical))
    if horizontal:
        inputs.append(_mouse(MOUSEEVENTF_HWHEEL, data=horizontal))
    _send(inputs)


def _vk_event(vk: int, up: bool) -> INPUT:
    flags = (KEYEVENTF_KEYUP if up else 0) | (KEYEVENTF_EXTENDEDKEY if vk in EXTENDED_KEYS else 0)
    return _key(vk, user32.MapVirtualKeyW(vk, 0), flags)


def key_combo(combo: tuple[int, ...]) -> None:
    """Press the keys in order, then release them in reverse, in one SendInput call."""
    downs = [_vk_event(vk, up=False) for vk in combo]
    ups = [_vk_event(vk, up=True) for vk in reversed(combo)]
    _send(downs + ups)


def type_text(text: str) -> None:
    """Type any Unicode text (any language, emoji) as UTF-16 code units. Newlines press Enter."""
    inputs = []
    for line_no, line in enumerate(text.split("\n")):
        if line_no:
            inputs += [_vk_event(VK_RETURN, up=False), _vk_event(VK_RETURN, up=True)]
        data = line.encode("utf-16-le", "surrogatepass")
        for i in range(0, len(data), 2):
            unit = int.from_bytes(data[i:i + 2], "little")
            inputs += [_key(0, unit, KEYEVENTF_UNICODE), _key(0, unit, KEYEVENTF_UNICODE | KEYEVENTF_KEYUP)]
    _send(inputs)


def lock_workstation() -> None:
    user32.LockWorkStation()


class Audio:
    """Reads the default output device's volume through Core Audio (pycaw). Optional."""

    REFRESH_S = 5  # finding the default device takes ~20 ms; reading its volume takes microseconds

    def __init__(self):
        self._endpoint = None
        self._found_at = 0.0
        try:
            from pycaw.pycaw import AudioUtilities
            self._utils = AudioUtilities
        except Exception:
            self._utils = None

    def read(self) -> tuple[int, bool] | None:
        if self._utils is None:
            return None
        now = time.monotonic()
        try:
            # Looked up again every few seconds: plugging in a TV over HDMI changes the default device.
            if self._endpoint is None or now - self._found_at > self.REFRESH_S:
                self._endpoint = self._utils.GetSpeakers().EndpointVolume
                self._found_at = now
            ep = self._endpoint
            return round(ep.GetMasterVolumeLevelScalar() * 100), bool(ep.GetMute())
        except Exception:
            self._endpoint = None
            return None
