import ctypes
import sys

import pytest

from nipulate.input import FakeBackend, select_backend
from nipulate.protocol import KEYS


def test_fake_mode_is_chosen_with_the_flag():
    backend, mode = select_backend(True, out=lambda line: None)
    assert isinstance(backend, FakeBackend)
    assert "TEST MODE" in mode


def test_fake_cursor_stays_on_screen():
    b = FakeBackend()
    b.move(-99999, 99999)
    assert b.cursor == (0, FakeBackend.HEIGHT - 1)


def test_fake_tracks_held_buttons():
    b = FakeBackend()
    b.button("left", True)
    assert b.held == {"left"}
    b.button("left", False)
    assert b.held == set()


def test_fake_volume_follows_the_volume_keys():
    b = FakeBackend()
    level, _ = b.volume()
    b.keys(KEYS["vol_up"][1])
    assert b.volume() == (level + 2, False)
    b.keys(KEYS["mute"][1])
    assert b.volume() == (level + 2, True)


@pytest.mark.skipif(sys.platform != "win32", reason="Windows only")
def test_input_struct_matches_the_windows_layout():
    from nipulate import _win32

    assert ctypes.sizeof(_win32.INPUT) == (40 if ctypes.sizeof(ctypes.c_void_p) == 8 else 28)


@pytest.mark.skipif(sys.platform != "win32", reason="Windows only")
def test_normalized_coordinates_round_up_to_the_target_pixel():
    from nipulate._win32 import _normalize

    for size in (1366, 1920, 2560, 3840):
        for pos in (0, 1, size // 3, size - 1):
            n = _normalize(pos, 0, size)
            assert 0 <= n <= 65535
            assert n * size // 65536 == pos
