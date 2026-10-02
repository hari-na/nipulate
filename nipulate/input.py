"""Input backends: where the phone's mouse and keyboard input goes.

``SendInputBackend`` injects real input into Windows through ``user32.SendInput``,
the same path a USB mouse and keyboard take, so no driver is needed.
``FakeBackend`` only records what it was asked to do, for ``--fake``, for
non-Windows systems, and for the tests.
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from typing import Protocol

from .protocol import VK_VOLUME_DOWN, VK_VOLUME_MUTE, VK_VOLUME_UP


class Backend(Protocol):
    def move(self, dx: int, dy: int) -> None: ...
    def button(self, name: str, down: bool) -> None: ...
    def scroll(self, vertical: int, horizontal: int) -> None: ...
    def keys(self, combo: tuple[int, ...]) -> None: ...
    def text(self, text: str) -> None: ...
    def lock(self) -> None: ...
    def volume(self) -> tuple[int, bool] | None: ...


class FakeBackend:
    """Records events instead of sending them. Pretends to be a 1920x1080 screen with a volume knob."""

    WIDTH, HEIGHT = 1920, 1080

    def __init__(self):
        self.events: list[tuple] = []
        self.cursor = (self.WIDTH // 2, self.HEIGHT // 2)
        self.held: set[str] = set()
        self.level = 40
        self.muted = False
        self.locked = False

    def move(self, dx: int, dy: int) -> None:
        x = min(self.WIDTH - 1, max(0, self.cursor[0] + dx))
        y = min(self.HEIGHT - 1, max(0, self.cursor[1] + dy))
        self.cursor = (x, y)
        self.events.append(("move", dx, dy))

    def button(self, name: str, down: bool) -> None:
        (self.held.add if down else self.held.discard)(name)
        self.events.append(("button", name, down))

    def scroll(self, vertical: int, horizontal: int) -> None:
        self.events.append(("scroll", vertical, horizontal))

    def keys(self, combo: tuple[int, ...]) -> None:
        if combo == (VK_VOLUME_UP,):
            self.level, self.muted = min(100, self.level + 2), False
        elif combo == (VK_VOLUME_DOWN,):
            self.level, self.muted = max(0, self.level - 2), False
        elif combo == (VK_VOLUME_MUTE,):
            self.muted = not self.muted
        self.events.append(("keys", combo))

    def text(self, text: str) -> None:
        self.events.append(("text", text))

    def lock(self) -> None:
        self.locked = True
        self.events.append(("lock",))

    def volume(self) -> tuple[int, bool] | None:
        return self.level, self.muted


class SendInputBackend:
    """Real mouse and keyboard input on Windows."""

    def __init__(self):
        from . import _win32

        self.w = _win32
        _win32.make_dpi_aware()
        self._audio = _win32.Audio()

    def move(self, dx: int, dy: int) -> None:
        if dx or dy:
            self.w.move_cursor_by(dx, dy)

    def button(self, name: str, down: bool) -> None:
        self.w.mouse_button(name, down)

    def scroll(self, vertical: int, horizontal: int) -> None:
        self.w.wheel(vertical, horizontal)

    def keys(self, combo: tuple[int, ...]) -> None:
        self.w.key_combo(combo)

    def text(self, text: str) -> None:
        self.w.type_text(text)

    def lock(self) -> None:
        self.w.lock_workstation()

    def volume(self) -> tuple[int, bool] | None:
        return self._audio.read()


def select_backend(fake: bool, out: Callable[[str], None] = print) -> tuple[Backend, str]:
    """Pick the backend to use. Returns ``(backend, mode_description)``."""
    if fake:
        return FakeBackend(), "TEST MODE (--fake): no input is sent to Windows"
    if sys.platform != "win32":
        out("Not running on Windows, so input can't be sent. Starting in test mode.")
        return FakeBackend(), "TEST MODE (not Windows): no input is sent"
    return SendInputBackend(), "live: phones control this PC"
