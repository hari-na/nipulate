"""Trackpad feel: pointer acceleration and scroll scaling.

The phone sends raw finger movement once per animation frame. The server
turns it into screen pixels here, so the feel is the same on every phone and
can be tested. Slow movements map nearly 1:1 for precise pointing; fast flicks
are multiplied so one swipe can cross a TV-sized screen.

The input backend positions the cursor absolutely, so Windows' own "Enhance
pointer precision" acceleration is not applied on top of this curve.
"""

from __future__ import annotations

import math

DEFAULT_SENSITIVITY = 1.5

# Finger speed (phone CSS pixels per millisecond) where acceleration starts and where it tops out.
SPEED_SLOW = 0.1
SPEED_FAST = 1.6
MAX_GAIN = 4.0

# Wheel units per phone pixel of two-finger movement. 120 units is one wheel notch (about 100 px in a browser).
SCROLL_UNITS_PER_PX = 2.5


def gain(speed: float) -> float:
    """Acceleration factor for a finger speed in px/ms: 1 when slow, up to MAX_GAIN when fast."""
    t = min(1.0, max(0.0, (speed - SPEED_SLOW) / (SPEED_FAST - SPEED_SLOW)))
    t = t * t * (3 - 2 * t)  # smoothstep, so there's no sudden jump where acceleration kicks in
    return 1.0 + (MAX_GAIN - 1.0) * t


class _Remainder:
    """Keeps the fractional part of each axis, so slow movement isn't rounded away."""

    def __init__(self):
        self.x = 0.0
        self.y = 0.0

    def take(self, x: float, y: float) -> tuple[int, int]:
        self.x += x
        self.y += y
        ix, iy = math.trunc(self.x), math.trunc(self.y)
        self.x -= ix
        self.y -= iy
        return ix, iy

    def clear(self) -> None:
        self.x = self.y = 0.0


class Pointer:
    """Converts one phone's trackpad input into whole screen pixels and wheel units."""

    def __init__(self, sensitivity: float = DEFAULT_SENSITIVITY):
        self.sensitivity = sensitivity
        self._move = _Remainder()
        self._scroll = _Remainder()

    def move(self, dx: float, dy: float, dt_ms: float) -> tuple[int, int]:
        """Finger movement over one frame -> cursor movement in screen pixels."""
        speed = math.hypot(dx, dy) / max(dt_ms, 1.0)
        k = gain(speed) * self.sensitivity
        return self._move.take(dx * k, dy * k)

    def scroll(self, dx: float, dy: float) -> tuple[int, int]:
        """Two-finger movement -> ``(vertical, horizontal)`` wheel units.

        ``dy`` positive scrolls toward the end of the page, which is a negative
        vertical wheel delta in Windows. ``dx`` positive scrolls right.
        """
        h, v = self._scroll.take(dx * SCROLL_UNITS_PER_PX, -dy * SCROLL_UNITS_PER_PX)
        return v, h

    def reset(self) -> None:
        self._move.clear()
        self._scroll.clear()
