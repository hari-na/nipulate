"""The phone-to-server message format and its validation.

Every message is a JSON object with a ``t`` (type) field. Anything a phone
sends is untrusted: numbers are clamped, text is cleaned, and keys are named
actions from ``KEYS``. A phone can never send a raw virtual-key code.

A phone's first message must be ``hello``, which names the browser tab so a
second tab of the same phone can take over from the first.
"""

from __future__ import annotations

import math
import unicodedata
from dataclasses import dataclass

# Windows virtual-key codes, used only on the server side.
VK_BACK, VK_TAB, VK_RETURN, VK_SHIFT, VK_CONTROL, VK_MENU = 0x08, 0x09, 0x0D, 0x10, 0x11, 0x12
VK_ESCAPE, VK_SPACE = 0x1B, 0x20
VK_LEFT, VK_UP, VK_RIGHT, VK_DOWN = 0x25, 0x26, 0x27, 0x28
VK_LWIN = 0x5B
VK_VOLUME_MUTE, VK_VOLUME_DOWN, VK_VOLUME_UP = 0xAD, 0xAE, 0xAF
VK_MEDIA_NEXT_TRACK, VK_MEDIA_PREV_TRACK, VK_MEDIA_PLAY_PAUSE = 0xB0, 0xB1, 0xB3

# Named actions a phone may trigger: name -> (label for logs, key combo).
# A combo is pressed in order and released in reverse.
KEYS: dict[str, tuple[str, tuple[int, ...]]] = {
    # Media keys work system-wide, whatever window has focus.
    "play_pause": ("Play/Pause", (VK_MEDIA_PLAY_PAUSE,)),
    "next": ("Next track", (VK_MEDIA_NEXT_TRACK,)),
    "prev": ("Previous track", (VK_MEDIA_PREV_TRACK,)),
    "vol_up": ("Volume up", (VK_VOLUME_UP,)),
    "vol_down": ("Volume down", (VK_VOLUME_DOWN,)),
    "mute": ("Mute", (VK_VOLUME_MUTE,)),
    # YouTube shortcuts: keystrokes to the focused window.
    "yt_back": ("YouTube back 10s (J)", (ord("J"),)),
    "yt_forward": ("YouTube forward 10s (L)", (ord("L"),)),
    "yt_fullscreen": ("YouTube fullscreen (F)", (ord("F"),)),
    "yt_captions": ("YouTube captions (C)", (ord("C"),)),
    "yt_next": ("YouTube next video (Shift+N)", (VK_SHIFT, ord("N"))),
    "browser_back": ("Browser back (Alt+Left)", (VK_MENU, VK_LEFT)),
    # Special keys.
    "esc": ("Esc", (VK_ESCAPE,)),
    "tab": ("Tab", (VK_TAB,)),
    "enter": ("Enter", (VK_RETURN,)),
    "backspace": ("Backspace", (VK_BACK,)),
    "space": ("Space", (VK_SPACE,)),
    "up": ("Up", (VK_UP,)),
    "down": ("Down", (VK_DOWN,)),
    "left": ("Left", (VK_LEFT,)),
    "right": ("Right", (VK_RIGHT,)),
    "win": ("Windows key", (VK_LWIN,)),
    "alt_tab": ("Alt+Tab", (VK_MENU, VK_TAB)),
    "copy": ("Ctrl+C", (VK_CONTROL, ord("C"))),
    "paste": ("Ctrl+V", (VK_CONTROL, ord("V"))),
    "close_tab": ("Ctrl+W", (VK_CONTROL, ord("W"))),
}

MOUSE_BUTTONS = ("left", "right", "middle")
BUTTON_ACTIONS = ("click", "down", "up")

MAX_MESSAGE_BYTES = 4096
TEXT_MAX = 256
CLIENT_ID_MAX = 64
DELTA_MAX = 2000.0  # pixels in one frame; anything bigger is a bug or an attack
DT_MIN_MS, DT_MAX_MS = 1.0, 250.0
SENSITIVITY_MIN, SENSITIVITY_MAX = 0.25, 5.0


@dataclass(frozen=True)
class Hello:
    client_id: str
    standalone: bool


@dataclass(frozen=True)
class Move:
    """Finger movement in phone CSS pixels since the last frame, and that frame's length."""
    dx: float
    dy: float
    dt: float


@dataclass(frozen=True)
class Scroll:
    """Two-finger scroll in phone pixels. Positive dy scrolls toward the end of the page, positive dx to the right."""
    dx: float
    dy: float


@dataclass(frozen=True)
class Button:
    button: str
    action: str


@dataclass(frozen=True)
class Key:
    name: str


@dataclass(frozen=True)
class Text:
    text: str


@dataclass(frozen=True)
class Settings:
    sensitivity: float


@dataclass(frozen=True)
class Ping:
    ping: float
    latency: float | None


@dataclass(frozen=True)
class Lock:
    pass


@dataclass(frozen=True)
class Release:
    """Let go of any held mouse button (the phone lost focus or the gesture was cancelled)."""


Message = Hello | Move | Scroll | Button | Key | Text | Settings | Ping | Lock | Release


def _number(value, lo: float, hi: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"expected a number, got {value!r}")
    return max(lo, min(hi, float(value)))


def _string(value, max_len: int) -> str:
    if not isinstance(value, str):
        raise ValueError(f"expected a string, got {type(value).__name__}")
    return value[:max_len]


def _client_id(value) -> str:
    return "".join(ch for ch in _string(value, CLIENT_ID_MAX) if ch.isprintable())


def clean_text(raw: str) -> str:
    """Typed text from a phone: keep letters, emoji and newlines, drop other control characters.

    Format characters (category Cf) stay, because emoji sequences need the zero-width joiner.
    """
    out = []
    for ch in raw[:TEXT_MAX]:
        cat = unicodedata.category(ch)
        if ch == "\n" or (cat != "Cc" and cat != "Cs"):
            out.append(ch)
    return "".join(out)


def parse_message(data) -> Message:
    """Validate one decoded JSON message from a phone. Raises ValueError for anything unexpected."""
    if not isinstance(data, dict):
        raise ValueError("message must be a JSON object")
    t = data.get("t")
    if t == "m":
        return Move(_number(data.get("dx"), -DELTA_MAX, DELTA_MAX), _number(data.get("dy"), -DELTA_MAX, DELTA_MAX),
                    _number(data.get("dt", 16), DT_MIN_MS, DT_MAX_MS))
    if t == "scroll":
        return Scroll(_number(data.get("dx", 0), -DELTA_MAX, DELTA_MAX),
                      _number(data.get("dy", 0), -DELTA_MAX, DELTA_MAX))
    if t == "button":
        button, action = data.get("b"), data.get("a", "click")
        if button not in MOUSE_BUTTONS or action not in BUTTON_ACTIONS:
            raise ValueError(f"unknown mouse button or action: {button!r} {action!r}")
        return Button(button, action)
    if t == "key":
        name = data.get("k")
        if not isinstance(name, str) or name not in KEYS:
            raise ValueError(f"unknown key: {name!r}")
        return Key(name)
    if t == "text":
        return Text(clean_text(_string(data.get("s"), TEXT_MAX)))
    if t == "set":
        return Settings(_number(data.get("sens"), SENSITIVITY_MIN, SENSITIVITY_MAX))
    if t == "ping":
        lat = data.get("lat")
        return Ping(_number(data.get("ping"), -1e15, 1e15),
                    None if lat is None else _number(lat, 0, 60_000))
    if t == "lock":
        return Lock()
    if t == "release":
        return Release()
    if t == "hello":
        return Hello(_client_id(data.get("id")), data.get("standalone") is True)
    raise ValueError(f"unknown message type: {t!r}")
