import asyncio
import time

import pytest

from nipulate.hub import TYPING_IDLE_S, Hub, Phone
from nipulate.input import FakeBackend
from nipulate.protocol import KEYS, Button, Key, Lock, Move, Release, Scroll, Settings, Text


class FakeSocket:
    def __init__(self, close_code=1001):
        self.closed = False
        self.close_code = close_code
        self.sent = []

    async def send_json(self, obj):
        self.sent.append(obj)

    async def send_str(self, data):
        self.sent.append(data)

    async def close(self):
        self.closed = True


@pytest.fixture
def lines():
    return []


@pytest.fixture
def hub(lines):
    return Hub(FakeBackend(), "test", verbose=True, out=lines.append)


def connect(hub, client_id="phone1", ip="192.168.1.20"):
    phone = Phone(client_id, FakeSocket(), ip, "iPhone Safari")
    hub.connect(phone)
    return phone


async def test_connected_phones_show_in_the_status(hub):
    connect(hub)
    status = hub.status()
    assert status["connected"] == 1
    assert status["phones"][0]["label"] == "iPhone Safari"
    assert status["phones"][0]["ip"] == "192.168.1.20"


async def test_same_phone_reconnecting_returns_the_old_connection(hub):
    first = connect(hub)
    second = Phone("phone1", FakeSocket(), "192.168.1.20", "iPhone Safari")
    assert hub.connect(second) is first
    hub.disconnect(first, first.ws)  # the old socket closing doesn't remove the new one
    assert hub.phones["phone1"] is second


async def test_moves_are_accelerated_into_pixels(hub):
    phone = connect(hub)
    phone.pointer.sensitivity = 1.0
    hub.handle(phone, Move(3, -2, 16))
    assert hub.backend.events == [("move", 3, -2)]


async def test_sub_pixel_moves_send_nothing(hub):
    phone = connect(hub)
    phone.pointer.sensitivity = 0.25
    hub.handle(phone, Move(1, 0, 16))
    assert hub.backend.events == []


async def test_scroll_becomes_wheel_events(hub):
    phone = connect(hub)
    hub.handle(phone, Scroll(0, 10))
    (kind, vertical, horizontal), = hub.backend.events
    assert kind == "scroll" and vertical < 0 and horizontal == 0


async def test_click_presses_and_releases(hub):
    phone = connect(hub)
    hub.handle(phone, Button("right", "click"))
    assert hub.backend.events == [("button", "right", True), ("button", "right", False)]


async def test_drag_holds_the_button_until_up(hub):
    phone = connect(hub)
    hub.handle(phone, Button("left", "down"))
    hub.handle(phone, Button("left", "down"))  # repeated downs are ignored
    assert hub.backend.held == {"left"}
    hub.handle(phone, Button("left", "up"))
    assert hub.backend.held == set()
    assert hub.backend.events == [("button", "left", True), ("button", "left", False)]


async def test_disconnect_releases_held_buttons(hub):
    phone = connect(hub)
    hub.handle(phone, Button("left", "down"))
    hub.disconnect(phone, phone.ws)
    assert hub.backend.held == set()
    assert "phone1" not in hub.phones


async def test_release_message_lets_go(hub):
    phone = connect(hub)
    hub.handle(phone, Button("left", "down"))
    hub.handle(phone, Release())
    assert hub.backend.held == set()


async def test_keys_send_their_combo(hub):
    phone = connect(hub)
    hub.handle(phone, Key("yt_next"))
    assert hub.backend.events == [("keys", KEYS["yt_next"][1])]


async def test_volume_keys_update_the_phone(hub):
    phone = connect(hub)
    hub.handle(phone, Key("vol_up"))
    hub.poll_volume()
    await asyncio.sleep(0)  # let the queued send run
    level = hub.backend.level
    assert {"t": "vol", "level": level, "muted": False} in phone.ws.sent


async def test_typed_text_is_sent_but_never_logged(hub, lines):
    phone = connect(hub)
    hub.handle(phone, Text("secret password"))
    assert hub.backend.events == [("text", "secret password")]
    hub.tick(time.monotonic() + TYPING_IDLE_S + 1)
    assert any("typed 15 characters" in line for line in lines)
    assert not any("secret" in line for line in lines)


async def test_settings_change_sensitivity(hub):
    phone = connect(hub)
    hub.handle(phone, Settings(3.0))
    assert phone.pointer.sensitivity == 3.0


async def test_lock_releases_buttons_and_locks(hub, lines):
    phone = connect(hub)
    hub.handle(phone, Button("left", "down"))
    hub.handle(phone, Lock())
    assert hub.backend.locked
    assert hub.backend.held == set()
    assert any("locked the PC" in line for line in lines)


async def test_disconnected_phones_leave_the_status(hub):
    phone = connect(hub)
    hub.disconnect(phone, phone.ws)
    assert hub.status()["phones"] == []
